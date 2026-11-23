#!/usr/bin/env bash
# 文章的主实验：4 个模型 × 4 种报错格式 × 6 个任务；每格温度 0 跑 1 次、温度 0.7 跑 seed 1-5。
# 每个 (模型, 格式) 单独拿一次 GPU 锁，单次持锁不超过十几分钟。
set -euo pipefail
cd "$(dirname "$0")"
for m in ${MODELS:-qwen2.5-coder:7b qwen2.5-coder:3b gemma4:latest llama3.1:8b}; do
  for v in bare sentence json hint; do
    ./batch.sh main "$m" --variant "$v" --temp 0 --seeds 1
    ./batch.sh main "$m" --variant "$v" --temp 0.7 --seeds 1 2 3 4 5
  done
done
