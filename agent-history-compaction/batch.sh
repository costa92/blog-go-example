#!/bin/sh
# 文章用的全部运行：3 个模型 × 7 种策略 × 5 个 seed × 6 个探针。
# LOCK 指向 GPU 锁文件时，每个 (模型, 策略) 单独拿一次锁，方便和别的任务交替用 GPU。
cd "$(dirname "$0")"
for m in ${MODELS:-qwen2.5:7b-instruct llama3.1:8b gemma4:latest}; do
  for st in ${STRATS:-full32k full8k window pin sysrules summary notes}; do
    ${LOCK:+flock "$LOCK"} python3 agent.py --model "$m" --strategy "$st" --out logs/main.jsonl
  done
done
