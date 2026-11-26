package solution

import (
	"testing"
	"time"
)

type clock struct{ t time.Time }

func (c *clock) now() time.Time { return c.t }

// at sets the clock to the given offset from a fixed epoch.
func (c *clock) at(d time.Duration) {
	c.t = time.Date(2026, 1, 1, 0, 0, 0, 0, time.UTC).Add(d)
}

func newCache(capacity int, ttl time.Duration) (*Cache, *clock) {
	c := &clock{}
	c.at(0)
	return New(capacity, ttl, c.now), c
}

func expectGet(t *testing.T, c *Cache, k, want string, wantOK bool) {
	t.Helper()
	v, ok := c.Get(k)
	if v != want || ok != wantOK {
		t.Fatalf("Get(%q) = (%q, %v), want (%q, %v)", k, v, ok, want, wantOK)
	}
}

func expectLen(t *testing.T, c *Cache, want int) {
	t.Helper()
	if got := c.Len(); got != want {
		t.Fatalf("Len() = %d, want %d", got, want)
	}
}

const s = time.Second

func TestBasicGetPut(t *testing.T) {
	t.Run("miss on empty", func(t *testing.T) {
		c, _ := newCache(2, time.Minute)
		expectGet(t, c, "a", "", false)
	})
	t.Run("hit", func(t *testing.T) {
		c, _ := newCache(2, time.Minute)
		c.Put("a", "1")
		c.Put("b", "2")
		expectGet(t, c, "a", "1", true)
		expectGet(t, c, "b", "2", true)
		expectGet(t, c, "c", "", false)
	})
	t.Run("empty key and value", func(t *testing.T) {
		c, _ := newCache(2, time.Minute)
		c.Put("", "")
		expectGet(t, c, "", "", true)
	})
	t.Run("capacity one", func(t *testing.T) {
		c, _ := newCache(1, time.Minute)
		c.Put("a", "1")
		c.Put("b", "2")
		expectGet(t, c, "a", "", false)
		expectGet(t, c, "b", "2", true)
	})
}

func TestLRUEviction(t *testing.T) {
	c, _ := newCache(3, time.Minute)
	c.Put("a", "1")
	c.Put("b", "2")
	c.Put("c", "3")
	c.Put("d", "4") // evicts a
	expectGet(t, c, "a", "", false)
	c.Put("e", "5") // evicts b
	expectGet(t, c, "b", "", false)
	expectGet(t, c, "c", "3", true)
	expectGet(t, c, "d", "4", true)
	expectGet(t, c, "e", "5", true)
	expectLen(t, c, 3)
}

func TestGetRefreshesRecency(t *testing.T) {
	c, _ := newCache(3, time.Minute)
	c.Put("a", "1")
	c.Put("b", "2")
	c.Put("c", "3")
	expectGet(t, c, "a", "1", true) // order now b, c, a
	c.Put("d", "4")                 // evicts b
	expectGet(t, c, "b", "", false)
	expectGet(t, c, "c", "3", true) // order a, d, c
	c.Put("e", "5")                 // evicts a
	expectGet(t, c, "a", "", false)
	expectGet(t, c, "d", "4", true)
	expectGet(t, c, "c", "3", true)
}

func TestPutExistingKey(t *testing.T) {
	t.Run("updates value without eviction", func(t *testing.T) {
		c, _ := newCache(2, time.Minute)
		c.Put("a", "1")
		c.Put("b", "2")
		c.Put("a", "1b")
		expectLen(t, c, 2)
		expectGet(t, c, "b", "2", true)
		expectGet(t, c, "a", "1b", true)
	})
	t.Run("update makes key MRU", func(t *testing.T) {
		c, _ := newCache(2, time.Minute)
		c.Put("a", "1")
		c.Put("b", "2")
		c.Put("a", "1b") // order b, a
		c.Put("c", "3")  // evicts b
		expectGet(t, c, "b", "", false)
		expectGet(t, c, "a", "1b", true)
		expectGet(t, c, "c", "3", true)
	})
}

