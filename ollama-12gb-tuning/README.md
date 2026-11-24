# 12GB 显卡上 Ollama 的上下文、KV 缓存和并发参数实测

配套文章：[12G 显卡跑 Ollama：llama3.1 开 32K 上下文只剩 10 token/s，KV 缓存改 q8_0 回到 29](https://costalong.com/2026/03/02/ollama-local-llm-deploy/)。

脚本另起一个 `ollama serve`（默认 `127.0.0.1:11500`，和系统服务共用模型目录），每组服务端环境变量各起一次，测：

- `num_ctx` 4K 到 64K、Flash Attention 开关、`OLLAMA_KV_CACHE_TYPE` f16 / q8_0 / q4_0 下的显存、`ollama ps` 的 CPU/GPU 比例、GPU 层数、加载时间、预填充和生成速度；
- 同样几种 KV 缓存类型下的长上下文检索：程序生成一份项目登记表（每条一个五位门禁码），按均匀分布的深度问 30 个门禁码，精确匹配判分；
- `OLLAMA_NUM_PARALLEL` 1 / 2 / 4 时 1、2、4、8 个并发客户端的总吞吐、单请求延迟和显存。

只用 Python 标准库，需要本机装好 Ollama 和 `nvidia-smi`。这是教学用的复现脚本，不是基准：显存余量取决于桌面程序占了多少，速度取决于显卡和机器负载。

## 文件

| 文件 | 作用 |
|---|---|
| `lib.py` | 起停临时服务、发请求、读 `/api/ps` 和 `nvidia-smi`、从服务日志里摘 llama-server 的加载信息、生成登记表 |
| `exp_ctx_kv.py` | `exp_ctx_kv.py MODEL OUT.jsonl`：4 组服务端配置 × 5 档 `num_ctx`，每档 3 次短提示词（约 3.6K token），32K 起再加 3 次长提示词 |
| `exp_quality.py` | `exp_quality.py MODEL NUM_CTX N_RECORDS N_QUESTIONS OUT.jsonl [default q8_0 q4_0]`；`HAYSTACK_SEED` 换一份登记表，`BENCH_NUM_GPU` 强制只放部分层到 GPU |
| `exp_parallel.py` | `exp_parallel.py MODEL NUM_CTX OUT.jsonl [NUM_PARALLEL ...]`，每档并发跑 3 轮；`BENCH_KV=q8_0` 时同时开 Flash Attention 和 q8_0 KV 缓存 |
| `stats.py` | 汇总 `logs/*.jsonl`，给中位数 |
| `logs/*.jsonl` | 文章里的原始结果（2026-11-24，Ollama 0.35.0，RTX 3060 12GB） |

## 运行

```sh
mkdir -p logs
python3 exp_ctx_kv.py llama3.1:8b logs/ctx_kv-llama3.1-8b.jsonl
python3 exp_quality.py llama3.1:8b 32768 500 30 logs/quality-llama3.1-8b.jsonl
python3 exp_quality.py qwen2.5-coder:7b 32768 500 30 logs/quality-qwen2.5-coder-7b.jsonl
python3 exp_parallel.py llama3.1:8b 8192 logs/parallel-llama3.1-8b.jsonl
python3 stats.py
```

模型目录不是 `/mnt/data/ollama/models` 时设 `OLLAMA_MODELS`；端口冲突时设 `BENCH_PORT`。临时服务带 `OLLAMA_NOPRUNE=1` 启动，不会清理模型目录。服务日志写在 `logs/server-*.log`，里面有本机路径，已被 `.gitignore` 排除。

## 边界

- 只测了 llama3.1:8b 和 qwen2.5-coder:7b 两个 Q4_K_M 模型、一张 RTX 3060。
- 检索题是合成数据，30 题一组，温度 0；一两题的差别在噪声范围内，看大的差别。
- 第一次加载（模型文件不在页缓存里）的耗时没有系统地测，文章里只引用了校准时的一次。
