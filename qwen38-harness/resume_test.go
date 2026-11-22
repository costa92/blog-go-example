package main

import (
	"context"
	"path/filepath"
	"strings"
	"testing"
)

func TestOnlyPairsSelectsWithoutChangingGlobalOrder(t *testing.T) {
	for _, bad := range []string{"unknown:base", "bytesize:other", "bytesize:base,bytesize:base"} {
		if validatePairs(bad) == nil {
			t.Fatalf("accepted %q", bad)
		}
	}
	spec := "retry-delay:base,csv-record:base,csv-record:adapter"
	if err := validatePairs(spec); err != nil {
		t.Fatal(err)
	}
	if includesPair(spec, "retry-delay", "adapter") || !includesPair(spec, "csv-record", "adapter") || !includesPair("", "bytesize", "base") {
		t.Fatal("wrong selection")
	}
}

func TestSummarizeRejectsDuplicateAndMismatchedTrials(t *testing.T) {
	dir := t.TempDir()
	a := filepath.Join(dir, "a.json")
	b := filepath.Join(dir, "b.json")
	base := Trial{Task: "bytesize", Condition: "base", Model: "base", Repetition: 1, TaskHash: "same-task", PromptHash: "same-prompt", Scorable: true, Passed: true, Status: "completed"}
	adapter := base
	adapter.Condition = "adapter"
	adapter.Model = "adapter"
	if err := writeJSON(a, []Trial{base}); err != nil {
		t.Fatal(err)
	}
	if err := writeJSON(b, []Trial{adapter}); err != nil {
		t.Fatal(err)
	}
	var output strings.Builder
	if err := execute(context.Background(), []string{"summarize", a, b}, &output); err != nil {
		t.Fatal(err)
	}
	if err := execute(context.Background(), []string{"summarize", a, a}, &output); err == nil {
		t.Fatal("accepted duplicate outcome")
	}
	adapter.TaskHash = "changed"
	if err := writeJSON(b, []Trial{adapter}); err != nil {
		t.Fatal(err)
	}
	if err := execute(context.Background(), []string{"summarize", a, b}, &output); err == nil {
		t.Fatal("mixed different task content")
	}
}
