//go:build goexperiment.jsonv2 && go1.27

package jsonv2

import (
	jsonv1 "encoding/json"
	jsonv2 "encoding/json/v2"
	"fmt"
	"strings"
	"testing"
)

type Item struct {
	ID    int64             `json:"id"`
	Name  string            `json:"name"`
	Price float64           `json:"price"`
	Tags  []string          `json:"tags"`
	Attrs map[string]string `json:"attrs"`
}

// 1000 个对象，约 98KB。
var benchData = func() []byte {
	var sb strings.Builder
	sb.WriteString("[")
	for i := range 1000 {
		if i > 0 {
			sb.WriteString(",")
		}
		fmt.Fprintf(&sb, `{"id":%d,"name":"item-%d","price":%d.5,"tags":["a","b","c"],"attrs":{"color":"red","size":"L"}}`, i, i, i)
	}
	sb.WriteString("]")
	return []byte(sb.String())
}()

func BenchmarkV1Unmarshal(b *testing.B) {
	b.SetBytes(int64(len(benchData)))
	for b.Loop() {
		var v []Item
		if err := jsonv1.Unmarshal(benchData, &v); err != nil {
			b.Fatal(err)
		}
	}
}

func BenchmarkV2Unmarshal(b *testing.B) {
	b.SetBytes(int64(len(benchData)))
	for b.Loop() {
		var v []Item
		if err := jsonv2.Unmarshal(benchData, &v); err != nil {
			b.Fatal(err)
		}
	}
}

func BenchmarkV1Marshal(b *testing.B) {
	var v []Item
	jsonv1.Unmarshal(benchData, &v)
	b.SetBytes(int64(len(benchData)))
	for b.Loop() {
		if _, err := jsonv1.Marshal(v); err != nil {
			b.Fatal(err)
		}
	}
}

func BenchmarkV2Marshal(b *testing.B) {
	var v []Item
	jsonv2.Unmarshal(benchData, &v)
	b.SetBytes(int64(len(benchData)))
	for b.Loop() {
		if _, err := jsonv2.Marshal(v); err != nil {
			b.Fatal(err)
		}
	}
}
