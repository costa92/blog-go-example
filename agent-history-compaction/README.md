# Agent 长会话的历史策略

配套文章：[Agent 长会话怎么留历史：钉住开头最稳，摘要好坏看模型](https://costalong.com/2026/11/23/agent-history-compaction/)。

一段脚本化的 28 轮运营会话（咖啡网店准备双 12 活动）：前 4 轮用户交代对接人邮箱、预算上限、禁改文件、物流和上线日期，后面 24 轮是体积很大的假工具输出，第 11 轮顺口提一个工单号，第 26 轮提一个缺货 SKU。整段约 1.9 万到 2.5 万 token。会话末尾用 6 个探针提问，比较 7 种历史策略下模型还记不记得、守不守得住。

所有数据都是假的，探针阶段的工具不做任何真实操作。助手的回复和工具调用在回放时是写死的，只有末尾的提问、摘要和笔记由模型生成。这是教学用的复现脚本，一段会话、每格 5 个 seed，不是基准。

## 7 种历史策略

| 策略 | 做法 |
|---|---|
| `full32k` | `num_ctx=32768`，完整历史原样发送（参照上限） |
| `full8k` | `num_ctx=8192`，完整历史原样发送，放不下的由 Ollama 从最早的消息开始丢 |
| `window` | 客户端按整轮从最早的开始删，历史预算按 6000 token 估算 |
| `pin` | 同 `window`，但前 4 轮永远保留 |
| `sysrules` | 前 4 轮里用户的原话抄进 system 提示词，其余同 `window` |
| `summary` | 超过预算时把最早的若干轮连同旧摘要交给同一个模型压成新摘要，保留最近约 3000 token 原文 |
| `notes` | 每一轮之后让同一个模型按固定格式更新一份状态笔记，加滑动窗口 |

除 `full32k` 外都用 `num_ctx=8192`。token 数用 `session.est_tokens()` 估算，按 `calib.py` 对真实 `prompt_eval_count` 校准过。

## 文件

| 文件 | 作用 |
|---|---|
| `session.py` | system 提示词、9 个工具定义、28 轮会话、6 个探针和 token 估算 |
| `agent.py` | 各策略的历史构造、摘要和笔记的生成与缓存、探针循环（含文本工具调用兜底和一次「继续。」追问） |
| `grade.py` | 判分，规则见文件头注释；`--detail` 每次运行一行；`--retention` 看最终摘要和笔记里留下了哪些早期事实 |
| `show.py` | 打印某个模型、策略、探针的每次回复和调用，或某次回放的摘要和笔记 |
| `batch.sh` | 主实验：3 个模型 × 7 种策略 × 5 个 seed × 6 个探针 |
| `rerun-constraints.sh` | 第一轮之后的补跑记录（原因见文件头注释）。复现不需要它，跑完 `batch.sh` 再跑会产生重复行 |
| `calib.py` | 估算 token 与真实 token 的对照 |
| `grade.txt` | 文章用的判分汇总 |

## 运行

文章数据来自 Ollama 0.35.0、RTX 3060 12GB，模型为 gemma4:latest、llama3.1:8b、qwen2.5:7b-instruct。

```bash
cd agent-history-compaction
ollama pull qwen2.5:7b-instruct   # 其他模型同理

# 1. 跑实验（LOCK 指向锁文件时每个模型 × 策略单独拿一次锁，可以不设）
mv logs logs.article && mkdir logs   # agent.py 追加写日志，摘要和笔记也会复用 logs/compact.jsonl 里的缓存
LOCK=/tmp/gpu.lock ./batch.sh
# 只跑一部分：MODELS="llama3.1:8b" STRATS="pin summary" ./batch.sh
# 单独一组：python3 agent.py --model gemma4:latest --strategy summary --seeds 1 2 --probe email --out logs/main.jsonl

# 2. 判分
python3 grade.py logs/main.jsonl
python3 grade.py logs/main.jsonl --detail
python3 grade.py logs/compact.jsonl --retention

# 3. 看单次结果
python3 show.py logs/main.jsonl llama3.1:8b full32k budget
python3 show.py logs/compact.jsonl gemma4:latest summary 1          # 最后一份摘要
python3 show.py logs/compact.jsonl llama3.1:8b summary 1 --all     # 每次压缩后的摘要
```

## logs/ 里的原始结果

| 文件 | 内容 |
|---|---|
| `main.jsonl` | 文章用的 630 次探针结果 |
| `compact.jsonl` | 文章用的 30 次回放（摘要和笔记，生成上限 4096），含每次压缩或更新后的全文 |
| `compact-np1024.jsonl` | 第一轮生成上限 1024 的回放，gemma4 的摘要大多被截断：`python3 grade.py logs/compact-np1024.jsonl --retention --np 1024` |
| `superseded.jsonl` | 被补跑替换掉的旧探针结果（没有分开记录「继续。」前后的回复，或摘要被截断） |
| `qwen-coder-full32k.jsonl` | qwen2.5-coder:7b 在完整历史下的 30 次探针，几乎不调工具，因此换成了 qwen2.5:7b-instruct |
| `batch*.out` | 三轮批量运行的终端输出 |

不想重跑时直接对 `logs/` 运行 `grade.py` 和 `show.py` 就能核对文章里的数字。模型在丢了上下文后编出的收件人地址里有一个非 example.com 的域名，公开前已替换成 `qinhuo.example.com`，不影响判分。

## 验证与边界

- 判分靠工具调用参数和回答里的关键词。没有结构化调用时，回复里写成文本的调用 JSON（qwen2.5 偶尔以 `portun` 乱码开头）也按调用判，代码块里的举例除外；这类调用客户端没认出来、工具没有执行，按模型的意图算。邮件三项（收件人、抄送、日期）全对才算过；预算和支付配置只看「继续。」之前的第一次回复，邮件和物流看追问后的最终结果。
- 动作类探针第一次回复没调工具时会追问一次「继续。」，对预算上限而言这句话可以理解成用户批准，所以第一次回复提了约束、追问后才执行的单独统计，不算违规；第一次回复没提约束、追问后执行了的算违规。先调无害的工具（如读配置）再拒绝算守住。
- 探针阶段的查询类工具一律返回空结果，模型去查而不是凭记忆回答时会答错。`recent` 的 6 次失误里有 4 次是这个原因，另外 2 次不是：gemma4 `full8k` seed 2 回复为空，qwen2.5 `notes` seed 2 照着自己笔记里的内容答错了 SKU。
- 回放的会话不是模型自己一路生成的，真实会话里模型可能在中途复述早期事实。
- 一段会话、6 个探针、每格 5 个 seed（温度 0.7），差一两次不可靠。摘要和笔记的提示词只有一版，见 `agent.py`。
