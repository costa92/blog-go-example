package superagent

import (
	"context"
	"encoding/json"
	"errors"
	"os"
	"sort"
	"time"

	"github.com/kart-io/goagent/core/durable"
)

var ErrSimulatedTimeout = errors.New("simulated timeout after remote receipt")

type Sender interface {
	Send(context.Context, Message) error
}

// Deliver serializes senders, but does not block intake or worker execution.
// An ambiguous send is retried with the same ID; receivers must deduplicate it.
func (e *Engine) Deliver(ctx context.Context, sender Sender, now time.Time) (err error) {
	if sender == nil {
		return errors.New("sender is required")
	}
	unlock, err := e.cfg.Store.Lock(ctx, "superagent/outbox-delivery")
	if err != nil {
		return err
	}
	defer func() { err = errors.Join(err, unlock()) }()
	state, err := e.Snapshot(ctx)
	if err != nil {
		return err
	}
	ids := []string{}
	for id, m := range state.Outbox {
		if !m.Sent && !now.Before(m.NextAttempt) {
			ids = append(ids, id)
		}
	}
	sort.Strings(ids)
	var failures []error
	for _, id := range ids {
		m := state.Outbox[id]
		sendErr := sender.Send(ctx, m)
		saveErr := e.state(ctx, true, func(s *State) error {
			current := s.Outbox[id]
			current.Attempts++
			if sendErr == nil {
				current.Sent = true
			} else {
				delay := time.Second * time.Duration(1<<min(current.Attempts-1, 6))
				current.NextAttempt = now.Add(delay)
			}
			s.Outbox[id] = current
			return nil
		})
		if sendErr != nil {
			failures = append(failures, sendErr)
		}
		if saveErr != nil {
			failures = append(failures, saveErr)
		}
		if ctx.Err() != nil {
			break
		}
	}
	if len(failures) == 1 {
		return failures[0]
	}
	return errors.Join(failures...)
}

// DemoReceiver is a local stand-in for an external service with idempotency keys.
// FailFirst simulates "accepted remotely, response lost". Receipts survive restart.
// This does not imply that GitHub or Feishu accepts the same idempotency contract.
type DemoReceiver struct {
	Store     durable.Store
	FailFirst bool
}
type receiverState struct {
	Receipts map[string]Message `json:"receipts"`
	Faulted  bool               `json:"faulted"`
}

const receiverKey = "demo-receiver"

func (r *DemoReceiver) load(ctx context.Context) (receiverState, error) {
	s := receiverState{Receipts: map[string]Message{}}
	cp, err := r.Store.Load(ctx, receiverKey)
	if errors.Is(err, os.ErrNotExist) {
		return s, nil
	}
	if err != nil {
		return s, err
	}
	if cp.Version != "receiver-v1" {
		return s, errors.New("invalid receiver version")
	}
	err = json.Unmarshal(cp.Data, &s)
	if err == nil && s.Receipts == nil {
		err = errors.New("invalid receiver receipts")
	}
	return s, err
}
func (r *DemoReceiver) Send(ctx context.Context, m Message) (err error) {
	unlock, err := r.Store.Lock(ctx, receiverKey)
	if err != nil {
		return err
	}
	defer func() { err = errors.Join(err, unlock()) }()
	s, err := r.load(ctx)
	if err != nil {
		return err
	}
	if prior, ok := s.Receipts[m.ID]; ok {
		if prior.Body != m.Body {
			return errors.New("idempotency key reused with different content")
		}
		return nil
	}
	s.Receipts[m.ID] = m
	fail := r.FailFirst && !s.Faulted
	if fail {
		s.Faulted = true
	}
	b, err := json.Marshal(s)
	if err != nil {
		return err
	}
	if err = r.Store.Save(ctx, receiverKey, &durable.Snapshot{Version: "receiver-v1", RunID: receiverKey, Data: b}); err != nil {
		return err
	}
	if fail {
		return ErrSimulatedTimeout
	}
	return nil
}
func (r *DemoReceiver) Receipts(ctx context.Context) (map[string]Message, error) {
	s, err := r.load(ctx)
	return s.Receipts, err
}
