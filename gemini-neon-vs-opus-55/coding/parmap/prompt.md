# Task: Bounded-concurrency ordered parallel map

Write a Go file in `package solution` (Go 1.27, standard library only) that exports exactly this API:

```go
var ErrBadLimit = errors.New("parmap: limit must be positive") // any message

func Map[T, R any](ctx context.Context, in []T, limit int, f func(context.Context, T) (R, error)) ([]R, error)
```

`Map` calls `f` once per element of `in` (at most once per element), running up to `limit` calls concurrently, and collects the results in input order. Tests run with `-race`.

## Rules

1. **Bad limit**: if `limit <= 0`, return `(nil, ErrBadLimit)` immediately without calling `f`. This check comes first, even when `in` is empty.
2. **Empty input**: if `len(in) == 0` (and `limit > 0`), return a **non-nil empty** slice and a nil error without calling `f`, regardless of the state of `ctx`.
3. **Concurrency bound**: at no moment may more than `limit` calls of `f` be in progress. When `limit` or more elements remain, `Map` must actually keep `limit` calls in progress (it must not, for example, run them one at a time or in fixed batches that wait for the whole batch).
4. **Start order**: calls are started in increasing index order: the call for index `i` never begins before the call for index `i-1` has begun. With `limit == 1` this means strictly one after another: index 0, then 1, then 2, ...
5. **Work context**: every call of `f` receives the same context, derived from `ctx`. It is canceled when `ctx` is canceled, when any call of `f` returns a non-nil error, and in any case before `Map` returns.
6. **Stop conditions**: once any call of `f` has returned a non-nil error, or once `ctx` is done, no new call of `f` may begin. (In particular, if `ctx` is already done when `Map` is called with non-empty `in`, `f` is never called.) Calls already in progress are not abandoned: `Map` waits for every call it started to return before it returns. `f` is never called after `Map` has returned, and no goroutine started by `Map` calls `f` afterwards.
7. **Return value**, decided after all started calls have returned:
   - If every element was processed and every call returned a nil error: return `(results, nil)`, where `results` has length `len(in)` and `results[i]` is the value `f` returned for `in[i]`.
   - Otherwise, if at least one call returned a non-nil error: return `(nil, err)` where `err` is the **first** non-nil error `Map` observed, returned as-is (not wrapped). Errors returned by other calls after that (for example `context.Canceled` from calls that noticed the cancellation) are ignored.
   - Otherwise (some elements were never started because `ctx` was done): return `(nil, ctx.Err())`.

Return the complete file in a single ```go code block and nothing else.
