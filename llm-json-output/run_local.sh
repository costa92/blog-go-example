#!/bin/bash
# Runs every local experiment; one model on the GPU at a time.
set -u
cd "$(dirname "$0")"
for m in qwen2.5-coder:3b qwen2.5-coder:7b llama3.1:8b; do
  python3 bench.py ollama:$m prompt,json,schema main.jsonl --tag main
  ollama ps; nvidia-smi --query-gpu=memory.used --format=csv,noheader
  python3 bench.py ollama:$m bare_json,bare_schema main.jsonl --tag bare
  python3 bench.py ollama:$m strict_schema,reason_first,reason_last main.jsonl --tag variants
  python3 bench.py ollama:$m prompt,json,schema main.jsonl --tag trunc --num-predict 40
  python3 bench.py ollama:$m prompt,schema main.jsonl --tag hot --temp 0.8 --reps 3
  ollama stop $m
done
m=gemma4:latest
python3 bench.py ollama:$m prompt,json,schema main.jsonl --tag main --think false
ollama ps; nvidia-smi --query-gpu=memory.used --format=csv,noheader
python3 bench.py ollama:$m bare_schema,strict_schema main.jsonl --tag variants --think false
python3 bench.py ollama:$m schema main.jsonl --tag think --cases 0,1,4,7,13,20,25,33 --num-predict 512
python3 bench.py ollama:$m schema main.jsonl --tag think --cases 0,1,4,7,13,20,25,33 --num-predict 4096
ollama stop $m
echo ALL_DONE
