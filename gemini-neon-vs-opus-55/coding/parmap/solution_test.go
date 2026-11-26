package solution

import (
	"context"
	"errors"
	"fmt"
	"runtime"
	"strconv"
	"sync"
	"sync/atomic"
	"testing"
	"time"
)

var errBoom = errors.New("boom")

func ints(n int) []int {
	out := make([]int, n)
	for i := range out {
		out[i] = i
	}
	return out
}

// waitOrTimeout returns false if ch is not closed within 5s (instead of hanging the test).
func waitOrTimeout(ch <-chan struct{}) bool {
	select {
	case <-ch:
		return true
	case <-time.After(5 * time.Second):
		return false
	}
}

func TestBadLimit(t *testing.T) {
	for _, limit := range []int{0, -1, -100} {
		for _, in := range [][]int{nil, {}, {1, 2, 3}} {
			t.Run(fmt.Sprintf("limit=%d/len=%d", limit, len(in)), func(t *testing.T) {
				var calls atomic.Int64
				got, err := Map(context.Background(), in, limit, func(ctx context.Context, x int) (int, error) {
					calls.Add(1)
					return x, nil
				})
				if !errors.Is(err, ErrBadLimit) || got != nil || calls.Load() != 0 {
					t.Fatalf("got (%v, %v) with %d calls; want (nil, ErrBadLimit) and 0 calls", got, err, calls.Load())
				}
			})
		}
	}
}

func TestEmptyInput(t *testing.T) {
	canceled, cancel := context.WithCancel(context.Background())
	cancel()
	cases := []struct {
		name string
		ctx  context.Context
		in   []int
	}{
		{"nil slice", context.Background(), nil},
		{"empty slice", context.Background(), []int{}},
		{"canceled ctx", canceled, nil},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			got, err := Map(c.ctx, c.in, 2, func(ctx context.Context, x int) (string, error) {
				t.Error("f called for empty input")
				return "", nil
			})
			if err != nil || got == nil || len(got) != 0 {
				t.Fatalf("got (%#v, %v); want non-nil empty slice, nil", got, err)
			}
		})
	}
}

func TestResultsInOrder(t *testing.T) {
	for _, limit := range []int{1, 4, 100} {
		t.Run(fmt.Sprint(limit), func(t *testing.T) {
			in := ints(60)
			got, err := Map(context.Background(), in, limit, func(ctx context.Context, x int) (string, error) {
				if x%7 == 0 {
					time.Sleep(time.Duration(x%5) * time.Millisecond)
				}
				runtime.Gosched()
				return "v" + strconv.Itoa(x*2), nil
			})
			if err != nil || len(got) != len(in) {
				t.Fatalf("got len %d, err %v", len(got), err)
			}
			for i, s := range got {
				if s != "v"+strconv.Itoa(i*2) {
					t.Fatalf("results[%d] = %q, want %q", i, s, "v"+strconv.Itoa(i*2))
				}
			}
		})
	}
}

func TestConcurrencyLimit(t *testing.T) {
	for _, tc := range []struct{ n, limit int }{{20, 1}, {20, 3}, {20, 8}, {10, 50}} {
		t.Run(fmt.Sprintf("n=%d/limit=%d", tc.n, tc.limit), func(t *testing.T) {
			want := int64(min(tc.n, tc.limit))
			var active, peak, entered atomic.Int64
			full := make(chan struct{})
			var once sync.Once
			_, err := Map(context.Background(), ints(tc.n), tc.limit, func(ctx context.Context, x int) (int, error) {
				cur := active.Add(1)
				defer active.Add(-1)
				for p := peak.Load(); cur > p && !peak.CompareAndSwap(p, cur); p = peak.Load() {
				}
				if cur == want {
					once.Do(func() { close(full) })
				}
				if entered.Add(1) <= want {
					waitOrTimeout(full) // the first `want` calls must overlap
				}
				runtime.Gosched()
				return x, nil
			})
			if err != nil {
				t.Fatal(err)
			}
			if peak.Load() != want {
				t.Fatalf("peak concurrency = %d, want exactly %d", peak.Load(), want)
			}
		})
	}
	t.Run("rolling window", func(t *testing.T) {
		// Item 0 stays in progress until items 1..4 have all finished; with limit 2 this
		// only completes if the free slot keeps being reused while item 0 is running.
		var finished atomic.Int64
		rest := make(chan struct{})
		var ok atomic.Bool
		_, err := Map(context.Background(), ints(5), 2, func(ctx context.Context, x int) (int, error) {
			if x == 0 {
				ok.Store(waitOrTimeout(rest))
				return x, nil
			}
			if finished.Add(1) == 4 {
				close(rest)
			}
			return x, nil
		})
		if err != nil || !ok.Load() {
			t.Fatalf("items 1..4 did not run while item 0 was in progress (err=%v)", err)
		}
	})
}

