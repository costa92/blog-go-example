#!/bin/sh
# 计时实验放在同一次 GPU 锁里跑完，避免别的实验中途加载模型。
set -e
S=qwen2.5-coder:3b B=qwen2.5-coder:7b
nvidia-smi --query-gpu=memory.used,memory.total --format=csv
python3 swap.py $S $B
for rule in small big valid lp+valid:-0.02; do python3 cascade.py $S $B $rule 30m; done
python3 cascade.py $S $B lp+valid:-0.02 0
