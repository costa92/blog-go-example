package solution

import (
	"errors"
	"reflect"
	"testing"
)

type parseCase struct {
	in   string
	want [][]string
}

func runParse(t *testing.T, cases []parseCase) {
	t.Helper()
	for _, c := range cases {
		t.Run(c.in, func(t *testing.T) {
			got, err := Parse(c.in)
			if err != nil {
				t.Fatalf("Parse(%q) error: %v", c.in, err)
			}
			if len(got) == 0 && len(c.want) == 0 {
				return
			}
			if !reflect.DeepEqual(got, c.want) {
				t.Fatalf("Parse(%q) = %q, want %q", c.in, got, c.want)
			}
		})
	}
}

type errCase struct {
	in   string
	line int
}

func runErr(t *testing.T, cases []errCase) {
	t.Helper()
	for _, c := range cases {
		t.Run(c.in, func(t *testing.T) {
			got, err := Parse(c.in)
			var pe *ParseError
			if !errors.As(err, &pe) {
				t.Fatalf("Parse(%q) = %q, %v; want *ParseError", c.in, got, err)
			}
			if pe.Line != c.line {
				t.Fatalf("Parse(%q) error line = %d, want %d", c.in, pe.Line, c.line)
			}
		})
	}
}

func TestSimpleRecords(t *testing.T) {
	runParse(t, []parseCase{
		{"a,b,c", [][]string{{"a", "b", "c"}}},
		{"a,b\nc,d", [][]string{{"a", "b"}, {"c", "d"}}},
		{"a,b\r\nc,d\r\n", [][]string{{"a", "b"}, {"c", "d"}}},
		{"a,,b", [][]string{{"a", "", "b"}}},
		{",", [][]string{{"", ""}}},
		{"a,", [][]string{{"a", ""}}},
		{"x\ny,z,w\n1", [][]string{{"x"}, {"y", "z", "w"}, {"1"}}},
		{" a , b ", [][]string{{" a ", " b "}}},
		{"a\rb,c\r", [][]string{{"a\rb", "c\r"}}},
	})
}

func TestLineEndsAndEmptyLines(t *testing.T) {
	runParse(t, []parseCase{
		{"", nil},
		{"a\n", [][]string{{"a"}}},
		{"a\r\n", [][]string{{"a"}}},
		{"\n", [][]string{{""}}},
		{"\r\n", [][]string{{""}}},
		{"a\n\nb", [][]string{{"a"}, {""}, {"b"}}},
		{"a\n\n", [][]string{{"a"}, {""}}},
		{"a\r\n\r\nb\r\n", [][]string{{"a"}, {""}, {"b"}}},
		{"\n\n", [][]string{{""}, {""}}},
		{"a\nb\r\nc", [][]string{{"a"}, {"b"}, {"c"}}},
	})
}

func TestQuotedFields(t *testing.T) {
	runParse(t, []parseCase{
		{`"a"`, [][]string{{"a"}}},
		{`""`, [][]string{{""}}},
		{`"a,b",c`, [][]string{{"a,b", "c"}}},
		{`"a""b"`, [][]string{{`a"b`}}},
		{`""""`, [][]string{{`"`}}},
		{`"x",""`, [][]string{{"x", ""}}},
		{"\"line1\nline2\",z", [][]string{{"line1\nline2", "z"}}},
		{"\"crlf\r\ninside\"\r\nnext", [][]string{{"crlf\r\ninside"}, {"next"}}},
		{"\"lone\rcr\"", [][]string{{"lone\rcr"}}},
		{"\"a\"\n", [][]string{{"a"}}},
		{"\"a\"\r\n\"b\"", [][]string{{"a"}, {"b"}}},
		{`"  spaced  "`, [][]string{{"  spaced  "}}},
		{"\"\n\"", [][]string{{"\n"}}},
	})
}

func TestStrayQuoteError(t *testing.T) {
	runErr(t, []errCase{
		{`a"b`, 1},
		{`a,b"`, 1},
		{` "a"`, 1},
		{"ok\nok2\nx\"y", 3},
		{"\"multi\nline\",ok\nbad\"", 3},
		{"a\r\nb\r\nc\"", 3},
	})
}

func TestCharAfterClosingQuote(t *testing.T) {
	runErr(t, []errCase{
		{`"a"b`, 1},
		{`"a" ,b`, 1},
		{"\"a\"\rb", 1},
		{"\"a\"\r", 1},
		{"x\n\"a\"x", 2},
		{"\"one\ntwo\"x", 2},
		{"\"a\",\"b\"\"c\"d", 1},
	})
}

func TestUnterminatedQuote(t *testing.T) {
	runErr(t, []errCase{
		{`"abc`, 1},
		{"\"abc\ndef\nghi", 1},
		{"a\nb\n\"open\nstill open", 3},
		{"x,\"", 1},
		{"\"a\"\"", 1},
		{"ok\r\n\"x\r\n", 2},
	})
}

func TestErrorShape(t *testing.T) {
	for _, in := range []string{`a"b`, `"a"b`, `"abc`} {
		t.Run(in, func(t *testing.T) {
			got, err := Parse(in)
			if got != nil {
				t.Errorf("records = %q, want nil on error", got)
			}
			var pe *ParseError
			if !errors.As(err, &pe) || err.Error() == "" {
				t.Fatalf("error %v is not a *ParseError with a message", err)
			}
		})
	}
}
