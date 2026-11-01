package csvbug

import (
	"encoding/csv"
	"reflect"
	"strings"
	"testing"
)

func TestExportRows(t *testing.T) {
	rows := [][]string{{"name", "value"}, {"alpha", "1"}}
	got, err := Export(rows)
	if err != nil || got != "name,value\nalpha,1\n" {
		t.Fatalf("Export() = %q, %v; want nonempty CSV with all rows", got, err)
	}
}

func TestExportEmpty(t *testing.T) {
	got, err := Export(nil)
	if err != nil || got != "" {
		t.Fatalf("Export(nil) = %q, %v; want empty CSV", got, err)
	}
}

func TestExportQuotedUnicode(t *testing.T) {
	rows := [][]string{{"名字", "逗号,引号\"和\n换行"}}
	got, err := Export(rows)
	if err != nil {
		t.Fatal(err)
	}
	parsed, err := csv.NewReader(strings.NewReader(got)).ReadAll()
	if err != nil || !reflect.DeepEqual(parsed, rows) {
		t.Fatalf("round trip = %v, %v; want %v", parsed, err, rows)
	}
}
