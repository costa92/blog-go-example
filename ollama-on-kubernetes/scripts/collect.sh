#!/usr/bin/env bash
# collect.sh NAME : save ollama pod timeline, logs and the client log to logs/NAME.*
set -uo pipefail
cd "$(dirname "$0")/.."; mkdir -p logs; k=scripts/k; n=$1
pod=$($k get pod -l app=ollama -o jsonpath='{.items[0].metadata.name}')
{
  echo "# pod $pod"
  $k get pod $pod -o jsonpath='created={.metadata.creationTimestamp}{"\n"}{range .status.conditions[*]}{.type}={.lastTransitionTime}{"\n"}{end}started={.status.containerStatuses[0].state.running.startedAt}{"\n"}restarts={.status.containerStatuses[0].restartCount}{"\n"}last={.status.containerStatuses[0].lastState}{"\n"}image={.status.containerStatuses[0].imageID}{"\n"}'
  echo "# events"
  $k get events --sort-by=.lastTimestamp -o custom-columns=FIRST:.firstTimestamp,LAST:.lastTimestamp,R:.reason,O:.involvedObject.name,M:.message --no-headers | grep -E "ollama|$pod" | tail -40
} > logs/$n.meta
$k logs $pod --timestamps > logs/$n.server.log 2>&1
$k logs ${CLIENT:-kclient} --timestamps > logs/$n.client.log 2>&1
echo "saved logs/$n.*"
