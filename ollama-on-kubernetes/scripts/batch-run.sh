#!/usr/bin/env bash
# Steady-state experiments. Needs the PVC filled by batch-start.sh (c2).
set -euo pipefail
cd "$(dirname "$0")"
export STORE=pvc PULL=0 KEEP_PVC=1
GEN='{"num_predict":128,"temperature":0,"seed":1}'
P="Write a Go function that reverses a singly linked list, then explain it step by step."

# keep_alive: 30s server default, requests 45s apart (model unloaded) vs 15s apart (still loaded)
ENV="OLLAMA_KEEP_ALIVE=30s" PROBE=root N=4 SLEEP=45 ./run-steady.sh k1-ka30-gap45
ENV="OLLAMA_KEEP_ALIVE=30s" PROBE=root N=4 SLEEP=15 ./run-steady.sh k2-ka30-gap15

# CPU limit vs generation speed; ollama picks its own thread count unless num_thread is set
for c in none 4 2 1; do
  cpu=$c; [[ $c == none ]] && cpu=
  CPU=$cpu MEM=4Gi WARM=1 PROBE=ready-file N=4 SLEEP=1 PROMPT="$P" OPTS="$GEN" ./run-steady.sh u-cpu$c
done
for c in 4 2 1; do
  CPU=$c MEM=4Gi WARM=1 PROBE=ready-file N=4 SLEEP=1 PROMPT="$P" \
    OPTS="{\"num_predict\":128,\"temperature\":0,\"seed\":1,\"num_thread\":$c}" ./run-steady.sh u-cpu$c-threads$c
done
