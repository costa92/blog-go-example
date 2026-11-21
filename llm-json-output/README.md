# 大模型结构化 JSON 输出的抽取实验

配套文章：[Ollama 结构化输出实测：schema 管得住格式，管不住对错](https://costalong.com/2026/11/20/llm-json-output/)。

36 条手写的客服消息，每条都有人工标注的 7 个字段（订单号、客户名、意图、商品、是否加急、等待天数、摘要）。`bench.py` 用不同方式让模型抽取：只靠提示词、`format: "json"`、`format: <JSON Schema>`，以及去掉字段说明、去掉 null、先写理由等变体；`score.py` 用 jsonschema 校验结构，再逐字段和标注比对。

这是教学用的小实验，只有一种抽取任务和 36 条样本，不是模型或推理框架的基准。

## 文件

| 文件 | 作用 |
|---|---|
| `cases.py` | 36 条消息和标注答案 |
| `bench.py` | `bench.py <backend:model> <arm[,arm]> <out.jsonl> [--tag] [--temp] [--reps] [--num-predict] [--cases] [--think]`，backend 是 `ollama` 或 `minimax` |
| `score.py` | 按 model、tag、arm、temp 汇总结构合法率和字段准确率，`--fields` 看逐字段 |
| `analyze.py` | 逐条列出错误，`--nulls` 统计该填 null 却编了值的情况 |
| `dump.py` | 按条件原样打印记录，例如 `dump.py main.jsonl "r['arm']=='strict_schema' and r['case']==15"` |
| `extra_checks.py` | 文章里引用、`score.py` 不打印的几项小统计 |
| `run_local.sh` | 四个本地模型依次跑全部本地实验，一次只有一个模型在显卡上 |
| `run_minimax.sh` | MiniMax-M3 的对照组 |

`bench.py` 里的 arm：

| arm | 提示词 | 约束 |
|---|---|---|
| `prompt` | 字段说明 | 无 |
| `json` | 字段说明 | `format: "json"` |
| `schema` | 字段说明 | JSON Schema |
| `bare_json` / `bare_schema` | 不描述字段 | `json` / Schema |
| `strict_schema` | 字段说明 | Schema 里去掉 null |
| `reason_first` / `reason_last` | 字段说明加一句理由要求 | Schema 多一个 `reasoning` 字段，放最前或最后 |
| `schema_anyof` / `bare_schema_anyof` | 字段说明 / 不描述字段 | 用 `anyOf` 写可空类型，MiniMax 组用 |

## 运行

文章数据来自 Ubuntu 26.04.1、Python 3.14.4、jsonschema 4.26.0，Ollama 0.35.0 的 `/api/chat`，RTX 3060 12 GiB（驱动 580.178.04），模型 qwen2.5-coder:3b、qwen2.5-coder:7b、llama3.1:8b、gemma4:latest（8.0B，Q4_K_M）。托管接口是 MiniMax `https://api.minimaxi.com/v1/chat/completions`，模型 MiniMax-M3。

```bash
cd llm-json-output
python3 -m venv .venv && .venv/bin/pip install jsonschema==4.26.0

./run_local.sh                      # 写 main.jsonl
.venv/bin/python score.py main.jsonl
.venv/bin/python analyze.py main.jsonl --tag main --arm schema
.venv/bin/python analyze.py main.jsonl --nulls --arm strict_schema
.venv/bin/python extra_checks.py

# MiniMax 对照，密钥只从环境变量读
export MINIMAX_CN_API_KEY=...
./run_minimax.sh                    # 写 minimax.jsonl
.venv/bin/python score.py minimax.jsonl
```

`bench.py` 只用标准库，`score.py`、`analyze.py`、`extra_checks.py` 需要 jsonschema。

## 验证与边界

- 温度 0 的组每条只跑一次；温度 0.8 的组每条 3 次。结构错误率在 4% 左右，几条之差就会改变结论。
- gemma4 默认开启思考，`run_local.sh` 里除专门测思考的两组外都传了 `--think false`。
- schema 约束只保证结构合法，不保证内容对；截断（`--num-predict 40`）时写到一半的 JSON 照样不合法。
- MiniMax 接口收下了 `response_format` 参数，但文章测试时没有按 schema 约束输出，结论只对那时的接口成立。
