#!/usr/bin/env bash
# GOMAXPROCS reported by three builds under different K8s CPU limits.
cd "$(dirname "$0")"; mkdir -p ../logs
K="kubectl --kubeconfig ${KUBECONFIG_FILE:-$PWD/../kubeconfig}"
for img in memload:go1.24 memload:go1.27-mod1.24 memload:go1.27-mod1.25; do
  for cpu in 500m 1 1500m 2 4; do
    n=cpu-$(echo $img | tr ':.' '--')-$cpu
    ./pod.sh $n $img 64Mi $cpu ONLY_INFO=1 | sed 's/restartPolicy: Always/restartPolicy: Never/' | $K apply -f - >/dev/null
  done
done
$K wait --for=jsonpath='{.status.phase}'=Succeeded pod -l app=memload --timeout=180s >/dev/null
for p in $($K get pod -l app=memload -o name | sort); do
  printf '%-40s %s\n' "${p#pod/}" "$($K logs $p | sed -E 's/ GOGC=.*memlimit=[0-9]+MiB//; s/ memory.max=.*//')"
done
$K delete pod -l app=memload --wait=false >/dev/null
