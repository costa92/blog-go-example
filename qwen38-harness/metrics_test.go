package main

import "testing"

func TestVLLMConfigDoesNotInjectLlamaSpecificLoRA(t *testing.T) {
	c := modelConfig(Config{BaseModel: "base", AdapterModel: "adapter"})
	provider := c["providers"].(map[string]any)["experiment"].(map[string]any)
	for _, raw := range provider["models"].([]any) {
		m := raw.(map[string]any)
		if _, exists := m["samplingParams"].(map[string]any)["lora"]; exists {
			t.Fatal("llama-specific scale leaked into default vLLM config")
		}
	}
}

func TestOnlyFinalAssistantMessagesCountUsage(t *testing.T) {
	s := newStreamState()
	for _, line := range []string{
		`{"type":"message_update","usage":{"input":999,"output":999}}`,
		`{"type":"message_end","message":{"role":"user","usage":{"input":999,"output":999}}}`,
		`{"type":"message_end","message":{"role":"assistant","stopReason":"toolUse","usage":{"input":100,"output":10,"cacheRead":2,"cacheWrite":3}}}`,
		`{"type":"tool_execution_start","toolCallId":"a"}`,
		`{"type":"tool_execution_start","toolCallId":"a"}`,
		`{"type":"tool_execution_end","toolCallId":"a","isError":true}`,
		`{"type":"tool_execution_end","toolCallId":"a","isError":true}`,
		`{"type":"message_end","message":{"role":"assistant","stopReason":"stop","usage":{"input":200,"output":20}}}`,
		`{"type":"agent_end","messages":[{"role":"assistant","usage":{"input":999,"output":999}}]}`,
		`{"type":"agent_settled","aborted":false}`,
	} {
		if err := s.accept([]byte(line)); err != nil {
			t.Fatal(err)
		}
	}
	m := s.metrics()
	if m.AssistantMessages != 2 || m.ToolCalls != 1 || m.ToolErrors != 1 || m.GeneratedTokens == nil || *m.GeneratedTokens != 30 || *m.InputTokens != 300 || *m.CacheReadTokens != 2 || *m.CacheWriteTokens != 3 || !s.settled {
		t.Fatalf("incorrect metrics: %+v", m)
	}
}

func TestMissingOrZeroUsageIsUnknown(t *testing.T) {
	for _, usage := range []string{``, `,"usage":{}`, `,"usage":{"input":0,"output":0}`} {
		s := newStreamState()
		if err := s.accept([]byte(`{"type":"message_end","message":{"role":"assistant"` + usage + `}}`)); err != nil {
			t.Fatal(err)
		}
		if s.metrics().GeneratedTokens != nil {
			t.Fatal("missing usage became a numeric saving")
		}
	}
}

func TestRejectMalformedEvent(t *testing.T) {
	if newStreamState().accept([]byte("not JSON")) == nil {
		t.Fatal("accepted non-JSON event")
	}
}

func TestSummaryUsesOnlyMatchedCompletedSuccesses(t *testing.T) {
	a, b := int64(30), int64(10)
	trials := []Trial{
		{Task: "one", Repetition: 1, Condition: "base", Scorable: true, Passed: true, Status: "completed", Metrics: Metrics{ToolCalls: 8, GeneratedTokens: &a}},
		{Task: "one", Repetition: 1, Condition: "adapter", Scorable: true, Passed: true, Status: "completed", Metrics: Metrics{ToolCalls: 3, GeneratedTokens: &b}},
		{Task: "two", Repetition: 1, Condition: "base", Scorable: true, Passed: false, Status: "completed", Metrics: Metrics{ToolCalls: 99}},
		{Task: "two", Repetition: 1, Condition: "adapter", Scorable: true, Passed: true, Status: "completed", Metrics: Metrics{ToolCalls: 1}},
		{Task: "three", Repetition: 1, Condition: "base", Scorable: false, Status: "agent_error"},
		{Task: "three", Repetition: 1, Condition: "adapter", Scorable: true, Passed: true, Status: "completed"},
		{Task: "four", Repetition: 1, Condition: "base", Scorable: true, Passed: true, Status: "timeout"},
		{Task: "four", Repetition: 1, Condition: "adapter", Scorable: true, Passed: true, Status: "completed"},
	}
	s := summarize(trials)
	if s.BothPassedPairs != 2 || s.CompletePairs != 1 || s.TokenPairs != 1 || *s.MedianToolCalls["base"] != 8 || *s.MedianOutputTokens["adapter"] != 10 || s.Conditions["base"].Unscorable != 1 {
		t.Fatalf("bad summary: %+v", s)
	}
	empty := summarize(nil)
	if empty.MedianOutputTokens["base"] != nil {
		t.Fatal("empty median should be null")
	}
}
