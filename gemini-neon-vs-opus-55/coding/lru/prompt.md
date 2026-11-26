# Task: LRU cache with per-entry TTL and an injected clock

Write a Go file in `package solution` (Go 1.27, standard library only) that exports exactly this API:

```go
type Cache struct {
	// unexported fields of your choice
}

func New(capacity int, ttl time.Duration, now func() time.Time) *Cache
func (c *Cache) Get(k string) (string, bool)
func (c *Cache) Put(k, v string)
func (c *Cache) Len() int
```

Callers guarantee `capacity >= 1`, `ttl > 0`, and `now != nil`. The cache must never read the real clock; it only uses `now`. The cache does not need to be safe for concurrent use.

## Expiry

- Every stored entry has an **expiry time** = the time `now()` returned when the entry was inserted or last updated by `Put`, plus `ttl`.
- An entry is **expired** when `now() >= expiry` (an entry inserted at time T with ttl 10s is live at T+9.999s and expired at exactly T+10s).
- An expired entry behaves exactly as if the key were absent, for every method.

## Recency

The cache keeps its entries in recency order, from least recently used (LRU) to most recently used (MRU).

## Methods

- `Get(k)`: if `k` has a live entry, return `(value, true)` and make it the MRU entry. `Get` does **not** change the entry's expiry time. Otherwise return `("", false)`.
- `Put(k, v)`:
  - If `k` has a live entry: replace its value with `v`, reset its expiry to `now() + ttl`, and make it the MRU entry. Nothing is evicted.
  - Otherwise (`k` is absent or its entry is expired; an expired entry for `k` is discarded first): insert a new entry for `k` as the MRU entry. Before inserting, if the number of stored entries (live or expired, not counting a discarded expired entry for `k`) equals `capacity`, first remove **all** expired entries; if the number of stored entries still equals `capacity`, remove the LRU entry.
- `Len()`: return the number of live (non-expired) entries at the current time.

So a cache never holds more than `capacity` entries, and a live entry is evicted only when the cache is full of live entries.

Return the complete file in a single ```go code block and nothing else.
