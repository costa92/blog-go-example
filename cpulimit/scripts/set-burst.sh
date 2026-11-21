#!/usr/bin/env bash
# set-burst.sh UID BURST_US: write cpu.max.burst on the node for the pod slice
# and every container scope in it that has a CPU limit. Kubernetes has no
# field for this; it goes straight into the kind node's cgroupfs and is lost
# when the Pod is recreated.
set -euo pipefail
uid=${1//-/_}; burst=$2
docker exec -i "${KIND_NODE:-cpulim-control-plane}" sh -s "$uid" "$burst" <<'SH'
set -e
pod=$(find /sys/fs/cgroup/kubelet.slice -maxdepth 3 -type d -name "*pod$1.slice")
for d in "$pod" "$pod"/cri-containerd-*.scope; do
  case "$(cat "$d/cpu.max")" in max*) continue ;; esac
  echo "$2" > "$d/cpu.max.burst"
  echo "${d#/sys/fs/cgroup/} cpu.max=$(cat "$d/cpu.max") cpu.max.burst=$(cat "$d/cpu.max.burst")"
done
SH
