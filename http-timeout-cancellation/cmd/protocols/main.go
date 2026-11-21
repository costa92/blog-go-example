package main

import (
	"context"
	"encoding/json"
	"flag"
	"fmt"
	"os"
	"runtime"
	"time"

	"github.com/costa92/blog-go-example/http-timeout-cancellation/internal/protocolcase"
)

func choices(value string, all []string) []string {
	if value == "all" {
		return all
	}
	return []string{value}
}

func main() {
	chain := flag.Bool("chain", false, "compare incoming context vs Background on A -> gRPC B")
	forwardDelay := flag.Duration("forward-delay", 20*time.Millisecond, "time A spends before calling B (chain only)")
	protocol := flag.String("protocol", "all", "all, http1, http2, grpc")
	trigger := flag.String("trigger", "all", "all, deadline, client-timeout (HTTP only), cancel, wait-only")
	mode := flag.String("mode", "all", "all, ignore, cooperate, detached")
	timeout := flag.Duration("timeout", 50*time.Millisecond, "caller deadline or wait duration")
	step := flag.Duration("step", 10*time.Millisecond, "duration per simulated work step")
	steps := flag.Int("steps", 20, "number of work steps")
	background := flag.Duration("background-limit", time.Second, "independent bound for detached tasks")
	flag.Parse()
	enc := json.NewEncoder(os.Stdout)
	emit := func(v any) {
		if err := enc.Encode(v); err != nil {
			fmt.Fprintln(os.Stderr, err)
			os.Exit(1)
		}
	}
	emit(map[string]any{"environment": map[string]any{"go": runtime.Version(), "os": runtime.GOOS, "arch": runtime.GOARCH, "grpc_go": "v1.76.0", "timeout_ms": timeout.Milliseconds(), "step_ms": step.Milliseconds(), "steps": *steps, "background_limit_ms": background.Milliseconds()}})
	cfg := protocolcase.Config{Timeout: *timeout, Step: *step, Steps: *steps, BackgroundLimit: *background, ForwardDelay: *forwardDelay}
	if *chain {
		for _, p := range choices(*protocol, []string{"http1", "http2", "grpc"}) {
			for _, pass := range []bool{true, false} {
				r, err := protocolcase.RunChain(context.Background(), cfg, p, pass)
				if err != nil {
					fmt.Fprintln(os.Stderr, err)
					os.Exit(1)
				}
				emit(r)
			}
		}
		return
	}
	for _, p := range choices(*protocol, []string{"http1", "http2", "grpc"}) {
		for _, t := range choices(*trigger, []string{"deadline", "client-timeout", "cancel", "wait-only"}) {
			if p == "grpc" && t == "client-timeout" && *trigger == "all" {
				continue
			}
			for _, m := range choices(*mode, []string{"ignore", "cooperate", "detached"}) {
				r, err := protocolcase.RunCase(context.Background(), cfg, p, t, m)
				if err != nil {
					fmt.Fprintln(os.Stderr, err)
					os.Exit(1)
				}
				emit(r)
			}
		}
	}
}
