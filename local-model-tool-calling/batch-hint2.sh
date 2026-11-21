#!/usr/bin/env bash
# Rerun every condition that uses HINTS, now with placeholder example IDs (TK-0000/U-00/C-000)
# that exist nowhere in the fake data. Same seeds 1-5.
set -euo pipefail
cd "$(dirname "$0")"
python3 agent.py --model llama3.1:8b --runs 5 --variant hint --out logs/hint2.jsonl
python3 agent.py --model llama3.1:8b --runs 5 --variant hint+sys --out logs/hint2.jsonl
python3 agent.py --model qwen2.5-coder:7b --runs 5 --textparse --variant hint+sys --out logs/hint2.jsonl
python3 agent.py --model qwen2.5-coder:3b --runs 5 --textparse --variant hint+sys --out logs/hint2.jsonl
python3 agent.py --model gemma4:latest --runs 5 --variant hint+sys --out logs/hint2.jsonl
echo BATCH_DONE
