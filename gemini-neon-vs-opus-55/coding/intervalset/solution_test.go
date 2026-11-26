package solution

import (
	"fmt"
	"math/rand"
	"reflect"
	"testing"
)

type op struct {
	add    bool
	lo, hi int
}

func apply(s *Set, ops []op) {
	for _, o := range ops {
		if o.add {
			s.Add(o.lo, o.hi)
		} else {
			s.Remove(o.lo, o.hi)
		}
	}
}

func A(lo, hi int) op { return op{true, lo, hi} }
func R(lo, hi int) op { return op{false, lo, hi} }

func expectIntervals(t *testing.T, s *Set, want [][2]int) {
	t.Helper()
	got := s.Intervals()
	if len(got) == 0 && len(want) == 0 {
		return
	}
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("Intervals() = %v, want %v", got, want)
	}
}

type seqCase struct {
	name string
	ops  []op
	want [][2]int
}

func runSeq(t *testing.T, cases []seqCase) {
	t.Helper()
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			var s Set
			apply(&s, c.ops)
			expectIntervals(t, &s, c.want)
		})
	}
}

func TestZeroValue(t *testing.T) {
	var s Set
	expectIntervals(t, &s, nil)
	for _, x := range []int{-1, 0, 1, 100} {
		if s.Contains(x) {
			t.Fatalf("empty set contains %d", x)
		}
	}
	s.Remove(0, 10)
	expectIntervals(t, &s, nil)
	s2 := Set{}
	s2.Add(1, 2)
	expectIntervals(t, &s2, [][2]int{{1, 2}})
}

func TestAddMerging(t *testing.T) {
	runSeq(t, []seqCase{
		{"single", []op{A(1, 3)}, [][2]int{{1, 3}}},
		{"adjacent merge", []op{A(1, 3), A(3, 5)}, [][2]int{{1, 5}}},
		{"adjacent merge reversed", []op{A(3, 5), A(1, 3)}, [][2]int{{1, 5}}},
		{"overlap", []op{A(1, 4), A(2, 6)}, [][2]int{{1, 6}}},
		{"gap of one kept", []op{A(1, 3), A(4, 6)}, [][2]int{{1, 3}, {4, 6}}},
		{"sorted output", []op{A(10, 12), A(1, 2), A(5, 6)}, [][2]int{{1, 2}, {5, 6}, {10, 12}}},
		{"bridge several", []op{A(1, 2), A(4, 5), A(7, 8), A(10, 11), A(2, 10)}, [][2]int{{1, 11}}},
		{"contained", []op{A(0, 10), A(3, 4)}, [][2]int{{0, 10}}},
		{"cover", []op{A(3, 4), A(5, 6), A(0, 10)}, [][2]int{{0, 10}}},
		{"negative", []op{A(-5, -2), A(-2, 0), A(-10, -7)}, [][2]int{{-10, -7}, {-5, 0}}},
		{"duplicate", []op{A(1, 3), A(1, 3)}, [][2]int{{1, 3}}},
	})
}

func TestRemoveSplitting(t *testing.T) {
	runSeq(t, []seqCase{
		{"split middle", []op{A(0, 10), R(3, 5)}, [][2]int{{0, 3}, {5, 10}}},
		{"trim left", []op{A(0, 10), R(-5, 2)}, [][2]int{{2, 10}}},
		{"trim right", []op{A(0, 10), R(8, 20)}, [][2]int{{0, 8}}},
		{"remove exact", []op{A(0, 10), R(0, 10)}, nil},
		{"remove across", []op{A(0, 3), A(5, 8), A(10, 12), R(2, 11)}, [][2]int{{0, 2}, {11, 12}}},
		{"remove disjoint", []op{A(0, 3), R(3, 5), R(-2, 0)}, [][2]int{{0, 3}}},
		{"single point", []op{A(0, 3), R(1, 2)}, [][2]int{{0, 1}, {2, 3}}},
		{"re-add after remove", []op{A(0, 10), R(3, 5), A(3, 5)}, [][2]int{{0, 10}}},
		{"remove all of many", []op{A(1, 2), A(3, 4), A(5, 6), R(0, 100)}, nil},
	})
}

