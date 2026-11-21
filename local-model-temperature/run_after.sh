#!/bin/bash
cd "$(dirname "$0")"
for x in $(ollama ps | awk 'NR>1{print $1}'); do ollama stop $x; done
# top_k/top_p disabled at high temperature
for m in qwen2.5-coder:3b qwen2.5-coder:7b; do
  BENCH_EXTRA='{"top_k":0,"top_p":1.0,"num_predict":512}' python3 bench.py ollama:$m 1.2,1.6 4 grid_notrunc.jsonl > log_notrunc_${m//[:.]/_}.txt 2>&1
  ollama stop $m
done
# determinism on 3b then 7b, num_ctx on 7b
python3 det.py qwen2.5-coder:3b det_local.jsonl > log_det_local_3b.txt 2>&1
ollama stop qwen2.5-coder:3b
python3 det.py qwen2.5-coder:7b det_local.jsonl > log_det_local.txt 2>&1
python3 ctx.py qwen2.5-coder:7b ctx.jsonl > log_ctx.txt 2>&1
ollama stop qwen2.5-coder:7b
echo AFTER-DONE
