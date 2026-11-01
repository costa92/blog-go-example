package superagent

import (
	"context"
	"github.com/kart-io/goagent/llm"
	"github.com/kart-io/goagent/llm/constants"
)

// OfflineModel exercises the real GoAgent loop with deterministic responses.
// It is not evidence of an LLM's reasoning or coding performance.
type OfflineModel struct {
	Role    string
	Respond func(context.Context, *llm.CompletionRequest) (string, error)
}

func OfflineFactory(role, _ string) (llm.Client, error) { return &OfflineModel{Role: role}, nil }
func (m *OfflineModel) Provider() constants.Provider    { return constants.ProviderCustom }
func (m *OfflineModel) IsAvailable() bool               { return true }
func (m *OfflineModel) Complete(ctx context.Context, r *llm.CompletionRequest) (*llm.CompletionResponse, error) {
	if err := ctx.Err(); err != nil {
		return nil, err
	}
	text := `{"accept":true}`
	if m.Role == "worker" {
		text = "教学方案：检查 CSV 编码器错误、空输入与写出缓冲；补充空行及正常数据的回归用例。未修改仓库、未执行测试、未创建 PR，等待人工评审。"
	}
	if m.Respond != nil {
		var err error
		text, err = m.Respond(ctx, r)
		if err != nil {
			return nil, err
		}
	}
	return &llm.CompletionResponse{Content: text, FinishReason: "stop", Model: "offline-script"}, nil
}
func (m *OfflineModel) Chat(ctx context.Context, msgs []llm.Message) (*llm.CompletionResponse, error) {
	return m.Complete(ctx, &llm.CompletionRequest{Messages: msgs})
}
func (m *OfflineModel) CompleteStream(ctx context.Context, r *llm.CompletionRequest) (<-chan *llm.StreamChunk, error) {
	res, err := m.Complete(ctx, r)
	if err != nil {
		return nil, err
	}
	ch := make(chan *llm.StreamChunk, 1)
	ch <- &llm.StreamChunk{Content: res.Content, Delta: res.Content, Done: true, FinishReason: "stop"}
	close(ch)
	return ch, nil
}
func (m *OfflineModel) ChatStream(ctx context.Context, msgs []llm.Message) (<-chan *llm.StreamChunk, error) {
	return m.CompleteStream(ctx, &llm.CompletionRequest{Messages: msgs})
}
