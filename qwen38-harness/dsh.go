package main

import (
	"bufio"
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net"
	"net/http"
	"net/http/httputil"
	"net/url"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"time"
)

const dshVersion = "0.2.2-rc.1"

func dshRequestPolicy(lora bool, scale int) map[string]any {
	p := map[string]any{"temperature": 0.8, "top_p": 1.0, "max_tokens": 4096, "chat_template_kwargs": map[string]any{"enable_thinking": false}}
	if lora {
		p["lora"] = []any{map[string]any{"id": 0, "scale": scale}}
	}
	return p
}

// A wire-policy gateway, not an Agent implementation: prompts, history and
// tool execution remain entirely in the pinned official DSH process.
func startDSHGateway(c Config, model, condition string, log io.Writer) (string, func(), error) {
	upstream, err := url.Parse(c.BaseURL)
	if err != nil {
		return "", nil, err
	}
	listener, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		return "", nil, err
	}
	scale := 0
	if condition == "adapter" {
		scale = 1
	}
	policy := dshRequestPolicy(c.LlamaLoRA, scale)
	var mu sync.Mutex
	proxy := httputil.NewSingleHostReverseProxy(upstream)
	transport := http.DefaultTransport.(*http.Transport).Clone()
	transport.Proxy = nil
	proxy.Transport = transport
	proxy.FlushInterval = -1
	proxy.Director = func(r *http.Request) {
		r.URL.Scheme = upstream.Scheme
		r.URL.Host = upstream.Host
		r.URL.Path = strings.TrimRight(upstream.Path, "/") + "/chat/completions"
		r.URL.RawQuery = ""
		r.Host = upstream.Host
		r.Header.Set("Authorization", "Bearer "+apiKey())
	}
	handler := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != "POST" || r.URL.Path != "/v1/chat/completions" {
			http.Error(w, "only chat completions are permitted", 404)
			return
		}
		var body map[string]any
		decoder := json.NewDecoder(http.MaxBytesReader(w, r.Body, 8<<20))
		if err := decoder.Decode(&body); err != nil {
			http.Error(w, "invalid request JSON", 400)
			return
		}
		if body["model"] != model || body["stream"] != true {
			http.Error(w, "unexpected model or non-stream request", 400)
			return
		}
		if tools, ok := body["tools"].([]any); ok {
			for _, raw := range tools {
				tool, _ := raw.(map[string]any)
				fn, _ := tool["function"].(map[string]any)
				name, _ := fn["name"].(string)
				if name != "read" && name != "write" && name != "edit" && name != "bash" {
					http.Error(w, "unexpected tool catalog: "+name, 400)
					return
				}
			}
		}
		for k, v := range policy {
			body[k] = v
		}
		delete(body, "max_completion_tokens")
		delete(body, "reasoning_effort")
		delete(body, "thinking")
		body["stream_options"] = map[string]any{"include_usage": true}
		b, err := json.Marshal(body)
		if err != nil {
			http.Error(w, "request serialization failed", 500)
			return
		}
		mu.Lock()
		_, err = log.Write(append(append([]byte{}, b...), '\n'))
		mu.Unlock()
		if err != nil {
			http.Error(w, "cannot preserve outgoing request", 500)
			return
		}
		r.Body = io.NopCloser(bytes.NewReader(b))
		r.ContentLength = int64(len(b))
		r.Header.Set("Content-Type", "application/json")
		r.Header.Del("Content-Length")
		proxy.ServeHTTP(w, r)
	})
	server := &http.Server{Handler: handler, ReadHeaderTimeout: 5 * time.Second}
	go server.Serve(listener)
	return "http://" + listener.Addr().String() + "/v1", func() { _ = server.Close(); transport.CloseIdleConnections() }, nil
}

func dshPatch(c Config, model, endpoint string) ([]byte, error) {
	rows := []any{
		map[string]any{"id": "agent-default-model", "config": map[string]any{"provider": "experiment", "model": model}},
		map[string]any{"id": "llm-pi-ai", "config": map[string]any{"providers": map[string]any{"experiment": map[string]any{
			"api": "openai-completions", "baseURL": endpoint, "apiKeyEnv": "HARNESS_EXPERIMENT_API_KEY",
			"compat":      map[string]any{"supportsDeveloperRole": false, "maxTokensField": "max_tokens"},
			"retryPolicy": map[string]any{"mode": "normal", "maxRetries": 0},
			"models":      []any{map[string]any{"id": model, "contextWindow": c.ContextWindow, "maxTokens": 4096, "input": []string{"text"}}},
		}}}},
		map[string]any{"id": "tool-fs", "config": map[string]any{"read": true, "write": true, "edit": true, "readImage": false, "applyPatch": false}},
		map[string]any{"id": "tool-bash", "config": map[string]any{"enableRunInBackground": false, "promoteOnTimeout": false}},
	}
	for _, id := range []string{"session-title-llm", "llm-retry", "compaction-basic", "tool-result-pruner", "image-offload", "agent-instructions", "skill", "skill-filesystem", "tool-skill", "tool-subagent", "tool-subagent-fork", "tool-subagent-control", "tool-agent-team", "tool-working-directory", "tool-fs-search", "tool-jobs", "tool-workflow", "tool-todo", "tool-goal", "tool-web", "repeat-tool-reminder", "deepseek-llm-api-extensions", "otel", "session-telemetry-otel", "user-questions"} {
		rows = append(rows, map[string]any{"id": id, "disabled": true})
	}
	return json.MarshalIndent(rows, "", "  ") // JSON is a YAML subset, with no interpolated executable values.
}

