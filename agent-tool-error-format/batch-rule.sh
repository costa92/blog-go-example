#!/usr/bin/env bash
# 对照实验：系统提示词加一段报错处理规则，其余和 batch-all.sh 相同，写到 logs/rule.jsonl。
set -euo pipefail
cd "$(dirname "$0")"
for m in ${MODELS:-qwen2.5-coder:7b qwen2.5-coder:3b gemma4:latest llama3.1:8b}; do
  for v in bare sentence json hint; do
    ./batch.sh rule "$m" --system rule --variant "$v" --temp 0 --seeds 1
    ./batch.sh rule "$m" --system rule --variant "$v" --temp 0.7 --seeds 1 2 3 4 5
  done
done
