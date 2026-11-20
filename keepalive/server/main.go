// server answers every request with its pod name.
//
// Env:
//
//	POD_NAME          returned in the body and X-Pod header
//	MAX_REQS_PER_CONN  >0: after this many requests on one connection, reply
//	                   with "Connection: close" so the client reconnects
//	H2C               non-empty: also accept HTTP/2 without TLS (h2c)
//	LATENCY           sleep this long in every / request (simulated work)
//	SHUTDOWN_DELAY    on SIGTERM, fail /ready and keep serving this long
//	                   before Server.Shutdown (default 0)
package main

import (
	"context"
	"fmt"
	"log"
	"net"
	"net/http"
	"os"
	"os/signal"
	"strconv"
	"sync/atomic"
	"syscall"
	"time"
)

type connKey struct{}

func main() {
	pod := os.Getenv("POD_NAME")
	maxReqs, _ := strconv.Atoi(os.Getenv("MAX_REQS_PER_CONN"))
	delay, _ := time.ParseDuration(os.Getenv("SHUTDOWN_DELAY"))
	latency, _ := time.ParseDuration(os.Getenv("LATENCY"))
	var draining atomic.Bool
	var conns atomic.Int64

	mux := http.NewServeMux()
	mux.HandleFunc("/ready", func(w http.ResponseWriter, r *http.Request) {
		if draining.Load() {
			http.Error(w, "draining", http.StatusServiceUnavailable)
			return
		}
		fmt.Fprintln(w, "ok")
	})
	mux.HandleFunc("/", func(w http.ResponseWriter, r *http.Request) {
		if maxReqs > 0 {
			if n, ok := r.Context().Value(connKey{}).(*atomic.Int64); ok && n.Add(1) >= int64(maxReqs) {
				w.Header().Set("Connection", "close")
			}
		}
		time.Sleep(latency)
		w.Header().Set("X-Pod", pod)
		fmt.Fprintln(w, pod)
	})

	protocols := new(http.Protocols)
	protocols.SetHTTP1(true)
	if os.Getenv("H2C") != "" {
		protocols.SetUnencryptedHTTP2(true)
	}
	srv := &http.Server{
		Addr:      ":8080",
		Handler:   mux,
		Protocols: protocols,
		ConnContext: func(ctx context.Context, c net.Conn) context.Context {
			conns.Add(1)
			return context.WithValue(ctx, connKey{}, new(atomic.Int64))
		},
	}

	go func() {
		ch := make(chan os.Signal, 1)
		signal.Notify(ch, syscall.SIGTERM, syscall.SIGINT)
		<-ch
		log.Printf("SIGTERM: draining for %s, %d connections accepted so far", delay, conns.Load())
		draining.Store(true)
		time.Sleep(delay)
		ctx, cancel := context.WithTimeout(context.Background(), 20*time.Second)
		defer cancel()
		log.Printf("Shutdown: %v", srv.Shutdown(ctx))
	}()
	log.Printf("%s listening, latency=%s maxReqsPerConn=%d h2c=%v", pod, latency, maxReqs, os.Getenv("H2C") != "")
	if err := srv.ListenAndServe(); err != http.ErrServerClosed {
		log.Fatal(err)
	}
}
