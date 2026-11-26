# Task: Integer interval set

Write a Go file in `package solution` (Go 1.27, standard library only) that exports exactly this API:

```go
type Set struct {
	// unexported fields of your choice
}

func (s *Set) Add(lo, hi int)
func (s *Set) Remove(lo, hi int)
func (s *Set) Contains(x int) bool
func (s *Set) Intervals() [][2]int
```

A `Set` represents a set of integers. The **zero value** `Set{}` (and `var s Set`) is an empty set ready to use, with no constructor.

## Semantics

- All ranges are **half-open**: `[lo, hi)` contains every integer `x` with `lo <= x < hi`. Any `int` values may be used, including negative ones (tests stay well inside ±1,000,000,000, so `hi - lo` never overflows).
- `Add(lo, hi)`: add every integer in `[lo, hi)` to the set. If `lo >= hi` the range is empty and the call does nothing.
- `Remove(lo, hi)`: remove every integer in `[lo, hi)` from the set (removing integers not in the set is fine). If `lo >= hi` the call does nothing. Removing from the middle of a stored interval splits it in two.
- `Contains(x)`: reports whether `x` is in the set.
- `Intervals()`: returns the set as the unique canonical list of half-open intervals `[2]int{lo, hi}` with `lo < hi`, sorted by `lo` ascending, pairwise disjoint, and **maximally merged**: two intervals that overlap or touch are always combined, so `Add(1,3)` followed by `Add(3,5)` yields `[[1 5]]`. Consequently, for consecutive intervals `a`, `b` in the result, `a[1] < b[0]` strictly. For an empty set it returns a slice of length 0 (nil or empty). The returned slice must be a fresh copy: modifying it must not affect the set, and later changes to the set must not affect a previously returned slice.

A `Set` is not used concurrently.

Return the complete file in a single ```go code block and nothing else.
