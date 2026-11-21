# Ollama 提示词前缀缓存的实验脚本

配套文章：[系统提示词开头加个时间戳，Ollama 首字延迟从 37ms 涨到 3 秒](https://costalong.com/2026/11/20/ollama-prefix-cache/)。

脚本用一份程序生成的"值班手册"（80 条规则，qwen2.5-coder 分词后约 6269 token）当系统提示词，在不同改动下连续发流式请求，每次记录 `prompt_eval_count`、`prompt_eval_cached_count`、`prompt_eval_duration`、`load_duration` 和客户端测得的首字延迟，看缓存在什么情况下会被打掉。

这是教学用的复现脚本，用来观察前缀缓存的命中条件，不是基准；延迟的绝对值取决于显卡和机器负载。

## 文件

| 文件 | 作用 |
|---|---|
| `lib.py` | 生成值班手册、发流式 `/api/chat` 请求并计时、卸载模型 |
| `run_all.py` | `run_all.py MODEL CASE...`，每个场景写一份 `logs/<model>-<case>.jsonl` |
| `show.py` | `show.py JSONL [LABEL...]`，每次调用打印一行摘要 |
| `stats.py` | 汇总 `logs/*.jsonl`，按场景和标签给中位数与范围 |

`run_all.py` 支持的场景：

| 场景 | 内容 |
|---|---|
| `cold` / `same` | 冷启动，和同一提示词连续重发 |
| `stamp` | 时间戳放在系统提示词开头、结尾或用户消息里 |
| `tools` | 工具定义顺序固定与每次打乱 |
| `turns` | 多轮对话：只追加，和只保留最近 3 轮 |
| `opts` | 改温度，和在 8192、16384 之间切换 `num_ctx` |
| `other` | 中间穿插 qwen2.5-coder:0.5b 或 llama3.1:8b 的请求 |
| `keepalive` | 请求里设 `keep_alive: 5s`，过期后再发同一提示词 |
| `interleave` / `interleave3` | 两份、三份不同的系统提示词轮流发 |
| `turns_tools` / `agent` | 带工具的多轮和工具循环 |
| `v1` / `generate` | `/v1/chat/completions`、`/api/generate` 与 `/api/chat` 混用 |

## 运行

文章数据来自 Ollama 0.35.0（systemd 服务，`OLLAMA_NUM_PARALLEL=1`，`OLLAMA_KEEP_ALIVE=5m`，没开 Flash Attention，自带 llama-server 对应 llama.cpp b11081），RTX 3060 12 GiB（驱动 580.178.04），模型 qwen2.5-coder:7b 为主，llama3.1:8b 复测，Python 3.14。请求里 `num_ctx` 8192，温度 0，`seed` 1。

```bash
cd ollama-prefix-cache
ollama pull qwen2.5-coder:7b
ollama pull llama3.1:8b
ollama pull qwen2.5-coder:0.5b      # 只有 other 场景用

python3 run_all.py qwen2.5-coder:7b cold same stamp tools turns opts other keepalive interleave interleave3 turns_tools v1 generate agent
python3 run_all.py llama3.1:8b same stamp tools   # 关键场景用 llama3.1 复测，按需选
python3 stats.py
python3 show.py logs/qwen2.5-coder_7b-stamp.jsonl
```

## 验证与边界

- 判断有没有命中缓存看 `prompt_eval_cached_count` 或 `prompt_eval_duration`，不要看 `prompt_eval_count`：0.35.0 把缓存命中数和实际计算数加在一起返回。
- 每种情况连续跑 5 次左右，取中位数。文章测试期间 CPU 上还跑着别的任务，首字延迟里几毫秒的差别不必当真。
- `OLLAMA_NUM_PARALLEL` 大于 1、开了 Flash Attention 或换了版本，缓存槽位和命中行为都可能不同。
- 源码对照没有放进本仓库，需要时看 Ollama v0.35.0 tag 的 `llm/llama_server.go`（`promptEvalCount`）、`server/sched.go`、`server/routes.go`、`openai/openai.go` 和 `api/types.go`。
