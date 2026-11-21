#!/usr/bin/env bash
# Follow-ups: headless with DNS logging, 32 workers with a big idle pool.
set -euo pipefail
cd "$(dirname "$0")"
L="LATENCY=10ms"
SERVER_ENV="$L" TARGET=http://echo-headless:8080/ ./run.sh g2-headless scale4 HEADLESS=echo-headless DURATION=90s
SERVER_ENV="$L" ./run.sh f2-conc32 scale4 WORKERS=32 RPS=800
SERVER_ENV="$L" ./run.sh f3-conc32-idle32 scale4 WORKERS=32 RPS=800 MAX_IDLE_PER_HOST=32
