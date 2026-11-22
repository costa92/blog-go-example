package main

import (
	"encoding/json"
	"fmt"
)

// Only message_end is authoritative. Streaming deltas and agent_end.messages
// repeat information and must not be added to the token totals a second time.
type Metrics struct {
	AssistantMessages int    `json:"assistant_messages"`
	ToolCalls         int    `json:"tool_calls"`
	ToolErrors        int    `json:"tool_errors"`
	GeneratedTokens   *int64 `json:"generated_tokens"`
	InputTokens       *int64 `json:"input_tokens"`
	CacheReadTokens   *int64 `json:"cache_read_tokens"`
	CacheWriteTokens  *int64 `json:"cache_write_tokens"`
}

type streamState struct {
	Metrics
	settled, aborted bool
	lastStop         string
	usageComplete    bool
	output, input    int64
	cacheRead        int64
	cacheWrite       int64
	tools            map[string]bool
	endedTools       map[string]bool
}

func newStreamState() *streamState {
	return &streamState{usageComplete: true, tools: map[string]bool{}, endedTools: map[string]bool{}}
}

func (s *streamState) accept(line []byte) error {
	var event struct {
		Type       string `json:"type"`
		ToolCallID string `json:"toolCallId"`
		IsError    bool   `json:"isError"`
		Aborted    bool   `json:"aborted"`
		Message    struct {
			Role       string `json:"role"`
			StopReason string `json:"stopReason"`
			Usage      *struct {
				Input      *int64 `json:"input"`
				Output     *int64 `json:"output"`
				CacheRead  int64  `json:"cacheRead"`
				CacheWrite int64  `json:"cacheWrite"`
			} `json:"usage"`
		} `json:"message"`
	}
	if err := json.Unmarshal(line, &event); err != nil {
		return fmt.Errorf("invalid Pi JSONL record: %w", err)
	}
	switch event.Type {
	case "message_end":
		if event.Message.Role != "assistant" {
			break
		}
		s.AssistantMessages++
		s.lastStop = event.Message.StopReason
		u := event.Message.Usage
		if u == nil || u.Input == nil || u.Output == nil || *u.Input < 0 || *u.Output < 0 ||
			(*u.Input == 0 && *u.Output == 0 && u.CacheRead == 0 && u.CacheWrite == 0) {
			s.usageComplete = false
			break
		}
		s.input += *u.Input
		s.output += *u.Output
		s.cacheRead += u.CacheRead
		s.cacheWrite += u.CacheWrite
	case "tool_execution_start":
		if event.ToolCallID == "" {
			return fmt.Errorf("tool execution has no ID")
		}
		if !s.tools[event.ToolCallID] {
			s.tools[event.ToolCallID] = true
			s.ToolCalls++
		}
	case "tool_execution_end":
		if !s.endedTools[event.ToolCallID] {
			s.endedTools[event.ToolCallID] = true
			if event.IsError {
				s.ToolErrors++
			}
		}
	case "agent_settled":
		s.settled, s.aborted = true, event.Aborted
	}
	return nil
}

func (s *streamState) metrics() Metrics {
	m := s.Metrics
	if s.usageComplete && s.AssistantMessages > 0 {
		m.GeneratedTokens = &s.output
		m.InputTokens = &s.input
		m.CacheReadTokens = &s.cacheRead
		m.CacheWriteTokens = &s.cacheWrite
	}
	return m
}
