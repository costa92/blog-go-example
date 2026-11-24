#!/usr/bin/env bash
# Usage: run-netpol.sh <kindnetd|calico> [calico-manifest]
# Creates a single-node kind cluster, applies the same default-deny NetworkPolicy and
# probes client -> server three times: no policy, default-deny, explicit allow.
# Optional: TAG=<label> to keep results of several kind versions apart.
# KUBECONFIG must point at a throwaway file; the script refuses ~/.kube/config.
set -euo pipefail
cni=$1
here=$(cd "$(dirname "$0")" && pwd)
: "${KUBECONFIG:?set KUBECONFIG to a throwaway file}"
[[ $KUBECONFIG == "$HOME/.kube/config" ]] && { echo "refusing to touch ~/.kube/config" >&2; exit 1; }
KIND=${KIND:-kind} KUBECTL=${KUBECTL:-kubectl}
name=np-$cni${TAG:+-$TAG}
case $cni in kindnetd) config=kind-a-kindnetd.yaml ;; calico) config=kind-b-calico.yaml ;; *) exit 2 ;; esac
out=$here/results/$cni${TAG:+-$TAG}.txt
: >"$out"
log() { echo "\$ $*" | tee -a "$out"; "$@" 2>&1 | tee -a "$out"; }

"$KIND" create cluster --name "$name" --config "$here/manifests/$config" --wait 0s
[[ $cni == calico ]] && log "$KUBECTL" apply -f "${2:?calico manifest}" >/dev/null
"$KUBECTL" wait --for=condition=Ready node --all --timeout=300s
[[ $cni == calico ]] && "$KUBECTL" -n kube-system rollout status ds/calico-node --timeout=600s

log "$KIND" version
log "$KUBECTL" version
log "$KUBECTL" get pods -n kube-system -o custom-columns=NAME:.metadata.name,IMAGE:.spec.containers[0].image -l 'k8s-app in (kindnet,calico-node)'

"$KUBECTL" apply -f "$here/manifests/workload.yaml"
"$KUBECTL" wait -n np-demo --for=condition=Ready pod/server pod/client --timeout=300s
ip=$("$KUBECTL" get pod -n np-demo server -o jsonpath='{.status.podIP}')
log "$KUBECTL" get pod -n np-demo -o wide

probe() {
  local phase=$1
  echo "--- $phase" | tee -a "$out"
  log "$KUBECTL" exec -n np-demo client -- curl -sS -o /dev/null -m 5 -w '%{http_code}\n' "http://$ip/" || true
}

probe "no policy"
log "$KUBECTL" apply -f "$here/manifests/default-deny.yaml"
log "$KUBECTL" get networkpolicy -n np-demo
sleep 5
probe "default-deny"
log "$KUBECTL" apply -f "$here/manifests/allow-client-to-server.yaml"
sleep 5
probe "default-deny + allow client->server:80"

# Strip local paths from the transcript.
sed -i "s#$KUBECTL#kubectl#g; s#$KIND#kind#g; s#$here/##g" "$out"
