#!/usr/bin/env bash
# kubectl rollout restart at 20s while a client sends one request per second.
set -euo pipefail
cd "$(dirname "$0")"
export STORE=pvc PULL=0 KEEP_PVC=1 N=150 SLEEP=1 AT=20
STRATEGY=Recreate      WARM=0 PROBE=root       ./run-steady.sh r1-recreate-root
STRATEGY=Recreate      WARM=1 PROBE=ready-file ./run-steady.sh r2-recreate-warm
STRATEGY=RollingUpdate WARM=0 PROBE=root       ./run-steady.sh r3-rolling-root
STRATEGY=RollingUpdate WARM=1 PROBE=ready-file ./run-steady.sh r4-rolling-warm
