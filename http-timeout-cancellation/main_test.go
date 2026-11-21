package main

import (
	"context"
	"errors"
	"io"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"
)

func TestCanceledWorkStopsBeforeFirstBatch(t *testing.T) {
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	done, _, err := runWork(ctx, 10000, true)
	if done != 0 || !errors.Is(err, context.Canceled) {
		t.Fatalf("done=%d err=%v; want no work and context.Canceled", done, err)
	}
}

func TestIgnoringContextStillCompletesWork(t *testing.T) {
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	done, _, err := runWork(ctx, 10000, false)
	if done != 10000 || err != nil {
		t.Fatalf("done=%d err=%v; want all 10000 hashes", done, err)
	}
}

func TestTimeoutHandlerRespondsBeforeWorkerStops(t *testing.T) {
	started := make(chan struct{})
	release := make(chan struct{})
	finished := make(chan error, 1)
	h := http.TimeoutHandler(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		close(started)
		<-release
		_, err := io.WriteString(w, "late result")
		finished <- err
	}), 20*time.Millisecond, "deadline")
	recorder := httptest.NewRecorder()
	h.ServeHTTP(recorder, httptest.NewRequest(http.MethodGet, "/", nil))
	<-started
	if recorder.Code != http.StatusServiceUnavailable {
		close(release)
		t.Fatalf("status=%d; want 503", recorder.Code)
	}
	select {
	case <-finished:
		t.Fatal("worker finished before it was released")
	default:
	}
	close(release)
	if err := <-finished; !errors.Is(err, http.ErrHandlerTimeout) {
		t.Fatalf("late write err=%v; want ErrHandlerTimeout", err)
	}
}

func TestHTTP1ClientCancellationReachesServer(t *testing.T) {
	started := make(chan struct{})
	canceled := make(chan struct{})
	release := make(chan struct{})
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		close(started)
		<-r.Context().Done()
		close(canceled)
		<-release
	}))
	defer server.Close()
	defer close(release)
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, server.URL, nil)
	if err != nil {
		t.Fatal(err)
	}
	result := make(chan error, 1)
	go func() {
		resp, err := server.Client().Do(req)
		if resp != nil {
			resp.Body.Close()
		}
		result <- err
	}()
	select {
	case <-started:
	case <-time.After(2 * time.Second):
		t.Fatal("handler did not start")
	}
	cancel()
	if err := <-result; !errors.Is(err, context.Canceled) {
		t.Fatalf("client error=%v", err)
	}
	select {
	case <-canceled:
	case <-time.After(2 * time.Second):
		t.Fatal("server did not observe cancellation")
	}
}
