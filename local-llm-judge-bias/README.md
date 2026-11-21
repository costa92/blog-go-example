# 本地模型当裁判的偏差实验

配套文章：[本地 8B 模型当裁判：错答案加长，llama3.1 判对率从 84% 掉到 61%](https://costalong.com/2026/11/21/local-llm-judge-bias/)。

`items.py` 是 32 道技术问答，每道有一个正确回答和一个埋了一处事实错误的回答，错误点由作者按官方文档核对过。`run.py` 让本地模型在两份回答里选更好的一份，并做各种变形：交换 A/B 顺序、把错答案加长、把某一份写成 markdown、两份内容相同只换格式，再试几种补救办法。每次调用追加一行到 `logs/<cond>.jsonl`，已有的记录会跳过，可以断点续跑。

这是教学用的小实验，题目只有 32 道，不是裁判模型的排行榜。

## 文件

| 文件 | 作用 |
|---|---|
| `items.py` | 32 道题：问题、正确回答、错误回答、错误说明、用于加长错答案的相关细节，自我偏好组用的 `SELF_QS`，以及 `plain`/`md`/`padded` 三种排版 |
| `run.py` | `run.py <cond> [judge...]`，不指定裁判时跑全部三个 |
| `stats.py` | `stats.py [cond...]`，汇总判对率、交换顺序后改口的比例等 |
| `show.py` | `show.py <cond> <judge> <item> [variant] [--prompt]`，打印原始判决，`--prompt` 连提示词一起打 |
| `seedq.py` | `seedq.py <judge> <item>`，温度 0.7 下换 seed、重复 seed，并打印第一个 token 的 A/B 对数概率 |

`run.py` 的条件：

| cond | 内容 |
|---|---|
| `naive` | 直接问哪份更好：原样、错答案加长、错答案用 markdown、对答案用 markdown、内容相同只换格式 |
| `reason` | 先写理由再给结论 |
| `point` | 不做对比，单独给每份回答打分 |
| `temp07` | 温度 0.7，seed 1、2、3 |
| `selfgen` / `selfjudge` | 三个模型先各自回答 `items.SELF_QS` 里的问题，再两两比较彼此的回答；`selfjudge` 依赖 `logs/selfgen.jsonl` |
| `rubric` | 给出评分要点 |
| `lp` / `lprubric` | 不看生成的文字，比较第一个 token 是 A 还是 B 的对数概率，后者加评分要点 |
| `think` | 打开思考，只对 gemma4 |

## 运行

文章数据来自 Ollama 0.35.0 的原生 `/api/chat`，RTX 3060 12 GiB（驱动 580.178.04），裁判 gemma4:latest、llama3.1:8b、qwen2.5-coder:7b（都是 Q4_K_M）。默认温度 0、`seed` 1，判 A/B 时 `num_predict` 8；gemma4 除 `think` 组外都传 `think: false`。

```bash
cd local-llm-judge-bias
for m in gemma4:latest llama3.1:8b qwen2.5-coder:7b; do ollama pull $m; done

python3 run.py naive
python3 run.py reason
python3 run.py point
python3 run.py temp07
python3 run.py selfgen && python3 run.py selfjudge
python3 run.py rubric
python3 run.py lp
python3 run.py lprubric
python3 run.py think
python3 stats.py
python3 stats.py lp lprubric point selfjudge
python3 show.py naive llama3.1:8b go-loopvar length
python3 seedq.py llama3.1:8b go-loopvar
```

## 验证与边界

- 温度 0、固定 seed 下每个组合只跑一次；`temp07` 的三个 seed 也不是三次独立重复，文章里单独讨论了这一点。
- 32 道题、每道一对回答，判对率差一两道题就是 3 到 6 个百分点。
- 自我偏好那组数据量太小，文章没有下结论。
- 错误回答都只埋了一处错误，而且是作者能核对的事实错误；更隐蔽或需要推理才能发现的错误没有覆盖。
