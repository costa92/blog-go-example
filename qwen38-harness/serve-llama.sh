#!/usr/bin/env bash
set -euo pipefail
: "${HARNESS_BASE_MODEL:?Set HARNESS_BASE_MODEL to a local base GGUF}"
: "${HARNESS_PI_ADAPTER:?Set HARNESS_PI_ADAPTER to the official Pi LoRA GGUF}"
exec "${HARNESS_LLAMA_BIN:-llama-server}" \
  -m "$HARNESS_BASE_MODEL" --lora "$HARNESS_PI_ADAPTER" --lora-init-without-apply \
  --alias qwen-base,qwen-pi --ctx-size "${HARNESS_CONTEXT_WINDOW:-16384}" \
  --parallel 1 --threads 4 --batch-size 256 --ubatch-size 128 \
  --n-gpu-layers "${HARNESS_GPU_LAYERS:-99}" \
  --chat-template-kwargs '{"enable_thinking": false}' --no-context-shift \
  --host 127.0.0.1 --port "${HARNESS_PORT:-8091}" "$@"
