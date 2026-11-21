#!/usr/bin/env bash
# cpu.max.burst set on the node, the no-limit baseline for burst 40, and a
# gctrace run to line slow requests up with GC cycles.
set -euo pipefail
cd "$(dirname "$0")/.."
n=$(nproc)
for b in 20 40; do
  LIMIT=1 CPU_BURST_US=100000 scripts/run.sh cburst-$b-def 100 $b
  LIMIT=1 CPU_BURST_US=100000 SERVER_ENV="GOMAXPROCS=$n" scripts/run.sh cburst-$b-p$n 100 $b
done
REQUEST=1 scripts/run.sh burst-40-nolim 100 40
SAVE_SERVER_LOG=1 LIMIT=1 SERVER_ENV="GOMAXPROCS=$n GOGC=off GOMEMLIMIT=180MiB GODEBUG=gctrace=1" scripts/run.sh trace-gcoff-10-p$n 100 10
SAVE_SERVER_LOG=1 LIMIT=1 SERVER_ENV="GOMAXPROCS=2 GOGC=off GOMEMLIMIT=180MiB GODEBUG=gctrace=1" scripts/run.sh trace-gcoff-10-p2 100 10
