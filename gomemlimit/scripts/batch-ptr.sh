#!/usr/bin/env bash
# Main memory matrix. Live set is pointer-linked 64-byte nodes (the GC has to
# traverse it, like a real service heap); garbage is produced at 300 MiB/s.
# Pod: memory limit 256Mi unless noted, CPU limit 2 (GOMAXPROCS=2).
cd "$(dirname "$0")"; mkdir -p ../logs
I=memload:go1.27-mod1.25
r() { n=$1 s=$2 m=$3; shift 3; ./run.sh $n $s $I $m 2 LIVE_PTR=1 CHURN_MIB_S=300 "$@"; }
r z-nolimit      40 1Gi   LIVE_MIB=150
r a-default      40 256Mi LIVE_MIB=150 INTERVAL=200ms
r a2-gctrace     20 256Mi LIVE_MIB=150 GODEBUG=gctrace=1
for l in 60 80 100; do r sweep-live$l 40 256Mi LIVE_MIB=$l; done
r b-limit230     60 256Mi LIVE_MIB=150 GOMEMLIMIT=230MiB
r c-limit230off  60 256Mi LIVE_MIB=150 GOMEMLIMIT=230MiB GOGC=off
r b100-limit230  40 256Mi LIVE_MIB=100 GOMEMLIMIT=230MiB
r c100-off       40 256Mi LIVE_MIB=100 GOMEMLIMIT=230MiB GOGC=off
r d-limit400     40 256Mi LIVE_MIB=150 GOMEMLIMIT=400MiB INTERVAL=200ms
r e-spiral      120 256Mi LIVE_MIB=150 GROW_MIB_S=1 GOMEMLIMIT=230MiB
r f-dapi-bytes   60 256Mi LIVE_MIB=150 GOMEMLIMIT=@limits.memory
r g-dapi-mib     30 256Mi LIVE_MIB=150 GOMEMLIMIT=@limits.memory/1Mi
r h-offheap      60 256Mi LIVE_MIB=150 OFFHEAP_MIB=60 GOMEMLIMIT=230MiB
echo BATCH DONE
