// client sends a steady request rate to TARGET and prints, once per
// second, how many responses came from each pod and how many new TCP
// connections were dialed.
//
// Env:
//
//	TARGET             URL, e.g. http://echo:8080/
//	WORKERS            concurrent request loops (default 8)
//	RPS                total requests per second (default 200)
//	DURATION           stop after this long (default 60s)
//	MAX_IDLE_PER_HOST  Transport.MaxIdleConnsPerHost (default 0 = Go default 2)
//	MAX_CONNS_PER_HOST Transport.MaxConnsPerHost (default 0 = unlimited)
//	IDLE_TIMEOUT       Transport.IdleConnTimeout (default 90s, the Go default)
//	CLOSE_IDLE_EVERY   call Transport.CloseIdleConnections at this interval
//	H2C                non-empty: speak HTTP/2 without TLS
//	HEADLESS           host name of a headless Service: resolve it every
//	                   RESOLVE_EVERY (default 5s) and round-robin over the IPs
package main

import (
	"context"
	"fmt"
	"io"
	"net"
	"net/http"
	"net/http/httptrace"
	"net/url"
	"os"
	"sort"
	"strconv"
	"strings"
	"sync"
	"sync/atomic"
	"time"
)

func envInt(k string, def int) int {
	if v, err := strconv.Atoi(os.Getenv(k)); err == nil {
		return v
	}
	return def
}

func envDur(k string, def time.Duration) time.Duration {
	if v, err := time.ParseDuration(os.Getenv(k)); err == nil {
		return v
	}
	return def
}

type stats struct {
	mu    sync.Mutex
	pods  map[string]int
	errs  map[string]int
	dials atomic.Int64
	reqs  atomic.Int64
}

func (s *stats) swap() (map[string]int, map[string]int) {
	s.mu.Lock()
	defer s.mu.Unlock()
	p, e := s.pods, s.errs
	s.pods, s.errs = map[string]int{}, map[string]int{}
	return p, e
}

func main() {
	target := os.Getenv("TARGET")
	workers := envInt("WORKERS", 8)
	rps := envInt("RPS", 200)
	dur := envDur("DURATION", 60*time.Second)

	tr := http.DefaultTransport.(*http.Transport).Clone()
	tr.MaxIdleConnsPerHost = envInt("MAX_IDLE_PER_HOST", 0)
	tr.MaxConnsPerHost = envInt("MAX_CONNS_PER_HOST", 0)
	tr.IdleConnTimeout = envDur("IDLE_TIMEOUT", 90*time.Second)
	if os.Getenv("H2C") != "" {
		p := new(http.Protocols)
		p.SetUnencryptedHTTP2(true)
		tr.Protocols = p
	}
	client := &http.Client{Transport: tr, Timeout: 5 * time.Second}

	if every := envDur("CLOSE_IDLE_EVERY", 0); every > 0 {
		go func() {
			for range time.Tick(every) {
				tr.CloseIdleConnections()
			}
		}()
	}

	// Headless mode: keep a fresh list of pod IPs and pick them in turn.
	var ips atomic.Pointer[[]string]
	var rr atomic.Uint64
	headless := os.Getenv("HEADLESS")
	if headless != "" {
		resolve := func() {
			addrs, err := net.DefaultResolver.LookupHost(context.Background(), headless)
			if err == nil && len(addrs) > 0 {
				sort.Strings(addrs)
				if old := ips.Load(); old == nil || strings.Join(*old, ",") != strings.Join(addrs, ",") {
					fmt.Printf("resolve %s: %d IPs %v\n", headless, len(addrs), addrs)
				}
				ips.Store(&addrs)
			}
		}
		resolve()
		go func() {
			for range time.Tick(envDur("RESOLVE_EVERY", 5*time.Second)) {
				resolve()
			}
		}()
	}
	u, _ := url.Parse(target)

	st := &stats{pods: map[string]int{}, errs: map[string]int{}}
	trace := &httptrace.ClientTrace{
		GotConn: func(i httptrace.GotConnInfo) {
			if !i.Reused {
				st.dials.Add(1)
			}
		},
	}

	start := time.Now()
	interval := time.Duration(int64(time.Second) * int64(workers) / int64(rps))
	var wg sync.WaitGroup
	for w := 0; w < workers; w++ {
		wg.Add(1)
		go func(w int) {
			defer wg.Done()
			// Spread the workers evenly over one interval so their requests
			// do not all start at the same instant.
			time.Sleep(interval * time.Duration(w) / time.Duration(workers))
			tick := time.NewTicker(interval)
			defer tick.Stop()
			for time.Since(start) < dur {
				<-tick.C
				reqURL := target
				if headless != "" {
					list := *ips.Load()
					ip := list[rr.Add(1)%uint64(len(list))]
					reqURL = u.Scheme + "://" + net.JoinHostPort(ip, u.Port()) + u.Path
				}
				req, _ := http.NewRequestWithContext(httptrace.WithClientTrace(context.Background(), trace), "GET", reqURL, nil)
				resp, err := client.Do(req)
				st.reqs.Add(1)
				if err != nil {
					msg := err.Error()
					if i := strings.LastIndex(msg, ": "); i >= 0 {
						msg = msg[i+2:]
					}
					st.mu.Lock()
					st.errs[msg]++
					st.mu.Unlock()
					continue
				}
				io.Copy(io.Discard, resp.Body)
				resp.Body.Close()
				key := resp.Header.Get("X-Pod")
				if resp.StatusCode != 200 {
					key = fmt.Sprintf("HTTP%d", resp.StatusCode)
				}
				st.mu.Lock()
				st.pods[key]++
				st.mu.Unlock()
			}
		}(w)
	}

	fmt.Printf("start target=%s workers=%d rps=%d maxIdlePerHost=%d maxConnsPerHost=%d idleTimeout=%s closeIdleEvery=%s h2c=%v headless=%q\n",
		target, workers, rps, tr.MaxIdleConnsPerHost, tr.MaxConnsPerHost, tr.IdleConnTimeout, os.Getenv("CLOSE_IDLE_EVERY"), os.Getenv("H2C") != "", headless)
	done := make(chan struct{})
	go func() { wg.Wait(); close(done) }()
	sec := time.NewTicker(time.Second)
	var lastDials int64
	for n := 1; ; n++ {
		select {
		case <-done:
			fmt.Println("done")
			return
		case <-sec.C:
		}
		pods, errs := st.swap()
		d := st.dials.Load()
		names := make([]string, 0, len(pods))
		for k := range pods {
			names = append(names, k)
		}
		sort.Strings(names)
		var b strings.Builder
		for _, k := range names {
			fmt.Fprintf(&b, " %s=%d", k, pods[k])
		}
		for k, v := range errs {
			fmt.Fprintf(&b, " ERR[%s]=%d", k, v)
		}
		fmt.Printf("t=%02ds dials=%d%s\n", n, d-lastDials, b.String())
		lastDials = d
	}
}
