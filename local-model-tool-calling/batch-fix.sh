#!/usr/bin/env bash
# Mitigations, same tasks and seeds as the baseline.
#   +parse : client turns a JSON tool call written as text into a structured call
#   hint   : tool descriptions spell out id formats, where ids come from, status enum
#   sys    : system prompt rules (one step at a time, ids only from earlier results, report errors)
set -euo pipefail
cd "$(dirname "$0")"
o=logs/fix.jsonl
for m in qwen2.5-coder:7b qwen2.5-coder:3b; do
  python3 agent.py --model $m --runs 5 --textparse --out $o
  python3 agent.py --model $m --runs 5 --textparse --variant hint+sys --out $o
done
for v in hint sys hint+sys; do
  python3 agent.py --model llama3.1:8b --runs 5 --variant $v --out $o
done
python3 agent.py --model gemma4:latest --runs 5 --variant hint+sys --out $o
python3 agent.py --model gemma4:latest --runs 5 --think false --out $o
echo BATCH_DONE
