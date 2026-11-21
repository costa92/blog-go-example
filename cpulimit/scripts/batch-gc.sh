#!/usr/bin/env bash
# GC almost off: GOGC=off plus GOMEMLIMIT under the 256Mi container limit, so
# the heap still gets collected every few seconds instead of hundreds of times.
set -euo pipefail
cd "$(dirname "$0")/.."
for b in 10 20; do
  LIMIT=1 SERVER_ENV="GOGC=off GOMEMLIMIT=180MiB" scripts/run.sh gcoff-$b-def 100 $b
  LIMIT=1 SERVER_ENV="GOMAXPROCS=$(nproc) GOGC=off GOMEMLIMIT=180MiB" scripts/run.sh gcoff-$b-p$(nproc) 100 $b
done
