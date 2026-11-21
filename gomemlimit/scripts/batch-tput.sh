#!/usr/bin/env bash
# Unthrottled garbage (CHURN_MIB_S=0): how much allocation throughput is left
# as GOMEMLIMIT approaches the live heap. Live set 120 MiB of pointer nodes.
cd "$(dirname "$0")"; mkdir -p ../logs
I=memload:go1.27-mod1.25
o() { n=$1 m=$2; shift 2; ./run-once.sh $n 30 $I $m 2 LIVE_PTR=1 CHURN_MIB_S=0 LIVE_MIB=120 DURATION=25s "$@"; }
o t-nolimit 1Gi
for l in 400 300 230 200 180 160; do o t-limit$l 1Gi GOMEMLIMIT=${l}MiB; done
echo BATCH DONE
