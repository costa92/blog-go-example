#!/usr/bin/env bash
# Follow-up runs with restartPolicy Never so the full log up to the kill is kept.
cd "$(dirname "$0")"; mkdir -p ../logs
I=memload:go1.27-mod1.25
o() { n=$1 s=$2; shift 2; ./run-once.sh $n $s $I 256Mi 2 LIVE_PTR=1 "$@"; }
o s1-spiral     150 CHURN_MIB_S=300 LIVE_MIB=150 GROW_MIB_S=1 GOMEMLIMIT=230MiB
o s2-spiral-max 150 CHURN_MIB_S=0   LIVE_MIB=150 GROW_MIB_S=1 GOMEMLIMIT=230MiB
o g2-dapi-mib    60 CHURN_MIB_S=300 LIVE_MIB=150 GOMEMLIMIT=@limits.memory/1Mi INTERVAL=50ms
o h2-offheap     60 CHURN_MIB_S=300 LIVE_MIB=150 OFFHEAP_MIB=60 GOMEMLIMIT=230MiB INTERVAL=100ms
o c60-off        40 CHURN_MIB_S=300 LIVE_MIB=60 GOMEMLIMIT=230MiB GOGC=off
o i-dapi-concat  40 CHURN_MIB_S=300 LIVE_MIB=150 MEM_MIB=@limits.memory/1Mi 'GOMEMLIMIT=$(MEM_MIB)MiB'
echo BATCH DONE