func TestExpiryBoundary(t *testing.T) {
	c, clk := newCache(4, 10*s)
	c.Put("a", "1")
	clk.at(10*s - time.Nanosecond)
	expectGet(t, c, "a", "1", true)
	clk.at(10 * s)
	expectGet(t, c, "a", "", false)
	clk.at(20 * s)
	expectGet(t, c, "a", "", false)
}

func TestTTLRefresh(t *testing.T) {
	t.Run("Get does not extend expiry", func(t *testing.T) {
		c, clk := newCache(2, 10*s)
		c.Put("a", "1")
		clk.at(9 * s)
		expectGet(t, c, "a", "1", true)
		clk.at(10 * s)
		expectGet(t, c, "a", "", false)
	})
	t.Run("Put resets expiry", func(t *testing.T) {
		c, clk := newCache(2, 10*s)
		c.Put("a", "1")
		clk.at(8 * s)
		c.Put("a", "2")
		clk.at(15 * s)
		expectGet(t, c, "a", "2", true)
		clk.at(18 * s)
		expectGet(t, c, "a", "", false)
	})
	t.Run("Put over expired key inserts fresh entry", func(t *testing.T) {
		c, clk := newCache(2, 10*s)
		c.Put("a", "1")
		clk.at(5 * s)
		c.Put("b", "2")
		clk.at(10 * s) // a expired, b live until 15s
		c.Put("a", "3")
		expectGet(t, c, "b", "2", true)
		expectGet(t, c, "a", "3", true)
		clk.at(19 * s) // b expired, a live until 20s
		expectGet(t, c, "a", "3", true)
		expectLen(t, c, 1)
	})
}

func TestExpiredDroppedBeforeEviction(t *testing.T) {
	t.Run("expired MRU entry is dropped instead of live LRU", func(t *testing.T) {
		c, clk := newCache(3, 10*s)
		c.Put("x", "x") // expires at 10s
		clk.at(5 * s)
		c.Put("a", "1") // expires at 15s
		c.Put("b", "2")
		clk.at(6 * s)
		expectGet(t, c, "x", "x", true) // order a, b, x
		clk.at(11 * s)                  // x expired
		c.Put("d", "4")
		expectGet(t, c, "a", "1", true)
		expectGet(t, c, "b", "2", true)
		expectGet(t, c, "d", "4", true)
	})
	t.Run("all expired entries are dropped", func(t *testing.T) {
		c, clk := newCache(3, 10*s)
		c.Put("x", "x")
		c.Put("y", "y")
		clk.at(5 * s)
		c.Put("a", "1")
		clk.at(6 * s)
		expectGet(t, c, "y", "y", true)
		expectGet(t, c, "x", "x", true) // order a, y, x
		clk.at(10 * s)                  // x, y expired
		c.Put("d", "4")
		c.Put("e", "5")
		expectGet(t, c, "a", "1", true)
		expectGet(t, c, "d", "4", true)
		expectGet(t, c, "e", "5", true)
	})
	t.Run("live LRU evicted when no entry expired", func(t *testing.T) {
		c, clk := newCache(2, 10*s)
		c.Put("a", "1")
		clk.at(1 * s)
		c.Put("b", "2")
		clk.at(9 * s)
		c.Put("c", "3") // nothing expired yet: evict a
		expectGet(t, c, "a", "", false)
		expectGet(t, c, "b", "2", true)
		expectGet(t, c, "c", "3", true)
	})
}

func TestLen(t *testing.T) {
	c, clk := newCache(5, 10*s)
	expectLen(t, c, 0)
	c.Put("a", "1")
	clk.at(4 * s)
	c.Put("b", "2")
	c.Put("c", "3")
	expectLen(t, c, 3)
	clk.at(10 * s) // a expired
	expectLen(t, c, 2)
	clk.at(14 * s) // b, c expired
	expectLen(t, c, 0)
	c.Put("d", "4")
	expectLen(t, c, 1)
	c.Put("d", "5")
	expectLen(t, c, 1)
}
