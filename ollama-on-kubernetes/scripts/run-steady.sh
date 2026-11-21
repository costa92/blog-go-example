#!/usr/bin/env bash
# run-steady.sh NAME : deploy ollama (env from ollama.sh, PVC kept), wait until Ready,
# run client.sh to completion (N/SLEEP/OPTS from env), optionally `rollout restart` at AT seconds,
# then save logs plus the container's cpu.stat / memory.events and the pod-level memory.events.
set -euo pipefail
mkdir -p "$(dirname "$0")/../logs"
cd "$(dirname "$0")"; n=$1
./k delete deploy ollama --ignore-not-found --wait >/dev/null
./k wait --for=delete pod -l app=ollama --timeout=120s >/dev/null 2>&1 || true
./ollama.sh | ./k apply -f - >/dev/null
./k rollout status deploy/ollama --timeout=${READY_TIMEOUT:-600s} >/dev/null || true
pod=$(./k get pod -l app=ollama -o jsonpath='{.items[0].metadata.name}')
cg() { ./k exec $pod -- sh -c 'echo "# cpu.stat"; cat /sys/fs/cgroup/cpu.stat; echo "# cpu.max $(cat /sys/fs/cgroup/cpu.max)"; echo "# memory.max $(cat /sys/fs/cgroup/memory.max) peak $(cat /sys/fs/cgroup/memory.peak 2>/dev/null)"; echo "# memory.events"; cat /sys/fs/cgroup/memory.events' 2>&1 || true; }
cg > ../logs/$n.cg-before
./client.sh
if [[ -n "${AT:-}" ]]; then sleep "$AT"; echo "# $(date -u +%T.%N) rollout restart" > ../logs/$n.t0; ./k rollout restart deploy/ollama >/dev/null; fi
./k wait --for=jsonpath='{.status.phase}'=Succeeded pod/kclient --timeout=${CLIENT_TIMEOUT:-1800s} >/dev/null || true
pod=$(./k get pod -l app=ollama -o jsonpath='{.items[0].metadata.name}')
cg > ../logs/$n.cg-after
uid=$(./k get pod $pod -o jsonpath='{.metadata.uid}' | tr - _)
docker exec ok8s-control-plane sh -c "f=\$(find /sys/fs/cgroup/kubelet.slice /sys/fs/cgroup/kubepods.slice -maxdepth 3 -type d -name '*pod$uid.slice' 2>/dev/null | head -1); echo \"# pod cgroup \$f\"; cat \$f/memory.events; echo peak \$(cat \$f/memory.peak)" > ../logs/$n.podcg 2>&1 || true
./collect.sh $n
./k delete pod kclient --wait=false >/dev/null
