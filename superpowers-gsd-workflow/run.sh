#!/usr/bin/env bash
# usage: run.sh <workdir> <logname> <prompt>
# 在 <workdir> 里跑一次 claude -p，stream-json 写到 logs/<logname>.jsonl，再打印汇总。
set -u
dir=$1; log=$2; prompt=$3
here=$(cd "$(dirname "$0")" && pwd)
mkdir -p "$here/logs"
start=$(date +%s)
(cd "$dir" && claude -p "$prompt" --model sonnet --output-format stream-json --verbose \
  --permission-mode bypassPermissions --max-budget-usd 3 --no-session-persistence) \
  > "$here/logs/$log.jsonl" 2> "$here/logs/$log.err"
end=$(date +%s)
python3 "$here/summ.py" "$here/logs/$log.jsonl" $((end-start))
