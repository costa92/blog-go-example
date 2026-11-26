package solution

import (
	"math"
	"sync"
	"time"
)

type Limiter struct {
	mu        sync.Mutex
	rate      float64
	burst     float64
	tokens    float64
	watermark time.Time
	now       func() time.Time
}

func New(rate float64, burst int, now func() time.Time) *Limiter {
	return &Limiter{rate: rate, burst: float64(burst), tokens: float64(burst), watermark: now(), now: now}
}

// refill must be called with l.mu held.
func (l *Limiter) refill() {
	t := l.now()
	if !t.After(l.watermark) {
		return
	}
	l.tokens = math.Min(l.burst, l.tokens+l.rate*t.Sub(l.watermark).Seconds())
	l.watermark = t
}

func (l *Limiter) Allow() bool { return l.AllowN(1) }

func (l *Limiter) AllowN(n int) bool {
	l.mu.Lock()
	defer l.mu.Unlock()
	l.refill()
	if float64(n) > l.burst || l.tokens < float64(n) {
		return false
	}
	l.tokens -= float64(n)
	return true
}

func (l *Limiter) Delay(n int) time.Duration {
	l.mu.Lock()
	defer l.mu.Unlock()
	l.refill()
	if float64(n) > l.burst {
		return -1
	}
	if l.tokens >= float64(n) {
		return 0
	}
	return time.Duration(math.Ceil((float64(n) - l.tokens) / l.rate * 1e9))
}
