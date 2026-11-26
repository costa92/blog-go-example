package solution

import "strings"

var wideRanges = [][2]rune{
	{0x1100, 0x115F},
	{0x2E80, 0xA4CF},
	{0xAC00, 0xD7A3},
	{0xF900, 0xFAFF},
	{0xFE30, 0xFE4F},
	{0xFF00, 0xFF60},
	{0xFFE0, 0xFFE6},
	{0x20000, 0x3FFFD},
}

func isWide(r rune) bool {
	for _, rg := range wideRanges {
		if r >= rg[0] && r <= rg[1] {
			return true
		}
	}
	return false
}

type unit struct {
	text  string
	width int
	word  int
}

func units(para string, width int) []unit {
	var out []unit
	wi := -1
	for _, w := range strings.Split(para, " ") {
		if w == "" {
			continue
		}
		wi++
		var narrow []rune
		flush := func() {
			for len(narrow) > 0 {
				n := min(len(narrow), width)
				out = append(out, unit{string(narrow[:n]), n, wi})
				narrow = narrow[n:]
			}
		}
		for _, r := range w {
			if isWide(r) {
				flush()
				out = append(out, unit{string(r), 2, wi})
			} else {
				narrow = append(narrow, r)
			}
		}
		flush()
	}
	return out
}

func Wrap(s string, width int) []string {
	lines := []string{}
	for _, para := range strings.Split(s, "\n") {
		var line strings.Builder
		lw, prevWord := 0, -1
		for _, u := range units(para, width) {
			sep := 0
			if u.word != prevWord {
				sep = 1
			}
			switch {
			case lw == 0:
				line.WriteString(u.text)
				lw = u.width
			case lw+sep+u.width <= width:
				if sep == 1 {
					line.WriteByte(' ')
				}
				line.WriteString(u.text)
				lw += sep + u.width
			default:
				lines = append(lines, line.String())
				line.Reset()
				line.WriteString(u.text)
				lw = u.width
			}
			prevWord = u.word
		}
		lines = append(lines, line.String())
	}
	return lines
}