type dshStreamState struct {
	Metrics
	session                              string
	final, ended, completed              bool
	usageComplete                        bool
	output, input, cacheRead, cacheWrite int64
	tools, endedTools                    map[string]bool
	steps                                map[string]bool
}

func newDSHStreamState() *dshStreamState {
	return &dshStreamState{usageComplete: true, tools: map[string]bool{}, endedTools: map[string]bool{}, steps: map[string]bool{}}
}
func (s *dshStreamState) accept(line []byte) error {
	// Explicit wire fields: DSH's usage uses camelCase, unlike Pi's event schema.
	var e struct {
		Type      string `json:"type"`
		Phase     string `json:"phase"`
		SessionID string `json:"sessionId"`
		CallID    string `json:"callId"`
		Status    string `json:"status"`
		Turn      int    `json:"turn"`
		Step      int    `json:"step"`
		Reason    *struct {
			Kind string `json:"kind"`
		} `json:"reason"`
		Usage *struct {
			Input      *int64 `json:"inputTokens"`
			Output     *int64 `json:"outputTokens"`
			CacheRead  int64  `json:"cacheReadTokens"`
			CacheWrite int64  `json:"cacheWriteTokens"`
		} `json:"usage"`
	}
	if err := json.Unmarshal(line, &e); err != nil {
		return err
	}

	switch e.Type {
	case "session":
		if e.SessionID == "" || s.session != "" {
			return errors.New("invalid DSH session event")
		}
		s.session = e.SessionID
	case "status":
		if e.Phase == "step_end" {
			key := fmt.Sprintf("%d/%d", e.Turn, e.Step)
			if s.steps[key] {
				return errors.New("duplicate DSH step end")
			}
			s.steps[key] = true
			s.AssistantMessages++
			u := e.Usage
			if u == nil || u.Input == nil || u.Output == nil || *u.Input < 0 || *u.Output < 0 || (*u.Input == 0 && *u.Output == 0 && u.CacheRead == 0 && u.CacheWrite == 0) {
				s.usageComplete = false
				break
			}
			s.input += *u.Input
			s.output += *u.Output
			s.cacheRead += u.CacheRead
			s.cacheWrite += u.CacheWrite
		}
		if e.Phase == "turn_end" {
			s.ended = e.Reason != nil && e.Reason.Kind == "completed"
		}
	case "tool_call":
		if e.CallID == "" {
			return errors.New("missing DSH tool call ID")
		}
		if !s.tools[e.CallID] {
			s.tools[e.CallID] = true
			s.ToolCalls++
		}
	case "tool_result":
		if e.CallID == "" {
			return errors.New("missing DSH tool result ID")
		}
		if !s.endedTools[e.CallID] {
			s.endedTools[e.CallID] = true
			if e.Status == "error" {
				s.ToolErrors++
			}
		}
	case "final":
		if s.final || s.session == "" || e.SessionID != s.session {
			return errors.New("invalid DSH final event")
		}
		s.final = true
		s.completed = e.Reason != nil && e.Reason.Kind == "completed"
	case "error":
		s.completed = false
	}
	return nil
}
func (s *dshStreamState) metrics() Metrics {
	m := s.Metrics
	if s.usageComplete && s.AssistantMessages > 0 {
		m.GeneratedTokens = &s.output
		m.InputTokens = &s.input
		m.CacheReadTokens = &s.cacheRead
		m.CacheWriteTokens = &s.cacheWrite
	}
	return m
}

