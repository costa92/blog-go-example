#!/usr/bin/env bash
# All memory experiments: limit 256Mi, cpu limit 2, Go 1.27 (go.mod go 1.25).
cd "$(dirname "$0")"; mkdir -p ../logs
I=memload:go1.27-mod1.25
./run.sh z-nolimit     40 $I 1Gi   2 LIVE_MIB=150 INTERVAL=1s
./run.sh a-default     40 $I 256Mi 2 LIVE_MIB=150 INTERVAL=100ms
for l in 60 80 100 120; do ./run.sh sweep-live$l 30 $I 256Mi 2 LIVE_MIB=$l INTERVAL=1s; done
./run.sh b-limit230    60 $I 256Mi 2 LIVE_MIB=150 GOMEMLIMIT=230MiB INTERVAL=1s
./run.sh c-limit230off 60 $I 256Mi 2 LIVE_MIB=150 GOMEMLIMIT=230MiB GOGC=off INTERVAL=1s
./run.sh d-limit400    40 $I 256Mi 2 LIVE_MIB=150 GOMEMLIMIT=400MiB INTERVAL=100ms
./run.sh e-spiral      90 $I 256Mi 2 LIVE_MIB=150 GROW_MIB_S=3 GOMEMLIMIT=230MiB INTERVAL=1s
./run.sh f-dapi-bytes  60 $I 256Mi 2 LIVE_MIB=150 GOMEMLIMIT=@limits.memory INTERVAL=1s
./run.sh g-dapi-mib    30 $I 256Mi 2 LIVE_MIB=150 GOMEMLIMIT=@limits.memory/1Mi INTERVAL=1s
./run.sh h-offheap     45 $I 256Mi 2 LIVE_MIB=150 OFFHEAP_MIB=60 GOMEMLIMIT=230MiB INTERVAL=1s
echo BATCH DONE