func TestEmptyAndInvertedIgnored(t *testing.T) {
	runSeq(t, []seqCase{
		{"empty add", []op{A(5, 5)}, nil},
		{"inverted add", []op{A(5, 2)}, nil},
		{"empty remove", []op{A(0, 10), R(5, 5)}, [][2]int{{0, 10}}},
		{"inverted remove", []op{A(0, 10), R(8, 2)}, [][2]int{{0, 10}}},
		{"empty add between adjacent", []op{A(0, 3), A(4, 6), A(3, 3)}, [][2]int{{0, 3}, {4, 6}}},
	})
}

func TestContains(t *testing.T) {
	var s Set
	apply(&s, []op{A(0, 10), R(3, 5), A(-4, -2), A(20, 21)})
	cases := map[int]bool{
		-5: false, -4: true, -3: true, -2: false, -1: false, 0: true, 2: true, 3: false,
		4: false, 5: true, 9: true, 10: false, 19: false, 20: true, 21: false,
	}
	for x, want := range cases {
		t.Run(fmt.Sprint(x), func(t *testing.T) {
			if got := s.Contains(x); got != want {
				t.Fatalf("Contains(%d) = %v, want %v", x, got, want)
			}
		})
	}
}

func TestIntervalsIsCopy(t *testing.T) {
	t.Run("caller mutation", func(t *testing.T) {
		var s Set
		s.Add(0, 5)
		s.Add(10, 15)
		got := s.Intervals()
		got[0][1] = 100
		got[1] = [2]int{-1, -1}
		expectIntervals(t, &s, [][2]int{{0, 5}, {10, 15}})
	})
	t.Run("later set changes", func(t *testing.T) {
		var s Set
		s.Add(0, 5)
		s.Add(10, 15)
		snap := s.Intervals()
		s.Remove(2, 3)
		s.Add(5, 10)
		s.Add(20, 30)
		if !reflect.DeepEqual(snap, [][2]int{{0, 5}, {10, 15}}) {
			t.Fatalf("earlier Intervals() result changed to %v", snap)
		}
	})
}

func bruteIntervals(b []bool, off int) [][2]int {
	var out [][2]int
	for i := 0; i < len(b); {
		if !b[i] {
			i++
			continue
		}
		j := i
		for j < len(b) && b[j] {
			j++
		}
		out = append(out, [2]int{i - off, j - off})
		i = j
	}
	return out
}

func TestRandomizedAgainstBruteForce(t *testing.T) {
	const off, size = 10, 240 // values in [-10, 230)
	for seed := int64(1); seed <= 5; seed++ {
		t.Run(fmt.Sprint(seed), func(t *testing.T) {
			rng := rand.New(rand.NewSource(seed))
			var s Set
			brute := make([]bool, size)
			for i := 0; i < 2000; i++ {
				lo := rng.Intn(200)
				hi := lo + rng.Intn(25) - 3 // sometimes empty or inverted
				add := rng.Intn(3) != 0
				if add {
					s.Add(lo, hi)
				} else {
					s.Remove(lo, hi)
				}
				for x := lo; x < hi; x++ {
					brute[x+off] = add
				}
				x := rng.Intn(size) - off
				if s.Contains(x) != brute[x+off] {
					t.Fatalf("op %d: Contains(%d) = %v, want %v", i, x, s.Contains(x), brute[x+off])
				}
				if i%20 == 0 {
					want := bruteIntervals(brute, off)
					if got := s.Intervals(); !(len(got) == 0 && len(want) == 0) && !reflect.DeepEqual(got, want) {
						t.Fatalf("op %d: Intervals() = %v, want %v", i, got, want)
					}
				}
			}
		})
	}
}
