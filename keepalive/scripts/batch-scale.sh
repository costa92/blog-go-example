#!/usr/bin/env bash
# Every fix, same load: 8 workers, 200 rps, 10ms handler, scale 2 -> 4 at 20s.
set -euo pipefail
cd "$(dirname "$0")"
L="LATENCY=10ms"
SERVER_ENV="$L MAX_REQS_PER_CONN=100"  ./run.sh b-maxreq100 scale4
SERVER_ENV="$L MAX_REQS_PER_CONN=1000" ./run.sh b-maxreq1000 scale4
SERVER_ENV="$L" ./run.sh c-closeidle5s scale4 CLOSE_IDLE_EVERY=5s
SERVER_ENV="$L" ./run.sh d-idle5s scale4 IDLE_TIMEOUT=5s
SERVER_ENV="$L" ./run.sh e-maxconns1 scale4 MAX_CONNS_PER_HOST=1
SERVER_ENV="$L" ./run.sh f-conc32 scale4 WORKERS=32 RPS=800
SERVER_ENV="$L" TARGET=http://echo-headless:8080/ ./run.sh g-headless scale4 HEADLESS=echo-headless
SERVER_ENV="$L H2C=1" ./run.sh h-h2c scale4 H2C=1
SERVER_ENV="$L H2C=1" ./run.sh h-h2c-conc32 scale4 H2C=1 WORKERS=32 RPS=800
SERVER_ENV="$L H2C=1 MAX_REQS_PER_CONN=100" ./run.sh h-h2c-maxreq100 scale4 H2C=1
