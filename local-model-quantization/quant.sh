#!/usr/bin/env bash
# 自己量化 + imatrix 量化 + KL 散度，结果写到 logs/kld/。
# 用法：LLAMA=./llama-b12596 FP16=models/qwen2.5-3b-fp16.gguf ./quant.sh
# FP16 可以直接用 Ollama 存储目录里 qwen2.5:3b-instruct-fp16 的 blob（ollama show --modelfile 里 FROM 那一行）。
set -euo pipefail
cd "$(dirname "$0")"
LLAMA=${LLAMA:?设置 LLAMA 为 llama.cpp 构建目录}
FP16=${FP16:?设置 FP16 为 FP16 GGUF 路径}
mkdir -p models logs/kld

# 1. FP16 在评测语料上的分布，作为 KL 散度的基准
"$LLAMA/llama-perplexity" -m "$FP16" -f corpus.txt -c 512 --kl-divergence-base models/fp16.kld > logs/kld/fp16.log 2>&1

# 2. 校准文本上算 imatrix
"$LLAMA/llama-imatrix" -m "$FP16" -f calib.txt -c 512 -o models/imatrix.gguf > logs/kld/imatrix.log 2>&1

for q in Q4_K_M Q3_K_M Q2_K; do
  # 3. 不加 imatrix 自己量化一份，和 Ollama 官方文件对照
  "$LLAMA/llama-quantize" "$FP16" "models/self-$q.gguf" "$q" > "logs/kld/quantize-$q.log" 2>&1
  # 4. 加 imatrix 量化
  "$LLAMA/llama-quantize" --imatrix models/imatrix.gguf "$FP16" "models/imat-$q.gguf" "$q" > "logs/kld/quantize-imat-$q.log" 2>&1
  for v in self imat; do
    "$LLAMA/llama-perplexity" -m "models/$v-$q.gguf" -f corpus.txt -c 512 \
      --kl-divergence-base models/fp16.kld --kl-divergence > "logs/kld/$v-$q.log" 2>&1
  done
done

# 5. 官方量化版本：把 Ollama blob 路径填进来，日志名要和 kld.py 的 ROWS 对应（q8_0、q4_K_M、q3_K_L、q3_K_M、q2_K）
# "$LLAMA/llama-perplexity" -m <blob> -f corpus.txt -c 512 --kl-divergence-base models/fp16.kld --kl-divergence > logs/kld/q4_K_M.log 2>&1

# 6. imatrix 版本导入 Ollama，供 run.py 跑题库：沿用官方 FP16 的模板和参数，只换 FROM
for q in Q4_K_M Q3_K_M Q2_K; do
  lq=$(echo "$q" | sed 's/^Q/q/')
  ollama show qwen2.5:3b-instruct-fp16 --modelfile | sed "s#^FROM .*#FROM $PWD/models/imat-$q.gguf#" > "models/Modelfile.imat-$lq"
  ollama create "qwen2.5:3b-instruct-imat-$lq" -f "models/Modelfile.imat-$lq"
done
