package superagent

import (
	"context"
	"encoding/json"
	"errors"
	"os"
	"sync/atomic"
	"testing"
	"time"

	"github.com/kart-io/goagent/core/durable"
	"github.com/kart-io/goagent/llm"
)

func setup(t *testing.T, factory ModelFactory) (*Engine, string) {
	t.Helper()
	dir := t.TempDir()
	st, err := durable.NewFileStore(dir)
	if err != nil {
		t.Fatal(err)
	}
	e, err := New(Config{Store: st, Models: factory, MaxWorkers: 2, Mode: Observe})
	if err != nil {
		t.Fatal(err)
	}
	return e, dir
}
func event(id, thread string) Event {
	return Event{ID: id, Thread: thread, Text: "修复 CSV 导出，并补回归测试", Scope: "csv-export", Actor: Human, Authorized: true, Explicit: true}
}
func submit(t *testing.T, e *Engine, ev Event) Route {
	t.Helper()
	r, err := e.Handle(context.Background(), ev)
	if err != nil {
		t.Fatal(err)
	}
	return r
}
func snapshot(t *testing.T, e *Engine) State {
	t.Helper()
	s, err := e.Snapshot(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	return s
}

func TestObserveAuthorizationAndDeduplication(t *testing.T) {
	e, _ := setup(t, OfflineFactory)
	ev := event("1", "issue/1")
	ev.Authorized = false
	if _, err := e.Handle(context.Background(), ev); !errors.Is(err, ErrUnauthorized) {
		t.Fatalf("unauthorized: %v", err)
	}
	ev.Authorized = true
	ev.Explicit = false
	if r := submit(t, e, ev); !r.Observed || r.Created != "" {
		t.Fatalf("observe: %+v", r)
	}
	direct := event("2", "issue/2")
	r := submit(t, e, direct)
	if r.Created == "" {
		t.Fatal("explicit request must work in observe mode")
	}
	if again := submit(t, e, direct); again != r {
		t.Fatalf("replayed event changed: %+v", again)
	}
	direct.Text = "different payload"
	if _, err := e.Handle(context.Background(), direct); !errors.Is(err, ErrEventConflict) {
		t.Fatalf("reused event ID: %v", err)
	}
	if len(snapshot(t, e).Tickets) != 1 {
		t.Fatal("duplicate ticket")
	}
}
func TestSubscribedHumanBotAndOutOfScopeRoutes(t *testing.T) {
	e, _ := setup(t, OfflineFactory)
	r := submit(t, e, event("start", "issue/1"))
	ev := event("review", "issue/1")
	ev.Explicit = false
	follow := submit(t, e, ev)
	if follow.Delivered != r.Created || follow.Evaluated {
		t.Fatalf("owned human followup: %+v", follow)
	}
	ev = event("bot", "issue/1")
	ev.Actor = Bot
	ev.Explicit = false
	bot := submit(t, e, ev)
	if bot.Delivered != r.Created || !bot.Evaluated || bot.Created != "" {
		t.Fatalf("bot must fan out and evaluate: %+v", bot)
	}
	ev = event("scope", "issue/1")
	ev.Scope = "auth-rewrite"
	outside := submit(t, e, ev)
	if !outside.Reroute || outside.Created != "" {
		t.Fatalf("scope expansion: %+v", outside)
	}
	if len(snapshot(t, e).Tickets) != 1 {
		t.Fatal("scope expansion silently created work")
	}
}
func TestNotificationRecoveryDoesNotRepeatWork(t *testing.T) {
	var work atomic.Int32
	factory := func(role, id string) (llm.Client, error) {
		m, _ := OfflineFactory(role, id)
		if role == "worker" {
			m.(*OfflineModel).Respond = func(context.Context, *llm.CompletionRequest) (string, error) {
				work.Add(1)
				return "检查清单：复现空输入并补回归测试；未执行仓库操作", nil
			}
		}
		return m, nil
	}
	e, dir := setup(t, factory)
	r := submit(t, e, event("start", "issue/1"))
	ctx := context.Background()
	if err := e.RunPending(ctx); err != nil {
		t.Fatal(err)
	}
	if snapshot(t, e).Tickets[r.Created].Status != Ready {
		t.Fatal("ready is not accepted")
	}
	remote, err := durable.NewFileStore(t.TempDir())
	if err != nil {
		t.Fatal(err)
	}
	receiver := &DemoReceiver{Store: remote, FailFirst: true}
	now := time.Unix(1000, 0)
	if err := e.Deliver(ctx, receiver, now); err == nil {
		t.Fatal("expected timeout after remote receipt")
	}
	if err := e.Deliver(ctx, receiver, now.Add(500*time.Millisecond)); err != nil {
		t.Fatal(err)
	}
	for _, m := range snapshot(t, e).Outbox {
		if m.Attempts != 1 {
			t.Fatal("backoff ignored")
		}
	}
	st, _ := durable.NewFileStore(dir)
	resumed, err := New(Config{Store: st, Models: factory, MaxWorkers: 2, Mode: Observe})
	if err != nil {
		t.Fatal(err)
	}
	if err = resumed.RunPending(ctx); err != nil {
		t.Fatal(err)
	}
	if err = resumed.Deliver(ctx, &DemoReceiver{Store: remote}, now.Add(time.Hour)); err != nil {
		t.Fatal(err)
	}
	if work.Load() != 1 {
		t.Fatalf("worker ran %d times", work.Load())
	}
	receipts, err := receiver.Receipts(ctx)
	if err != nil || len(receipts) != 1 {
		t.Fatalf("remote receipts: %v %v", receipts, err)
	}
	for _, m := range snapshot(t, resumed).Outbox {
		if !m.Sent || m.Attempts != 2 {
			t.Fatalf("outbox: %+v", m)
		}
	}
	if err := resumed.Accept(ctx, r.Created, false); !errors.Is(err, ErrUnauthorized) {
		t.Fatal(err)
	}
	if err := resumed.Accept(ctx, r.Created, true); err != nil {
		t.Fatal(err)
	}
	if snapshot(t, resumed).Tickets[r.Created].Status != Accepted {
		t.Fatal("human acceptance was not saved")
	}
}
func TestWorkerConcurrencyAndIndependentInputs(t *testing.T) {
	var active, peak, calls atomic.Int32
	paired := make(chan struct{})
	factory := func(role, id string) (llm.Client, error) {
		m, _ := OfflineFactory(role, id)
		if role == "worker" {
			m.(*OfflineModel).Respond = func(ctx context.Context, req *llm.CompletionRequest) (string, error) {
				n := active.Add(1)
				defer active.Add(-1)
				for old := peak.Load(); n > old && !peak.CompareAndSwap(old, n); old = peak.Load() {
				}
				if calls.Add(1) == 2 {
					close(paired)
				}
				select {
				case <-ctx.Done():
					return "", ctx.Err()
				case <-paired:
				}
				return id, nil
			}
		}
		return m, nil
	}
	e, _ := setup(t, factory)
	for _, id := range []string{"a", "b", "c", "d"} {
		submit(t, e, event(id, id))
	}
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	if err := e.RunPending(ctx); err != nil {
		t.Fatal(err)
	}
	if calls.Load() != 4 || peak.Load() > 2 || peak.Load() < 2 {
		t.Fatalf("calls=%d peak=%d", calls.Load(), peak.Load())
	}
	for id, ticket := range snapshot(t, e).Tickets {
		if ticket.Result != "worker/"+id+"/1" {
			t.Fatalf("worker contexts mixed: %q != %q", ticket.Result, id)
		}
	}
}
func TestCorruptStateFailsClosed(t *testing.T) {
	st, _ := durable.NewFileStore(t.TempDir())
	ctx := context.Background()
	unlock, _ := st.Lock(ctx, stateKey)
	if err := st.Save(ctx, stateKey, &durable.Snapshot{Version: stateVersion, Data: []byte(`{"tickets":"broken"}`)}); err != nil {
		t.Fatal(err)
	}
	_ = unlock()
	e, err := New(Config{Store: st, Models: OfflineFactory, MaxWorkers: 1, Mode: Observe})
	if err != nil {
		t.Fatal(err)
	}
	if _, err = e.Handle(ctx, event("a", "a")); err == nil || errors.Is(err, os.ErrNotExist) {
		t.Fatalf("corrupt state overwritten: %v", err)
	}
}

type failReadyStore struct {
	durable.Store
	failed atomic.Bool
}

func (s *failReadyStore) Save(ctx context.Context, id string, cp *durable.Snapshot) error {
	if id == stateKey {
		var state State
		if json.Unmarshal(cp.Data, &state) == nil {
			for _, ticket := range state.Tickets {
				if ticket.Status == Ready && s.failed.CompareAndSwap(false, true) {
					return errors.New("injected failure after graph completion")
				}
			}
		}
	}
	return s.Store.Save(ctx, id, cp)
}
func TestCompletedGraphSurvivesApplicationCommitFailure(t *testing.T) {
	var calls atomic.Int32
	factory := func(role, id string) (llm.Client, error) {
		m, _ := OfflineFactory(role, id)
		if role == "worker" {
			m.(*OfflineModel).Respond = func(context.Context, *llm.CompletionRequest) (string, error) {
				calls.Add(1)
				return "saved graph result", nil
			}
		}
		return m, nil
	}
	dir := t.TempDir()
	store, _ := durable.NewFileStore(dir)
	e, err := New(Config{Store: &failReadyStore{Store: store}, Models: factory, MaxWorkers: 1, Mode: Observe})
	if err != nil {
		t.Fatal(err)
	}
	r := submit(t, e, event("start", "issue/1"))
	if err = e.RunPending(context.Background()); err == nil {
		t.Fatal("expected state save fault")
	}
	reopened, _ := durable.NewFileStore(dir)
	resume, _ := New(Config{Store: reopened, Models: factory, MaxWorkers: 1, Mode: Observe})
	if err = resume.RunPending(context.Background()); err != nil {
		t.Fatal(err)
	}
	if calls.Load() != 1 || snapshot(t, resume).Tickets[r.Created].Status != Ready {
		t.Fatalf("worker replayed after graph checkpoint: calls=%d", calls.Load())
	}
}
func TestAutoIntakeRequiresAllowedScope(t *testing.T) {
	store, _ := durable.NewFileStore(t.TempDir())
	e, err := New(Config{Store: store, Models: OfflineFactory, MaxWorkers: 1, Mode: Auto, AutoScopes: []string{"csv-export"}})
	if err != nil {
		t.Fatal(err)
	}
	ev := event("1", "issue/1")
	ev.Explicit = false
	if submit(t, e, ev).Created == "" {
		t.Fatal("allowed auto candidate not accepted")
	}
	ev = event("2", "issue/2")
	ev.Explicit = false
	ev.Scope = "auth"
	if submit(t, e, ev).Created != "" {
		t.Fatal("non-allowlisted scope accepted")
	}
}

func TestNewInputDuringWorkCannotBeOverwritten(t *testing.T) {
	started := make(chan struct{})
	release := make(chan struct{})
	var calls atomic.Int32
	factory := func(role, id string) (llm.Client, error) {
		m, _ := OfflineFactory(role, id)
		if role == "worker" {
			m.(*OfflineModel).Respond = func(ctx context.Context, _ *llm.CompletionRequest) (string, error) {
				if calls.Add(1) == 1 {
					close(started)
					select {
					case <-release:
					case <-ctx.Done():
						return "", ctx.Err()
					}
				}
				return id, nil
			}
		}
		return m, nil
	}
	e, _ := setup(t, factory)
	r := submit(t, e, event("start", "issue/1"))
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	done := make(chan error, 1)
	go func() { done <- e.RunPending(ctx) }()
	select {
	case <-started:
	case <-ctx.Done():
		t.Fatal(ctx.Err())
	}
	submit(t, e, event("followup", "issue/1"))
	close(release)
	if err := <-done; err != nil {
		t.Fatal(err)
	}
	if snapshot(t, e).Tickets[r.Created].Status != Pending {
		t.Fatal("old worker result overwrote new input")
	}
	if err := e.RunPending(ctx); err != nil {
		t.Fatal(err)
	}
	s := snapshot(t, e)
	if calls.Load() != 2 || s.Tickets[r.Created].Revision != 2 || len(s.Outbox) != 1 {
		t.Fatalf("calls=%d state=%+v", calls.Load(), s)
	}
}
func TestInvalidCoordinatorResponseCannotCreateWork(t *testing.T) {
	factory := func(role, id string) (llm.Client, error) {
		m, _ := OfflineFactory(role, id)
		m.(*OfflineModel).Respond = func(context.Context, *llm.CompletionRequest) (string, error) { return "I think yes", nil }
		return m, nil
	}
	e, _ := setup(t, factory)
	if _, err := e.Handle(context.Background(), event("1", "issue/1")); err == nil {
		t.Fatal("malformed decision accepted")
	}
	if len(snapshot(t, e).Tickets) != 0 {
		t.Fatal("invalid decision created a ticket")
	}
}
