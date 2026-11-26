# Task: Deterministic topological sort with canonical cycle reporting

Write a Go file in `package solution` (Go 1.27, standard library only) that exports exactly this API:

```go
type CycleError struct {
	Cycle []string
}

func (e *CycleError) Error() string

func Order(deps map[string][]string) ([]string, error)
```

## Graph

- `deps[a]` lists the nodes that must come **before** `a` in the output. Read it as directed edges `a → d` for every `d` in `deps[a]` ("`a` depends on `d`").
- The node set is every key of `deps` plus every string that appears in any `deps[a]` list (a node that appears only as a dependency is included). A key whose list is nil or empty is still a node.
- The same dependency may be listed more than once in one list; duplicates have no extra effect.
- A node may list itself (`deps["a"] = ["a"]`), which is a cycle.
- Node names are arbitrary strings (possibly empty); compare them with plain Go string comparison (`<`, byte order).

## Success: ordering

If the graph has no cycle, return `(order, nil)` where `order` contains every node exactly once and every node appears after all of its dependencies. Among all valid orders, return the one produced by Kahn's algorithm that **always picks the lexicographically smallest node among those whose dependencies have all been output**. For an empty or nil map, return an empty slice (length 0) and nil error.

Example: `{"b": {"a"}, "c": {"a"}, "d": {}}` → `["a", "b", "c", "d"]`, and `{"a": {"z"}, "b": {}}` → `["b", "z", "a"]`.

## Failure: cycles

If the graph contains at least one cycle, return `(nil, err)` where `err` is a `*CycleError` (returned directly, so `errors.As(err, &ce)` with `ce *CycleError` succeeds). Its `Cycle` field must be exactly the following canonical cycle:

1. Let `n0` be the lexicographically smallest node that lies on any cycle (a node lies on a cycle if, following edges `a → d`, there is a path of length ≥ 1 from it back to itself).
2. Consider every sequence `[n0, n1, ..., nk]` (k ≥ 0) of **distinct** nodes such that `n(i+1)` is in `deps[n(i)]` for each `i < k`, and `n0` is in `deps[nk]`. (For a self-loop on `n0`, `[n0]` is such a sequence.)
3. `Cycle` is the lexicographically smallest of these sequences, comparing element by element with string comparison; if one sequence is a proper prefix of another, the shorter one is smaller.

Examples:

- `{"a": {"a"}}` → `Cycle = ["a"]`
- `{"a": {"b"}, "b": {"a"}}` → `["a", "b"]`
- `{"a": {"c", "b"}, "b": {"d"}, "c": {"a"}, "d": {"a"}}` → candidates `[a b d]` and `[a c]`; the answer is `["a", "b", "d"]` (because `"b" < "c"`).
- `{"x": {"y"}, "y": {"x"}, "a": {"x"}}` → `"a"` is not on a cycle, so `n0 = "x"` and the answer is `["x", "y"]`.

`Error()` must return a non-empty string; its exact text is not checked.

Return the complete file in a single ```go code block and nothing else.
