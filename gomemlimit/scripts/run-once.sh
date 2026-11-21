#!/usr/bin/env bash
# Usage: run-once.sh NAME MAX_SECONDS IMAGE MEM_LIMIT CPU_LIMIT [ENV=VAL ...]
# Like run.sh but restartPolicy Never: follows the single container's log
# until it exits (or MAX_SECONDS), so the lines right before an OOM kill
# are kept.
set -u
cd "$(dirname "$0")"; mkdir -p ../logs
K="kubectl --kubeconfig ${KUBECONFIG_FILE:-$PWD/../kubeconfig}"
name=$1 secs=$2; shift 2
./pod.sh "$name" "$@" | sed 's/restartPolicy: Always/restartPolicy: Never/' > ../logs/$name.yaml
$K apply -f ../logs/$name.yaml >/dev/null
$K wait --for=jsonpath='{.status.phase}'=Running pod/$name --timeout=60s >/dev/null
echo "running $(date +%T)" > ../logs/$name.meta
timeout "$secs" $K logs -f $name > ../logs/$name.log 2>&1
$K wait --for=jsonpath='{.status.phase}'=Failed pod/$name --timeout=5s >/dev/null 2>&1
echo "done $(date +%T)" >> ../logs/$name.meta
uid=$($K get pod $name -o jsonpath='{.metadata.uid}' | tr - _)
cg=$(docker exec gomem-control-plane find /sys/fs/cgroup/kubelet.slice -maxdepth 3 -type d -name "*pod${uid}.slice" | head -1)
{ echo "# pod cgroup $cg"; docker exec gomem-control-plane sh -c "echo memory.max=\$(cat $cg/memory.max); echo memory.peak=\$(cat $cg/memory.peak); cat $cg/memory.events; echo; cat $cg/cpu.stat"; } > ../logs/$name.events 2>&1
$K get pod $name > ../logs/$name.get
$K describe pod $name > ../logs/$name.describe
$K get pod $name -o jsonpath='{range .status.containerStatuses[*]}{.state.terminated.reason} {.state.terminated.exitCode} {.state.terminated.startedAt} {.state.terminated.finishedAt}{"\n"}{end}' > ../logs/$name.status
$K delete pod $name --grace-period=1 --wait=false >/dev/null
echo "== $name"; cat ../logs/$name.get ../logs/$name.status ../logs/$name.events; tail -3 ../logs/$name.log
