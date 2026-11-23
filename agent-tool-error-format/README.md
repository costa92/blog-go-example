# 工具报错的写法与本地模型 Agent 的恢复

配套文章：[工具报错怎么写，本地模型 Agent 才会自己修：只有带修法的报错有用，503 要靠提示词让它重试](https://costalong.com/2026/11/22/agent-tool-error-format/)。

一个最小的工具调用 Agent，直接调 Ollama 的 `/api/chat`。假的运营系统有 10 个工具，6 个任务各在某个工具上注入一种失败：月份格式不对、缺必填字段、订单号不全、库存服务临时 503、没有删除权限、短信日配额用完。同一种失败用四种写法返回给模型，看它能不能自己修好、会不会如实告诉用户、会不会编结果或者原地打转。

所有数据都是假的，开发票、发短信、改工单只在内存里记一笔。这是教学用的复现脚本，任务少、失败是人为注入的，不是 Agent 能力的基准。

## 四种报错写法

| 写法 | 例子（月份格式错） |
|---|---|
| `bare` | `400 Bad Request` |
| `sentence` | `Error: invalid value for month: '2026-11'.` |
| `json` | `{"error": {"code": "INVALID_ARGUMENT", "message": "invalid value for month", "field": "month", "value": "2026-11"}}` |
| `hint` | `json` 再加 `"expected": "YYYYMM, six digits without separator, e.g. 202401", "retryable": true` |

`sentence` 和 `json` 信息量相同，只差结构；`hint` 额外说明怎么改、能不能重试。每种失败的四种写法见 `agent.py` 里的 `ERRORS`。

## 文件

| 文件 | 作用 |
|---|---|
| `agent.py` | 假数据、工具、注入的失败、Agent 循环；系统提示词有 `plain` 和 `rule`（多一段报错处理规则）两种 |
| `batch.sh` | 拿着 GPU 锁跑一次 `agent.py`，结果追加到 `logs/<名字>.jsonl` |
| `batch-all.sh` | 主实验：4 个模型 × 4 种写法 × 6 个任务，温度 0 跑 1 次、温度 0.7 跑 seed 1 到 5 |
| `batch-rule.sh` | 同样的组合，系统提示词换成 `rule` |
| `grade.py` | 判分，标签含义见文件头注释；`--by` 选分组，`--kind recoverable/fatal` 只看一类任务，`--list 标签` 打印明细 |
| `show.py` | 打印某次运行的每一步调用、工具返回和最终回答 |

## 运行

文章数据来自 Ollama 0.35.0、RTX 3060 12GB，模型为 gemma4:latest、llama3.1:8b、qwen2.5-coder:7b、qwen2.5-coder:3b。

```bash
cd agent-tool-error-format
ollama pull qwen2.5-coder:7b   # 其他模型同理

# 1. 跑实验（GPU_LOCK 默认 /tmp/gpu.lock，和别的任务共用显卡时用同一把锁）
./batch-all.sh     # 576 次运行，写 logs/main.jsonl
./batch-rule.sh    # 576 次运行，写 logs/rule.jsonl
# 只跑一部分：MODELS="llama3.1:8b" ./batch-all.sh

# 2. 判分
python3 grade.py logs/main.jsonl logs/rule.jsonl --by system variant --kind recoverable
python3 grade.py logs/main.jsonl logs/rule.jsonl --by system variant --kind fatal
python3 grade.py logs/main.jsonl logs/rule.jsonl --by task system model --kind recoverable
python3 grade.py logs/main.jsonl --list ask_user

# 3. 看单次运行
python3 show.py logs/main.jsonl llama3.1:8b t3 hint --seed 1
```

`logs/` 是文章所用的原始结果（`main.jsonl` 默认提示词、`rule.jsonl` 加报错处理规则，`summary.txt` 是判分汇总），不想重跑时直接对它运行 `grade.py` 和 `show.py` 就能核对文章里的数字。`agent.py` 以追加方式写日志，自己重跑前先移走：`mv logs logs.article`，否则会重复计数。

## 验证与边界

- 判分靠关键词和服务端状态：开票看内存里有没有发票，其他任务看回答里有没有正确的值（186,420.5、派送中、37）。失败时的分类（推回给用户、放弃、没说失败）是正则匹配，文章作者抽查过「编造」「没说失败」「未触发」三类的全部明细，其余没有逐条核对。
- 注入的错误没触发的运行不计入分母，主要是 qwen2.5-coder:3b 第一轮就把调用写成了不合法的 JSON。
- 客户端有一个兜底：回复里只有 JSON 工具调用时当成结构化调用；JSON 前后夹了文字就不算，这类运行标成 `text_call`。
- `rule` 提示词是看过主实验结果之后写的，里面列的几类处理方式正好对应这 6 个任务，换成别的任务效果可能更差。
- 温度 0.7 每格只有 5 个 seed，每个模型每种写法每个任务最多 6 次，小差距不可靠。
- 单条回复上限 2048 token，qwen2.5-coder:3b（多在 t6）和 llama3.1:8b 偶尔写满单条回复上限，撞到上限的运行标成 `loop`。
