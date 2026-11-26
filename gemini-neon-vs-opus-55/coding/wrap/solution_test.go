package solution

import (
	"fmt"
	"reflect"
	"testing"
)

type wrapCase struct {
	in    string
	width int
	want  []string
}

func runWrap(t *testing.T, cases []wrapCase) {
	t.Helper()
	for _, c := range cases {
		t.Run(fmt.Sprintf("%q/%d", c.in, c.width), func(t *testing.T) {
			got := Wrap(c.in, c.width)
			if !reflect.DeepEqual(got, c.want) {
				t.Fatalf("Wrap(%q, %d) = %q, want %q", c.in, c.width, got, c.want)
			}
		})
	}
}

func TestASCIIGreedy(t *testing.T) {
	runWrap(t, []wrapCase{
		{"the quick brown fox jumps over the lazy dog", 10,
			[]string{"the quick", "brown fox", "jumps over", "the lazy", "dog"}},
		{"abc def", 7, []string{"abc def"}},
		{"abc def", 6, []string{"abc", "def"}},
		{"a b c d e", 3, []string{"a b", "c d", "e"}},
		{"hello", 5, []string{"hello"}},
		{"Hello, world! ok", 6, []string{"Hello,", "world!", "ok"}},
	})
}

func TestWhitespace(t *testing.T) {
	runWrap(t, []wrapCase{
		{"  a   b  ", 10, []string{"a b"}},
		{"a    b", 3, []string{"a b"}},
		{"   ", 4, []string{""}},
		{"x  ", 2, []string{"x"}},
		{"ab   cd", 4, []string{"ab", "cd"}},
	})
}

func TestParagraphs(t *testing.T) {
	runWrap(t, []wrapCase{
		{"", 5, []string{""}},
		{"a\n\nb", 5, []string{"a", "", "b"}},
		{"a\n", 5, []string{"a", ""}},
		{"\n", 5, []string{"", ""}},
		{"   \nx", 5, []string{"", "x"}},
		{"aa bb\ncc dd", 5, []string{"aa bb", "cc dd"}},
		{"aa bb cc\n中文", 4, []string{"aa", "bb", "cc", "中文"}},
	})
}

func TestCJK(t *testing.T) {
	runWrap(t, []wrapCase{
		{"你好世界", 4, []string{"你好", "世界"}},
		{"你好世界", 5, []string{"你好", "世界"}},
		{"你好世界", 3, []string{"你", "好", "世", "界"}},
		{"你好世界", 8, []string{"你好世界"}},
		{"你好，世界。", 4, []string{"你好", "，世", "界。"}},
		{"한국어 텍스트", 6, []string{"한국어", "텍스트"}},
		{"你 好", 4, []string{"你", "好"}},
		{"你 好", 5, []string{"你 好"}},
		{"你　好", 4, []string{"你　", "好"}}, // U+3000 is a wide rune, not a separator
	})
}

func TestMixedScripts(t *testing.T) {
	runWrap(t, []wrapCase{
		{"我爱Go语言", 6, []string{"我爱Go", "语言"}},
		{"使用 Go 编写 服务", 7, []string{"使用 Go", "编写 服", "务"}},
		{"abc中def", 4, []string{"abc", "中", "def"}},
		{"abc中def", 5, []string{"abc中", "def"}},
		{"Hello, 世界!", 8, []string{"Hello,", "世界!"}},
		{"在Kubernetes里部署", 12, []string{"在Kubernetes", "里部署"}},
		{"用Go语言,ok go", 8, []string{"用Go语言", ",ok go"}},
		{"Go 语言 is 好", 4, []string{"Go", "语言", "is", "好"}},
	})
}

func TestHardSplit(t *testing.T) {
	runWrap(t, []wrapCase{
		{"abcdefghij k", 4, []string{"abcd", "efgh", "ij k"}},
		{"ab cdefghij", 4, []string{"ab", "cdef", "ghij"}},
		{"abcd", 4, []string{"abcd"}},
		{"abcde", 4, []string{"abcd", "e"}},
		{"中abcdefgh", 5, []string{"中", "abcde", "fgh"}},
		{"x abcdef", 3, []string{"x", "abc", "def"}},
		{"abcdefg中", 3, []string{"abc", "def", "g中"}},
		{"https://example.com/a", 8, []string{"https://", "example.", "com/a"}},
	})
}

func TestRuneWidthTable(t *testing.T) {
	// Each case puts two copies of a rune in one word at width 3:
	// wide runes give two lines, narrow runes fit on one line.
	wide := []rune{0x1100, 0x115F, 0x2E80, 0xA4CF, 0xAC00, 0xD7A3, 0xF900, 0xFAFF,
		0xFE30, 0xFE4F, 0xFF00, 0xFF60, 0xFFE0, 0xFFE6, 0x20000, 0x3FFFD}
	narrow := []rune{0x10FF, 0x1160, 0x2E7F, 0xA4D0, 0xABFF, 0xD7A4, 0xF8FF, 0xFB00,
		0xFE2F, 0xFE50, 0xFF61, 0xFFDF, 0xFFE7, 0x1FFFF, 0x3FFFE, 0xE9}
	var cases []wrapCase
	for _, r := range wide {
		cases = append(cases, wrapCase{string([]rune{r, r}), 3, []string{string(r), string(r)}})
	}
	for _, r := range narrow {
		cases = append(cases, wrapCase{string([]rune{r, r}), 3, []string{string([]rune{r, r})}})
	}
	runWrap(t, cases)
}

func TestNarrowNonASCII(t *testing.T) {
	runWrap(t, []wrapCase{
		{"café naïve", 4, []string{"café", "naïv", "e"}},
		{"café au lait", 7, []string{"café au", "lait"}},
		{"résumé", 6, []string{"résumé"}},
		{"ｱｲｳｴ", 3, []string{"ｱｲｳ", "ｴ"}}, // halfwidth katakana are narrow
		{"a b c", 3, []string{"a b", "c"}},
	})
}