func TestSequentialErrorStopsDispatch(t *testing.T) {
	for _, failAt := range []int{0, 3, 9} {
		t.Run(fmt.Sprint(failAt), func(t *testing.T) {
			var order []int
			var mu sync.Mutex
			got, err := Map(context.Background(), ints(10), 1, func(ctx context.Context, x int) (int, error) {
				mu.Lock()
				order = append(order, x)
				mu.Unlock()
				if x == failAt {
					return 0, errBoom
				}
				return x, nil
			})
			if err != errBoom || got != nil {
				t.Fatalf("got (%v, %v), want (nil, errBoom)", got, err)
			}
			if want := ints(failAt + 1); fmt.Sprint(order) != fmt.Sprint(want) {
				t.Fatalf("calls made in order %v, want %v", order, want)
			}
		})
	}
}

func TestFirstErrorCancelsInFlight(t *testing.T) {
	var calls atomic.Int64
	var sawCancel, returned [3]atomic.Bool
	started := make(chan int, 3)
	var finishedBeforeMapReturned atomic.Int64
	got, err := Map(context.Background(), ints(6), 3, func(ctx context.Context, x int) (int, error) {
		calls.Add(1)
		switch x {
		case 0:
			// Fail only after items 1 and 2 are in flight.
			<-started
			<-started
			return 0, errBoom
		case 1, 2:
			started <- x
			select {
			case <-ctx.Done():
				sawCancel[x].Store(true)
			case <-time.After(5 * time.Second):
			}
			returned[x].Store(true)
			finishedBeforeMapReturned.Add(1)
			return 0, ctx.Err()
		}
		return x, nil
	})
	if err != errBoom || got != nil {
		t.Fatalf("got (%v, %v), want (nil, errBoom)", got, err)
	}
	t.Run("no new calls after error", func(t *testing.T) {
		if calls.Load() != 3 {
			t.Errorf("f called %d times, want 3", calls.Load())
		}
	})
	t.Run("in-flight calls see cancellation", func(t *testing.T) {
		if !sawCancel[1].Load() || !sawCancel[2].Load() {
			t.Errorf("in-flight calls did not observe ctx cancellation")
		}
	})
	t.Run("waits for in-flight calls", func(t *testing.T) {
		if finishedBeforeMapReturned.Load() != 2 {
			t.Errorf("Map returned before in-flight calls finished")
		}
	})
}

