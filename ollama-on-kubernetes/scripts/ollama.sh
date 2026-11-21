#!/usr/bin/env bash
# Print an Ollama Deployment + Service.
# Env:
#   MODEL       model to pull at start (default qwen2.5-coder:0.5b)
#   STORE       emptydir | pvc   where /root/.ollama lives (default emptydir)
#   PULL        1 = container pulls MODEL before it is considered ready (default 1)
#   WARM        1 = after pulling, load the model with `ollama run MODEL hi` and touch /tmp/ready
#   PROBE       root | ready-file | none   readinessProbe (default root = httpGet /)
#   CPU, MEM    limits (empty = none); requests = limits when set
#   ENV         extra "K=V K=V" for the ollama container (e.g. OLLAMA_KEEP_ALIVE=30s)
#   STRATEGY    Recreate | RollingUpdate (default Recreate)
#   IMAGE       default ollama/ollama:0.40.16
#   TRAP        1 = forward SIGTERM from the sh wrapper to ollama serve
set -euo pipefail
MODEL=${MODEL:-qwen2.5-coder:0.5b}; STORE=${STORE:-emptydir}; PULL=${PULL:-1}; WARM=${WARM:-0}
PROBE=${PROBE:-root}; IMAGE=${IMAGE:-ollama/ollama:0.40.16}
env=""
for kv in ${ENV:-}; do env+="
        - {name: ${kv%%=*}, value: \"${kv#*=}\"}"; done
res=""
if [[ -n "${CPU:-}${MEM:-}" ]]; then
  l=""; [[ -n "${CPU:-}" ]] && l+="cpu: \"$CPU\", "; [[ -n "${MEM:-}" ]] && l+="memory: \"$MEM\", "
  l="{${l%, }}"
  res="
        resources: {requests: $l, limits: $l}"
fi
probe=""
case $PROBE in
  root) probe="
        readinessProbe: {httpGet: {path: /, port: 11434}, periodSeconds: 1, failureThreshold: 1}" ;;
  ready-file) probe="
        readinessProbe: {exec: {command: [test, -f, /tmp/ready]}, periodSeconds: 1, failureThreshold: 1}" ;;
esac
start='ollama serve & pid=$!; '"${TRAP:+trap \"kill -TERM \$pid; wait \$pid\" TERM; }"'until ollama list >/dev/null 2>&1; do sleep 0.2; done; echo "$(date -u +%T.%N) server up"'
[[ $PULL == 1 ]] && start+="; ollama pull $MODEL >/dev/null 2>&1; echo \"\$(date -u +%T.%N) pulled $MODEL\""
[[ $WARM == 1 ]] && start+="; ollama run $MODEL hi >/dev/null 2>&1; echo \"\$(date -u +%T.%N) warmed\"; touch /tmp/ready"
start+='; wait $pid'
if [[ $STORE == pvc ]]; then
  vol="persistentVolumeClaim: {claimName: ollama-models}"
  cat <<YAML
apiVersion: v1
kind: PersistentVolumeClaim
metadata: {name: ollama-models}
spec: {accessModes: [ReadWriteOnce], resources: {requests: {storage: 5Gi}}}
---
YAML
else
  vol="emptyDir: {}"
fi
cat <<YAML
apiVersion: apps/v1
kind: Deployment
metadata: {name: ollama}
spec:
  replicas: 1
  strategy: {type: ${STRATEGY:-Recreate}}
  selector: {matchLabels: {app: ollama}}
  template:
    metadata: {labels: {app: ollama}}
    spec:
      containers:
      - name: ollama
        image: $IMAGE
        imagePullPolicy: IfNotPresent
        command: [sh, -c, '$start']
        ports: [{containerPort: 11434}]
        env:
        - {name: OLLAMA_HOST, value: "0.0.0.0:11434"}$env$res$probe
        volumeMounts: [{name: models, mountPath: /root/.ollama}]
      volumes:
      - name: models
        $vol
---
apiVersion: v1
kind: Service
metadata: {name: ollama}
spec:
  selector: {app: ollama}
  ports: [{port: 11434, targetPort: 11434}]
YAML
