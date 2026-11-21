#!/usr/bin/env bash
# Time from `kubectl delete pod` to the pod being gone, with and without forwarding SIGTERM.
set -euo pipefail
mkdir -p "$(dirname "$0")/../logs"
cd "$(dirname "$0")"
for t in "" 1; do
  name=g-trap${t:-0}
  ./k delete deploy ollama --ignore-not-found --wait >/dev/null
  STORE=pvc PULL=0 WARM=1 PROBE=ready-file TRAP=$t bash ollama.sh | ./k apply -f - >/dev/null
  ./k rollout status deploy/ollama --timeout=300s >/dev/null
  pod=$(./k get pod -l app=ollama -o jsonpath='{.items[0].metadata.name}')
  s=$(date +%s.%N); ./k delete pod "$pod" --wait >/dev/null; e=$(date +%s.%N)
  echo "$name delete-wait $(echo "$e - $s" | bc) s" | tee ../logs/$name.log
  ./k get events --field-selector involvedObject.name=$pod -o custom-columns=T:.lastTimestamp,R:.reason,M:.message --no-headers | tail -4 >> ../logs/$name.log
done
