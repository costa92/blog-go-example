#!/usr/bin/env bash
# run.sh NAME ACTION [CLIENT_ENV...]
# Deploy echo with REPLICAS (2), start a 60s client Pod, run ACTION at AT
# seconds (default 20), save the client log to logs/NAME.log, then clean up.
# ACTION: scale4 | restart | none
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p logs
K="kubectl --kubeconfig ${KUBECONFIG_FILE:-$PWD/kubeconfig}"
name=$1; action=$2; shift 2
AT=${AT:-20}
$K delete deploy echo --ignore-not-found --wait >/dev/null
$K wait --for=delete pod -l app=echo --timeout=60s >/dev/null 2>&1 || true
scripts/echo.sh | $K apply -f - >/dev/null
$K rollout status deploy/echo --timeout=90s >/dev/null
sleep 3
envs=(--env=TARGET=${TARGET:-http://echo:8080/})
for kv in "$@"; do envs+=(--env="$kv"); done
$K delete pod kclient --ignore-not-found --wait >/dev/null
$K run kclient --image=keepalive:v1 --image-pull-policy=Never --restart=Never \
  "${envs[@]}" --command -- /client >/dev/null
$K wait --for=condition=Ready pod/kclient --timeout=60s >/dev/null
sleep "$AT"
echo "# $(date +%T) action=$action at=${AT}s server_env='${SERVER_ENV:-}' readiness=${READINESS:-1} prestop=${PRESTOP_SLEEP:-0}" > logs/$name.meta
case $action in
  scale4) $K scale deploy/echo --replicas=4 >/dev/null ;;
  restart) $K rollout restart deploy/echo >/dev/null ;;
esac
$K wait --for=jsonpath='{.status.phase}'=Succeeded pod/kclient --timeout=120s >/dev/null
$K logs kclient > logs/$name.log
echo "client started $($K get pod kclient -o jsonpath='{.status.containerStatuses[0].state.terminated.startedAt}')" >> logs/$name.meta
$K get pods -l app=echo -o jsonpath='{range .items[*]}{.metadata.name} {.status.podIP} created={.metadata.creationTimestamp} ready={.status.conditions[?(@.type=="Ready")].lastTransitionTime}{"\n"}{end}' >> logs/$name.meta
$K get events --sort-by=.lastTimestamp -o custom-columns=T:.lastTimestamp,R:.reason,O:.involvedObject.name,M:.message --no-headers | grep -E 'echo-|kclient' | tail -40 >> logs/$name.meta || true
for p in $($K get pods -l app=echo -o name); do echo "== $p"; $K logs $p; done >> logs/$name.meta 2>&1 || true
$K delete pod kclient --wait >/dev/null
echo "saved logs/$name.log"
