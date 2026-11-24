#!/bin/sh
# 只是当时的补跑记录，复现不需要它：现在的 agent.py 和 batch.sh 已经包含这两处修正，
# 跑完 batch.sh 再跑它会在 logs/main.jsonl 里多出重复的行。
# 第一轮有两个问题，这里补跑：
# 1. 预算、支付配置探针没有分开记录「继续。」之前和之后的回复，判不出先问了再执行还是直接执行，
#    所以 full32k/full8k/window/pin 重跑这两个探针；
# 2. 摘要和笔记的生成上限只有 1024，gemma4 的摘要被截在半句话，所以 summary/notes 用 4096 重新回放，6 个探针全部重跑。
cd "$(dirname "$0")"
for m in llama3.1:8b gemma4:latest; do
  for st in full32k full8k window pin; do
    ${LOCK:+flock "$LOCK"} python3 agent.py --model "$m" --strategy "$st" --probe budget payment --out logs/main.jsonl
  done
  for st in summary notes; do
    ${LOCK:+flock "$LOCK"} python3 agent.py --model "$m" --strategy "$st" --out logs/main.jsonl
  done
done
