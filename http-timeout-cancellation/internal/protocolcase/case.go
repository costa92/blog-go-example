// Package protocolcase observes real HTTP/1.1, HTTP/2 and gRPC cancellation.
// Timed steps represent interruptible work; they are not a CPU benchmark.
package protocolcase

import (
	"context"
	"errors"
	"fmt"
	"sync"
	"time"

	pb "github.com/costa92/blog-go-example/http-timeout-cancellation/api"
	"google.golang.org/grpc/status"
)

type Config struct {
	Timeout         time.Duration
	Step            time.Duration
	Steps           int
	BackgroundLimit time.Duration
	ForwardDelay    time.Duration
}

type Task struct {
	Protocol           string  `json:"observed_protocol"`
	HasRequestDeadline bool    `json:"has_request_deadline"`
	RequestBudgetMS    float64 `json:"request_budget_ms,omitempty"`
	HasWorkDeadline    bool    `json:"has_work_deadline"`
	ParentError        string  `json:"parent_error_at_task_end"`
	WorkError          string  `json:"work_error"`
	WorkContextError   string  `json:"work_context_error_at_task_end"`
	Steps              int     `json:"steps_completed"`
	Completed          bool    `json:"completed"`
}

type Result struct {
	Protocol               string  `json:"protocol"`
	Trigger                string  `json:"trigger"`
	Mode                   string  `json:"mode"`
	ClientError            string  `json:"client_wait_result"`
	ActualCallError        string  `json:"actual_call_result"`
	ClientWaitMS           float64 `json:"client_wait_ms"`
	TaskDoneAtClientReturn bool    `json:"task_done_at_client_return"`
	TaskEndMS              float64 `json:"task_end_ms"`
	Task                   Task    `json:"task"`
}

type trace struct {
	mu      sync.Mutex
	started chan struct{}
	done    chan struct{}
	task    Task
	ended   time.Time
}

func newTrace() *trace { return &trace{started: make(chan struct{}), done: make(chan struct{})} }
func (t *trace) snapshot() (Task, time.Time) {
	t.mu.Lock()
	defer t.mu.Unlock()
	return t.task, t.ended
}

func label(err error) string {
	if err == nil {
		return "OK"
	}
	if errors.Is(err, context.DeadlineExceeded) {
		return "DeadlineExceeded"
	}
	if errors.Is(err, context.Canceled) {
		return "Canceled"
	}
	if s, ok := status.FromError(err); ok {
		return s.Code().String()
	}
	return err.Error()
}
func contextError(ctx context.Context) string {
	if ctx.Err() == nil {
		return ""
	}
	return label(ctx.Err())
}
func milliseconds(d time.Duration) float64 { return float64(d.Microseconds()) / 1000 }

func doSteps(ctx context.Context, cfg Config, ignore bool) (int, error) {
	for done := 0; done < cfg.Steps; done++ {
		if ignore {
			time.Sleep(cfg.Step)
			continue
		}
		if err := ctx.Err(); err != nil {
			return done, err
		}
		timer := time.NewTimer(cfg.Step)
		select {
		case <-ctx.Done():
			timer.Stop()
			return done, ctx.Err()
		case <-timer.C:
		}
	}
	return cfg.Steps, nil
}

func (t *trace) service(cfg Config) handler {
	return func(parent context.Context, req *pb.WorkRequest) (*pb.WorkReply, error) {
		mode := req.GetMode()
		if mode != "ignore" && mode != "cooperate" && mode != "detached" {
			return nil, fmt.Errorf("unknown work mode %q", mode)
		}
		workCtx := parent
		cancel := func() {}
		if mode == "detached" {
			workCtx, cancel = context.WithTimeout(context.WithoutCancel(parent), cfg.BackgroundLimit)
		}
		t.mu.Lock()
		t.task.Protocol, _ = parent.Value(protocolKey{}).(string)
		if deadline, ok := parent.Deadline(); ok {
			t.task.HasRequestDeadline = true
			t.task.RequestBudgetMS = milliseconds(time.Until(deadline))
		}
		_, t.task.HasWorkDeadline = workCtx.Deadline()
		t.mu.Unlock()
		close(t.started)
		run := func() error {
			defer cancel()
			steps, err := doSteps(workCtx, cfg, mode == "ignore")
			t.mu.Lock()
			t.task.ParentError = contextError(parent)
			t.task.WorkContextError = contextError(workCtx)
			if err != nil {
				t.task.WorkError = label(err)
			}
			t.task.Steps = steps
			t.task.Completed = err == nil
			t.ended = time.Now()
			t.mu.Unlock()
			close(t.done)
			return err
		}
		if mode == "detached" {
			// The handler may return while this bounded, independently owned task runs.
			go func() { _ = run() }()
			select {
			case <-parent.Done():
				return nil, status.FromContextError(parent.Err()).Err()
			case <-t.done:
				task, _ := t.snapshot()
				if task.WorkError != "" {
					return nil, status.FromContextError(context.DeadlineExceeded).Err()
				}
				return &pb.WorkReply{Outcome: "completed"}, nil
			}
		}
		if err := run(); err != nil {
			return nil, status.FromContextError(err).Err()
		}
		return &pb.WorkReply{Outcome: "completed"}, nil
	}
}

