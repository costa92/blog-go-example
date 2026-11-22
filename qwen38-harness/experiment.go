package main

import (
	"bufio"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strings"
	"time"
)

const piVersion = "1.5.2"

type Config struct {
	Harness       string        `json:"harness,omitempty"`
	BaseURL       string        `json:"base_url"`
	BaseModel     string        `json:"base_model"`
	AdapterModel  string        `json:"adapter_model"`
	Runs          int           `json:"runs_per_task_per_model"`
	RunOffset     int           `json:"run_offset"`
	Timeout       time.Duration `json:"timeout_ns"`
	Pi            string        `json:"-"`
	DSH           string        `json:"-"`
	Out           string        `json:"-"`
	ContextWindow int           `json:"context_window"`
	LlamaLoRA     bool          `json:"llama_per_request_lora"`
	OnlyPairs     string        `json:"only_pairs,omitempty"`
}

type Trial struct {
	Harness         string  `json:"harness,omitempty"`
	Task            string  `json:"task"`
	Repetition      int     `json:"repetition"`
	Condition       string  `json:"condition"`
	Model           string  `json:"model"`
	Status          string  `json:"status"`
	Scorable        bool    `json:"scorable"`
	Passed          bool    `json:"passed"`
	AgentMS         int64   `json:"agent_wall_ms"`
	GradeMS         int64   `json:"grade_wall_ms"`
	Grade           Grade   `json:"grade"`
	Metrics         Metrics `json:"metrics"`
	TaskHash        string  `json:"task_sha256"`
	PromptHash      string  `json:"prompt_sha256"`
	FinalSourceHash string  `json:"final_source_sha256,omitempty"`
	Error           string  `json:"error,omitempty"`
}

func digest(data []byte) string {
	sum := sha256.Sum256(data)
	return hex.EncodeToString(sum[:])
}

func modelConfig(c Config) map[string]any {
	window := c.ContextWindow
	if window == 0 {
		window = 131072
	}
	models := []any{}
	for index, id := range []string{c.BaseModel, c.AdapterModel} {
		model := map[string]any{
			"id": id, "reasoning": false, "input": []string{"text"},
			"contextWindow": window, "maxTokens": 4096,
			"samplingParams": map[string]any{
				"temperature": 0.8, "top_p": 1.0,
				"chat_template_kwargs": map[string]any{"enable_thinking": false},
			},
		}
		if c.LlamaLoRA {
			// llama.cpp applies this adapter scale to this request only. Both
			// aliases use the same base GGUF; no global LoRA state is toggled.
			model["samplingParams"].(map[string]any)["lora"] = []any{map[string]any{"id": 0, "scale": index}}
		}
		models = append(models, model)
	}
	return map[string]any{"providers": map[string]any{"experiment": map[string]any{
		"baseUrl": c.BaseURL, "api": "openai-completions",
		"apiKey": "$HARNESS_EXPERIMENT_API_KEY", "models": models,
	}}}
}

func writeJSON(path string, value any) error {
	b, err := json.MarshalIndent(value, "", "  ")
	if err != nil {
		return err
	}
	return writeFile(path, append(b, '\n'))
}

func apiKey() string {
	if key := os.Getenv("HARNESS_EXPERIMENT_API_KEY"); key != "" {
		return key
	}
	return "dummy"
}

