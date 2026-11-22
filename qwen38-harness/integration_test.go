package main

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

// This is a scripted OpenAI-compatible server, NOT Qwen inference. It proves
// that the pinned real Pi executes read/write/bash and that the external grader
// receives the changed source. The server supplies the reference deliberately.
func TestRealPiWithScriptedEndpoint(t *testing.T) {
	pi := os.Getenv("HARNESS_PI_BIN")
	if pi == "" {
		t.Skip("set HARNESS_PI_BIN to Pi 1.5.2 to exercise real CLI and tools")
	}
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/v1/models" {
			io.WriteString(w, `{"data":[{"id":"fixture","aliases":["fixture-base","fixture-adapter"]}]}`)
			return
		}
		if r.URL.Path == "/lora-adapters" {
			io.WriteString(w, `[{"id":0,"path":"fixture.gguf","scale":0}]`)
			return
		}
		if r.URL.Path != "/v1/chat/completions" {
			http.NotFound(w, r)
			return
		}
		var request struct {
			Model    string `json:"model"`
			Messages []struct {
				Role    string          `json:"role"`
				Content json.RawMessage `json:"content"`
			} `json:"messages"`
			Temperature         float64        `json:"temperature"`
			TopP                float64        `json:"top_p"`
			Template            map[string]any `json:"chat_template_kwargs"`
			Stream              bool           `json:"stream"`
			MaxTokens           int            `json:"max_tokens"`
			MaxCompletionTokens int            `json:"max_completion_tokens"`
			LoRA                []struct {
				ID    int     `json:"id"`
				Scale float64 `json:"scale"`
			} `json:"lora"`
		}
		if err := json.NewDecoder(r.Body).Decode(&request); err != nil {
			t.Error(err)
			http.Error(w, "bad request", 400)
			return
		}
		if request.Temperature != 0.8 || request.TopP != 1 || request.Template["enable_thinking"] != false || !request.Stream || (request.MaxTokens != 4096 && request.MaxCompletionTokens != 4096) {
			t.Errorf("unexpected sampling configuration: %+v", request)
		}
		expectedScale := float64(0)
		if request.Model == "fixture-adapter" {
			expectedScale = 1
		}
		if len(request.LoRA) != 1 || request.LoRA[0].ID != 0 || request.LoRA[0].Scale != expectedScale {
			t.Errorf("LoRA request did not match condition: %+v", request.LoRA)
		}
		toolResults := 0
		task := ""
		for _, message := range request.Messages {
			if message.Role == "tool" {
				toolResults++
			}
			for _, id := range taskIDs {
				if strings.Contains(string(message.Content), "Task: "+id) {
					task = id
				}
			}
		}
		var name string
		var args any
		switch toolResults {
		case 0:
			name, args = "read", map[string]any{"path": "TASK.md"}
		case 1:
			if task == "" {
				t.Error("read result did not contain task ID")
				http.Error(w, "missing task", 400)
				return
			}
			name, args = "write", map[string]any{"path": "solution.go", "content": string(asset(task, "reference.go.txt"))}
		case 2:
			name, args = "bash", map[string]any{"command": "go test ./..."}
		}
		w.Header().Set("Content-Type", "text/event-stream")
		send := func(value any) { b, _ := json.Marshal(value); fmt.Fprintf(w, "data: %s\n\n", b) }
		delta := map[string]any{"role": "assistant"}
		finish := "stop"
		if name != "" {
			arguments, _ := json.Marshal(args)
			delta["tool_calls"] = []any{map[string]any{"index": 0, "id": fmt.Sprintf("fixture_call_%d", toolResults), "type": "function", "function": map[string]any{"name": name, "arguments": string(arguments)}}}
			finish = "tool_calls"
		} else {
			delta["content"] = "Scripted fixture completed, not a model judgment."
		}
		chunk := func(choices []any) map[string]any {
			return map[string]any{"id": "fixture", "object": "chat.completion.chunk", "created": 1, "model": request.Model, "choices": choices}
		}
		send(chunk([]any{map[string]any{"index": 0, "delta": delta, "finish_reason": nil}}))
		send(chunk([]any{map[string]any{"index": 0, "delta": map[string]any{}, "finish_reason": finish}}))
		usage := chunk([]any{})
		usage["usage"] = map[string]int{"prompt_tokens": 100, "completion_tokens": 10, "total_tokens": 110}
		send(usage)
		io.WriteString(w, "data: [DONE]\n\n")
	}))
	defer server.Close()
	c := Config{BaseURL: server.URL + "/v1", BaseModel: "fixture-base", AdapterModel: "fixture-adapter", Runs: 1, RunOffset: 1, Timeout: 45 * time.Second, Pi: pi, Out: filepath.Join(t.TempDir(), "run"), LlamaLoRA: true, ContextWindow: 16384}
	var output strings.Builder
	if err := runExperiment(context.Background(), c, &output); err != nil {
		t.Fatalf("%v\n%s\ninspect temporary results at %s", err, output.String(), c.Out)
	}
	data, err := os.ReadFile(filepath.Join(c.Out, "results.json"))
	if err != nil {
		t.Fatal(err)
	}
	var trials []Trial
	if err := json.Unmarshal(data, &trials); err != nil {
		t.Fatal(err)
	}
	if len(trials) != 6 {
		t.Fatalf("got %d trials", len(trials))
	}
	if trials[0].Condition != "adapter" || trials[2].Condition != "base" {
		t.Fatal("continued repetition did not reverse condition order")
	}
	for _, trial := range trials {
		if trial.Repetition != 2 {
			t.Fatalf("continued run reused repetition: %+v", trial)
		}
		if _, err := os.Stat(filepath.Join(c.Out, fmt.Sprintf("02-%s-%s", trial.Task, trial.Condition), "result.json")); err != nil {
			t.Fatal(err)
		}
		if !trial.Passed || !trial.Scorable || trial.Metrics.ToolCalls != 3 || trial.Metrics.GeneratedTokens == nil || *trial.Metrics.GeneratedTokens != 40 {
			t.Fatalf("real Pi contract mismatch: %+v", trial)
		}
	}
	t.Log("Real Pi executed read/write/bash on all 3 tasks in both conditions; scripted server only, no Qwen inference")
}

func TestPreflightRejectsSameModelBeforeCallingPi(t *testing.T) {
	_, err := preflight(context.Background(), Config{BaseURL: "http://localhost/v1", BaseModel: "same", AdapterModel: "same", Runs: 1, Timeout: time.Second, Pi: "not-installed"})
	if err == nil || !strings.Contains(err.Error(), "distinct") {
		t.Fatalf("got %v", err)
	}
}

func TestPreflightRejectsInvalidRepetitionRange(t *testing.T) {
	for _, offset := range []int{-1, int(^uint(0) >> 1)} {
		_, err := preflight(context.Background(), Config{BaseURL: "http://localhost/v1", RunOffset: offset, Runs: 1})
		if err == nil || !strings.Contains(err.Error(), "run-offset") {
			t.Fatalf("offset %d: %v", offset, err)
		}
	}
}