func TestParentCancel(t *testing.T) {
	t.Run("f ignores ctx", func(t *testing.T) {
		ctx, cancel := context.WithCancel(context.Background())
		defer cancel()
		started := make(chan struct{}, 10)
		gate := make(chan struct{})
		var calls atomic.Int64
		done := make(chan struct{})
		var got []int
		var err error
		go func() {
			defer close(done)
			got, err = Map(ctx, ints(6), 2, func(c context.Context, x int) (int, error) {
				calls.Add(1)
				started <- struct{}{}
				<-gate
				return x, nil
			})
		}()
		<-started
		<-started
		cancel()
		close(gate)
		<-done
		if !errors.Is(err, context.Canceled) || got != nil {
			t.Fatalf("got (%v, %v), want (nil, context.Canceled)", got, err)
		}
		if calls.Load() != 2 {
			t.Fatalf("f called %d times, want 2", calls.Load())
		}
	})
	t.Run("f honors ctx", func(t *testing.T) {
		ctx, cancel := context.WithCancel(context.Background())
		defer cancel()
		started := make(chan struct{}, 10)
		var calls atomic.Int64
		done := make(chan struct{})
		var got []int
		var err error
		go func() {
			defer close(done)
			got, err = Map(ctx, ints(6), 3, func(c context.Context, x int) (int, error) {
				calls.Add(1)
				started <- struct{}{}
				select {
				case <-c.Done():
					return 0, c.Err()
				case <-time.After(5 * time.Second):
					return x, nil
				}
			})
		}()
		<-started
		<-started
		<-started
		cancel()
		<-done
		if !errors.Is(err, context.Canceled) || got != nil {
			t.Fatalf("got (%v, %v), want (nil, context.Canceled)", got, err)
		}
		if calls.Load() != 3 {
			t.Fatalf("f called %d times, want 3", calls.Load())
		}
	})
	t.Run("work ctx canceled after return", func(t *testing.T) {
		var seen context.Context
		var mu sync.Mutex
		_, err := Map(context.Background(), ints(3), 1, func(c context.Context, x int) (int, error) {
			mu.Lock()
			seen = c
			mu.Unlock()
			return x, nil
		})
		if err != nil {
			t.Fatal(err)
		}
		if seen.Err() == nil {
			t.Fatalf("context passed to f is still live after Map returned")
		}
	})
}

func TestPreCanceledContext(t *testing.T) {
	canceled, cancel := context.WithCancel(context.Background())
	cancel()
	expired, cancel2 := context.WithDeadline(context.Background(), time.Unix(0, 0))
	defer cancel2()
	cases := []struct {
		name string
		ctx  context.Context
		want error
	}{
		{"canceled", canceled, context.Canceled},
		{"deadline", expired, context.DeadlineExceeded},
	}
	for _, c := range cases {
		for _, limit := range []int{1, 3, 20} {
			t.Run(fmt.Sprintf("%s/%d", c.name, limit), func(t *testing.T) {
				var calls atomic.Int64
				got, err := Map(c.ctx, ints(10), limit, func(ctx context.Context, x int) (int, error) {
					calls.Add(1)
					return x, nil
				})
				if !errors.Is(err, c.want) || got != nil || calls.Load() != 0 {
					t.Fatalf("got (%v, %v) with %d calls; want (nil, %v) and 0 calls", got, err, calls.Load(), c.want)
				}
			})
		}
	}
}

func TestNoCallsAfterReturn(t *testing.T) {
	var late atomic.Int64
	for iter := 0; iter < 40; iter++ {
		var returned atomic.Bool
		var active atomic.Int64
		failAt := iter % 25
		_, err := Map(context.Background(), ints(25), 4, func(ctx context.Context, x int) (int, error) {
			if returned.Load() {
				late.Add(1)
			}
			active.Add(1)
			defer active.Add(-1)
			runtime.Gosched()
			if x == failAt {
				return 0, errBoom
			}
			if x > failAt && ctx.Err() != nil {
				return 0, ctx.Err()
			}
			return x, nil
		})
		returned.Store(true)
		if err != errBoom {
			t.Fatalf("iter %d: err = %v, want errBoom", iter, err)
		}
		if n := active.Load(); n != 0 {
			t.Fatalf("iter %d: %d calls still running after Map returned", iter, n)
		}
	}
	time.Sleep(50 * time.Millisecond)
	if late.Load() != 0 {
		t.Fatalf("f was called %d times after Map returned", late.Load())
	}
}
