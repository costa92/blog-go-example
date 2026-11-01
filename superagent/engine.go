// Package superagent is a teaching implementation of task coordination built on
// GoAgent. It does not execute repository commands or integrate with GitHub.
package superagent

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"sort"
	"sync"
	"time"

	"github.com/kart-io/goagent/builder"
	"github.com/kart-io/goagent/core/durable"
	"github.com/kart-io/goagent/llm"
	"github.com/kart-io/goagent/workflow"
)

type Actor string

const (
	Human Actor = "human"
	Bot   Actor = "bot"
)

type Mode string

const (
	Observe Mode = "observe"
	Auto    Mode = "auto"
)

type Status string

const (
	Pending  Status = "pending"
	Running  Status = "running"
	Ready    Status = "ready"
	Accepted Status = "accepted"
)

var (
	ErrUnauthorized  = errors.New("request is not authorized")
	ErrEventConflict = errors.New("event ID was reused with a different payload")
)

const stateKey = "superagent/application"
const stateVersion = "superagent-v1"

// Authorized and Scope must come from a trusted host adapter, not LLM output.
// Scope is a preclassified business tag here, not a semantic security boundary.
type Event struct {
	ID         string `json:"id"`
	Thread     string `json:"thread"`
	Text       string `json:"text"`
	Scope      string `json:"scope"`
	Actor      Actor  `json:"actor"`
	Authorized bool   `json:"authorized"`
	Explicit   bool   `json:"explicit"`
}
type Route struct {
	Created   string `json:"created,omitempty"`
	Delivered string `json:"delivered,omitempty"`
	Evaluated bool   `json:"evaluated"`
	Observed  bool   `json:"observed"`
	Reroute   bool   `json:"reroute"`
}
type Input struct {
	Event   Event `json:"event"`
	InScope bool  `json:"in_scope"`
}
type Evidence struct {
	Image        string   `json:"image,omitempty"`
	RunID        string   `json:"run_id"`
	Summary      string   `json:"summary"`
	Workspace    string   `json:"workspace"`
	BeforeTests  string   `json:"before_tests"`
	TestOutput   string   `json:"test_output"`
	Diff         string   `json:"diff"`
	SourceSHA256 string   `json:"source_sha256"`
	Executor     string   `json:"executor"`
	Tools        []string `json:"tools"`
}

// CodeWorker is implemented by the optional Harness execution adapter.
type CodeWorker interface {
	Run(context.Context, string, string) (Evidence, error)
	Verify(context.Context, Evidence) error
}

type Ticket struct {
	Execution string    `json:"execution,omitempty"`
	Evidence  *Evidence `json:"evidence,omitempty"`
	ID        string    `json:"id"`
	Thread    string    `json:"thread"`
	Mandate   string    `json:"mandate"`
	Inputs    []Input   `json:"inputs"`
	Revision  int       `json:"revision"`
	Status    Status    `json:"status"`
	Result    string    `json:"result,omitempty"`
}
type Message struct {
	ID          string    `json:"id"`
	TicketID    string    `json:"ticket_id"`
	Body        string    `json:"body"`
	Attempts    int       `json:"attempts"`
	NextAttempt time.Time `json:"next_attempt"`
	Sent        bool      `json:"sent"`
}
type Receipt struct {
	Hash  string `json:"hash"`
	Route Route  `json:"route"`
}
type State struct {
	Tickets       map[string]Ticket  `json:"tickets"`
	Subscriptions map[string]string  `json:"subscriptions"`
	Events        map[string]Receipt `json:"events"`
	Outbox        map[string]Message `json:"outbox"`
}
type ModelFactory func(role, session string) (llm.Client, error)
type Config struct {
	Worker     CodeWorker
	Store      durable.Store
	Models     ModelFactory
	MaxWorkers int
	Mode       Mode
	AutoScopes []string
}
type Engine struct {
	cfg   Config
	runMu sync.Mutex
}

