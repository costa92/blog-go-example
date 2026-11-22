package main

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/http/httptest"
	"os"
	"strings"
	"testing"
	"time"
)

func TestDSHMetricsUseCommittedStepUsage(t *testing.T) {
	s := newDSHStreamState()
	for _, line := range []string{
		`{"type":"session","sessionId":"s"}`,
		`{"type":"tool_call","callId":"c"}`,
		`{"type":"tool_call","callId":"c"}`,
		`{"type":"tool_result","callId":"c","status":"error"}`,
		`{"type":"tool_result","callId":"c","status":"error"}`,
		`{"type":"status","phase":"step_end","turn":1,"step":1,"usage":{"inputTokens":20,"outputTokens":5,"cacheReadTokens":10}}`,
		`{"type":"status","phase":"step_end","turn":1,"step":2,"usage":{"inputTokens":30,"outputTokens":7}}`,
		`{"type":"status","phase":"turn_end","reason":{"kind":"completed"}}`,
		`{"type":"final","sessionId":"s","reason":{"kind":"completed"}}`,
	} {
		if err := s.accept([]byte(line)); err != nil {
			t.Fatal(err)
		}
	}
	m := s.metrics()
	if !s.completed || !s.ended || !s.final || m.ToolCalls != 1 || m.ToolErrors != 1 || m.GeneratedTokens == nil || *m.GeneratedTokens != 12 || *m.InputTokens != 50 {
		t.Fatalf("wrong DSH metrics: %+v", s)
	}
	missing := newDSHStreamState()
	_ = missing.accept([]byte(`{"type":"status","phase":"step_end","turn":1,"step":1}`))
	if missing.metrics().GeneratedTokens != nil {
		t.Fatal("missing usage became known zero")
	}
	if err := s.accept([]byte(`{"type":"final","sessionId":"s","reason":{"kind":"completed"}}`)); err == nil {
		t.Fatal("duplicate final accepted")
	}
	bad := newDSHStreamState()
	if err := bad.accept([]byte(`{"type":"tool_call"}`)); err == nil {
		t.Fatal("missing tool ID accepted")
	}
}

func TestDSHGatewayEnforcesWireParameters(t *testing.T) {
	count := 0
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		count++
		if r.URL.Path != "/v1/chat/completions" {
			t.Error(r.URL.Path)
		}
		var body map[string]any
		_ = json.NewDecoder(r.Body).Decode(&body)
		if body["temperature"] != 0.8 || body["top_p"] != float64(1) || body["max_tokens"] != float64(4096) {
			t.Errorf("bad sampling: %+v", body)
		}
		if _, ok := body["max_completion_tokens"]; ok {
			t.Error("duplicate token field")
		}
		l := body["lora"].([]any)[0].(map[string]any)
		if l["scale"] != float64(1) {
			t.Error(l)
		}
		io.WriteString(w, "data: [DONE]\n\n")
	}))
	defer upstream.Close()
	var log bytes.Buffer
	endpoint, stop, err := startDSHGateway(Config{BaseURL: upstream.URL + "/v1", LlamaLoRA: true}, "adapter", "adapter", &log)
	if err != nil {
		t.Fatal(err)
	}
	defer stop()
	resp, err := http.Post(endpoint+"/chat/completions", "application/json", strings.NewReader(`{"model":"adapter","stream":true,"temperature":99,"max_completion_tokens":12,"tools":[{"function":{"name":"read"}}]}`))
	if err != nil {
		t.Fatal(err)
	}
	io.Copy(io.Discard, resp.Body)
	resp.Body.Close()
	if resp.StatusCode != 200 || count != 1 || log.Len() == 0 {
		t.Fatal("request not forwarded and logged")
	}
	resp, err = http.Post(endpoint+"/chat/completions", "application/json", strings.NewReader(`{"model":"adapter","stream":true,"tools":[{"function":{"name":"web_search"}}]}`))
	if err != nil {
		t.Fatal(err)
	}
	resp.Body.Close()
	if resp.StatusCode != 400 || count != 1 {
		t.Fatal("unexpected tool catalog forwarded")
	}
}

