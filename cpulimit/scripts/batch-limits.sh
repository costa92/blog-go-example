#!/usr/bin/env bash
# Limit sweep at ~50% of the limit, Poisson arrivals: default GOMAXPROCS vs forced to the node CPU count.
set -euo pipefail
cd "$(dirname "$0")/.."
export POISSON=1
for spec in 500m:50 1:100 2:200 4:400; do
  l=${spec%:*}; r=${spec#*:}
  LIMIT=$l scripts/run.sh lim-$l-def $r
  LIMIT=$l SERVER_ENV="GOMAXPROCS=$(nproc)" scripts/run.sh lim-$l-p$(nproc) $r
  REQUEST=$l scripts/run.sh nolim-$l $r
done