func New(cfg Config) (*Engine, error) {
	if cfg.Store == nil || cfg.Models == nil {
		return nil, errors.New("store and model factory are required")
	}
	if cfg.MaxWorkers < 1 || cfg.MaxWorkers > 32 {
		return nil, errors.New("MaxWorkers must be between 1 and 32")
	}
	if cfg.Mode != Observe && cfg.Mode != Auto {
		return nil, errors.New("unknown intake mode")
	}
	return &Engine{cfg: cfg}, nil
}
func emptyState() State {
	return State{Tickets: map[string]Ticket{}, Subscriptions: map[string]string{}, Events: map[string]Receipt{}, Outbox: map[string]Message{}}
}
func digest(v any) string {
	b, _ := json.Marshal(v)
	h := sha256.Sum256(b)
	return hex.EncodeToString(h[:])
}
func (e *Engine) state(ctx context.Context, write bool, fn func(*State) error) (err error) {
	unlock, err := e.cfg.Store.Lock(ctx, stateKey)
	if err != nil {
		return err
	}
	defer func() { err = errors.Join(err, unlock()) }()
	saved, err := e.cfg.Store.Load(ctx, stateKey)
	s := emptyState()
	if errors.Is(err, os.ErrNotExist) {
		err = nil
	} else if err == nil {
		if saved.Version != stateVersion {
			return errors.New("unsupported application state version")
		}
		err = json.Unmarshal(saved.Data, &s)
	}
	if err != nil {
		return err
	}
	if s.Tickets == nil || s.Subscriptions == nil || s.Events == nil || s.Outbox == nil {
		return errors.New("invalid application state")
	}
	if err = fn(&s); err != nil || !write {
		return err
	}
	b, err := json.Marshal(s)
	if err != nil {
		return err
	}
	return e.cfg.Store.Save(ctx, stateKey, &durable.Snapshot{Version: stateVersion, RunID: stateKey, Data: b})
}
func (e *Engine) Snapshot(ctx context.Context) (s State, err error) {
	err = e.state(ctx, false, func(v *State) error { s = *v; return nil })
	return
}

// Handle never holds the application lock during a model request. The route is
// rechecked under lock before committing the event and its task changes together.
func (e *Engine) Handle(ctx context.Context, ev Event) (Route, error) {
	var out Route
	if !ev.Authorized {
		return out, ErrUnauthorized
	}
	if ev.ID == "" || ev.Thread == "" || ev.Text == "" || ev.Scope == "" || (ev.Actor != Human && ev.Actor != Bot) {
		return out, errors.New("invalid event")
	}
	hash := digest(ev)
	s, err := e.Snapshot(ctx)
	if err != nil {
		return out, err
	}
	if prior, ok := s.Events[ev.ID]; ok {
		if prior.Hash != hash {
			return out, ErrEventConflict
		}
		return prior.Route, nil
	}
	owner := s.Subscriptions[ev.Thread]
	needsEval := owner == "" || ev.Actor == Bot || s.Tickets[owner].Mandate != ev.Scope
	accept := false
	if needsEval {
		payload, _ := json.Marshal(ev)
		answer, err := e.agent(ctx, "coordinator", "intake/"+hash, string(payload))
		if err != nil {
			return out, err
		}
		var decision struct {
			Accept *bool `json:"accept"`
		}
		if err = json.Unmarshal([]byte(answer), &decision); err != nil || decision.Accept == nil {
			return out, errors.New("coordinator must return JSON with boolean accept")
		}
		accept = *decision.Accept
	}
	err = e.state(ctx, true, func(s *State) error {
		if prior, ok := s.Events[ev.ID]; ok {
			if prior.Hash != hash {
				return ErrEventConflict
			}
			out = prior.Route
			return nil
		}
		owner = s.Subscriptions[ev.Thread]
		out.Evaluated = needsEval
		if owner != "" {
			t, ok := s.Tickets[owner]
			if !ok {
				return errors.New("subscription points to missing ticket")
			}
			inScope := ev.Scope == t.Mandate
			t.Inputs = append(t.Inputs, Input{Event: ev, InScope: inScope})
			out.Delivered = owner
			out.Reroute = !inScope
			// Bot messages provide context, but do not independently reopen work.
			if inScope && ev.Actor == Human {
				t.Revision++
				t.Status = Pending
				t.Result = ""
				t.Evidence = nil
			}
			s.Tickets[owner] = t
		} else {
			allowed := ev.Actor == Human && ev.Explicit
			if ev.Actor == Human && !ev.Explicit && e.cfg.Mode == Auto {
				for _, scope := range e.cfg.AutoScopes {
					allowed = allowed || ev.Scope == scope
				}
			}
			out.Observed = accept && !allowed
			if accept && allowed {
				id := "ticket-" + digest(ev.ID)[:16]
				execution := "plan"
				if e.cfg.Worker != nil {
					execution = "coding"
				}
				s.Tickets[id] = Ticket{Execution: execution, ID: id, Thread: ev.Thread, Mandate: ev.Scope, Inputs: []Input{{Event: ev, InScope: true}}, Revision: 1, Status: Pending}
				s.Subscriptions[ev.Thread] = id
				out.Created = id
			}
		}
		s.Events[ev.ID] = Receipt{Hash: hash, Route: out}
		return nil
	})
	return out, err
}

