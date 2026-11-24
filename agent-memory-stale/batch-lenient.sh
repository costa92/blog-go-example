#!/usr/bin/env bash
# 与 batch.sh + batch2.sh 相同的 720 次组合，只把客户端兜底换成宽松解析（文字里夹的 JSON 调用也执行）。写 logs/lenient.jsonl。
set -euo pipefail
cd "$(dirname "$0")"
LOCK=${GPU_LOCK:-/tmp/gpu.lock}
SEEDS=$(seq 1 "${N:-20}")
OUT=logs/lenient.jsonl
for m in ${MODELS:-llama3.1:8b qwen2.5-coder:7b}; do
  for sys in plain persist; do
    flock "$LOCK" python3 agent.py --parser lenient --model "$m" --system $sys --scenario new --mode none pointer raw fp gate --seeds $SEEDS --out $OUT
    flock "$LOCK" python3 agent.py --parser lenient --model "$m" --system $sys --scenario old --mode none pointer raw fp --seeds $SEEDS --out $OUT
  done
done
