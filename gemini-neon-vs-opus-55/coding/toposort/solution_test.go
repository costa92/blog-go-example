package solution

import (
	"errors"
	"fmt"
	"math/rand"
	"reflect"
	"slices"
	"testing"
)

type orderCase struct {
	name string
	deps map[string][]string
	want []string
}

func runOrder(t *testing.T, cases []orderCase) {
	t.Helper()
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			got, err := Order(c.deps)
			if err != nil {
				t.Fatalf("Order error: %v", err)
			}
			if len(got) == 0 && len(c.want) == 0 {
				return
			}
			if !reflect.DeepEqual(got, c.want) {
				t.Fatalf("Order(%v) = %q, want %q", c.deps, got, c.want)
			}
		})
	}
}

type cycleCase struct {
	name string
	deps map[string][]string
	want []string
}

func runCycle(t *testing.T, cases []cycleCase) {
	t.Helper()
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			_, err := Order(c.deps)
			var ce *CycleError
			if !errors.As(err, &ce) {
				t.Fatalf("Order(%v) error = %v, want *CycleError", c.deps, err)
			}
			if !reflect.DeepEqual(ce.Cycle, c.want) {
				t.Fatalf("Order(%v) cycle = %q, want %q", c.deps, ce.Cycle, c.want)
			}
		})
	}
}

func TestBasicOrders(t *testing.T) {
	runOrder(t, []orderCase{
		{"chain", map[string][]string{"c": {"b"}, "b": {"a"}, "a": nil}, []string{"a", "b", "c"}},
		{"diamond", map[string][]string{"d": {"b", "c"}, "b": {"a"}, "c": {"a"}}, []string{"a", "b", "c", "d"}},
		{"single", map[string][]string{"x": {}}, []string{"x"}},
		{"reverse names", map[string][]string{"a": {"b"}, "b": {"c"}}, []string{"c", "b", "a"}},
	})
}

func TestLexicographicKahn(t *testing.T) {
	runOrder(t, []orderCase{
		{"spec example", map[string][]string{"b": {"a"}, "c": {"a"}, "d": {}}, []string{"a", "b", "c", "d"}},
		{"dependency-only node", map[string][]string{"a": {"z"}, "b": {}}, []string{"b", "z", "a"}},
		{"newly ready beats older", map[string][]string{"b": {"a"}, "c": {}, "a": {}}, []string{"a", "b", "c"}},
		{"not layer by layer", map[string][]string{"c": {"a"}, "b": {"x"}, "x": {}, "a": {}}, []string{"a", "c", "x", "b"}},
		{"byte order", map[string][]string{"B": {}, "a": {}, "_": {}, "": {}}, []string{"", "B", "_", "a"}},
		{"wide", map[string][]string{"m": {"k"}, "k": {}, "z": {}, "b": {"z"}, "a": {"m"}},
			[]string{"k", "m", "a", "z", "b"}},
	})
}

func TestImplicitNodesAndDuplicates(t *testing.T) {
	runOrder(t, []orderCase{
		{"implicit", map[string][]string{"app": {"lib", "log"}}, []string{"lib", "log", "app"}},
		{"duplicates", map[string][]string{"b": {"a", "a", "a"}, "c": {"b", "a", "b"}}, []string{"a", "b", "c"}},
		{"implicit chain", map[string][]string{"c": {"b"}, "b": {"a"}}, []string{"a", "b", "c"}},
		{"empty list key", map[string][]string{"q": nil, "p": {"q", "q"}}, []string{"q", "p"}},
	})
}

func TestEmptyInput(t *testing.T) {
	for _, deps := range []map[string][]string{nil, {}} {
		got, err := Order(deps)
		if err != nil || len(got) != 0 {
			t.Fatalf("Order(%v) = %q, %v; want empty, nil", deps, got, err)
		}
	}
}

func TestCycleErrorShape(t *testing.T) {
	cases := []map[string][]string{
		{"a": {"b"}, "b": {"a"}},
		{"a": {"a"}},
		{"a": {}, "b": {"a", "c"}, "c": {"b"}},
	}
	for i, deps := range cases {
		t.Run(fmt.Sprint(i), func(t *testing.T) {
			got, err := Order(deps)
			if got != nil {
				t.Errorf("order = %q, want nil on cycle", got)
			}
			var ce *CycleError
			if !errors.As(err, &ce) || ce == nil {
				t.Fatalf("error %v is not *CycleError", err)
			}
			if err.Error() == "" {
				t.Errorf("Error() returned empty string")
			}
		})
	}
}

func TestSelfLoop(t *testing.T) {
	runCycle(t, []cycleCase{
		{"lone", map[string][]string{"a": {"a"}}, []string{"a"}},
		{"self loop beats longer cycle", map[string][]string{"a": {"b", "a"}, "b": {"a"}}, []string{"a"}},
		{"self loop on later node", map[string][]string{"a": {}, "m": {"m"}, "z": {"m"}}, []string{"m"}},
	})
}

