#!/usr/bin/env bash
# 第二轮：pointer 对照组（plain 提示词，两个场景），以及 persist 提示词下的各模式。追加到 logs/runs.jsonl。
set -euo pipefail
cd "$(dirname "$0")"
LOCK=${GPU_LOCK:-/tmp/gpu.lock}
SEEDS=$(seq 1 "${N:-20}")
for m in ${MODELS:-llama3.1:8b qwen2.5-coder:7b}; do
  flock "$LOCK" python3 agent.py --model "$m" --scenario new old --mode pointer --seeds $SEEDS --out logs/runs.jsonl
  flock "$LOCK" python3 agent.py --model "$m" --system persist --scenario new --mode none pointer raw fp gate --seeds $SEEDS --out logs/runs.jsonl
  flock "$LOCK" python3 agent.py --model "$m" --system persist --scenario old --mode none pointer raw fp --seeds $SEEDS --out logs/runs.jsonl
done
