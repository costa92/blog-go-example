// loadgen sends /work requests on a fixed schedule (open loop): request i
// is due at start + i*interval whether or not earlier ones have returned,
// and its latency is measured from that due time. A slow server therefore
// cannot slow the generator down and hide its own stalls (coordinated
// omission).
//
// Env:
//
//	TARGET    base URL, e.g. http://cpu:8080
//	RPS       mean requests per second (default 100)
//	DURATION  measured period (default 30s), after WARMUP (default 5s)
//	BURST     requests sent together in each tick (default 1 = smooth).
//	          With BURST=n the ticks are n/RPS apart, so the mean rate is
//	          unchanged.
//	POISSON   non-empty: exponential gaps between ticks (mean unchanged)
//	          instead of a fixed interval, seeded by SEED (default 1) so
//	          every run sees the same arrival pattern.
//	SLOW_MS   requests at least this slow (default 100) are listed with
//	          their due time (UTC), at most 40 of them, to line up with
//	          server-side timestamps such as gctrace.
//	DUMP      non-empty: also print every latency (ms, 0.1 resolution, in
//	          send order) on one LATS line, for finer histograms.
//
// Output: one summary line with percentiles, a latency histogram, and the
// server's cgroup cpu.stat delta over the measured period.
package main

import (
	"bufio"
	"fmt"
	"io"
	"log"
	"math/rand"
	"net/http"
	"os"
	"sort"
	"strconv"
	"strings"
	"sync"
	"time"
)

func main() {
	target := env("TARGET", "http://cpu:8080")
	rps, _ := strconv.ParseFloat(env("RPS", "100"), 64)
	dur, _ := time.ParseDuration(env("DURATION", "30s"))
	warm, _ := time.ParseDuration(env("WARMUP", "5s"))
	burst, _ := strconv.Atoi(env("BURST", "1"))
	slowMS, _ := strconv.Atoi(env("SLOW_MS", "100"))
	slowAt := time.Duration(slowMS) * time.Millisecond
	poisson := os.Getenv("POISSON") != ""
	seed, _ := strconv.ParseInt(env("SEED", "1"), 10, 64)
	rng := rand.New(rand.NewSource(seed))
	client := &http.Client{
		Timeout:   10 * time.Second,
		Transport: &http.Transport{MaxIdleConnsPerHost: 2000, MaxIdleConns: 2000},
	}
	interval := time.Duration(float64(burst) / rps * float64(time.Second))
	fmt.Printf("start target=%s rps=%g burst=%d interval=%s poisson=%v warmup=%s duration=%s\n", target, rps, burst, interval, poisson, warm, dur)

	var (
		mu      sync.Mutex
		lat     []time.Duration
		errs    int
		maxLag  time.Duration
		wg      sync.WaitGroup
		before  map[string]int64
		slow    []string
		order   []time.Duration
		measure = false
	)
	start := time.Now()
	total := warm + dur
	var offset time.Duration
	for tick := 0; ; tick++ {
		if tick > 0 {
			if poisson {
				offset += time.Duration(rng.ExpFloat64() * float64(interval))
			} else {
				offset += interval
			}
		}
		due := start.Add(offset)
		if due.Sub(start) >= total {
			break
		}
		if d := time.Until(due); d > 0 {
			time.Sleep(d)
		}
		if !measure && due.Sub(start) >= warm {
			before = cpustat(client, target)
			measure = true
		}
		if lag := time.Since(due); measure && lag > maxLag {
			maxLag = lag
		}
		rec := measure
		for b := 0; b < burst; b++ {
			wg.Add(1)
			go func() {
				defer wg.Done()
				resp, err := client.Get(target + "/work")
				if err == nil {
					io.Copy(io.Discard, resp.Body)
					resp.Body.Close()
				}
				l := time.Since(due)
				if !rec {
					return
				}
				mu.Lock()
				if err != nil || resp.StatusCode != 200 {
					errs++
				} else {
					lat = append(lat, l)
					order = append(order, l)
					if l >= slowAt && len(slow) < 40 {
						slow = append(slow, fmt.Sprintf("SLOW due=%s lat=%.1f", due.UTC().Format("15:04:05.000"), ms(l)))
					}
				}
				mu.Unlock()
			}()
		}
	}
	after := cpustat(client, target)
	wg.Wait()

	sort.Slice(lat, func(i, j int) bool { return lat[i] < lat[j] })
	if len(lat) == 0 {
		log.Fatalf("no successful requests, errs=%d", errs)
	}
	p := func(q float64) float64 {
		if len(lat) == 0 {
			return 0
		}
		return ms(lat[int(q*float64(len(lat)-1))])
	}
	d := func(k string) int64 { return after[k] - before[k] }
	fmt.Printf("RESULT n=%d errs=%d p50=%.1f p90=%.1f p99=%.1f p999=%.1f max=%.1f maxlag=%.1f "+
		"periods=%d throttled=%d throttled_ms=%.0f usage_ms=%.0f gc=%d gomaxprocs=%d bursts=%d burst_ms=%.0f\n",
		len(lat), errs, p(.5), p(.9), p(.99), p(.999), ms(lat[len(lat)-1]), ms(maxLag),
		d("nr_periods"), d("nr_throttled"), float64(d("throttled_usec"))/1000, float64(d("usage_usec"))/1000,
		d("num_gc"), after["gomaxprocs"], d("nr_bursts"), float64(d("burst_usec"))/1000)
	edges := []float64{5, 10, 20, 50, 100, 150, 200, 300, 500, 1000}
	counts := make([]int, len(edges)+1)
	for _, l := range lat {
		i := sort.SearchFloat64s(edges, ms(l))
		counts[i]++
	}
	var sb strings.Builder
	lo := 0.0
	for i, c := range counts {
		hi := "inf"
		if i < len(edges) {
			hi = fmt.Sprint(edges[i])
		}
		fmt.Fprintf(&sb, " %g-%sms:%d", lo, hi, c)
		if i < len(edges) {
			lo = edges[i]
		}
	}
	fmt.Println("HIST" + sb.String())
	for _, l := range slow {
		fmt.Println(l)
	}
	if os.Getenv("DUMP") != "" {
		sb.Reset()
		for _, l := range order {
			fmt.Fprintf(&sb, " %.1f", ms(l))
		}
		fmt.Println("LATS" + sb.String())
	}
}

func cpustat(c *http.Client, target string) map[string]int64 {
	m := map[string]int64{}
	resp, err := c.Get(target + "/cpustat")
	if err != nil {
		log.Printf("cpustat: %v", err)
		return m
	}
	defer resp.Body.Close()
	sc := bufio.NewScanner(resp.Body)
	for sc.Scan() {
		f := strings.Fields(sc.Text())
		if len(f) == 2 {
			if v, err := strconv.ParseInt(f[1], 10, 64); err == nil {
				m[f[0]] = v
			}
		}
	}
	return m
}

func ms(d time.Duration) float64 { return float64(d) / 1e6 }

func env(k, def string) string {
	if v := os.Getenv(k); v != "" {
		return v
	}
	return def
}
