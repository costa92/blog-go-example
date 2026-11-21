#!/usr/bin/env bash
# Same configs as the burst-40 rows, with every latency dumped (DUMP=1) for
# the fine-grained histogram in the post.
set -euo pipefail
cd "$(dirname "$0")/.."
export DUMP=1
n=$(nproc)
LIMIT=1 SERVER_ENV="GOMAXPROCS=$n" scripts/run.sh fine-40-p$n 100 40
LIMIT=1 SERVER_ENV="GOMAXPROCS=1" scripts/run.sh fine-40-p1 100 40
REQUEST=1 scripts/run.sh fine-40-nolim 100 40
