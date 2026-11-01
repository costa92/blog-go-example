package superagent

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/kart-io/goagent/llm"
	"github.com/kart-io/goagent/llm/providers"
)

// Contract fixture only: this is not a real model quality/availability test.
func TestOpenAICompatibleStreamingAdapter(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/v1/chat/completions" {
			http.NotFound(w, r)
			return
		}
		var req struct {
			Messages []llm.Message `json:"messages"`
			Stream   bool          `json:"stream"`
		}
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
			http.Error(w, "bad request", 400)
			return
		}
		text := "本地 HTTP 契约响应：未执行仓库操作"
		for _, msg := range req.Messages {
			if strings.Contains(msg.Content, "协调器") {
				text = `{"accept":true}`
			}
		}
		if !req.Stream {
			http.Error(w, "expected GoAgent streaming adapter", 400)
			return
		}
		w.Header().Set("Content-Type", "text/event-stream")
		chunk := map[string]any{"id": "fixture", "object": "chat.completion.chunk", "choices": []any{map[string]any{"index": 0, "delta": map[string]any{"content": text}}}}
		data, _ := json.Marshal(chunk)
		fmt.Fprintf(w, "data: %s\n\n", data)
		fmt.Fprint(w, "data: {\"id\":\"fixture\",\"object\":\"chat.completion.chunk\",\"choices\":[{\"index\":0,\"delta\":{},\"finish_reason\":\"stop\"}]}\n\ndata: [DONE]\n\n")
	}))
	defer server.Close()
	factory := func(_, _ string) (llm.Client, error) {
		return providers.NewOpenAIWithOptions(llm.WithAPIKey("local-fixture-placeholder"), llm.WithBaseURL(server.URL+"/v1"), llm.WithModel("fixture"), llm.WithTimeout(2*time.Second))
	}
	e, _ := setup(t, factory)
	r := submit(t, e, event("http", "issue/http"))
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	if err := e.RunPending(ctx); err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(snapshot(t, e).Tickets[r.Created].Result, "HTTP 契约") {
		t.Fatal("provider was not used")
	}
}
