package codingworker

import (
	"context"
	"encoding/json"
	"fmt"
	"strings"

	example "github.com/costa92/blog-go-example/superagent"
	"github.com/kart-io/goagent/interfaces"
	"github.com/kart-io/goagent/llm"
)

// ScriptModel emits known tool calls for the embedded fixture. Files are really
// edited and tests really execute; the repair decision is scripted, not inferred.
type ScriptModel struct {
	*example.OfflineModel
	OnRequest func()
}

func NewScriptModel() *ScriptModel {
	return &ScriptModel{OfflineModel: &example.OfflineModel{Role: "worker"}}
}
func ScriptFactory(role, id string) (llm.Client, error) {
	if role == "coordinator" {
		return example.OfflineFactory(role, id)
	}
	return NewScriptModel(), nil
}
func (m *ScriptModel) CompleteToolsStream(ctx context.Context, req *llm.CompletionRequest, _ []interfaces.Tool) (<-chan *llm.StreamChunk, error) {
	if err := ctx.Err(); err != nil {
		return nil, err
	}
	if m.OnRequest != nil {
		m.OnRequest()
	}
	// Count completed tool-result messages, including the journal replayed history.
	completed := 0
	for _, msg := range req.Messages {
		if msg.Role == "tool" {
			completed++
		}
	}
	name := ""
	args := map[string]any{}
	switch completed {
	case 0:
		name = "run_command"
		args["command"] = TestCommand
	case 1:
		name = "read_file"
		args["path"] = "export.go"
	case 2:
		name = "edit_file"
		args["path"] = "export.go"
		args["old_string"] = "\treturn buf.String(), writer.Error()"
		args["new_string"] = "\twriter.Flush()\n\treturn buf.String(), writer.Error()"
	case 3:
		name = "run_command"
		args["command"] = TestCommand
	}
	chunk := &llm.StreamChunk{Content: "脚本 Worker 已通过 Harness 补上 CSV Flush 并执行回归测试；请人工评审 diff。未创建 PR。", Done: true, FinishReason: "stop"}
	if name != "" {
		data, err := json.Marshal(args)
		if err != nil {
			return nil, err
		}
		call := llm.ToolCall{ID: fmt.Sprintf("csv-step-%d", completed), Type: "function"}
		call.Function.Name = name
		call.Function.Arguments = string(data)
		chunk = &llm.StreamChunk{ToolCalls: []llm.ToolCall{call}, Done: true, FinishReason: "tool_calls"}
	} else {
		chunk.Delta = chunk.Content
	}
	// A rejected tool is not a successful fix. Stop; the host verifier reports it.
	if len(req.Messages) > 0 && strings.Contains(req.Messages[len(req.Messages)-1].Content, "is denied") {
		return nil, fmt.Errorf("script tool rejected")
	}
	ch := make(chan *llm.StreamChunk, 1)
	ch <- chunk
	close(ch)
	return ch, nil
}