func preflight(ctx context.Context, c Config) (json.RawMessage, error) {
	if c.Harness != "" && c.Harness != "pi" && c.Harness != "deepseek-harness" {
		return nil, errors.New("harness must be pi or deepseek-harness")
	}
	if err := validatePairs(c.OnlyPairs); err != nil {
		return nil, err
	}
	u, err := url.Parse(c.BaseURL)
	if err != nil || (u.Scheme != "http" && u.Scheme != "https") || u.Host == "" || u.User != nil || u.RawQuery != "" || u.Fragment != "" {
		return nil, errors.New("url must be an http(s) API base URL without credentials, query or fragment")
	}
	if c.RunOffset < 0 || c.Runs > int(^uint(0)>>1)-c.RunOffset {
		return nil, errors.New("run-offset must be nonnegative and repetition range must not overflow")
	}
	if c.BaseModel == c.AdapterModel || c.BaseModel == "" || c.AdapterModel == "" || c.Runs < 1 || c.Timeout <= 0 || c.ContextWindow < 0 {
		return nil, errors.New("distinct model names, positive runs and timeout required")
	}
	versionCtx, cancel := context.WithTimeout(ctx, 15*time.Second)
	defer cancel()
	cli, wantVersion := c.Pi, piVersion
	if c.Harness == "deepseek-harness" {
		cli, wantVersion = c.DSH, dshVersion
	}
	version, err := ownedCommand(versionCtx, cli, "--version").Output()
	if err != nil || strings.TrimSpace(string(version)) != wantVersion {
		return nil, fmt.Errorf("requires pinned harness version %s; pass -pi or -dsh", wantVersion)
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, strings.TrimRight(c.BaseURL, "/")+"/models", nil)
	if err != nil {
		return nil, err
	}
	req.Header.Set("Authorization", "Bearer "+apiKey())
	client := &http.Client{Timeout: 10 * time.Second}
	resp, err := client.Do(req)
	if err != nil {
		return nil, errors.New("model-list request failed; check the endpoint")
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("model-list HTTP %d", resp.StatusCode)
	}
	body, err := io.ReadAll(io.LimitReader(resp.Body, 2<<20))
	if err != nil {
		return nil, err
	}
	var models struct {
		Data []struct {
			ID      string   `json:"id"`
			Aliases []string `json:"aliases"`
		} `json:"data"`
	}
	if err := json.Unmarshal(body, &models); err != nil {
		return nil, errors.New("invalid model-list response")
	}
	found := map[string]bool{}
	for _, model := range models.Data {
		found[model.ID] = true
		if c.LlamaLoRA {
			for _, alias := range model.Aliases {
				found[alias] = true
			}
		}
	}
	if !found[c.BaseModel] || !found[c.AdapterModel] {
		return nil, errors.New("model-list response must contain both configured model IDs")
	}
	return body, nil
}

func validatePairs(spec string) error {
	if spec == "" {
		return nil
	}
	valid := map[string]bool{}
	for _, task := range taskIDs {
		for _, condition := range []string{"base", "adapter"} {
			valid[task+":"+condition] = true
		}
	}
	seen := map[string]bool{}
	for _, pair := range strings.Split(spec, ",") {
		if !valid[pair] || seen[pair] {
			return fmt.Errorf("invalid or duplicate task:condition selection %q", pair)
		}
		seen[pair] = true
	}
	return nil
}

func includesPair(spec, task, condition string) bool {
	if spec == "" {
		return true
	}
	for _, pair := range strings.Split(spec, ",") {
		if pair == task+":"+condition {
			return true
		}
	}
	return false
}

func llamaAdapterSnapshot(ctx context.Context, c Config) (json.RawMessage, error) {
	endpoint := strings.TrimSuffix(strings.TrimRight(c.BaseURL, "/"), "/v1") + "/lora-adapters"
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, endpoint, nil)
	if err != nil {
		return nil, err
	}
	req.Header.Set("Authorization", "Bearer "+apiKey())
	resp, err := (&http.Client{Timeout: 10 * time.Second}).Do(req)
	if err != nil {
		return nil, errors.New("llama LoRA inventory request failed")
	}
	defer resp.Body.Close()
	if resp.StatusCode != 200 {
		return nil, fmt.Errorf("llama LoRA inventory HTTP %d", resp.StatusCode)
	}
	body, err := io.ReadAll(io.LimitReader(resp.Body, 1<<20))
	if err != nil {
		return nil, err
	}
	var adapters []struct {
		ID   int    `json:"id"`
		Path string `json:"path"`
	}
	if err := json.Unmarshal(body, &adapters); err != nil {
		return nil, err
	}
	if len(adapters) != 1 || adapters[0].ID != 0 || adapters[0].Path == "" {
		return nil, errors.New("llama mode requires exactly one loaded adapter, ID 0")
	}
	return body, nil
}

