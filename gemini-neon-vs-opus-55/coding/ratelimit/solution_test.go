package solution

import (
	"sync"
	"sync/atomic"
	"testing"
	"time"
)

var epoch = time.Date(2026, 1, 1, 0, 0, 0, 0, time.UTC)

type fakeClock struct{ ns atomic.Int64 }

func (c *fakeClock) now() time.Time          { return epoch.Add(time.Duration(c.ns.Load())) }
func (c *fakeClock) set(d time.Duration)     { c.ns.Store(int64(d)) }
func (c *fakeClock) advance(d time.Duration) { c.ns.Add(int64(d)) }

func newLimiter(rate float64, burst int) (*Limiter, *fakeClock) {
	c := &fakeClock{}
	return New(rate, burst, c.now), c
}

func expectAllowN(t *testing.T, l *Limiter, n int, want bool) {
	t.Helper()
	if got := l.AllowN(n); got != want {
		t.Fatalf("AllowN(%d) = %v, want %v", n, got, want)
	}
}

func drain(t *testing.T, l *Limiter, burst int) {
	t.Helper()
	expectAllowN(t, l, burst, true)
	expectAllowN(t, l, 1, false)
}

func TestStartsFull(t *testing.T) {
	for _, burst := range []int{1, 3, 10} {
		t.Run("Allow", func(t *testing.T) {
			l, _ := newLimiter(1, burst)
			for i := 0; i < burst; i++ {
				if !l.Allow() {
					t.Fatalf("burst=%d: Allow #%d = false, want true", burst, i+1)
				}
			}
			if l.Allow() {
				t.Fatalf("burst=%d: Allow beyond burst = true, want false", burst)
			}
		})
		t.Run("AllowN", func(t *testing.T) {
			l, _ := newLimiter(1, burst)
			expectAllowN(t, l, burst, true)
			expectAllowN(t, l, 1, false)
		})
	}
}

func TestRefillAndCap(t *testing.T) {
	t.Run("one token after quarter second at rate 4", func(t *testing.T) {
		l, c := newLimiter(4, 4)
		drain(t, l, 4)
		c.advance(250 * time.Millisecond)
		expectAllowN(t, l, 1, true)
		expectAllowN(t, l, 1, false)
	})
	t.Run("capped at burst", func(t *testing.T) {
		l, c := newLimiter(4, 4)
		drain(t, l, 4)
		c.advance(10 * time.Second)
		expectAllowN(t, l, 4, true)
		expectAllowN(t, l, 1, false)
	})
	t.Run("cap applies when full from start", func(t *testing.T) {
		l, c := newLimiter(100, 2)
		c.advance(time.Hour)
		expectAllowN(t, l, 2, true)
		expectAllowN(t, l, 1, false)
	})
	t.Run("slow rate", func(t *testing.T) {
		l, c := newLimiter(0.5, 1)
		drain(t, l, 1)
		c.advance(1500 * time.Millisecond)
		expectAllowN(t, l, 1, false)
		c.advance(500 * time.Millisecond)
		expectAllowN(t, l, 1, true)
	})
}

func TestFractionalAccumulation(t *testing.T) {
	l, c := newLimiter(4, 2)
	drain(t, l, 2)
	for i := 0; i < 3; i++ {
		c.advance(62500 * time.Microsecond)
		expectAllowN(t, l, 1, false)
	}
	c.advance(62500 * time.Microsecond)
	expectAllowN(t, l, 1, true)
	expectAllowN(t, l, 1, false)
}

func TestAllowNOverBurst(t *testing.T) {
	cases := []struct{ burst, n int }{{1, 2}, {5, 6}, {5, 100}}
	for _, c := range cases {
		t.Run("", func(t *testing.T) {
			l, _ := newLimiter(1, c.burst)
			expectAllowN(t, l, c.n, false)
			expectAllowN(t, l, c.burst, true) // nothing was consumed
		})
	}
}

func TestFailedAllowConsumesNothing(t *testing.T) {
	t.Run("partial", func(t *testing.T) {
		l, _ := newLimiter(1, 5)
		expectAllowN(t, l, 3, true)
		expectAllowN(t, l, 3, false)
		expectAllowN(t, l, 2, true)
		expectAllowN(t, l, 1, false)
	})
	t.Run("after refill", func(t *testing.T) {
		l, c := newLimiter(4, 4)
		drain(t, l, 4)
		c.advance(500 * time.Millisecond) // 2 tokens
		expectAllowN(t, l, 3, false)
		expectAllowN(t, l, 2, true)
	})
}

func expectDelay(t *testing.T, l *Limiter, n int, want time.Duration) {
	t.Helper()
	got := l.Delay(n)
	diff := got - want
	if diff < 0 {
		diff = -diff
	}
	if want == -1 && got != -1 || diff > time.Microsecond {
		t.Fatalf("Delay(%d) = %v, want %v", n, got, want)
	}
}

