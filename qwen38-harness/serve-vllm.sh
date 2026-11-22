#!/usr/bin/env bash
set -euo pipefail

# Provide local snapshots, downloaded with explicit Hub revisions (see README).
: "${HARNESS_BASE_MODEL:?Set HARNESS_BASE_MODEL to a local Qwen3.8-27B BF16 snapshot}"
: "${HARNESS_PI_ADAPTER:?Set HARNESS_PI_ADAPTER to a local Pi adapter snapshot}"

exec "${HARNESS_VLLM_BIN:-vllm}" serve "$HARNESS_BASE_MODEL" \
  --served-model-name qwen-base \
  --enable-lora --max-lora-rank 32 \
  --lora-modules "qwen-pi=$HARNESS_PI_ADAPTER" \
  --language-model-only --enable-prefix-caching --mamba-cache-mode align \
  --enable-auto-tool-choice --tool-call-parser qwen3_xml --reasoning-parser qwen3 \
  --default-chat-template-kwargs '{"enable_thinking": false}' \
  --max-model-len 131072 --max-num-seqs 1 \
  --tensor-parallel-size "${HARNESS_TENSOR_PARALLEL:-1}" \
  --host 127.0.0.1 --port "${HARNESS_PORT:-8000}" \
  "$@"
