# 本地模型多步工具调用的实验脚本

配套文章：[同是 8B，多步工具调用 25 比 0：本地模型在第二步断开](https://costalong.com/2026/11/20/local-model-tool-calling/)。

`agent.py` 是一个假的工单系统加一个最小的工具循环：6 个工具（搜工单、查工单、查用户、查订单、改工单、计算）和它们的数据都写在文件里，邮箱用 `example.com`。5 个任务各需要两到四步调用，模型通过 Ollama 原生 `/api/chat` 的 `tools` 字段发起调用，循环最多 10 轮。每次运行写一行 JSON，`grade.py` 按"第一处出错的地方"给每次运行打标签。

这是教学用的小实验，任务和数据都是虚构的，不是工具调用能力的基准。

## 文件

| 文件 | 作用 |
|---|---|
| `agent.py` | 工具、假数据、5 个任务和工具循环；`--variant` 选提示方式，`--textparse` 让客户端把正文里的 JSON 调用转成结构化调用 |
| `grade.py` | `grade.py LOG.jsonl...`，给每次运行打标签，按模型和条件出表 |
| `show.py` | `show.py LOG.jsonl [model] [task] [variant]`，把匹配的运行打印成紧凑的调用轨迹 |
| `batch-base.sh` | 基线：4 个模型 × 5 个任务 × seed 1～5，写 `logs/base.jsonl` |
| `batch-fix.sh` | 补救办法：文本解析兜底、系统提示词规则、gemma4 `think=false`，写 `logs/fix.jsonl` |
| `batch-fix2.sh` | qwen2.5-coder 换用能解析多个 JSON 对象的解析器（v2）重跑，写 `logs/fix2.jsonl` |
| `batch-hint2.sh` | 所有用到工具描述提示的条件重跑，示例 ID 换成假数据里不存在的占位值，写 `logs/hint2.jsonl` |

`--variant` 的取值：`base`；`hint` 在工具描述里写明 ID 格式、来源和状态枚举；`sys` 在系统提示词里加"一次一步、ID 只取自之前的结果、出错要报告"几条规则；`hint+sys` 两者都加。

## 运行

文章数据来自 Ollama 0.35.0，RTX 3060 12 GiB（驱动 580.178.04），温度 0.8，`seed` 1～5，`num_ctx` 8192。模型 qwen2.5-coder:7b、qwen2.5-coder:3b、llama3.1:8b、gemma4:latest，都是 Q4_K_M。

```bash
cd local-model-tool-calling
for m in qwen2.5-coder:7b qwen2.5-coder:3b llama3.1:8b gemma4:latest; do ollama pull $m; done

./batch-base.sh
./batch-fix.sh
./batch-fix2.sh
./batch-hint2.sh
python3 grade.py logs/base.jsonl logs/fix.jsonl logs/fix2.jsonl logs/hint2.jsonl
python3 show.py logs/base.jsonl llama3.1:8b t2
```

单独跑一组：

```bash
python3 agent.py --model llama3.1:8b --task t1 t2 --runs 5 --variant hint+sys --out logs/demo.jsonl
```

## 验证与边界

- 每个条件 25 次运行（5 个任务 × 5 个 seed）。seed 固定只保证同一配置下可复现，换显卡或 Ollama 版本后结果可能不同。
- 文章原始数据里，`fix.jsonl` 的提示条件是用旧版工具描述跑的，示例写的是假数据里真实存在的 ID，模型会照抄，所以图表的提示条件只取 `hint2.jsonl`，文本解析的数据只取 `fix2`、`hint2`。本仓库的 `agent.py` 已是占位 ID 版本，重跑 `batch-fix.sh` 得到的提示条件和 `hint2` 用的是同一份描述。
- qwen2.5-coder 在这组任务里没有产生结构化调用，原因是推测（模型没按模板输出 `<tool_call>` 标签），没有读源码确认。
- 只测了原生 `/api/chat`，没有测 `/v1` 兼容接口的工具调用。