func TestRealDSHWithScriptedEndpoint(t *testing.T) {
	dsh := os.Getenv("HARNESS_DSH_BIN")
	if dsh == "" {
		t.Skip("set HARNESS_DSH_BIN for pinned real DSH; scripted model only")
	}
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		var req struct {
			Model    string `json:"model"`
			Messages []struct {
				Role    string          `json:"role"`
				Content json.RawMessage `json:"content"`
			} `json:"messages"`
			Temperature float64                   `json:"temperature"`
			TopP        float64                   `json:"top_p"`
			MaxTokens   int                       `json:"max_tokens"`
			Lora        []struct{ ID, Scale int } `json:"lora"`
		}
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
			t.Error(err)
			http.Error(w, "bad", 400)
			return
		}
		want := 0
		if req.Model == "fixture-adapter" {
			want = 1
		}
		if req.Temperature != 0.8 || req.TopP != 1 || req.MaxTokens != 4096 || len(req.Lora) != 1 || req.Lora[0].Scale != want {
			t.Errorf("unexpected request: %+v", req)
		}
		tools := 0
		for _, m := range req.Messages {
			if m.Role == "tool" {
				tools++
			}
		}
		var name string
		var args any
		switch tools {
		case 0:
			name, args = "read", map[string]any{"file_path": "TASK.md"}
		case 1:
			name, args = "write", map[string]any{"file_path": "solution.go", "content": string(asset("bytesize", "reference.go.txt"))}
		case 2:
			name, args = "bash", map[string]any{"command": "go test ./...", "description": "Run the visible Go tests"}
		}
		w.Header().Set("Content-Type", "text/event-stream")
		send := func(v any) { b, _ := json.Marshal(v); fmt.Fprintf(w, "data: %s\n\n", b) }
		delta := map[string]any{"role": "assistant"}
		finish := "stop"
		if name != "" {
			a, _ := json.Marshal(args)
			delta["tool_calls"] = []any{map[string]any{"index": 0, "id": fmt.Sprintf("fixture_call_%d", tools), "type": "function", "function": map[string]any{"name": name, "arguments": string(a)}}}
			finish = "tool_calls"
		} else {
			delta["content"] = "Scripted protocol fixture completed; not model inference."
		}
		chunk := func(choices []any) map[string]any {
			return map[string]any{"id": "fixture", "object": "chat.completion.chunk", "created": 1, "model": req.Model, "choices": choices}
		}
		send(chunk([]any{map[string]any{"index": 0, "delta": delta, "finish_reason": nil}}))
		send(chunk([]any{map[string]any{"index": 0, "delta": map[string]any{}, "finish_reason": finish}}))
		usage := chunk([]any{})
		usage["usage"] = map[string]int{"prompt_tokens": 100, "completion_tokens": 10, "total_tokens": 110}
		send(usage)
		io.WriteString(w, "data: [DONE]\n\n")
	}))
	defer server.Close()
	for _, condition := range []string{"base", "adapter"} {
		dir := t.TempDir()
		c := Config{Harness: "deepseek-harness", DSH: dsh, BaseURL: server.URL + "/v1", LlamaLoRA: true, ContextWindow: 16384, Timeout: 45 * time.Second}
		tr := runDSHTrial(context.Background(), c, "bytesize", condition, "fixture-"+condition, 1, dir)
		if !tr.Scorable || !tr.Passed || tr.Status != "completed" || tr.Metrics.ToolCalls != 3 || tr.Metrics.GeneratedTokens == nil || *tr.Metrics.GeneratedTokens != 40 {
			log, _ := os.ReadFile(dir + "/stderr.log")
			events, _ := os.ReadFile(dir + "/events.jsonl")
			t.Fatalf("DSH protocol mismatch: %+v\nstderr: %s\nevents: %s", tr, log, events)
		}
	}
}

func TestSummarizeDoesNotMixHarnesses(t *testing.T) {
	dir := t.TempDir()
	a := dir + "/pi.json"
	b := dir + "/dsh.json"
	pi := Trial{Task: "bytesize", Condition: "base", Model: "base", Repetition: 1}
	dsh := Trial{Harness: "deepseek-harness", Task: "csv-record", Condition: "base", Model: "base", Repetition: 1}
	if err := writeJSON(a, []Trial{pi}); err != nil {
		t.Fatal(err)
	}
	if err := writeJSON(b, []Trial{dsh}); err != nil {
		t.Fatal(err)
	}
	var out bytes.Buffer
	if err := execute(context.Background(), []string{"summarize", a, b}, &out); err == nil || !strings.Contains(err.Error(), "different harnesses") {
		t.Fatalf("mixed harnesses: %v", err)
	}
}
