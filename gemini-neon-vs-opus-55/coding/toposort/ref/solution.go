package solution

import (
	"container/heap"
	"slices"
	"strings"
)

type CycleError struct {
	Cycle []string
}

func (e *CycleError) Error() string {
	return "dependency cycle: " + strings.Join(e.Cycle, " -> ")
}

type strHeap []string

func (h strHeap) Len() int           { return len(h) }
func (h strHeap) Less(i, j int) bool { return h[i] < h[j] }
func (h strHeap) Swap(i, j int)      { h[i], h[j] = h[j], h[i] }
func (h *strHeap) Push(x any)        { *h = append(*h, x.(string)) }
func (h *strHeap) Pop() any {
	old := *h
	x := old[len(old)-1]
	*h = old[:len(old)-1]
	return x
}

func Order(deps map[string][]string) ([]string, error) {
	// adj[a] = sorted distinct dependencies of a; users[d] = nodes depending on d.
	adj := map[string][]string{}
	for a, ds := range deps {
		if _, ok := adj[a]; !ok {
			adj[a] = nil
		}
		for _, d := range ds {
			if _, ok := adj[d]; !ok {
				adj[d] = nil
			}
		}
	}
	for a, ds := range deps {
		u := slices.Clone(ds)
		slices.Sort(u)
		adj[a] = slices.Compact(u)
	}
	users := map[string][]string{}
	indeg := map[string]int{}
	for a, ds := range adj {
		indeg[a] = len(ds)
		for _, d := range ds {
			users[d] = append(users[d], a)
		}
	}
	h := &strHeap{}
	for n, k := range indeg {
		if k == 0 {
			heap.Push(h, n)
		}
	}
	order := []string{}
	for h.Len() > 0 {
		n := heap.Pop(h).(string)
		order = append(order, n)
		for _, u := range users[n] {
			indeg[u]--
			if indeg[u] == 0 {
				heap.Push(h, u)
			}
		}
	}
	if len(order) == len(adj) {
		return order, nil
	}
	return nil, &CycleError{Cycle: canonicalCycle(adj)}
}

func reaches(adj map[string][]string, from, target string) bool {
	seen := map[string]bool{}
	stack := slices.Clone(adj[from])
	for len(stack) > 0 {
		n := stack[len(stack)-1]
		stack = stack[:len(stack)-1]
		if n == target {
			return true
		}
		if !seen[n] {
			seen[n] = true
			stack = append(stack, adj[n]...)
		}
	}
	return false
}

func canonicalCycle(adj map[string][]string) []string {
	nodes := make([]string, 0, len(adj))
	for n := range adj {
		nodes = append(nodes, n)
	}
	slices.Sort(nodes)
	var n0 string
	for _, n := range nodes {
		if reaches(adj, n, n) {
			n0 = n
			break
		}
	}
	path := []string{n0}
	onPath := map[string]bool{n0: true}
	var dfs func(cur string) bool
	dfs = func(cur string) bool {
		if slices.Contains(adj[cur], n0) {
			return true // closing now gives a prefix, which is smallest
		}
		for _, next := range adj[cur] {
			if onPath[next] {
				continue
			}
			path = append(path, next)
			onPath[next] = true
			if dfs(next) {
				return true
			}
			path = path[:len(path)-1]
			delete(onPath, next)
		}
		return false
	}
	dfs(n0)
	return path
}
