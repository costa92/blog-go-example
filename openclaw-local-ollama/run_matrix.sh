#!/usr/bin/env bash
# default = what non-interactive onboard writes; slim = coding profile, bundled skills off, BOOTSTRAP.md removed
set -euo pipefail
S=$(cd "$(dirname "$0")/.." && pwd)
export OC=${OC:-$S/pkg/node_modules/.bin/openclaw} PROXY_LOG=${PROXY_LOG:-$S/logs/proxy-tasks.jsonl}
MODELS=${MODELS:-qwen2.5-coder:3b,qwen2.5-coder:7b,llama3.1:8b}
N=${N:-4}
WS=$HOME/.openclaw/workspace
rm -rf "$WS" && cp -a "$S/ws-backup" "$WS"
$OC config unset skills.allowBundled >/dev/null || true
$OC config set tools '{"profile":"full"}' --strict-json >/dev/null
CONFIG_LABEL=default MODELS=$MODELS N=$N python3 -I "$S/code/tasks.py" "$S/logs/tasks.jsonl"
rm -f "$WS/BOOTSTRAP.md"
$OC config set skills.allowBundled '[]' --strict-json >/dev/null
$OC config set tools '{"profile":"coding"}' --strict-json >/dev/null
CONFIG_LABEL=slim MODELS=$MODELS N=$N python3 -I "$S/code/tasks.py" "$S/logs/tasks.jsonl"
echo MATRIX_DONE
