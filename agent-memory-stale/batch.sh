#!/usr/bin/env bash
# 文章用的完整一轮：2 个模型 × 场景 new 的 4 种模式 + 场景 old 的 3 种模式（old 下 gate 与 fp 提示词相同，不重复跑）
# 温度 0.7，seed 1..20。结果追加到 logs/runs.jsonl。
set -euo pipefail
cd "$(dirname "$0")"
LOCK=${GPU_LOCK:-/tmp/gpu.lock}
SEEDS=$(seq 1 "${N:-20}")
for m in ${MODELS:-llama3.1:8b qwen2.5-coder:7b}; do
  flock "$LOCK" python3 agent.py --model "$m" --scenario new --mode none raw fp gate --seeds $SEEDS --out logs/runs.jsonl
  flock "$LOCK" python3 agent.py --model "$m" --scenario old --mode none raw fp --seeds $SEEDS --out logs/runs.jsonl
done