func runTrial(ctx context.Context, c Config, task, condition, model string, repetition int, dir string) Trial {
	if c.Harness == "deepseek-harness" {
		return runDSHTrial(ctx, c, task, condition, model, repetition, dir)
	}
	prompt := "Read TASK.md, fix solution.go, and run the visible Go tests. Only modify solution.go."
	t := Trial{Task: task, Repetition: repetition, Condition: condition, Model: model,
		Status: "agent_error", TaskHash: digest(append(append(asset(task, "prompt.md"), asset(task, "solution.go.txt")...), asset(task, "visible_test.go.txt")...)),
		PromptHash: digest([]byte(prompt))}
	fail := func(err error) Trial {
		t.Status, t.Scorable, t.Passed, t.Error = "runner_error", false, false, err.Error()
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
	agentDir, err := os.MkdirTemp("", "harness-pi-")
	if err != nil {
		return fail(err)
	}
	defer os.RemoveAll(agentDir)
	if err := writeJSON(filepath.Join(agentDir, "models.json"), modelConfig(c)); err != nil {
		return fail(err)
	}
	settings := map[string]any{"compaction": map[string]bool{"enabled": false},
		"retry": map[string]bool{"enabled": false}, "enableInstallTelemetry": false, "quietStartup": true}
	if err := writeJSON(filepath.Join(agentDir, "settings.json"), settings); err != nil {
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
	cmd := ownedCommand(agentCtx, c.Pi, "--mode", "json", "--print", "--no-session",
		"--no-extensions", "--no-mcp", "--no-skills", "--no-prompt-templates", "--no-themes", "--no-context-files",
		"--tools", "read,bash,edit,write", "--provider", "experiment", "--model", model, "--thinking", "off", prompt)
	cmd.Dir = work
	cmd.Env = replaceEnv(os.Environ(), map[string]string{"PI_CODING_AGENT_DIR": agentDir,
		"HARNESS_EXPERIMENT_API_KEY": apiKey(), "GOWORK": "off", "GOTOOLCHAIN": "local", "GOPROXY": "off", "GOSUMDB": "off"})
	cmd.Stderr = stderr
	pipe, err := cmd.StdoutPipe()
	if err != nil {
		return fail(err)
	}
	start := time.Now()
	if err := cmd.Start(); err != nil {
		return fail(err)
	}
	state := newStreamState()
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
		t.Error = "invalid or oversized Pi event stream"
	} else if errors.Is(agentCtx.Err(), context.DeadlineExceeded) {
		t.Status, t.Scorable = "timeout", true
	} else if waitErr == nil && state.settled && !state.aborted && state.AssistantMessages > 0 && (state.lastStop == "stop" || state.lastStop == "length") {
		t.Status, t.Scorable = "completed", true
	} else {
		t.Error = "Pi did not settle successfully; inspect stderr.log and events.jsonl"
	}
	if ctx.Err() != nil {
		t.Status, t.Scorable, t.Error = "cancelled", false, "experiment cancelled"
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
	// A timed-out transcript can be missing the final usage. Never publish a
	// partial token total as the cost of a complete attempt.
	if t.Status != "completed" {
		t.Metrics.GeneratedTokens, t.Metrics.InputTokens = nil, nil
		t.Metrics.CacheReadTokens, t.Metrics.CacheWriteTokens = nil, nil
	}
	if err := writeFile(filepath.Join(dir, "grade.jsonl"), []byte(t.Grade.Log)); err != nil {
		return fail(err)
	}
	return t
}

func runExperiment(ctx context.Context, c Config, out io.Writer) error {
	cli := c.Pi
	if c.Harness == "deepseek-harness" {
		cli = c.DSH
	}
	piPath, err := exec.LookPath(cli)
	if err != nil {
		return fmt.Errorf("find Pi executable: %w", err)
	}
	cliPath, err := filepath.Abs(piPath)
	if err != nil {
		return err
	}
	if c.Harness == "deepseek-harness" {
		c.DSH = cliPath
	} else {
		c.Pi = cliPath
	}
	// Check a known-good answer before spending requests on model attempts.
	gate := gradeSource(ctx, taskIDs[0], asset(taskIDs[0], "reference.go.txt"))
	if !gate.Passed {
		return fmt.Errorf("grader preflight failed (%s); run selfcheck and verify the Go toolchain", gate.Status)
	}
	models, err := preflight(ctx, c)
	if err != nil {
		return err
	}
	var adapterSnapshot json.RawMessage
	if c.LlamaLoRA {
		adapterSnapshot, err = llamaAdapterSnapshot(ctx, c)
		if err != nil {
			return err
		}
	}
	if err := os.MkdirAll(filepath.Dir(c.Out), 0700); err != nil {
		return err
	}
	if err := os.Mkdir(c.Out, 0700); err != nil {
		return fmt.Errorf("create fresh output directory: %w", err)
	}
	if err := writeFile(filepath.Join(c.Out, "server-models.json"), models); err != nil {
		return err
	}
	if c.LlamaLoRA {
		if err := writeFile(filepath.Join(c.Out, "llama-lora-adapters.json"), adapterSnapshot); err != nil {
			return err
		}
	}
	version, err := exec.Command("go", "version").Output()
	if err != nil {
		return err
	}
	metadata := map[string]any{"schema": 1, "kind": "real_pi_external_endpoint",
		"started_at": time.Now().UTC().Format(time.RFC3339), "pi_version": piVersion,
		"go_version": strings.TrimSpace(string(version)), "os": runtime.GOOS, "arch": runtime.GOARCH,
		"config": c, "pi_models_config": modelConfig(c), "seed_controlled": false,
		"weight_identity": "model IDs are routing names, verify server weights and revisions separately"}
	if c.Harness == "deepseek-harness" {
		metadata["kind"] = "real_deepseek_harness_external_endpoint"
		metadata["harness_version"] = dshVersion
		metadata["request_policy"] = map[string]any{"base": dshRequestPolicy(c.LlamaLoRA, 0), "adapter": dshRequestPolicy(c.LlamaLoRA, 1)}
		metadata["tool_names"] = []string{"read", "write", "edit", "bash"}
		metadata["node_minimum_version"] = "24.9.0"
		metadata["policy_gateway"] = "Only normalizes request sampling and LoRA; agent loop, prompt and native tools are DSH. Full outgoing bodies saved per trial."
		delete(metadata, "pi_version")
		delete(metadata, "pi_models_config")
	}
	if err := writeJSON(filepath.Join(c.Out, "metadata.json"), metadata); err != nil {
		return err
	}
	var trials []Trial
	for run := 0; run < c.Runs; run++ {
		repetition := c.RunOffset + run + 1
		for index, task := range taskIDs {
			conditions := []struct{ name, model string }{{"base", c.BaseModel}, {"adapter", c.AdapterModel}}
			if (repetition+index)%2 == 0 {
				conditions[0], conditions[1] = conditions[1], conditions[0]
			}
			for _, condition := range conditions {
				if !includesPair(c.OnlyPairs, task, condition.name) {
					continue
				}
				if ctx.Err() != nil {
					return ctx.Err()
				}
				dir := filepath.Join(c.Out, fmt.Sprintf("%02d-%s-%s", repetition, task, condition.name))
				if err := os.Mkdir(dir, 0700); err != nil {
					return err
				}
				trial := runTrial(ctx, c, task, condition.name, condition.model, repetition, dir)
				trials = append(trials, trial)
				if err := writeJSON(filepath.Join(dir, "result.json"), trial); err != nil {
					return err
				}
				if err := writeJSON(filepath.Join(c.Out, "results.json"), trials); err != nil {
					return err
				}
				fmt.Fprintf(out, "%s / %s / %d: status=%s scorable=%t passed=%t\n", task, condition.name, repetition, trial.Status, trial.Scorable, trial.Passed)
			}
		}
	}
	summary := summarize(trials)
	if err := writeJSON(filepath.Join(c.Out, "summary.json"), summary); err != nil {
		return err
	}
	for _, condition := range []string{"base", "adapter"} {
		r := summary.Conditions[condition]
		fmt.Fprintf(out, "%s: %d/%d scored attempts passed; %d unscorable\n", condition, r.Passed, r.Scorable, r.Unscorable)
	}
	if summary.Conditions["base"].Unscorable+summary.Conditions["adapter"].Unscorable > 0 {
		return errors.New("one or more attempts were unscorable; inspect results before drawing conclusions")
	}
	return nil
}
