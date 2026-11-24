#!/bin/bash
# 依次跑各模型；每 8 道题拿一次 GPU 锁，和别的实验交替用 GPU。
# 用法：LOCK=/path/to/gpu.lock ./batch.sh [--temp 0.7 --seed 2] -- model1 model2 ...
set -e
cd "$(dirname "$0")"
LOCK=${LOCK:-/dev/null}
extra=()
while [ "$1" != "--" ] && [ -n "$1" ]; do extra+=("$1"); shift; done
shift || true
ids=$(python3 -c "import grade; print(' '.join(grade.TASKS))")
for m in "$@"; do
  set -- $ids
  while [ $# -gt 0 ]; do
    chunk=("${@:1:8}"); shift $(( $# < 8 ? $# : 8 ))
    flock "$LOCK" bash -c 'm=$1; shift; n=$1; shift; ex=("${@:1:$n}"); shift $n; for i in "$@"; do python3 run.py "$m" "${ex[@]}" --only "$i" >/dev/null; done' _ "$m" "${#extra[@]}" "${extra[@]}" "${chunk[@]}"
    echo "$(date +%T) $m ${chunk[0]}..${chunk[-1]}"
  done
done
echo ALL DONE
