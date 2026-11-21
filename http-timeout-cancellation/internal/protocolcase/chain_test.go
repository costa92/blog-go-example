package protocolcase

import (
	"context"
	"testing"
	"time"
)

func TestDownstreamUsesIncomingCancellation(t *testing.T) {
	for _, protocol := range []string{"http1", "http2", "grpc"} {
		t.Run(protocol, func(t *testing.T) {
			r, err := RunChain(context.Background(), testConfig(), protocol, true)
			if err != nil {
				t.Fatal(err)
			}
			if r.Backend.Completed || r.Backend.WorkError == "" {
				t.Fatalf("downstream failed to cancel: %+v", r)
			}
			if r.Backend.HasRequestDeadline != (protocol == "grpc") {
				t.Fatalf("deadline propagation: %+v", r)
			}
		})
	}
}

func TestGRPCDoesNotRestartBudgetAtNextHop(t *testing.T) {
	cfg := testConfig()
	cfg.Timeout = 100 * time.Millisecond
	cfg.ForwardDelay = 40 * time.Millisecond
	cfg.Steps = 100
	r, err := RunChain(context.Background(), cfg, "grpc", true)
	if err != nil {
		t.Fatal(err)
	}
	// A has already used 40ms; giving B a fresh 100ms would violate this.
	if !r.Backend.HasRequestDeadline || r.Backend.RequestBudgetMS <= 0 || r.Backend.RequestBudgetMS > 70 {
		t.Fatalf("downstream received a fresh budget: %+v", r)
	}
}

func TestBackgroundContextBreaksDownstreamCancellation(t *testing.T) {
	for _, protocol := range []string{"http1", "http2", "grpc"} {
		t.Run(protocol, func(t *testing.T) {
			r, err := RunChain(context.Background(), testConfig(), protocol, false)
			if err != nil {
				t.Fatal(err)
			}
			if !r.Backend.Completed || r.Backend.HasRequestDeadline || r.Backend.ParentError != "" {
				t.Fatalf("background context was unexpectedly canceled: %+v", r)
			}
		})
	}
}
