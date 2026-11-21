#!/usr/bin/env bash
# run-cold.sh NAME : fresh ollama Deployment (env from ollama.sh), client starts at the same moment;
# stop when the client has seen OK (default 3) HTTP 200s or after MAXWAIT seconds.
set -euo pipefail
mkdir -p "$(dirname "$0")/../logs"
cd "$(dirname "$0")"; n=$1
./k delete deploy ollama --ignore-not-found --wait >/dev/null
./k wait --for=delete pod -l app=ollama --timeout=120s >/dev/null 2>&1 || true
[[ ${KEEP_PVC:-0} == 1 ]] || ./k delete pvc ollama-models --ignore-not-found --wait >/dev/null
echo "# $(date -u +%T.%N) apply" > ../logs/$n.t0
./ollama.sh | ./k apply -f - >/dev/null
./client.sh
end=$((SECONDS + ${MAXWAIT:-1200}))
until [[ $(./k logs kclient 2>/dev/null | grep -c '^200 ') -ge ${OK:-3} ]] || (( SECONDS > end )) ||
  [[ $(./k get pod -l app=ollama -o jsonpath='{.items[0].status.containerStatuses[0].restartCount}') -ge 3 ]]; do sleep 2; done
./collect.sh $n
./k delete pod kclient --wait=false >/dev/null
