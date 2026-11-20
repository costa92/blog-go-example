#!/usr/bin/env bash
# Print the echo Deployment and its two Services.
# Env: REPLICAS (2), SERVER_ENV ("K=V K=V"), READINESS (1 = add /ready probe),
#      PRESTOP_SLEEP (seconds, 0 = none)
set -euo pipefail
REPLICAS=${REPLICAS:-2}; READINESS=${READINESS:-1}; PRESTOP_SLEEP=${PRESTOP_SLEEP:-0}
envs=""
for kv in ${SERVER_ENV:-}; do
  envs+="
        - {name: ${kv%%=*}, value: \"${kv#*=}\"}"
done
probe=""
[[ $READINESS == 1 ]] && probe="
        readinessProbe:
          httpGet: {path: /ready, port: 8080}
          periodSeconds: 1
          failureThreshold: 1"
prestop=""
[[ $PRESTOP_SLEEP != 0 ]] && prestop="
        lifecycle:
          preStop:
            sleep: {seconds: $PRESTOP_SLEEP}"
cat <<YAML
apiVersion: apps/v1
kind: Deployment
metadata: {name: echo}
spec:
  replicas: $REPLICAS
  selector: {matchLabels: {app: echo}}
  template:
    metadata: {labels: {app: echo}}
    spec:
      terminationGracePeriodSeconds: 30
      containers:
      - name: echo
        image: keepalive:v1
        imagePullPolicy: Never
        command: [/server]
        ports: [{containerPort: 8080}]
        env:
        - name: POD_NAME
          valueFrom: {fieldRef: {fieldPath: metadata.name}}$envs$probe$prestop
---
apiVersion: v1
kind: Service
metadata: {name: echo}
spec:
  selector: {app: echo}
  ports: [{port: 8080, targetPort: 8080}]
---
apiVersion: v1
kind: Service
metadata: {name: echo-headless}
spec:
  clusterIP: None
  selector: {app: echo}
  ports: [{port: 8080, targetPort: 8080}]
YAML
