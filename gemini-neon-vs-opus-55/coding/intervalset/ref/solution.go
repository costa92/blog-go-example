package solution

import "slices"

type Set struct {
	iv [][2]int // sorted, disjoint, non-touching
}

func (s *Set) Add(lo, hi int) {
	if lo >= hi {
		return
	}
	var out [][2]int
	i := 0
	for ; i < len(s.iv) && s.iv[i][1] < lo; i++ {
		out = append(out, s.iv[i])
	}
	for ; i < len(s.iv) && s.iv[i][0] <= hi; i++ {
		lo = min(lo, s.iv[i][0])
		hi = max(hi, s.iv[i][1])
	}
	out = append(out, [2]int{lo, hi})
	s.iv = append(out, s.iv[i:]...)
}

func (s *Set) Remove(lo, hi int) {
	if lo >= hi {
		return
	}
	var out [][2]int
	for _, r := range s.iv {
		if r[1] <= lo || r[0] >= hi {
			out = append(out, r)
			continue
		}
		if r[0] < lo {
			out = append(out, [2]int{r[0], lo})
		}
		if r[1] > hi {
			out = append(out, [2]int{hi, r[1]})
		}
	}
	s.iv = out
}

func (s *Set) Contains(x int) bool {
	i, _ := slices.BinarySearchFunc(s.iv, x, func(r [2]int, x int) int {
		if r[1] <= x {
			return -1
		}
		if r[0] > x {
			return 1
		}
		return 0
	})
	return i < len(s.iv) && s.iv[i][0] <= x && x < s.iv[i][1]
}

func (s *Set) Intervals() [][2]int {
	return slices.Clone(s.iv)
}
