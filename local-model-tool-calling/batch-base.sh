#!/usr/bin/env bash
# Baseline: 4 models x 5 tasks x 5 seeds, temperature 0.8, default think.
set -euo pipefail
cd "$(dirname "$0")"
for m in qwen2.5-coder:7b qwen2.5-coder:3b llama3.1:8b gemma4:latest; do
  python3 agent.py --model $m --runs 5 --out logs/base.jsonl
done
echo BATCH_DONE
