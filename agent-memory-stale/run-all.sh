#!/usr/bin/env bash
# 两套客户端兜底各跑一遍完整组合：logs/runs.jsonl（严格）和 logs/lenient.jsonl（宽松），共 1440 次
set -euo pipefail
cd "$(dirname "$0")"
./batch.sh && ./batch2.sh && ./batch-lenient.sh
