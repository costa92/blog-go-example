package main

import (
	"fmt"
	"sync"
	"sync/atomic"
	"time"
)

func fixture(id string) (*Gate, Plan) {
	now := time.Unix(1800000000, 0)
	g := NewGate(Resource{Service: "checkout", UID: "deployment-1", Version: 41, Image: "v17"}, func() time.Time { return now })
	p := Plan{ID: id, Actor: "agent-a", Service: "checkout", UID: "deployment-1", ExpectedVersion: 41,
		Before: "v17", After: "v16", PolicyRevision: 1, ExpiresAt: now.Add(5 * time.Minute).Unix()}
	require(g.Approve("reviewer-b", p))
	return g, p
}

func main() {
	g, p := fixture("stale")
	g.ExternalChange("v18")
	_, _, err := g.Execute("agent-a", p)
	r, n := g.Snapshot()
	fmt.Printf("stale approval: error=%v image=%s gate_applied=%d\n", err, r.Image, n)

	g, p = fixture("lost-reply")
	// Deliberately discard a successful result, modelling a lost response.
	// No HTTP request or actual network failure is involved.
	_, _, err = g.Execute("agent-a", p)
	require(err)
	receipt, replay, err := g.Execute("agent-a", p)
	require(err)
	_, n = g.Snapshot()
	fmt.Printf("lost reply (simulated): replay=%v receipt_version=%d gate_applied=%d\n", replay, receipt.Version, n)
	changed := p
	changed.After = "v15"
	_, _, err = g.Execute("agent-a", changed)
	fmt.Printf("same ID, changed target: error=%v\n", err)

	g, p = fixture("policy")
	g.SetPolicy(2, true)
	_, _, err = g.Execute("agent-a", p)
	_, n = g.Snapshot()
	fmt.Printf("new policy: error=%v gate_applied=%d\n", err, n)

	g, p = fixture("parallel")
	var applied, replayed, failed atomic.Int64
	var wg sync.WaitGroup
	for range 32 {
		wg.Add(1)
		go func() {
			defer wg.Done()
			_, again, e := g.Execute("agent-a", p)
			if e != nil {
				failed.Add(1)
			} else if again {
				replayed.Add(1)
			} else {
				applied.Add(1)
			}
		}()
	}
	wg.Wait()
	r, n = g.Snapshot()
	fmt.Printf("32 concurrent calls: applied=%d replayed=%d errors=%d final_version=%d gate_applied=%d\n", applied.Load(), replayed.Load(), failed.Load(), r.Version, n)
}
