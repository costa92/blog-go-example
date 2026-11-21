#!/usr/bin/env bash
# Usage: pod.sh NAME IMAGE MEM_LIMIT CPU_LIMIT [ENV=VAL ...]
# Prints a Pod manifest. ENV value "@limits.memory" or "@limits.memory/1Mi"
# becomes a downward-API resourceFieldRef.
name=$1 image=$2 mem=$3 cpu=$4; shift 4
cat <<YAML
apiVersion: v1
kind: Pod
metadata:
  name: $name
  labels: {app: memload}
spec:
  restartPolicy: Always
  containers:
  - name: app
    image: $image
    imagePullPolicy: Never
    resources:
      requests: {memory: "$mem", cpu: "100m"}
      limits: {memory: "$mem", cpu: "$cpu"}
    env:
YAML
for kv in "$@"; do
  k=${kv%%=*} v=${kv#*=}
  if [[ $v == @limits.memory* ]]; then
    div=${v#@limits.memory}; div=${div#/}
    echo "    - name: $k"
    echo "      valueFrom:"
    echo "        resourceFieldRef:"
    echo "          containerName: app"
    echo "          resource: limits.memory"
    [[ -n $div ]] && echo "          divisor: $div"
  else
    echo "    - {name: $k, value: \"$v\"}"
  fi
done
