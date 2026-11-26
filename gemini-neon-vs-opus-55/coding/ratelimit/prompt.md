# Task: Token-bucket rate limiter with an injected clock

Write a Go file in `package solution` (Go 1.27, standard library only) that exports exactly this API:

```go
type Limiter struct {
	// unexported fields of your choice
}

func New(rate float64, burst int, now func() time.Time) *Limiter
func (l *Limiter) Allow() bool
func (l *Limiter) AllowN(n int) bool
func (l *Limiter) Delay(n int) time.Duration
```

Callers guarantee `rate > 0`, `burst >= 1`, `n >= 1`, and `now != nil`. The limiter must never read the real clock; it only uses `now`.

## Model

- The bucket holds a real-valued (fractional) number of tokens, at most `burst`.
- `New` calls `now()` once; the bucket starts **full** (`burst` tokens) and that time becomes the initial **watermark**.
- Every call to `Allow`, `AllowN` or `Delay` first calls `now()` once and performs a **refill step**:
  - let `t = now()`. If `t` is after the watermark, add `rate * (t - watermark in seconds)` tokens (capped at `burst`) and set the watermark to `t`.
  - If `t` is equal to or **before** the watermark (the clock did not move, or moved backwards), nothing changes: no tokens are added or removed and the watermark keeps its old (later) value. Refill therefore resumes only once the clock passes the latest time ever observed. Example: watermark at T, clock goes back to T-10s, then forward to T+250ms → exactly 0.25 s worth of tokens is added.
- Refill is continuous: fractional tokens accumulate across calls (four calls 62.5 ms apart at rate 4/s add exactly 1 token in total).

## Methods

- `AllowN(n)`: after the refill step, if `n > burst` return `false`. Otherwise, if the bucket holds at least `n` tokens, remove `n` tokens and return `true`; else return `false`. A call that returns `false` removes no tokens.
- `Allow()`: same as `AllowN(1)`.
- `Delay(n)`: after the refill step, without removing tokens:
  - if `n > burst`, return `time.Duration(-1)`;
  - if the bucket holds at least `n` tokens, return `0`;
  - otherwise return the time needed to refill the missing tokens, `(n - tokens) / rate` seconds, rounded **up** to a whole nanosecond. Results within 1 microsecond of this value are accepted.

## Concurrency

All methods must be safe for concurrent use by multiple goroutines (tests run with `-race`). Under concurrency each call's refill step and consumption must be atomic: with a stopped clock and a full bucket of `burst` tokens, exactly `burst` concurrent `Allow()` calls in total succeed. The `now` function supplied by tests is itself safe for concurrent use.

Return the complete file in a single ```go code block and nothing else.