func TestCycleStartNode(t *testing.T) {
	runCycle(t, []cycleCase{
		{"two cycle", map[string][]string{"a": {"b"}, "b": {"a"}}, []string{"a", "b"}},
		{"start at smallest", map[string][]string{"c": {"a"}, "a": {"b"}, "b": {"c"}}, []string{"a", "b", "c"}},
		{"smallest node not on cycle", map[string][]string{"x": {"y"}, "y": {"x"}, "a": {"x"}}, []string{"x", "y"}},
		{"two disjoint cycles", map[string][]string{"p": {"q"}, "q": {"p"}, "d": {"e"}, "e": {"f"}, "f": {"d"}}, []string{"d", "e", "f"}},
		{"cycle reachable from acyclic part", map[string][]string{"a": {"m"}, "m": {"n"}, "n": {"o"}, "o": {"m"}}, []string{"m", "n", "o"}},
	})
}

func TestCycleLexSmallest(t *testing.T) {
	runCycle(t, []cycleCase{
		{"lexicographic beats short", map[string][]string{"a": {"c", "b"}, "b": {"d"}, "c": {"a"}, "d": {"a"}}, []string{"a", "b", "d"}},
		{"prefix is smaller", map[string][]string{"a": {"b"}, "b": {"c", "a"}, "c": {"a"}}, []string{"a", "b"}},
		{"dead end branch", map[string][]string{"a": {"b", "c"}, "b": {"x"}, "c": {"a"}, "x": {}}, []string{"a", "c"}},
		{"no repeated nodes", map[string][]string{"a": {"b"}, "b": {"c"}, "c": {"b", "d"}, "d": {"a"}}, []string{"a", "b", "c", "d"}},
		{"inner cycle not through n0", map[string][]string{"a": {"b"}, "b": {"c"}, "c": {"b", "z"}, "z": {"a"}}, []string{"a", "b", "c", "z"}},
	})
}

// ---- brute force oracle ----

func bfNodes(deps map[string][]string) []string {
	set := map[string]bool{}
	for a, ds := range deps {
		set[a] = true
		for _, d := range ds {
			set[d] = true
		}
	}
	var out []string
	for n := range set {
		out = append(out, n)
	}
	slices.Sort(out)
	return out
}

func bfOrder(deps map[string][]string) []string {
	nodes := bfNodes(deps)
	done := map[string]bool{}
	var out []string
	for len(out) < len(nodes) {
		picked := false
		for _, n := range nodes { // sorted, so first ready node is the smallest
			if done[n] {
				continue
			}
			ready := true
			for _, d := range deps[n] {
				if !done[d] {
					ready = false
				}
			}
			if ready {
				done[n] = true
				out = append(out, n)
				picked = true
				break
			}
		}
		if !picked {
			return nil
		}
	}
	return out
}

func bfCycle(deps map[string][]string) []string {
	var cycles [][]string
	var walk func(path []string)
	walk = func(path []string) {
		last := path[len(path)-1]
		for _, d := range deps[last] {
			if d == path[0] {
				cycles = append(cycles, slices.Clone(path))
			} else if !slices.Contains(path, d) {
				walk(append(path, d))
			}
		}
	}
	for _, n := range bfNodes(deps) {
		walk([]string{n})
		if len(cycles) > 0 {
			slices.SortFunc(cycles, slices.Compare[[]string])
			return cycles[0]
		}
	}
	return nil
}

func TestRandomizedAgainstBruteForce(t *testing.T) {
	rng := rand.New(rand.NewSource(42))
	names := []string{"a", "b", "c", "d", "e", "f", "g"}
	for iter := 0; iter < 400; iter++ {
		deps := map[string][]string{}
		n := 2 + rng.Intn(len(names)-1)
		acyclic := iter%2 == 0
		for i := 0; i < n; i++ {
			a := names[i]
			deps[a] = nil
			for j := 0; j < n; j++ {
				if acyclic && j >= i {
					continue // only depend on earlier names: no cycles
				}
				if rng.Intn(4) == 0 {
					deps[a] = append(deps[a], names[j])
				}
			}
		}
		if acyclic { // shuffle names so the DAG is not trivially sorted
			perm := rng.Perm(n)
			shuffled := map[string][]string{}
			for a, ds := range deps {
				var nd []string
				for _, d := range ds {
					nd = append(nd, names[perm[slices.Index(names, d)]])
				}
				shuffled[names[perm[slices.Index(names, a)]]] = nd
			}
			deps = shuffled
		}
		t.Run(fmt.Sprint(iter), func(t *testing.T) {
			got, err := Order(deps)
			if want := bfOrder(deps); want != nil {
				if err != nil || !reflect.DeepEqual(got, want) {
					t.Fatalf("Order(%v) = %q, %v; want %q", deps, got, err, want)
				}
				return
			}
			want := bfCycle(deps)
			var ce *CycleError
			if !errors.As(err, &ce) || !reflect.DeepEqual(ce.Cycle, want) {
				t.Fatalf("Order(%v) error = %v; want cycle %q", deps, err, want)
			}
		})
	}
}
