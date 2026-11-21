// server burns a fixed amount of CPU time per request so CFS throttling
// shows up directly in request latency.
//
// Env:
//
//	WORK      CPU time each /work request consumes (default 5ms). Measured
//	          with the thread's own CPU clock, so it does not depend on
//	          whether the goroutine lands on a fast or slow core, and time
//	          spent throttled or descheduled does not count.
//	ALLOC_KB  garbage allocated per request (default 256), to give the GC
//	          something to do. GOGC applies as usual.
//
// ADDR is the listen address (default :8080).
//
// Endpoints: /work, /cpustat (the container's cgroup cpu.stat and cpu.max
// plus GOMAXPROCS and GC count), /healthz.
package main

import (
	"crypto/sha256"
	"fmt"
	"log"
	"net/http"
	"os"
	"runtime"
	"strconv"
	"syscall"
	"time"
)

const rusageThread = 1 // RUSAGE_THREAD on Linux

func threadCPU() time.Duration {
	var ru syscall.Rusage
	if err := syscall.Getrusage(rusageThread, &ru); err != nil {
		panic(err)
	}
	return time.Duration(ru.Utime.Nano() + ru.Stime.Nano())
}

var sink [32]byte

func burn(d time.Duration, allocKB int) {
	runtime.LockOSThread()
	defer runtime.UnlockOSThread()
	garbage := make([]byte, allocKB<<10)
	buf := garbage
	if len(buf) < 1024 {
		buf = make([]byte, 1024)
	}
	start := threadCPU()
	for {
		for i := 0; i < 32; i++ {
			sink = sha256.Sum256(buf[:1024])
			buf[i] = sink[0]
		}
		if threadCPU()-start >= d {
			return
		}
	}
}

func main() {
	work, err := time.ParseDuration(env("WORK", "5ms"))
	if err != nil {
		log.Fatal(err)
	}
	allocKB, _ := strconv.Atoi(env("ALLOC_KB", "256"))
	cpuMax, _ := os.ReadFile("/sys/fs/cgroup/cpu.max")
	log.Printf("GOMAXPROCS=%d NumCPU=%d cpu.max=%q work=%s allocKB=%d GOGC=%q",
		runtime.GOMAXPROCS(0), runtime.NumCPU(), string(cpuMax), work, allocKB, os.Getenv("GOGC"))

	http.HandleFunc("/work", func(w http.ResponseWriter, r *http.Request) {
		burn(work, allocKB)
		w.Write([]byte("ok\n"))
	})
	http.HandleFunc("/cpustat", func(w http.ResponseWriter, r *http.Request) {
		stat, _ := os.ReadFile("/sys/fs/cgroup/cpu.stat")
		max, _ := os.ReadFile("/sys/fs/cgroup/cpu.max")
		var ms runtime.MemStats
		runtime.ReadMemStats(&ms)
		fmt.Fprintf(w, "%sgomaxprocs %d\nnum_gc %d\ncpu.max %s", stat, runtime.GOMAXPROCS(0), ms.NumGC, max)
	})
	http.HandleFunc("/healthz", func(w http.ResponseWriter, r *http.Request) { w.Write([]byte("ok\n")) })
	log.Fatal(http.ListenAndServe(env("ADDR", ":8080"), nil))
}

func env(k, def string) string {
	if v := os.Getenv(k); v != "" {
		return v
	}
	return def
}
