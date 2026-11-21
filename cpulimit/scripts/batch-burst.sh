#!/usr/bin/env bash
# Limit 1 core, 100 rps (50%): burst size x GOMAXPROCS (default = 2 here, 1, node CPU count).
set -euo pipefail
cd "$(dirname "$0")/.."
for b in 1 10 20 40; do
  LIMIT=1 scripts/run.sh burst-$b-def 100 $b
  for p in 1 $(nproc); do
    LIMIT=1 SERVER_ENV="GOMAXPROCS=$p" scripts/run.sh burst-$b-p$p 100 $b
  done
done
REQUEST=1 scripts/run.sh burst-20-nolim 100 20
