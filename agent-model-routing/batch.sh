#!/bin/sh
# 题库批次：每次 run.py 单独拿一次 GPU 锁（和别的实验共用一张卡时用）。不用锁时把 LOCK 设成空。
LOCK=${LOCK-"flock ../../gpu.lock"}
set -e
$LOCK python3 run.py qwen2.5-coder:3b plain
$LOCK python3 run.py qwen2.5-coder:7b plain
$LOCK python3 run.py qwen2.5-coder:0.5b plain
$LOCK python3 run.py qwen2.5-coder:3b conf
$LOCK python3 run.py qwen2.5-coder:3b route
$LOCK python3 run.py qwen2.5-coder:0.5b route
$LOCK python3 run.py llama3.1:8b plain
$LOCK python3 run.py qwen2.5-coder:0.5b conf
for s in 1 2 3; do
  $LOCK python3 run.py qwen2.5-coder:3b plain 0.7 $s
  $LOCK python3 run.py qwen2.5-coder:7b plain 0.7 $s
done