func TestDelay(t *testing.T) {
	t.Run("available now", func(t *testing.T) {
		l, _ := newLimiter(2, 5)
		expectDelay(t, l, 5, 0)
		expectDelay(t, l, 1, 0)
	})
	t.Run("over burst", func(t *testing.T) {
		l, _ := newLimiter(2, 5)
		expectDelay(t, l, 6, -1)
		drain(t, l, 5)
		expectDelay(t, l, 6, -1)
	})
	t.Run("empty bucket", func(t *testing.T) {
		l, c := newLimiter(2, 5)
		drain(t, l, 5)
		expectDelay(t, l, 1, 500*time.Millisecond)
		expectDelay(t, l, 5, 2500*time.Millisecond)
		c.advance(250 * time.Millisecond)
		expectDelay(t, l, 1, 250*time.Millisecond)
		expectDelay(t, l, 3, 1250*time.Millisecond)
	})
	t.Run("fractional tokens", func(t *testing.T) {
		l, c := newLimiter(4, 4)
		drain(t, l, 4)
		c.advance(125 * time.Millisecond) // 0.5 tokens
		expectDelay(t, l, 1, 125*time.Millisecond)
		expectDelay(t, l, 2, 375*time.Millisecond)
	})
	t.Run("non-terminating rate", func(t *testing.T) {
		l, _ := newLimiter(3, 1)
		drain(t, l, 1)
		expectDelay(t, l, 1, 333333334*time.Nanosecond)
	})
	t.Run("does not consume", func(t *testing.T) {
		l, c := newLimiter(2, 5)
		expectDelay(t, l, 5, 0)
		expectAllowN(t, l, 5, true)
		expectDelay(t, l, 1, 500*time.Millisecond)
		expectDelay(t, l, 1, 500*time.Millisecond)
		c.advance(500 * time.Millisecond)
		expectDelay(t, l, 1, 0)
		expectAllowN(t, l, 1, true)
	})
}

func TestClockBackwards(t *testing.T) {
	t.Run("no tokens lost", func(t *testing.T) {
		l, c := newLimiter(4, 4)
		expectAllowN(t, l, 2, true)
		c.set(-10 * time.Second)
		expectAllowN(t, l, 2, true)
		expectAllowN(t, l, 1, false)
	})
	t.Run("refill resumes past watermark only", func(t *testing.T) {
		l, c := newLimiter(4, 4)
		drain(t, l, 4)
		c.set(-10 * time.Second)
		expectAllowN(t, l, 1, false)
		c.set(250 * time.Millisecond)
		expectAllowN(t, l, 2, false)
		expectAllowN(t, l, 1, true)
		expectAllowN(t, l, 1, false)
	})
	t.Run("watermark is latest time seen", func(t *testing.T) {
		l, c := newLimiter(4, 4)
		c.set(time.Second)
		drain(t, l, 4)
		c.set(500 * time.Millisecond)
		expectAllowN(t, l, 1, false)
		c.set(1250 * time.Millisecond)
		expectAllowN(t, l, 2, false)
		expectAllowN(t, l, 1, true)
	})
}

func TestConcurrentUse(t *testing.T) {
	t.Run("stopped clock", func(t *testing.T) {
		l, _ := newLimiter(1, 100)
		var ok atomic.Int64
		var wg sync.WaitGroup
		start := make(chan struct{})
		for g := 0; g < 50; g++ {
			wg.Add(1)
			go func() {
				defer wg.Done()
				<-start
				for i := 0; i < 20; i++ {
					if l.Allow() {
						ok.Add(1)
					}
					_ = l.Delay(1)
				}
			}()
		}
		close(start)
		wg.Wait()
		if ok.Load() != 100 {
			t.Fatalf("successful Allow calls = %d, want 100", ok.Load())
		}
	})
	t.Run("moving clock", func(t *testing.T) {
		// rate 1000/s, clock advances 1ms per tick for 200 ticks: at most burst + 200 tokens.
		l, c := newLimiter(1000, 10)
		var ok atomic.Int64
		var wg sync.WaitGroup
		for g := 0; g < 8; g++ {
			wg.Add(1)
			go func() {
				defer wg.Done()
				for i := 0; i < 500; i++ {
					if l.Allow() {
						ok.Add(1)
					}
				}
			}()
		}
		for i := 0; i < 200; i++ {
			c.advance(time.Millisecond)
		}
		wg.Wait()
		c.advance(time.Hour)
		remaining := 0
		for l.Allow() {
			remaining++
		}
		if ok.Load() > 210 {
			t.Fatalf("successful Allow calls = %d, want <= 210", ok.Load())
		}
		if remaining != 10 {
			t.Fatalf("after long idle, %d tokens available, want 10", remaining)
		}
	})
}
