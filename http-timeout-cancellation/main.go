// Demonstrates request timeouts without pretending to measure production load.
// CPU accounting uses getrusage and supports Linux and macOS.
package main

import (
	"context"
	"crypto/sha256"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"math"
	"net/http"
	"net/http/httptest"
	"os"
	"runtime"
	"sync/atomic"
	"syscall"
	"time"
)

const batch = 1024

func runWork(ctx context.Context, rounds int, cooperative bool) (int, [32]byte, error) {
	var sum [32]byte
	for done := 0; done < rounds; {
		if cooperative {
			if err := ctx.Err(); err != nil {
				return done, sum, err
			}
		}
		end := min(done+batch, rounds)
		for ; done < end; done++ {
			sum = sha256.Sum256(sum[:])
		}
		if done == rounds {
			return done, sum, nil
		}
	}
	return 0, sum, nil
}

func cpuTime() time.Duration {
	var r syscall.Rusage
	if err := syscall.Getrusage(syscall.RUSAGE_SELF, &r); err != nil {
		panic(err)
	}
	return time.Duration(r.Utime.Nano() + r.Stime.Nano())
}

func calibrate(target time.Duration) (int, time.Duration) {
	for rounds := batch; ; rounds *= 2 {
		start := cpuTime()
		_, _, _ = runWork(context.Background(), rounds, false)
		used := cpuTime() - start
		if used >= 80*time.Millisecond {
			n := max(batch, int(float64(rounds)*float64(target)/float64(used))/batch*batch)
			return n, used
		}
	}
}

type settings struct {
	Requests int
	Rounds   int
	Deadline time.Duration
}

type result struct {
	Mode             string  `json:"mode"`
	Run              int     `json:"run"`
	Requests         int     `json:"requests"`
	ClientErrors     int     `json:"client_errors"`
	Status503        int     `json:"status_503"`
	ClientDoneMS     float64 `json:"client_done_ms"`
	ActiveAtReturn   int64   `json:"active_at_return"`
	DrainMS          float64 `json:"drain_ms"`
	TotalCPUMS       float64 `json:"total_cpu_ms"`
	AfterReturnCPUMS float64 `json:"after_return_cpu_ms"`
	Completed        int     `json:"full_work_completed"`
	Canceled         int     `json:"work_canceled"`
	LateWriteErrors  int     `json:"late_write_errors"`
	Hashes           int     `json:"hashes"`
}

type outcome struct {
	done                int
	canceled, lateWrite bool
}
type reply struct {
	status int
	err    error
}

func millis(d time.Duration) float64 {
	return math.Round(float64(d)/float64(time.Millisecond)*1000) / 1000
}

func runScenario(cfg settings, mode string) (result, error) {
	var active atomic.Int64
	ready := make(chan struct{}, cfg.Requests)
	gate := make(chan struct{})
	finished := make(chan outcome, cfg.Requests)
	h := http.Handler(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		active.Add(1)
		ready <- struct{}{}
		<-gate
		done, sum, err := runWork(r.Context(), cfg.Rounds, mode == "cooperative")
		var writeErr error
		if err == nil {
			_, writeErr = fmt.Fprintf(w, "%x\n", sum[:4])
		}
		active.Add(-1)
		finished <- outcome{done, err != nil, errors.Is(writeErr, http.ErrHandlerTimeout)}
	}))
	if mode == "handler-timeout" {
		h = http.TimeoutHandler(h, cfg.Deadline, "deadline\n")
	}
	server := httptest.NewServer(h)
	defer server.Close()
	transport := &http.Transport{MaxConnsPerHost: cfg.Requests, Proxy: nil}
	defer transport.CloseIdleConnections()
	client := &http.Client{Transport: transport, Timeout: cfg.Deadline}
	if mode == "handler-timeout" {
		client.Timeout = 20 * time.Second
	}
	replies := make(chan reply, cfg.Requests)
	cpuStart := cpuTime()
	for i := 0; i < cfg.Requests; i++ {
		go func() {
			resp, err := client.Get(server.URL)
			status := 0
			if resp != nil {
				status = resp.StatusCode
				_, readErr := io.Copy(io.Discard, resp.Body)
				resp.Body.Close()
				if err == nil {
					err = readErr
				}
			}
			replies <- reply{status, err}
		}()
	}
	// No CPU work begins before every request has entered its handler.
	for i := 0; i < cfg.Requests; i++ {
		select {
		case <-ready:
		case <-time.After(2 * time.Second):
			close(gate)
			return result{}, fmt.Errorf("only %d/%d handlers admitted; increase deadline or reduce requests", i, cfg.Requests)
		}
	}
	start := time.Now()
	close(gate)
	r := result{Mode: mode, Requests: cfg.Requests}
	for i := 0; i < cfg.Requests; i++ {
		p := <-replies
		if p.err != nil {
			r.ClientErrors++
		}
		if p.status == 503 {
			r.Status503++
		}
	}
	clientEnd, cpuClientEnd := time.Now(), cpuTime()
	r.ClientDoneMS = millis(clientEnd.Sub(start))
	r.ActiveAtReturn = active.Load()
	for i := 0; i < cfg.Requests; i++ {
		o := <-finished
		r.Hashes += o.done
		if o.done == cfg.Rounds {
			r.Completed++
		}
		if o.canceled {
			r.Canceled++
		}
		if o.lateWrite {
			r.LateWriteErrors++
		}
	}
	r.DrainMS = millis(time.Since(clientEnd))
	cpuEnd := cpuTime()
	r.TotalCPUMS = millis(cpuEnd - cpuStart)
	r.AfterReturnCPUMS = millis(cpuEnd - cpuClientEnd)
	return r, nil
}

func main() {
	requests := flag.Int("requests", 8, "concurrent HTTP/1.1 requests per case")
	runs := flag.Int("runs", 3, "repetitions per case")
	deadline := flag.Duration("deadline", 100*time.Millisecond, "client or handler timeout")
	work := flag.Duration("work", 400*time.Millisecond, "target CPU time per complete job, calibrated once")
	procs := flag.Int("procs", 2, "GOMAXPROCS")
	flag.Parse()
	if *requests < 1 || *runs < 1 || *deadline <= 0 || *work <= 0 || *procs < 1 {
		fmt.Fprintln(os.Stderr, "positive values required")
		os.Exit(2)
	}
	runtime.GOMAXPROCS(*procs)
	rounds, calibrationCPU := calibrate(*work)
	enc := json.NewEncoder(os.Stdout)
	if err := enc.Encode(map[string]any{"go": runtime.Version(), "os": runtime.GOOS, "arch": runtime.GOARCH, "procs": *procs, "rounds": rounds, "deadline_ms": millis(*deadline), "target_work_cpu_ms": millis(*work), "calibration_cpu_ms": millis(calibrationCPU)}); err != nil {
		panic(err)
	}
	for run := 1; run <= *runs; run++ {
		for _, mode := range []string{"client-timeout", "handler-timeout", "cooperative"} {
			r, err := runScenario(settings{*requests, rounds, *deadline}, mode)
			if err != nil {
				fmt.Fprintln(os.Stderr, err)
				os.Exit(1)
			}
			r.Run = run
			if err := enc.Encode(r); err != nil {
				panic(err)
			}
		}
	}
}
