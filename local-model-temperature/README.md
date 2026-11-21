# 本地代码模型的采样温度实验

配套文章：[qwen2.5-coder:7b 写代码，温度 0 通过率反而最低：1200 次带测试的生成实测](https://costalong.com/2026/11/20/local-model-temperature/)。

10 道自包含的 Python 小题（罗马数字、区间合并、括号匹配、LRU 缓存等），每题有一组模型看不到的断言。`bench.py` 在不同温度下让模型写函数，抽出代码在子进程里跑断言（超时 5 秒），记录是否通过、语法错误、AST 去重后的代码种数和生成速度。同一套题也发给 MiniMax 的托管接口做对照。

这是教学用的小实验，题目都是几十行以内的单函数，不是代码能力基准，也不代表多文件的真实任务。

## 文件

| 文件 | 作用 |
|---|---|
| `tasks.py` | 10 道题的提示词和隐藏断言 |
| `refcheck.py` | 用参考实现跑一遍断言，确认测试本身没写错 |
| `bench.py` | `bench.py <backend:model> <温度,逗号分隔> <每档次数> <out.jsonl> [seed]`，backend 是 `ollama` 或 `minimax`；`BENCH_EXTRA` 环境变量可追加 Ollama options |
| `analyze.py` | 按模型和温度汇总通过率、语法错误、代码种数、速度 |
| `pertask.py` | `pertask.py <model> <jsonl>...`，逐题看各温度的通过情况 |
| `t0pattern.py` | 温度 0 下同一题多次输出的重复模式 |
| `det.py` | `det.py <model> <out.jsonl>`，本地模型的可复现性：温度 0 连续重复、和别的提示词交替、带与不带 seed |
| `det_minimax.py` | MiniMax 的同类检查，写 `det_minimax.jsonl` |
| `ctx.py` | `ctx.py <model> <out.jsonl> [num_ctx,...]`，确认提示词没被上下文截断 |
| `run_local.sh` | 三个本地模型依次跑 5 档温度 × 每题 8 次，同时用 `nvidia-smi` 采样显存 |
| `run_after.sh` | 关掉 `top_k`/`top_p` 截断的高温组、可复现性和 `num_ctx` 检查 |

## 运行

文章数据来自 Ollama 0.35.0（localhost:11434），RTX 3060 12 GiB（驱动 580.178.04），模型 qwen2.5-coder:3b、qwen2.5-coder:7b、llama3.1:8b（Ollama 默认量化），判题用 Python 3.14.4。托管接口是 MiniMax `https://api.minimaxi.com/v1/chat/completions`，模型 MiniMax-M3。

```bash
cd local-model-temperature
python3 refcheck.py                 # 先确认 10 题的断言都对

./run_local.sh                      # 1200 次本地生成，写 grid_local.jsonl
./run_after.sh                      # 关截断的高温组、det_local.jsonl、ctx.jsonl
python3 analyze.py grid_local.jsonl
python3 pertask.py qwen2.5-coder:7b grid_local.jsonl
python3 t0pattern.py grid_local.jsonl

# MiniMax 对照，密钥只从环境变量读
export MINIMAX_CN_API_KEY=...
python3 bench.py minimax:MiniMax-M3 0,0.8,1.6 5 grid_minimax.jsonl
python3 det_minimax.py
```

两个 shell 脚本会先 `ollama stop` 当前加载的所有模型，保证显卡上一次只有一个模型。

## 验证与边界

- 每个模型、每档温度每题 8 次，一共 80 次一格。通过率差几个百分点不要当成结论。
- Ollama 默认带 `top_k=40`、`top_p=0.9`，高温下不崩主要是因为截断发生在温度之前；`run_after.sh` 用 `BENCH_EXTRA` 把截断关掉做对照。
- MiniMax 文档写明 MiniMax-M3 的 temperature 固定为 1，传入的值不生效；`det_minimax.py` 里的 MiniMax-M2.5 文章写作时可用，之后可能下线。
- 量化版本用的是拉取时的默认 tag，没有对比不同量化精度。
