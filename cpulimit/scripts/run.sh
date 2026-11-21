#!/usr/bin/env bash
# run.sh NAME RPS [BURST] [REPS]
# POISSON=1 for exponential arrival gaps (same seed every rep unless SEED set).
# CPU_BURST_US writes cpu.max.burst on the node (scripts/set-burst.sh).
# SAVE_SERVER_LOG=1 keeps the server's timestamped log as logs/NAME.server.log.
# Fresh server Pod (LIMIT / REQUEST / SERVER_ENV, see server.sh), then REPS
# (default 3) back-to-back loadgen runs against it. Everything goes to
# logs/NAME.log.
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p logs
K="kubectl --kubeconfig ${KUBECONFIG_FILE:-$PWD/kubeconfig}"
name=$1; rps=$2; burst=${3:-1}; reps=${4:-3}
out=logs/$name.log
$K delete deploy cpu --ignore-not-found --wait >/dev/null
$K wait --for=delete pod -l app=cpu --timeout=60s >/dev/null 2>&1 || true
scripts/server.sh | $K apply -f - >/dev/null
$K rollout status deploy/cpu --timeout=90s >/dev/null
{
  echo "# $(date +%T) name=$name limit=${LIMIT:-none} request=${REQUEST:-} server_env='${SERVER_ENV:-}' rps=$rps burst=$burst poisson=${POISSON:-}"
  $K logs deploy/cpu
  if [ -n "${CPU_BURST_US:-}" ]; then
    scripts/set-burst.sh "$($K get pod -l app=cpu -o jsonpath='{.items[0].metadata.uid}')" "$CPU_BURST_US"
  fi
} > "$out"
for i in $(seq 1 "$reps"); do
  $K delete pod lg --ignore-not-found --wait >/dev/null
  $K run lg --image=cpulim:v1 --image-pull-policy=Never --restart=Never \
    --env=TARGET=http://cpu:8080 --env=RPS="$rps" --env=BURST="$burst" \
    --env=POISSON="${POISSON:-}" --env=SEED="${SEED:-1}" --env=DUMP="${DUMP:-}" --env=DURATION="${DURATION:-30s}" --env=WARMUP="${WARMUP:-5s}" --command -- /loadgen >/dev/null
  $K wait --for=jsonpath='{.status.phase}'=Succeeded pod/lg --timeout=180s >/dev/null
  echo "## rep $i" >> "$out"
  $K logs lg >> "$out"
done
if [ -n "${SAVE_SERVER_LOG:-}" ]; then $K logs --timestamps deploy/cpu > "logs/$name.server.log"; fi
$K delete pod lg --wait >/dev/null
grep RESULT "$out" | awk -v n="$name" '{print n, $0}'
