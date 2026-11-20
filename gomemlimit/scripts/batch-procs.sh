#!/usr/bin/env bash
# Same unthrottled load under a 2-CPU limit, GOMAXPROCS=26 (go.mod go 1.24)
# vs GOMAXPROCS=2 (go.mod go 1.25); plus GODEBUG/GOMAXPROCS overrides.
cd "$(dirname "$0")"; mkdir -p ../logs
o() { n=$1 img=$2; shift 2; ./run-once.sh $n 30 $img 1Gi 2 LIVE_PTR=1 CHURN_MIB_S=0 LIVE_MIB=120 "$@"; }
o mp-mod124 memload:go1.27-mod1.24
o mp-mod125 memload:go1.27-mod1.25
o mp-mod124-godebug memload:go1.27-mod1.24 GODEBUG=containermaxprocs=1
o mp-mod125-env26   memload:go1.27-mod1.25 GOMAXPROCS=26
echo BATCH DONE
