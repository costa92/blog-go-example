package main

import (
	"fmt"
	"sort"
)

type ConditionSummary struct {
	Attempts   int `json:"attempts"`
	Scorable   int `json:"scorable"`
	Passed     int `json:"passed"`
	Unscorable int `json:"unscorable"`
}

type Summary struct {
	Conditions         map[string]ConditionSummary `json:"conditions"`
	BothPassedPairs    int                         `json:"both_passed_pairs"`
	CompletePairs      int                         `json:"both_passed_and_completed_pairs"`
	TokenPairs         int                         `json:"pairs_with_complete_usage"`
	MedianToolCalls    map[string]*float64         `json:"median_tool_calls_on_complete_pairs"`
	MedianAgentMS      map[string]*float64         `json:"median_agent_ms_on_complete_pairs"`
	MedianOutputTokens map[string]*float64         `json:"median_generated_tokens_on_usage_pairs"`
}

func median(values []float64) *float64 {
	if len(values) == 0 {
		return nil
	}
	sort.Float64s(values)
	n := len(values)
	v := values[n/2]
	if n%2 == 0 {
		v = (values[n/2-1] + v) / 2
	}
	return &v
}

func summarize(trials []Trial) Summary {
	s := Summary{Conditions: map[string]ConditionSummary{"base": {}, "adapter": {}},
		MedianToolCalls: map[string]*float64{}, MedianAgentMS: map[string]*float64{}, MedianOutputTokens: map[string]*float64{}}
	pairs := map[string]map[string]Trial{}
	for _, t := range trials {
		c := s.Conditions[t.Condition]
		c.Attempts++
		if t.Scorable {
			c.Scorable++
			if t.Passed {
				c.Passed++
			}
		} else {
			c.Unscorable++
		}
		s.Conditions[t.Condition] = c
		key := fmt.Sprintf("%s/%d", t.Task, t.Repetition)
		if pairs[key] == nil {
			pairs[key] = map[string]Trial{}
		}
		pairs[key][t.Condition] = t
	}
	tools, times, tokens := map[string][]float64{}, map[string][]float64{}, map[string][]float64{}
	for _, pair := range pairs {
		b, bok := pair["base"]
		a, aok := pair["adapter"]
		if !bok || !aok || !b.Scorable || !a.Scorable || !b.Passed || !a.Passed {
			continue
		}
		s.BothPassedPairs++
		if b.Status != "completed" || a.Status != "completed" {
			continue
		}
		s.CompletePairs++
		for _, t := range []Trial{b, a} {
			tools[t.Condition] = append(tools[t.Condition], float64(t.Metrics.ToolCalls))
			times[t.Condition] = append(times[t.Condition], float64(t.AgentMS))
		}
		if b.Metrics.GeneratedTokens == nil || a.Metrics.GeneratedTokens == nil {
			continue
		}
		s.TokenPairs++
		tokens["base"] = append(tokens["base"], float64(*b.Metrics.GeneratedTokens))
		tokens["adapter"] = append(tokens["adapter"], float64(*a.Metrics.GeneratedTokens))
	}
	for _, condition := range []string{"base", "adapter"} {
		s.MedianToolCalls[condition] = median(tools[condition])
		s.MedianAgentMS[condition] = median(times[condition])
		s.MedianOutputTokens[condition] = median(tokens[condition])
	}
	return s
}
