package solution

import (
	"strconv"
	"strings"
)

type ParseError struct {
	Line int
}

func (e *ParseError) Error() string {
	return "csv: parse error on line " + strconv.Itoa(e.Line)
}

func Parse(s string) ([][]string, error) {
	var records [][]string
	line := 1
	i := 0
	// lineEndAt reports the length of a line end starting at j (0 if none).
	lineEndAt := func(j int) int {
		if j < len(s) && s[j] == '\n' {
			return 1
		}
		if j+1 < len(s) && s[j] == '\r' && s[j+1] == '\n' {
			return 2
		}
		return 0
	}
	for i < len(s) {
		var rec []string
		for {
			var field strings.Builder
			if i < len(s) && s[i] == '"' {
				openLine := line
				i++
				for {
					if i >= len(s) {
						return nil, &ParseError{Line: openLine}
					}
					c := s[i]
					if c == '"' {
						if i+1 < len(s) && s[i+1] == '"' {
							field.WriteByte('"')
							i += 2
							continue
						}
						i++
						break
					}
					if c == '\n' {
						line++
					}
					field.WriteByte(c)
					i++
				}
				if i < len(s) && s[i] != ',' && lineEndAt(i) == 0 {
					return nil, &ParseError{Line: line}
				}
			} else {
				for i < len(s) && s[i] != ',' && lineEndAt(i) == 0 {
					if s[i] == '"' {
						return nil, &ParseError{Line: line}
					}
					field.WriteByte(s[i])
					i++
				}
			}
			rec = append(rec, field.String())
			if i < len(s) && s[i] == ',' {
				i++
				continue
			}
			if n := lineEndAt(i); n > 0 {
				i += n
				line++
			}
			break
		}
		records = append(records, rec)
	}
	return records, nil
}
