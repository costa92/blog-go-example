package solution

import (
	"fmt"
	"math/rand"
	"testing"
	"time"
)

type countCase struct {
	from, to string
	hol      []string
	want     int
}

func runCount(t *testing.T, cases []countCase) {
	t.Helper()
	for _, c := range cases {
		t.Run(fmt.Sprintf("%s_%s_%v", c.from, c.to, c.hol), func(t *testing.T) {
			got, err := Count(c.from, c.to, c.hol)
			if err != nil {
				t.Fatalf("Count error: %v", err)
			}
			if got != c.want {
				t.Fatalf("Count(%q, %q, %q) = %d, want %d", c.from, c.to, c.hol, got, c.want)
			}
		})
	}
}

func TestWeekCounting(t *testing.T) {
	// 2027-01-04 is a Monday.
	runCount(t, []countCase{
		{"2027-01-04", "2027-01-11", nil, 5},
		{"2027-01-04", "2027-01-09", nil, 5},
		{"2027-01-04", "2027-01-08", nil, 4}, // end excluded
		{"2027-01-04", "2027-01-05", nil, 1}, // start included
		{"2027-01-09", "2027-01-11", nil, 0},
		{"2027-01-02", "2027-01-04", nil, 0},
		{"2027-01-08", "2027-01-12", nil, 2}, // Fri, Mon
		{"2027-01-04", "2027-02-01", nil, 20},
	})
}

func TestEmptyAndReversed(t *testing.T) {
	runCount(t, []countCase{
		{"2027-01-04", "2027-01-04", nil, 0},
		{"2027-01-09", "2027-01-09", nil, 0},
		{"2027-01-11", "2027-01-04", nil, -5},
		{"2027-01-05", "2027-01-04", nil, -1},
		{"2027-01-11", "2027-01-04", []string{"2027-01-06"}, -4},
		{"2027-01-12", "2027-01-08", nil, -2},
	})
}

func TestHolidays(t *testing.T) {
	runCount(t, []countCase{
		{"2027-01-04", "2027-01-11", []string{"2027-01-06"}, 4},
		{"2027-01-04", "2027-01-11", []string{"2027-01-06", "2027-01-06", "2027-01-06"}, 4},
		{"2027-01-04", "2027-01-11", []string{"2027-01-09", "2027-01-10"}, 5}, // weekend
		{"2027-01-04", "2027-01-11", []string{"2027-01-11", "2026-01-05"}, 5}, // outside range
		{"2027-01-04", "2027-01-11", []string{"2027-01-04"}, 4},               // start date
		{"2027-01-04", "2027-01-11", []string{"2027-01-04", "2027-01-04", "2027-01-09", "2027-01-11", "2026-01-05"}, 4},
		{"2027-01-04", "2027-01-09", []string{"2027-01-04", "2027-01-05", "2027-01-06", "2027-01-07", "2027-01-08"}, 0},
		{"2027-01-04", "2027-01-11", []string{}, 5},
	})
}

func TestYearBoundary(t *testing.T) {
	runCount(t, []countCase{
		{"2026-12-28", "2027-01-05", []string{"2026-12-31", "2027-01-01"}, 4},
		{"2026-12-25", "2027-01-04", nil, 6},
		{"2026-12-31", "2027-01-01", nil, 1},
		{"2027-01-01", "2026-12-31", nil, -1},
		{"2027-01-01", "2028-01-01", nil, 261},
		{"2020-01-01", "2030-01-01", nil, 2609},
	})
}

func TestLeapYears(t *testing.T) {
	runCount(t, []countCase{
		{"2028-02-28", "2028-03-02", nil, 3},
		{"2027-02-26", "2027-03-02", nil, 2},
		{"2028-02-29", "2028-03-01", nil, 1},
		{"2028-02-28", "2028-03-02", []string{"2028-02-29"}, 2},
		{"2028-01-01", "2029-01-01", nil, 260},
		{"2000-02-29", "2000-03-01", nil, 1},
	})
}

func TestInvalidDates(t *testing.T) {
	bad := []string{
		"2027-02-29", "2027-04-31", "2027-13-01", "2027-00-10", "2027-01-00", "2027-01-32",
		"1900-02-29", "2027-1-05", "2027-01-5", "27-01-05", "2027/01/05", "20270105",
		" 2027-01-05", "2027-01-05 ", "2027-01-05T00:00", "", "abcd-ef-gh", "+027-01-05",
		"2027-0a-05", "２０２７-01-05",
	}
	for _, d := range bad {
		t.Run("from="+d, func(t *testing.T) {
			if _, err := Count(d, "2027-01-04", nil); err == nil {
				t.Errorf("Count(%q, ...) returned nil error", d)
			}
		})
		t.Run("to="+d, func(t *testing.T) {
			if _, err := Count("2027-01-04", d, nil); err == nil {
				t.Errorf("Count(..., %q, ...) returned nil error", d)
			}
		})
	}
	for _, d := range []string{"2000-02-29", "2400-02-29", "0001-01-01", "9999-12-31"} {
		t.Run("valid="+d, func(t *testing.T) {
			if _, err := Count(d, d, nil); err != nil {
				t.Errorf("Count(%q, %q) error: %v", d, d, err)
			}
		})
	}
}

func TestInvalidHoliday(t *testing.T) {
	cases := [][]string{
		{"2027-02-29"},
		{"2027-01-06", "bad"},
		{"2030-1-01"},                 // outside range, still invalid
		{"2027-01-06", "2027-01-06 "}, // trailing space
		{""},
	}
	for _, h := range cases {
		t.Run(fmt.Sprint(h), func(t *testing.T) {
			if _, err := Count("2027-01-04", "2027-01-11", h); err == nil {
				t.Errorf("Count with holidays %q returned nil error", h)
			}
		})
	}
}

func bruteCount(from, to time.Time, hol map[time.Time]bool) int {
	sign := 1
	if to.Before(from) {
		from, to, sign = to, from, -1
	}
	n := 0
	for d := from; d.Before(to); d = d.AddDate(0, 0, 1) {
		if wd := d.Weekday(); wd != time.Saturday && wd != time.Sunday && !hol[d] {
			n++
		}
	}
	return sign * n
}

func TestRandomRangesAgainstBruteForce(t *testing.T) {
	rng := rand.New(rand.NewSource(7))
	base := time.Date(2019, 1, 1, 0, 0, 0, 0, time.UTC)
	day := func() time.Time { return base.AddDate(0, 0, rng.Intn(365*12)) }
	for i := 0; i < 150; i++ {
		from, to := day(), day()
		hol := map[time.Time]bool{}
		var hs []string
		for j := rng.Intn(30); j > 0; j-- {
			h := day()
			if rng.Intn(2) == 0 { // cluster some holidays near the range
				h = from.AddDate(0, 0, rng.Intn(60)-10)
			}
			hol[h] = true
			hs = append(hs, h.Format("2006-01-02"))
			if rng.Intn(5) == 0 {
				hs = append(hs, h.Format("2006-01-02")) // duplicate
			}
		}
		f, tt := from.Format("2006-01-02"), to.Format("2006-01-02")
		t.Run(f+"_"+tt, func(t *testing.T) {
			got, err := Count(f, tt, hs)
			want := bruteCount(from, to, hol)
			if err != nil || got != want {
				t.Fatalf("Count(%s, %s, %d holidays) = %d, %v; want %d", f, tt, len(hs), got, err, want)
			}
		})
	}
}
