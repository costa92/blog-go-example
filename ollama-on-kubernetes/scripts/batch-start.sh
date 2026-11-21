#!/usr/bin/env bash
# Cold start variants. The model is ~400 MB and pulled from the Ollama registry inside the Pod.
set -euo pipefail
cd "$(dirname "$0")"
# c1: emptyDir, pull in the container, readinessProbe on /
STORE=emptydir PULL=1 PROBE=root N=900 ./run-cold.sh c1-emptydir-root
# c2: PVC (first run fills it), pull + warm-up, readinessProbe = /tmp/ready written after warm-up
STORE=pvc PULL=1 WARM=1 PROBE=ready-file N=900 ./run-cold.sh c2-pvc-first
# c3: PVC already has the model, still runs `ollama pull` (re-checks the registry)
KEEP_PVC=1 STORE=pvc PULL=1 WARM=1 PROBE=ready-file N=900 ./run-cold.sh c3-pvc-repull
# c4: PVC already has the model, no pull, only warm-up
KEEP_PVC=1 STORE=pvc PULL=0 WARM=1 PROBE=ready-file N=900 ./run-cold.sh c4-pvc-nopull
