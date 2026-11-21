#!/usr/bin/env bash
# CPU limit vs generation speed, 128 tokens at temperature 0. Default threads vs num_thread = limit.
set -euo pipefail
cd "$(dirname "$0")"
export STORE=pvc PULL=0 KEEP_PVC=1 MEM=4Gi WARM=1 PROBE=ready-file SLEEP=1
P="Write a Go function that reverses a singly linked list, then explain it step by step."
for c in none 4 2 1; do
  cpu=$c; [[ $c == none ]] && cpu=
  CPU=$cpu N=${N:-2} PROMPT="$P" OPTS='{"num_predict":128,"temperature":0,"seed":1}' ./run-steady.sh u-cpu$c-b
done
for c in 4 2 1; do
  CPU=$c N=${N:-2} PROMPT="$P" OPTS="{\"num_predict\":128,\"temperature\":0,\"seed\":1,\"num_thread\":$c}" ./run-steady.sh u-cpu$c-threads$c-b
done
