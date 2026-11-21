#!/bin/bash
cd "$(dirname "$0")"
python3 bench.py minimax:MiniMax-M3 prompt,json,schema_anyof,bare_schema_anyof minimax.jsonl --tag main --num-predict 4096
python3 bench.py minimax:MiniMax-M3 schema_anyof minimax.jsonl --tag split --num-predict 4096 --minimax-extra '{"reasoning_split": true}'
echo ALL_DONE
