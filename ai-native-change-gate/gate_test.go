package main

import (
	"errors"
	"sync"
	"sync/atomic"
	"testing"
	"time"
)

func TestChangedStateDoesNotOverwriteHotfix(t *testing.T) {
	g, p := fixture("stale")
	g.ExternalChange("v18")
	_, _, err := g.Execute(p.Actor, p)
	r, n := g.Snapshot()
	if !errors.Is(err, ErrStale) || r.Image != "v18" || n != 0 {
		t.Fatalf("%+v applied=%d err=%v", r, n, err)
	}
}

func TestApprovedContentCannotChange(t *testing.T) {
	g, p := fixture("changed")
	p.After = "v15"
	_, _, err := g.Execute(p.Actor, p)
	if !errors.Is(err, ErrApproval) {
		t.Fatal(err)
	}
	_, n := g.Snapshot()
	if n != 0 {
		t.Fatal(n)
	}
}

func TestOneIDCannotMeanAnotherMutation(t *testing.T) {
	g, p := fixture("reuse")
	_, _, err := g.Execute(p.Actor, p)
	if err != nil {
		t.Fatal(err)
	}
	p.After = "v15"
	_, _, err = g.Execute(p.Actor, p)
	if !errors.Is(err, ErrKeyReuse) {
		t.Fatal(err)
	}
	if !errors.Is(g.Approve("reviewer-b", p), ErrKeyReuse) {
		t.Fatal("approval rebound")
	}
}

func TestReplayedReceiptIsHistoryNotCurrentState(t *testing.T) {
	g, p := fixture("history")
	first, _, err := g.Execute(p.Actor, p)
	if err != nil {
		t.Fatal(err)
	}
	g.ExternalChange("v18")
	g.SetPolicy(2, false)
	// Even an expired approval can be used to retrieve its historical receipt.
	g.now = func() time.Time { return time.Unix(p.ExpiresAt+1, 0) }
	again, replay, err := g.Execute(p.Actor, p)
	current, n := g.Snapshot()
	if err != nil || !replay || again != first || current.Image != "v18" || n != 1 {
		t.Fatalf("replay=%v receipt=%+v current=%+v n=%d err=%v", replay, again, current, n, err)
	}
}

func TestPolicyExpiryRevocationAndIdentity(t *testing.T) {
	for _, tc := range []struct {
		name   string
		change func(*Gate, Plan)
		caller string
		want   error
	}{
		{"policy", func(g *Gate, p Plan) { g.SetPolicy(2, true) }, "agent-a", ErrPolicy},
		{"expiry", func(g *Gate, p Plan) { g.now = func() time.Time { return time.Unix(p.ExpiresAt, 0) } }, "agent-a", ErrExpired},
		{"revoked", func(g *Gate, p Plan) { g.SetPolicy(1, false) }, "agent-a", ErrRevoked},
		{"identity", func(g *Gate, p Plan) {}, "agent-other", ErrActor},
		{"recreated", func(g *Gate, p Plan) { g.resource.UID = "different-uid" }, "agent-a", ErrStale},
	} {
		t.Run(tc.name, func(t *testing.T) {
			g, p := fixture(tc.name)
			tc.change(g, p)
			_, _, err := g.Execute(tc.caller, p)
			_, n := g.Snapshot()
			if !errors.Is(err, tc.want) || n != 0 {
				t.Fatalf("applied=%d err=%v", n, err)
			}
		})
	}
}

func TestOtherCallerCannotReadReplayedReceipt(t *testing.T) {
	g, p := fixture("private-receipt")
	_, _, err := g.Execute(p.Actor, p)
	if err != nil {
		t.Fatal(err)
	}
	_, _, err = g.Execute("agent-other", p)
	if !errors.Is(err, ErrActor) {
		t.Fatal(err)
	}
}

func TestConcurrentIdenticalRequestsApplyOnce(t *testing.T) {
	g, p := fixture("parallel")
	var fresh, replays, failures atomic.Int64
	var wg sync.WaitGroup
	for range 64 {
		wg.Add(1)
		go func() {
			defer wg.Done()
			_, again, err := g.Execute(p.Actor, p)
			if err != nil {
				failures.Add(1)
			} else if again {
				replays.Add(1)
			} else {
				fresh.Add(1)
			}
		}()
	}
	wg.Wait()
	r, n := g.Snapshot()
	if fresh.Load() != 1 || replays.Load() != 63 || failures.Load() != 0 || n != 1 || r.Version != 42 {
		t.Fatalf("fresh=%d replay=%d errors=%d applied=%d version=%d", fresh.Load(), replays.Load(), failures.Load(), n, r.Version)
	}
}

func TestTwoApprovedPlansCompeteForOneVersion(t *testing.T) {
	g, p := fixture("first")
	other := p
	other.ID = "second"
	other.After = "v15"
	if err := g.Approve("reviewer-b", other); err != nil {
		t.Fatal(err)
	}
	start := make(chan struct{})
	out := make(chan error, 2)
	for _, plan := range []Plan{p, other} {
		go func() { <-start; _, _, err := g.Execute(plan.Actor, plan); out <- err }()
	}
	close(start)
	var ok, stale int
	for range 2 {
		err := <-out
		if err == nil {
			ok++
		} else if errors.Is(err, ErrStale) {
			stale++
		} else {
			t.Fatal(err)
		}
	}
	_, n := g.Snapshot()
	if ok != 1 || stale != 1 || n != 1 {
		t.Fatalf("ok=%d stale=%d applied=%d", ok, stale, n)
	}
}