func runDSHTrial(ctx context.Context, c Config, task, condition, model string, repetition int, dir string) Trial {
	prompt := "Read TASK.md, fix solution.go, and run the visible Go tests. Only modify solution.go."
	t := Trial{Harness: "deepseek-harness", Task: task, Repetition: repetition, Condition: condition, Model: model, Status: "agent_error", TaskHash: digest(append(append(asset(task, "prompt.md"), asset(task, "solution.go.txt")...), asset(task, "visible_test.go.txt")...)), PromptHash: digest([]byte(prompt))}
	fail := func(err error) Trial {
		t.Status = "runner_error"
		t.Scorable = false
		t.Passed = false
		t.Error = err.Error()
		return t
	}
	work, err := os.MkdirTemp("", "harness-task-")
	if err != nil {
		return fail(err)
	}
	defer os.RemoveAll(work)
	if err := prepareTask(work, task); err != nil {
		return fail(err)
	}
	home, err := os.MkdirTemp("", "harness-dsh-")
	if err != nil {
		return fail(err)
	}
	defer os.RemoveAll(home)
	reqlog, err := os.OpenFile(filepath.Join(dir, "outgoing-requests.jsonl"), os.O_CREATE|os.O_EXCL|os.O_WRONLY, 0600)
	if err != nil {
		return fail(err)
	}
	defer reqlog.Close()
	endpoint, closeGateway, err := startDSHGateway(c, model, condition, reqlog)
	if err != nil {
		return fail(err)
	}
	defer closeGateway()
	patch, err := dshPatch(c, model, endpoint)
	if err != nil {
		return fail(err)
	}
	patchPath, err := filepath.Abs(filepath.Join(dir, "dsh.cordis.patch.yml"))
	if err != nil {
		return fail(err)
	}
	if err := writeFile(patchPath, patch); err != nil {
		return fail(err)
	}
	stdout, err := os.OpenFile(filepath.Join(dir, "events.jsonl"), os.O_CREATE|os.O_EXCL|os.O_WRONLY, 0600)
	if err != nil {
		return fail(err)
	}
	defer stdout.Close()
	stderr, err := os.OpenFile(filepath.Join(dir, "stderr.log"), os.O_CREATE|os.O_EXCL|os.O_WRONLY, 0600)
	if err != nil {
		return fail(err)
	}
	defer stderr.Close()
	agentCtx, cancel := context.WithTimeout(ctx, c.Timeout)
	defer cancel()
	cmd := ownedCommand(agentCtx, c.DSH, "--profile", "headless", "--patch", patchPath, "--json", "--permission-mode", "danger-full-access", prompt)
	cmd.Dir = work
	cmd.Env = replaceEnv(os.Environ(), map[string]string{"DSH_HOME": home, "HARNESS_EXPERIMENT_API_KEY": apiKey(), "GOWORK": "off", "GOTOOLCHAIN": "local", "GOPROXY": "off", "GOSUMDB": "off"})
	cmd.Stderr = stderr
	pipe, err := cmd.StdoutPipe()
	if err != nil {
		return fail(err)
	}
	start := time.Now()
	if err := cmd.Start(); err != nil {
		return fail(err)
	}
	state := newDSHStreamState()
	scanner := bufio.NewScanner(io.TeeReader(pipe, stdout))
	scanner.Buffer(make([]byte, 64<<10), 16<<20)
	var parseErr error
	for scanner.Scan() {
		if len(scanner.Bytes()) == 0 {
			continue
		}
		if err := state.accept(scanner.Bytes()); err != nil {
			parseErr = err
			cancel()
			break
		}
	}
	if err := scanner.Err(); err != nil {
		parseErr = err
		cancel()
	}
	waitErr := cmd.Wait()
	t.AgentMS = time.Since(start).Milliseconds()
	t.Metrics = state.metrics()
	if parseErr != nil {
		t.Error = "invalid DSH event stream"
	} else if errors.Is(agentCtx.Err(), context.DeadlineExceeded) {
		t.Status = "timeout"
		t.Scorable = true
	} else if waitErr == nil && state.final && state.completed && state.ended && state.AssistantMessages > 0 {
		t.Status = "completed"
		t.Scorable = true
	} else {
		t.Error = "DSH did not finish with a committed completed turn; inspect events and stderr"
	}
	if ctx.Err() != nil {
		t.Status = "cancelled"
		t.Scorable = false
		t.Error = "experiment cancelled"
	}
	source, err := readSolution(work)
	if err != nil {
		t.Grade = Grade{Status: "invalid_source", Log: err.Error()}
	} else {
		t.FinalSourceHash = digest(source)
		if err := writeFile(filepath.Join(dir, "solution.go.txt"), source); err != nil {
			return fail(err)
		}
		start := time.Now()
		t.Grade = gradeSource(ctx, task, source)
		t.GradeMS = time.Since(start).Milliseconds()
	}
	if t.Grade.Status == "grader_error" {
		t.Scorable = false
	}
	t.Passed = t.Scorable && t.Grade.Passed
	if t.Status != "completed" {
		t.Metrics.GeneratedTokens = nil
		t.Metrics.InputTokens = nil
		t.Metrics.CacheReadTokens = nil
		t.Metrics.CacheWriteTokens = nil
	}
	if err := writeFile(filepath.Join(dir, "grade.jsonl"), []byte(t.Grade.Log)); err != nil {
		return fail(err)
	}
	return t
}
