#!/usr/bin/env bash
# 用法: batch.sh OUT MODEL [agent.py 的其他参数]；整批拿着 GPU 锁跑，避免和别的任务抢显卡
set -euo pipefail
cd "$(dirname "$0")"
out=$1 model=$2; shift 2
LOCK=${GPU_LOCK:-/tmp/gpu.lock}
exec flock "$LOCK" python3 agent.py --model "$model" --out "logs/$out.jsonl" "$@"
