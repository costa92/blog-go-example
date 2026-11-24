package main

import (
	"strings"
	"testing"
)

func TestCount(t *testing.T) {
	tests := []struct {
		name string
		in   string
		want Counts
	}{
		{"empty", "", Counts{}},
		{"one line", "a b c\n", Counts{Lines: 1, Words: 3}},
		{"two lines", "a b\nc\n", Counts{Lines: 2, Words: 3}},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got, err := Count(strings.NewReader(tt.in))
			if err != nil || got != tt.want {
				t.Fatalf("Count(%q) = %+v, %v; want %+v", tt.in, got, err, tt.want)
			}
		})
	}
}
