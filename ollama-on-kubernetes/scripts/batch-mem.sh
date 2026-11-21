#!/usr/bin/env bash
# Memory limit vs num_ctx. The first request loads the model under the limit.
set -euo pipefail
cd "$(dirname "$0")"
export STORE=pvc PULL=0 KEEP_PVC=1 PROBE=root READY_TIMEOUT=120s CLIENT_TIMEOUT=600s
for m in ${MEMS:-256Mi 512Mi 768Mi 1Gi}; do
  for ctx in ${CTXS:-4096 32768}; do
    MEM=$m N=3 SLEEP=2 OPTS="{\"num_predict\":16,\"num_ctx\":$ctx}" ./run-steady.sh m-$m-ctx$ctx
  done
done