func RunCase(ctx context.Context, cfg Config, protocol, trigger, mode string) (Result, error) {
	if cfg.Timeout <= 0 || cfg.Step <= 0 || cfg.Steps < 1 || cfg.BackgroundLimit <= 0 {
		return Result{}, errors.New("positive timing and steps required")
	}
	if protocol == "grpc" && trigger == "client-timeout" {
		return Result{}, errors.New("Client.Timeout is an HTTP-only option")
	}
	if mode != "ignore" && mode != "cooperate" && mode != "detached" {
		return Result{}, fmt.Errorf("unknown mode %q", mode)
	}
	if trigger != "deadline" && trigger != "client-timeout" && trigger != "cancel" && trigger != "wait-only" {
		return Result{}, fmt.Errorf("unknown trigger %q", trigger)
	}
	t := newTrace()
	e, err := openEndpoint(protocol, t.service(cfg))
	if err != nil {
		return Result{}, err
	}
	defer e.close()
	if err := warm(ctx, e); err != nil {
		return Result{}, err
	}
	callCtx, cancel := context.WithCancel(ctx)
	if trigger == "deadline" {
		cancel()
		callCtx, cancel = context.WithTimeout(ctx, cfg.Timeout)
	}
	defer cancel()
	clientTimeout := time.Duration(0)
	if trigger == "client-timeout" {
		clientTimeout = cfg.Timeout
	}
	returned := make(chan error, 1) // A late result must not block after wait-only returns.
	start := time.Now()
	go func() { _, err := e.call(callCtx, &pb.WorkRequest{Mode: mode}, clientTimeout); returned <- err }()
	select {
	case <-t.started:
	case <-time.After(2 * time.Second):
		return Result{}, errors.New("request did not enter the service")
	case <-ctx.Done():
		return Result{}, ctx.Err()
	}
	var stopCancel *time.Timer
	if trigger == "cancel" {
		stopCancel = time.AfterFunc(cfg.Timeout, cancel)
		defer stopCancel.Stop()
	}
	var clientErr error
	actualReceived := false
	if trigger == "wait-only" {
		timer := time.NewTimer(cfg.Timeout)
		defer timer.Stop()
		select {
		case clientErr = <-returned:
			actualReceived = true
		case <-timer.C:
			clientErr = errors.New("LocalWaitTimeout")
		}
	} else {
		clientErr = <-returned
		actualReceived = true
	}
	r := Result{Protocol: protocol, Trigger: trigger, Mode: mode, ClientError: label(clientErr), ClientWaitMS: milliseconds(time.Since(start))}
	select {
	case <-t.done:
		r.TaskDoneAtClientReturn = true
	default:
	}
	// Even detached tasks are joined before the experiment exits.
	select {
	case <-t.done:
	case <-time.After(cfg.Step*time.Duration(cfg.Steps) + cfg.BackgroundLimit + 2*time.Second):
		return r, errors.New("task did not terminate")
	case <-ctx.Done():
		return r, ctx.Err()
	}
	task, startEnd := t.snapshot()
	r.Task = task
	r.TaskEndMS = milliseconds(startEnd.Sub(start))
	if actualReceived {
		r.ActualCallError = r.ClientError
	} else {
		select {
		case err := <-returned:
			r.ActualCallError = label(err)
		case <-time.After(time.Second):
			return r, errors.New("underlying call did not finish")
		}
	}
	return r, nil
}
