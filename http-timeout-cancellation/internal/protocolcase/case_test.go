package protocolcase

import (
	"context"
	"testing"
	"time"
)

func testConfig() Config {
	return Config{Timeout: 25 * time.Millisecond, Step: 5 * time.Millisecond, Steps: 20, BackgroundLimit: time.Second}
}

func TestTransportCancellationDoesNotForceBusinessToStop(t *testing.T) {
	for _, protocol := range []string{"http1", "http2", "grpc"} {
		for _, trigger := range []string{"deadline", "cancel"} {
			t.Run(protocol+"/"+trigger, func(t *testing.T) {
				r, err := RunCase(context.Background(), testConfig(), protocol, trigger, "ignore")
				if err != nil {
					t.Fatal(err)
				}
				if !r.Task.Completed || r.Task.Steps != 20 || r.Task.ParentError == "" {
					t.Fatalf("canceled request must still complete ignored work: %+v", r)
				}
				if protocol == "http2" && r.Task.Protocol != "HTTP/2.0" {
					t.Fatalf("not HTTP/2: %+v", r)
				}
				if r.Task.HasRequestDeadline != (protocol == "grpc" && trigger == "deadline") {
					t.Fatalf("unexpected deadline: %+v", r)
				}
			})
		}
	}
}

func TestCooperativeWorkStopsAcrossProtocols(t *testing.T) {
	for _, protocol := range []string{"http1", "http2", "grpc"} {
		t.Run(protocol, func(t *testing.T) {
			r, err := RunCase(context.Background(), testConfig(), protocol, "deadline", "cooperate")
			if err != nil {
				t.Fatal(err)
			}
			if r.Task.Completed || r.Task.Steps >= 20 || r.Task.WorkError == "" {
				t.Fatalf("work did not stop: %+v", r)
			}
			if protocol == "grpc" && r.ClientError != "DeadlineExceeded" {
				t.Fatalf("gRPC status: %+v", r)
			}
		})
	}
}

func TestNativeHTTPClientTimeoutCancelsServerContext(t *testing.T) {
	for _, protocol := range []string{"http1", "http2"} {
		t.Run(protocol, func(t *testing.T) {
			r, err := RunCase(context.Background(), testConfig(), protocol, "client-timeout", "cooperate")
			if err != nil {
				t.Fatal(err)
			}
			if r.ClientError != "DeadlineExceeded" || r.Task.HasRequestDeadline || r.Task.Completed {
				t.Fatalf("unexpected HTTP timeout: %+v", r)
			}
		})
	}
}

func TestLocalWaitTimeoutDoesNotCancelUnderlyingRequest(t *testing.T) {
	for _, protocol := range []string{"http1", "http2", "grpc"} {
		t.Run(protocol, func(t *testing.T) {
			r, err := RunCase(context.Background(), testConfig(), protocol, "wait-only", "cooperate")
			if err != nil {
				t.Fatal(err)
			}
			if r.ClientError != "LocalWaitTimeout" || r.ActualCallError != "OK" || !r.Task.Completed || r.Task.ParentError != "" {
				t.Fatalf("local wait canceled work: %+v", r)
			}
		})
	}
}

func TestDetachedTaskHasIndependentBound(t *testing.T) {
	for _, protocol := range []string{"http1", "http2", "grpc"} {
		t.Run(protocol, func(t *testing.T) {
			cfg := testConfig()
			r, err := RunCase(context.Background(), cfg, protocol, "cancel", "detached")
			if err != nil {
				t.Fatal(err)
			}
			if !r.Task.Completed || r.Task.ParentError == "" || r.Task.WorkError != "" || !r.Task.HasWorkDeadline {
				t.Fatalf("detachment failed: %+v", r)
			}
			cfg.BackgroundLimit = 40 * time.Millisecond
			r, err = RunCase(context.Background(), cfg, protocol, "cancel", "detached")
			if err != nil {
				t.Fatal(err)
			}
			if r.Task.Completed || r.Task.WorkError != "DeadlineExceeded" {
				t.Fatalf("own deadline did not bound detached task: %+v", r)
			}
		})
	}
}
