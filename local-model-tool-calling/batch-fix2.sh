#!/usr/bin/env bash
# qwen2.5-coder again with the multi-object text parser (agent.py PARSER=v2).
set -euo pipefail
cd "$(dirname "$0")"
for m in qwen2.5-coder:7b qwen2.5-coder:3b; do
  for v in base hint+sys; do
    python3 agent.py --model $m --runs 5 --textparse --variant $v --out logs/fix2.jsonl
  done
done
echo BATCH_DONE
