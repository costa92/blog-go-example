// memload keeps a fixed live heap, churns short-lived garbage and prints
// runtime/metrics plus the container's cgroup memory every INTERVAL.
//
// Env:
//
//	LIVE_MIB      steady live set kept for the whole run (default 150)
//	GROW_MIB_S    extra live MiB added per second, never freed (default 0)
//	CHURN_KIB     size of each short-lived object (default 64)
//	CHURN_MIB_S   cap garbage production at this rate (default 0 = as fast as possible)
//	LIVE_PTR      non-empty: build the live set from pointer-linked 64-byte nodes
//	OFFHEAP_MIB   anonymous mmap outside the Go heap, touched once (default 0)
//	DURATION      stop after this long (default 0 = forever)
//	INTERVAL      sampling interval (default 1s); rates are per second
//	ONLY_INFO     non-empty: print the runtime/cgroup header line and exit
package main

import (
	"fmt"
	"os"
	"runtime"
	"runtime/debug"
	"runtime/metrics"
	"strconv"
	"strings"
	"sync/atomic"
	"syscall"
	"time"
)

const mib = 1 << 20

func envInt(k string, def int) int {
	if v, err := strconv.Atoi(os.Getenv(k)); err == nil {
		return v
	}
	return def
}

func touch(b []byte) {
	for i := 0; i < len(b); i += 4096 {
		b[i] = 1
	}
}

func cgroup(name string) string {
	b, err := os.ReadFile("/sys/fs/cgroup/" + name)
	if err != nil {
		return "-"
	}
	return strings.TrimSpace(string(b))
}

func cgMiB(name string) string {
	n, err := strconv.ParseInt(cgroup(name), 10, 64)
	if err != nil {
		return "-"
	}
	return strconv.FormatInt(n/mib, 10)
}

var sink atomic.Pointer[[]byte]

type node struct {
	next *node
	pad  [56]byte
}

// liveSet keeps MiB-sized chunks reachable, either as noscan byte slices or
// as pointer-linked nodes the GC has to traverse.
type liveSet struct {
	ptr    bool
	blocks [][]byte
	head   *node
}

func (l *liveSet) addMiB() {
	if !l.ptr {
		b := make([]byte, mib)
		touch(b)
		l.blocks = append(l.blocks, b)
		return
	}
	for i := 0; i < mib/64; i++ {
		l.head = &node{next: l.head}
	}
}

func main() {
	start := time.Now()
	live := envInt("LIVE_MIB", 150)
	grow := envInt("GROW_MIB_S", 0)
	churn := envInt("CHURN_KIB", 64) << 10
	offheap := envInt("OFFHEAP_MIB", 0)
	rate := int64(envInt("CHURN_MIB_S", 0)) * mib
	dur, _ := time.ParseDuration(os.Getenv("DURATION"))
	interval, err := time.ParseDuration(os.Getenv("INTERVAL"))
	if err != nil || interval <= 0 {
		interval = time.Second
	}

	fmt.Printf("start go=%s NumCPU=%d GOMAXPROCS=%d GOGC=%q GOMEMLIMIT=%q memlimit=%dMiB cpu.max=%q memory.max=%q\n",
		runtime.Version(), runtime.NumCPU(), runtime.GOMAXPROCS(0), os.Getenv("GOGC"), os.Getenv("GOMEMLIMIT"),
		debug.SetMemoryLimit(-1)/mib, cgroup("cpu.max"), cgroup("memory.max"))
	if os.Getenv("ONLY_INFO") != "" {
		return
	}

	if offheap > 0 {
		m, err := syscall.Mmap(-1, 0, offheap*mib, syscall.PROT_READ|syscall.PROT_WRITE, syscall.MAP_ANON|syscall.MAP_PRIVATE)
		if err != nil {
			panic(err)
		}
		touch(m)
	}

	keep := &liveSet{ptr: os.Getenv("LIVE_PTR") != ""}
	for i := 0; i < live; i++ {
		keep.addMiB()
	}

	fmt.Printf("live set of %d MiB (ptr=%v) ready at t=%.2fs\n", live, keep.ptr, time.Since(start).Seconds())

	var allocated atomic.Int64
	go func() {
		t0 := time.Now()
		for {
			if rate > 0 && allocated.Load() > int64(time.Since(t0).Seconds()*float64(rate)) {
				time.Sleep(time.Millisecond)
				continue
			}
			b := make([]byte, churn)
			touch(b)
			sink.Store(&b)
			allocated.Add(int64(churn))
		}
	}()

	names := []string{
		"/gc/heap/live:bytes",
		"/gc/heap/goal:bytes",
		"/memory/classes/total:bytes",
		"/memory/classes/heap/released:bytes",
		"/gc/cycles/total:gc-cycles",
		"/cpu/classes/gc/total:cpu-seconds",
		"/cpu/classes/total:cpu-seconds",
	}
	samples := make([]metrics.Sample, len(names))
	for i, n := range names {
		samples[i].Name = n
	}
	read := func() []float64 {
		metrics.Read(samples)
		out := make([]float64, len(samples))
		for i, s := range samples {
			if s.Value.Kind() == metrics.KindUint64 {
				out[i] = float64(s.Value.Uint64())
			} else {
				out[i] = s.Value.Float64()
			}
		}
		return out
	}

	prev := read()
	prevAlloc := int64(0)
	perSec := float64(time.Second) / float64(interval)
	growAcc := 0.0
	for {
		time.Sleep(interval)
		growAcc += float64(grow) / perSec
		if growAcc >= 1 {
			for ; growAcc >= 1; growAcc-- {
				keep.addMiB()
			}
		}
		cur := read()
		a := allocated.Load()
		gcFrac := 0.0
		if d := cur[6] - prev[6]; d > 0 {
			gcFrac = (cur[5] - prev[5]) / d
		}
		fmt.Printf("t=%5.2fs live=%4.0fMiB goal=%4.0fMiB runtime=%4.0fMiB gc=%6.0f (+%4.0f/s) gcCPU=%5.1f%% churn=%5.0fMiB/s cg.cur=%sMiB cg.peak=%sMiB\n",
			time.Since(start).Seconds(), cur[0]/mib, cur[1]/mib, (cur[2]-cur[3])/mib, cur[4], (cur[4]-prev[4])*perSec, gcFrac*100,
			float64(a-prevAlloc)/mib*perSec, cgMiB("memory.current"), cgMiB("memory.peak"))
		prev, prevAlloc = cur, a
		runtime.KeepAlive(keep)
		if dur > 0 && time.Since(start) >= dur {
			fmt.Printf("done after %s, total gc=%.0f\n", dur, cur[4])
			return
		}
	}
}
