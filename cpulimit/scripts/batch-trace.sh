#!/usr/bin/env bash
# Hunt for the rare multi-period stall at GOMAXPROCS=node CPUs, burst 10:
# gctrace on, timestamped server log kept, slow requests listed with due time.
set -euo pipefail
cd "$(dirname "$0")/.."
n=$(nproc)
SAVE_SERVER_LOG=1 LIMIT=1 SERVER_ENV="GOMAXPROCS=$n GODEBUG=gctrace=1" scripts/run.sh trace-10-p$n 100 10 5
SAVE_SERVER_LOG=1 LIMIT=1 SERVER_ENV="GOMAXPROCS=$n GOGC=off GOMEMLIMIT=180MiB GODEBUG=gctrace=1" scripts/run.sh trace2-gcoff-10-p$n 100 10 5
