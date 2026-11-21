#!/bin/bash
# sequential: one model on GPU at a time
cd "$(dirname "$0")"
for m in qwen2.5-coder:3b qwen2.5-coder:7b llama3.1:8b; do
  for x in $(ollama ps | awk 'NR>1{print $1}'); do ollama stop $x; done
  tag=${m//[:.]/_}
  nvidia-smi --query-gpu=timestamp,memory.used --format=csv,noheader -l 1 > vram_$tag.log &
  sp=$!
  echo "START $m $(date +%T)"
  python3 bench.py ollama:$m 0,0.4,0.8,1.2,1.6 8 grid_local.jsonl > log_$tag.txt 2>&1
  ollama ps >> log_$tag.txt
  kill $sp
  ollama stop $m
  echo "DONE $m $(date +%T)"
done
