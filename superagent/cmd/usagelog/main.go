// Command usagelog is a local measuring proxy for live runs: it forwards
// OpenAI-compatible chat requests upstream, asks for streamed usage, and appends
// one JSON line per request (usage, tool calls, rejected commands). It never logs
// the Authorization header.
package main

import (
	"bufio"
	"bytes"
	"encoding/json"
	"flag"
	"io"
	"log"
	"net/http"
	"os"
	"strings"
	"sync"
	"time"
)

type record struct {
	Time       string          `json:"time"`
	Role       string          `json:"role"` // worker requests carry tools, coordinator requests do not
	Messages   int             `json:"messages"`
	Status     int             `json:"status"`
	Usage      json.RawMessage `json:"usage,omitempty"`
	Content    string          `json:"content,omitempty"`
	ToolCalls  []string        `json:"tool_calls,omitempty"`
	Finish     string          `json:"finish_reason,omitempty"`
	LastTool   string          `json:"last_tool_result,omitempty"`
	Rejections int             `json:"rejections_in_history"`
}

const rejectMark = "outside fixed CSV task"

func main() {
	addr := flag.String("addr", "127.0.0.1:18080", "listen address")
	upstream := flag.String("upstream", "https://api.deepseek.com", "upstream base URL")
	out := flag.String("log", "usage.jsonl", "JSON lines output")
	flag.Parse()
	f, err := os.OpenFile(*out, os.O_CREATE|os.O_APPEND|os.O_WRONLY, 0600)
	if err != nil {
		log.Fatal(err)
	}
	var mu sync.Mutex
	write := func(r record) {
		mu.Lock()
		defer mu.Unlock()
		b, _ := json.Marshal(r)
		f.Write(append(b, '\n'))
	}
	http.HandleFunc("/", func(w http.ResponseWriter, req *http.Request) {
		body, _ := io.ReadAll(req.Body)
		var in map[string]any
		rec := record{Time: time.Now().UTC().Format(time.RFC3339), Role: "coordinator"}
		if json.Unmarshal(body, &in) == nil {
			if _, ok := in["tools"]; ok {
				rec.Role = "worker"
			}
			if s, _ := in["stream"].(bool); s {
				in["stream_options"] = map[string]any{"include_usage": true}
				body, _ = json.Marshal(in)
			}
			msgs, _ := in["messages"].([]any)
			rec.Messages = len(msgs)
			for _, m := range msgs {
				mm, _ := m.(map[string]any)
				if mm["role"] == "tool" {
					c, _ := mm["content"].(string)
					rec.LastTool = c
					if strings.Contains(c, rejectMark) {
						rec.Rejections++
					}
				}
			}
			if len(rec.LastTool) > 300 {
				rec.LastTool = rec.LastTool[:300]
			}
		}
		up, _ := http.NewRequestWithContext(req.Context(), req.Method, *upstream+strings.TrimPrefix(req.URL.Path, "/v1"), bytes.NewReader(body))
		up.Header = req.Header.Clone()
		up.Header.Del("Content-Length")
		up.Header.Del("Accept-Encoding")
		resp, err := http.DefaultClient.Do(up)
		if err != nil {
			http.Error(w, err.Error(), 502)
			return
		}
		defer resp.Body.Close()
		rec.Status = resp.StatusCode
		for k, v := range resp.Header {
			w.Header()[k] = v
		}
		w.WriteHeader(resp.StatusCode)
		var content strings.Builder
		calls := map[float64]string{}
		sc := bufio.NewScanner(io.TeeReader(resp.Body, flushWriter{w}))
		sc.Buffer(make([]byte, 1<<20), 1<<24)
		for sc.Scan() {
			line := strings.TrimPrefix(sc.Text(), "data: ")
			var chunk struct {
				Usage   json.RawMessage `json:"usage"`
				Choices []struct {
					Delta struct {
						Content   string `json:"content"`
						ToolCalls []struct {
							Index    float64 `json:"index"`
							Function struct {
								Name, Arguments string
							} `json:"function"`
						} `json:"tool_calls"`
					} `json:"delta"`
					FinishReason string `json:"finish_reason"`
				} `json:"choices"`
			}
			if json.Unmarshal([]byte(line), &chunk) != nil {
				continue
			}
			if len(chunk.Usage) > 0 && string(chunk.Usage) != "null" {
				rec.Usage = chunk.Usage
			}
			for _, c := range chunk.Choices {
				content.WriteString(c.Delta.Content)
				for _, tc := range c.Delta.ToolCalls {
					calls[tc.Index] += tc.Function.Name + tc.Function.Arguments
				}
				if c.FinishReason != "" {
					rec.Finish = c.FinishReason
				}
			}
		}
		rec.Content = content.String()
		for i := 0; i < len(calls); i++ {
			rec.ToolCalls = append(rec.ToolCalls, calls[float64(i)])
		}
		write(rec)
	})
	log.Fatal(http.ListenAndServe(*addr, nil))
}

type flushWriter struct{ w http.ResponseWriter }

func (f flushWriter) Write(p []byte) (int, error) {
	n, err := f.w.Write(p)
	if fl, ok := f.w.(http.Flusher); ok {
		fl.Flush()
	}
	return n, err
}
