package solution

import (
	"errors"
	"time"
)

var errBadDate = errors.New("invalid date")

// parseDay returns the number of days since 1970-01-01 (a Thursday).
func parseDay(s string) (int, error) {
	if len(s) != 10 || s[4] != '-' || s[7] != '-' {
		return 0, errBadDate
	}
	num := func(b string) (int, bool) {
		n := 0
		for i := 0; i < len(b); i++ {
			if b[i] < '0' || b[i] > '9' {
				return 0, false
			}
			n = n*10 + int(b[i]-'0')
		}
		return n, true
	}
	y, ok1 := num(s[0:4])
	m, ok2 := num(s[5:7])
	d, ok3 := num(s[8:10])
	if !ok1 || !ok2 || !ok3 || m < 1 || m > 12 || d < 1 {
		return 0, errBadDate
	}
	t := time.Date(y, time.Month(m), d, 0, 0, 0, 0, time.UTC)
	if t.Day() != d || int(t.Month()) != m {
		return 0, errBadDate
	}
	return int(t.Unix() / 86400), nil
}

func isWeekday(day int) bool {
	wd := ((day+4)%7 + 7) % 7 // 0 = Sunday
	return wd != 0 && wd != 6
}

func weekdaysBetween(a, b int) int {
	n := (b - a) / 7 * 5
	for d := a + (b-a)/7*7; d < b; d++ {
		if isWeekday(d) {
			n++
		}
	}
	return n
}

func Count(from, to string, holidays []string) (int, error) {
	a, err := parseDay(from)
	if err != nil {
		return 0, err
	}
	b, err := parseDay(to)
	if err != nil {
		return 0, err
	}
	hs := map[int]bool{}
	for _, h := range holidays {
		d, err := parseDay(h)
		if err != nil {
			return 0, err
		}
		hs[d] = true
	}
	sign := 1
	if b < a {
		a, b, sign = b, a, -1
	}
	n := weekdaysBetween(a, b)
	for d := range hs {
		if d >= a && d < b && isWeekday(d) {
			n--
		}
	}
	return sign * n, nil
}
