#!/usr/bin/env bash
# Rolling update (kubectl rollout restart at 20s), 2 replicas, default client.
set -euo pipefail
cd "$(dirname "$0")"
L="LATENCY=10ms"
SERVER_ENV="$L" ./run.sh a2-baseline scale4
SERVER_ENV="$L" READINESS=0 ./run.sh r1-bare restart
SERVER_ENV="$L" READINESS=1 ./run.sh r2-probe restart
SERVER_ENV="$L" READINESS=1 PRESTOP_SLEEP=5 ./run.sh r3-probe-prestop5 restart
SERVER_ENV="$L SHUTDOWN_DELAY=5s" READINESS=1 ./run.sh r4-probe-drain5 restart
SERVER_ENV="$L" READINESS=0 ./run.sh r5-bare-conc32 restart WORKERS=32 RPS=800
SERVER_ENV="$L" READINESS=1 PRESTOP_SLEEP=5 ./run.sh r6-prestop5-conc32 restart WORKERS=32 RPS=800
