package main

import (
	"crypto/sha256"
	"encoding/json"
	"errors"
	"fmt"
	"sync"
	"time"
)

var (
	ErrInvalid  = errors.New("invalid plan")
	ErrActor    = errors.New("caller does not own this plan")
	ErrApproval = errors.New("plan differs from approved content")
	ErrKeyReuse = errors.New("operation ID reused with different content")
	ErrExpired  = errors.New("approval expired")
	ErrPolicy   = errors.New("policy revision changed")
	ErrRevoked  = errors.New("execution disabled")
	ErrStale    = errors.New("target state changed")
)

// Plan is deliberately a fixed struct, not arbitrary JSON or a shell command.
// ExpiresAt is Unix seconds. This demo hashes Go's encoding of this exact type;
// it does not define a cross-language canonical-JSON or signed-token standard.
type Plan struct {
	ID              string `json:"id"`
	Actor           string `json:"actor"`
	Service         string `json:"service"`
	UID             string `json:"uid"`
	ExpectedVersion uint64 `json:"expected_version"`
	Before          string `json:"before"`
	After           string `json:"after"`
	PolicyRevision  uint64 `json:"policy_revision"`
	ExpiresAt       int64  `json:"expires_at"`
}

type Resource struct {
	Service string
	UID     string
	Version uint64
	Image   string
}

type Receipt struct {
	OperationID string
	PlanHash    [32]byte
	Image       string
	Version     uint64
}

type approval struct {
	hash     [32]byte
	reviewer string
}

// Gate is a single-process in-memory model. Its mutex covers BOTH the resource
// mutation and the receipt. It cannot make a database and Kubernetes atomic.
type Gate struct {
	mu             sync.Mutex
	resource       Resource
	policyRevision uint64
	enabled        bool
	now            func() time.Time
	approvals      map[string]approval
	receipts       map[string]Receipt
	applied        int
}

func NewGate(r Resource, now func() time.Time) *Gate {
	return &Gate{resource: r, policyRevision: 1, enabled: true, now: now,
		approvals: map[string]approval{}, receipts: map[string]Receipt{}}
}

func digest(p Plan) [32]byte {
	// This concrete type contains only JSON-supported scalar fields.
	b, err := json.Marshal(p)
	if err != nil {
		panic(err)
	}
	return sha256.Sum256(b)
}

func valid(p Plan) bool {
	return p.ID != "" && p.Actor != "" && p.Service != "" && p.UID != "" &&
		p.ExpectedVersion > 0 && p.Before != "" && p.After != "" && p.Before != p.After &&
		p.PolicyRevision > 0 && p.ExpiresAt > 0
}

// Approve simulates the TRUSTED review service, not an Agent-callable tool.
// Authentication, reviewer roles and separation of duties are intentionally
// outside this executable model. Caller strings must come from trusted auth.
func (g *Gate) Approve(reviewer string, p Plan) error {
	g.mu.Lock()
	defer g.mu.Unlock()
	if reviewer == "" || reviewer == p.Actor || !valid(p) {
		return ErrInvalid
	}
	h := digest(p)
	if a, ok := g.approvals[p.ID]; ok {
		if a.hash != h {
			return ErrKeyReuse
		}
		return nil
	}
	g.approvals[p.ID] = approval{hash: h, reviewer: reviewer}
	return nil
}

func (g *Gate) Execute(caller string, p Plan) (Receipt, bool, error) {
	g.mu.Lock()
	defer g.mu.Unlock()
	if !valid(p) {
		return Receipt{}, false, ErrInvalid
	}
	if caller != p.Actor {
		return Receipt{}, false, ErrActor
	}
	h := digest(p)
	// A replay returns HISTORY. It does not assert the resource is still there
	// or healthy, and does not authorize a new mutation after revocation.
	if r, ok := g.receipts[p.ID]; ok {
		if r.PlanHash != h {
			return Receipt{}, false, ErrKeyReuse
		}
		return r, true, nil
	}
	a, ok := g.approvals[p.ID]
	if !ok || a.hash != h {
		return Receipt{}, false, ErrApproval
	}
	if !g.enabled {
		return Receipt{}, false, ErrRevoked
	}
	if g.now().Unix() >= p.ExpiresAt {
		return Receipt{}, false, ErrExpired
	}
	if g.policyRevision != p.PolicyRevision {
		return Receipt{}, false, ErrPolicy
	}
	if g.resource.Service != p.Service || g.resource.UID != p.UID ||
		g.resource.Version != p.ExpectedVersion || g.resource.Image != p.Before {
		return Receipt{}, false, ErrStale
	}
	// Check + change + receipt share one critical section in THIS model only.
	g.resource.Image = p.After
	g.resource.Version++
	r := Receipt{OperationID: p.ID, PlanHash: h, Image: p.After, Version: g.resource.Version}
	g.receipts[p.ID] = r
	g.applied++
	return r, false, nil
}

// ExternalChange models another operator, not a capability given to the Agent.
func (g *Gate) ExternalChange(image string) {
	g.mu.Lock()
	defer g.mu.Unlock()
	g.resource.Image = image
	g.resource.Version++
}
func (g *Gate) SetPolicy(revision uint64, enabled bool) {
	g.mu.Lock()
	defer g.mu.Unlock()
	g.policyRevision = revision
	g.enabled = enabled
}
func (g *Gate) Snapshot() (Resource, int) {
	g.mu.Lock()
	defer g.mu.Unlock()
	return g.resource, g.applied
}
func require(err error) {
	if err != nil {
		panic(fmt.Sprintf("demo setup: %v", err))
	}
}
