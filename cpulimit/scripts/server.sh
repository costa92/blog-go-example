#!/usr/bin/env bash
# Print the cpu Deployment + Service.
# Env: LIMIT (e.g. 1 or 500m; empty = no CPU limit), REQUEST (default = LIMIT,
#      or 100m when LIMIT is empty), SERVER_ENV ("K=V K=V", e.g. GOMAXPROCS=1)
set -euo pipefail
LIMIT=${LIMIT:-}; REQUEST=${REQUEST:-${LIMIT:-100m}}
envs=""
for kv in ${SERVER_ENV:-}; do
  envs+="
        - {name: ${kv%%=*}, value: \"${kv#*=}\"}"
done
limits=""
[[ -n $LIMIT ]] && limits="
          limits: {cpu: \"$LIMIT\", memory: 256Mi}"
cat <<YAML
apiVersion: apps/v1
kind: Deployment
metadata: {name: cpu}
spec:
  replicas: 1
  selector: {matchLabels: {app: cpu}}
  template:
    metadata: {labels: {app: cpu}}
    spec:
      containers:
      - name: server
        image: cpulim:v1
        imagePullPolicy: Never
        command: [/server]
        ports: [{containerPort: 8080}]
        readinessProbe:
          httpGet: {path: /healthz, port: 8080}
          periodSeconds: 2
        resources:
          requests: {cpu: "$REQUEST", memory: 64Mi}$limits
        env:
        - {name: WORK, value: "${WORK:-5ms}"}$envs
---
apiVersion: v1
kind: Service
metadata: {name: cpu}
spec:
  selector: {app: cpu}
  ports: [{port: 8080, targetPort: 8080}]
YAML