type agentState struct {
	Prompt string `json:"prompt"`
	Result string `json:"result"`
}

// Each event/worker revision has its own durable workflow and Agent invocation.
// Completed model calls can replay from GoAgent's journal after a node retry.
func (e *Engine) agent(ctx context.Context, role, id, prompt string) (string, error) {
	g := workflow.NewGraph[agentState](workflow.Config{MaxSteps: 3, MaxConcurrency: 1})
	err := g.AddNode("agent", func(ctx context.Context, s agentState) (agentState, error) {
		client, err := e.cfg.Models(role, id)
		if err != nil {
			return s, err
		}
		system := "你是独立 Worker。仅给出所授权任务的修复方案和回归测试检查清单。没有仓库执行工具，必须说明未修改文件、未运行测试、未创建 PR。不要声称任务已验收。"
		if role == "coordinator" {
			system = "你是任务协调器。判断消息是否包含可开展的具体工作，仅输出 JSON：{\"accept\":true} 或 {\"accept\":false}。你不能授予权限，程序会单独核对授权和范围。"
		}
		a, err := builder.NewSimpleBuilder(client).WithAgentID(role).WithSessionID(id).WithDurableScope(role).WithSystemPrompt(system).WithMaxIterations(2).WithTimeout(45 * time.Second).Build()
		if err != nil {
			return s, err
		}
		result, err := a.AsRunnable().Invoke(ctx, s.Prompt)
		if err != nil {
			return s, err
		}
		text, ok := result.Result.(string)
		if !ok || text == "" {
			return s, errors.New("agent returned no text")
		}
		s.Result = text
		return s, nil
	})
	if err != nil {
		return "", err
	}
	if err = g.AddEdge(workflow.START, "agent"); err != nil {
		return "", err
	}
	if err = g.AddEdge("agent", workflow.END); err != nil {
		return "", err
	}
	graph, err := g.CompileDurable(ctx, workflow.DurableConfig{Store: e.cfg.Store, Version: "superagent/" + role + "/v1"})
	if err != nil {
		return "", err
	}
	snap, err := graph.AsRunnable().Invoke(ctx, workflow.RunRequest[agentState]{RunID: id, Initial: agentState{Prompt: prompt}})
	if err != nil {
		return "", err
	}
	return snap.State.Result, nil
}
func (e *Engine) RunPending(ctx context.Context) error {
	e.runMu.Lock()
	defer e.runMu.Unlock()
	s, err := e.Snapshot(ctx)
	if err != nil {
		return err
	}
	ids := []string{}
	for id, t := range s.Tickets {
		if t.Status == Pending || t.Status == Running {
			ids = append(ids, id)
		}
	}
	sort.Strings(ids)
	sem := make(chan struct{}, e.cfg.MaxWorkers)
	var wg sync.WaitGroup
	var mu sync.Mutex
	var failures []error
	for _, id := range ids {
		select {
		case sem <- struct{}{}:
		case <-ctx.Done():
			wg.Wait()
			return ctx.Err()
		}
		wg.Add(1)
		go func(id string) {
			defer wg.Done()
			defer func() { <-sem }()
			if err := e.runTicket(ctx, id); err != nil {
				mu.Lock()
				failures = append(failures, err)
				mu.Unlock()
			}
		}(id)
	}
	wg.Wait()
	return errors.Join(failures...)
}
func (e *Engine) runTicket(ctx context.Context, id string) error {
	var t Ticket
	skip := false
	err := e.state(ctx, true, func(s *State) error {
		var ok bool
		t, ok = s.Tickets[id]
		if !ok {
			return errors.New("missing ticket")
		}
		if t.Status != Pending && t.Status != Running {
			skip = true
			return nil
		}
		t.Status = Running
		s.Tickets[id] = t
		return nil
	})
	if err != nil || skip {
		return err
	}
	inputs := []Event{}
	for _, in := range t.Inputs {
		if in.InScope {
			inputs = append(inputs, in.Event)
		}
	}
	b, _ := json.Marshal(struct {
		Mandate string
		Inputs  []Event
	}{t.Mandate, inputs})
	runID := fmt.Sprintf("worker/%s/%d", id, t.Revision)
	// ModelFactory receives the stable ticket ID as session name via this run ID.
	var result string
	var evidence *Evidence
	if t.Execution == "coding" {
		if e.cfg.Worker == nil {
			return errors.New("coding task requires its Harness worker; refusing to downgrade to a plan")
		}
		proof, runErr := e.cfg.Worker.Run(ctx, runID, string(b))
		if runErr != nil {
			return runErr
		}
		evidence = &proof
		result = proof.Summary
	} else {
		if e.cfg.Worker != nil {
			return errors.New("plan task cannot silently become a coding task; use a new coding request")
		}
		result, err = e.agent(ctx, "worker", runID, string(b))
		if err != nil {
			return err
		}
	}
	return e.state(ctx, true, func(s *State) error {
		latest := s.Tickets[id]
		if latest.Revision != t.Revision {
			return nil
		} // New input remains pending; never overwrite it.
		latest.Result = result
		latest.Evidence = evidence
		latest.Status = Ready
		s.Tickets[id] = latest
		key := fmt.Sprintf("result/%s/%d", id, t.Revision)
		if _, exists := s.Outbox[key]; !exists {
			s.Outbox[key] = Message{ID: key, TicketID: id, Body: result}
		}
		return nil
	})
}

// Accept is a trusted host action, not a model decision or a public HTTP handler.
func (e *Engine) Accept(ctx context.Context, id string, authorizedHuman bool) error {
	if !authorizedHuman {
		return ErrUnauthorized
	}
	current, err := e.Snapshot(ctx)
	if err != nil {
		return err
	}
	ticket, ok := current.Tickets[id]
	if !ok || ticket.Status != Ready {
		return errors.New("ticket is not ready for review")
	}
	if ticket.Evidence != nil {
		if e.cfg.Worker == nil {
			return errors.New("Harness verifier is required to accept a coding task")
		}
		if err = e.cfg.Worker.Verify(ctx, *ticket.Evidence); err != nil {
			return err
		}
	}
	return e.state(ctx, true, func(s *State) error {
		latest := s.Tickets[id]
		if latest.Status != Ready || latest.Revision != ticket.Revision || digest(latest.Evidence) != digest(ticket.Evidence) {
			return errors.New("ticket changed during review")
		}
		latest.Status = Accepted
		s.Tickets[id] = latest
		return nil
	})
}
