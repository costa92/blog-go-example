package protocolcase

import (
	"context"
	"errors"
	"sync"
	"time"

	pb "github.com/costa92/blog-go-example/http-timeout-cancellation/api"
)

type ChainResult struct {
	FrontendProtocol     string  `json:"frontend_protocol"`
	PassedRequestContext bool    `json:"passed_request_context"`
	FrontendHasDeadline  bool    `json:"frontend_has_deadline"`
	ClientError          string  `json:"client_result"`
	ClientWaitMS         float64 `json:"client_wait_ms"`
	BackendEndMS         float64 `json:"backend_end_ms"`
	ForwardDelayMS       float64 `json:"forward_delay_ms"`
	Backend              Task    `json:"backend"`
}

// RunChain sends a deadline-bound call through A to a real gRPC backend B.
// B cooperates with cancellation. Only A's outgoing context choice changes.
func RunChain(ctx context.Context, cfg Config, protocol string, passParent bool) (ChainResult, error) {
	if cfg.Timeout <= 0 || cfg.Step <= 0 || cfg.Steps < 1 {
		return ChainResult{}, errors.New("positive timings required")
	}
	if cfg.ForwardDelay < 0 || cfg.ForwardDelay >= cfg.Timeout {
		return ChainResult{}, errors.New("forward-delay must be nonnegative and shorter than timeout")
	}
	backendTrace := newTrace()
	backend, err := openEndpoint("grpc", backendTrace.service(cfg))
	if err != nil {
		return ChainResult{}, err
	}
	defer backend.close()
	if err = warm(ctx, backend); err != nil {
		return ChainResult{}, err
	}
	var mu sync.Mutex
	frontHadDeadline := false
	frontDone := make(chan struct{})
	frontend, err := openEndpoint(protocol, func(parent context.Context, req *pb.WorkRequest) (*pb.WorkReply, error) {
		defer close(frontDone)
		mu.Lock()
		_, frontHadDeadline = parent.Deadline()
		mu.Unlock()
		if cfg.ForwardDelay > 0 {
			timer := time.NewTimer(cfg.ForwardDelay)
			defer timer.Stop()
			select {
			case <-timer.C:
			case <-parent.Done():
				return nil, parent.Err()
			}
		}
		outgoing := parent
		if !passParent {
			outgoing = context.Background()
		}
		return backend.call(outgoing, req, 0)
	})
	if err != nil {
		return ChainResult{}, err
	}
	defer frontend.close()
	if err = warm(ctx, frontend); err != nil {
		return ChainResult{}, err
	}
	callCtx, cancel := context.WithTimeout(ctx, cfg.Timeout)
	defer cancel()
	returned := make(chan error, 1)
	start := time.Now()
	go func() { _, err := frontend.call(callCtx, &pb.WorkRequest{Mode: "cooperate"}, 0); returned <- err }()
	select {
	case <-backendTrace.started:
	case <-time.After(2 * time.Second):
		return ChainResult{}, errors.New("backend did not start")
	}
	clientErr := <-returned
	r := ChainResult{FrontendProtocol: protocol, PassedRequestContext: passParent, ClientError: label(clientErr), ClientWaitMS: milliseconds(time.Since(start)), ForwardDelayMS: milliseconds(cfg.ForwardDelay)}
	select {
	case <-backendTrace.done:
	case <-time.After(cfg.Step*time.Duration(cfg.Steps) + 2*time.Second):
		return r, errors.New("backend did not stop")
	}
	var ended time.Time
	r.Backend, ended = backendTrace.snapshot()
	r.BackendEndMS = milliseconds(ended.Sub(start))
	select {
	case <-frontDone:
	case <-time.After(time.Second):
		return r, errors.New("frontend did not return")
	}
	mu.Lock()
	r.FrontendHasDeadline = frontHadDeadline
	mu.Unlock()
	return r, nil
}
