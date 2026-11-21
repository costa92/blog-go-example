#!/usr/bin/env bash
# Usage: run.sh NAME SECONDS IMAGE MEM_LIMIT CPU_LIMIT [ENV=VAL ...]
# Runs one Pod for SECONDS, then saves logs, describe and the pod cgroup's
# memory.events under ../logs/NAME.*, and deletes the Pod.
set -u
cd "$(dirname "$0")"; mkdir -p ../logs
K="kubectl --kubeconfig ${KUBECONFIG_FILE:-$PWD/../kubeconfig}"
name=$1 secs=$2; shift 2
./pod.sh "$name" "$@" > ../logs/$name.yaml
$K apply -f ../logs/$name.yaml >/dev/null
$K wait --for=condition=Initialized pod/$name --timeout=60s >/dev/null
echo "applied $(date +%T)" > ../logs/$name.meta
sleep "$secs"
uid=$($K get pod $name -o jsonpath='{.metadata.uid}' | tr - _)
cg=$(docker exec gomem-control-plane find /sys/fs/cgroup/kubelet.slice -maxdepth 3 -type d -name "*pod${uid}.slice" | head -1)
{ echo "# pod cgroup $cg"; docker exec gomem-control-plane sh -c "echo memory.max=\$(cat $cg/memory.max); echo memory.peak=\$(cat $cg/memory.peak); cat $cg/memory.events"; } > ../logs/$name.events
$K get pod $name -o wide > ../logs/$name.get
$K describe pod $name > ../logs/$name.describe
$K logs $name > ../logs/$name.log 2>&1
$K logs $name --previous > ../logs/$name.prev.log 2>&1
$K get pod $name -o jsonpath='{range .status.containerStatuses[*]}{.restartCount} {.lastState.terminated.reason} {.lastState.terminated.exitCode} {.lastState.terminated.startedAt} {.lastState.terminated.finishedAt}{"\n"}{end}' > ../logs/$name.status
# every container attempt, from the kubelet's log files on the node
docker exec gomem-control-plane sh -c "cd /var/log/pods/default_${name}_*/app && for f in \$(ls | sort -n); do echo \"### attempt \$f\"; cat \$f; done" > ../logs/$name.attempts 2>&1
$K delete pod $name --grace-period=1 --wait=false >/dev/null
echo "== $name"; cat ../logs/$name.get ../logs/$name.status ../logs/$name.events
