# Gemini 4 Neon 与 Claude Opus 5.5 实测

配套文章：[Gemini 4 Neon 对 Claude Opus 5.5 实测：答对率几乎打平，Neon 默认思考慢 3 到 8 倍](https://costalong.com/2026/11/26/gemini-4-neon-vs-claude-opus-5-5/)。

三套能自动判分的题：10 道 Go 编程题（隐藏测试判分）、30 道推理与数学题（精确答案判分）、3 份 10 万到 60 万 token 的长上下文检索题（埋 8 条真记录和 4 条干扰记录）。两个模型都用 high 思考强度，编程和推理另用 Neon 的 low 强度跑一遍作对照。每次调用记下延迟、token 和按官方标价算的成本。

这是教学用的复现脚本，题目是自己出的，每题只跑 2 到 3 遍，不是模型基准。

## 文件

| 文件 | 作用 |
|---|---|
| `clients.py` | 两个模型的统一调用：Gemini 走 REST（`GEMINI_API_KEY`），Claude 走 `claude -p`；返回文本、延迟、token 和成本 |
| `run.py` | 跑一套题：`python3 run.py <coding\|reasoning\|longctx> <gemini\|claude\|both\|gemini-low> [--runs N] [--jobs N]`，结果追加到 `logs/<套题>.jsonl`，已有的 (题目, 模型, 轮次) 会跳过 |
| `reasoning.py` | 生成 `reasoning.jsonl`：网格路径、数位计数、排座、骰子概率、工作日推算五类各 6 题，固定种子，答案由程序算出 |
| `longctx.py` | 生成 `longctx/{100k,300k,600k}.json`：Go 标准库源码当干草堆，埋 8 条 `NOTE(ops-ledger)` 真记录和 4 条 `NOTE(test-fixture)` 干扰记录 |
| `coding/<题目>/` | 每题一个 `prompt.md`（发给模型的题面）、`solution_test.go`（隐藏测试）、`ref/solution.go`（参考实现）；`coding/check_refs.sh` 用参考实现跑一遍测试 |
| `gocheck.py` | 取回答里第一个 ```go 代码块，配隐藏测试跑 `go test -race -count=3`，三遍都过才算过；写 `logs/coding-tests.jsonl` |
| `grade.py` | 只读 `logs/`，打印文章里的全部数字：`python3 grade.py coding\|reasoning\|longctx\|cost` |
| `chart.py` | 从 `logs/` 画文章配图 `chart.png`，需要 matplotlib 和 Noto Sans CJK 字体 |
| `logs/` | 文章用到的原始结果，含每次调用的完整回答 |

## 运行

文章数据来自 2026-11-26，Go 1.27.4，模型 `gemini-4-neon`（Gemini API 标准层）和 `claude-opus-5-5`（Claude Code CLI，订阅登录）。

```bash
cd gemini-neon-vs-opus-55
python3 reasoning.py
python3 longctx.py                          # 依赖本机 GOROOT 里的标准库源码
(cd coding && ./check_refs.sh)              # 参考实现应全部 PASS

export GEMINI_API_KEY=...
python3 run.py coding both --runs 3
python3 run.py coding gemini-low
python3 run.py reasoning both --runs 2
python3 run.py reasoning gemini-low
python3 run.py longctx both --runs 2 --jobs 2
python3 gocheck.py
python3 grade.py cost
```

`longctx/` 下的题目约 2.9MB，不放进仓库，要用 Go 1.27.4 重新生成。生成结果和文章所用的一致时 md5 为：

```
86d3140c1292390e74e57379f4325a88  longctx/100k.json
b1bdc4d27b069955e39e1ada04cc44ea  longctx/300k.json
f4ce08fa6d3550bf1dbcb836567f6a40  longctx/600k.json
```

`reasoning.jsonl` 的 md5 是 `575614ac840b2d47a0adb5c599babeb5`。

不想重跑模型时，`grade.py coding`、`reasoning`、`cost` 直接读仓库里的 `logs/`；`grade.py longctx` 和 `chart.py` 还要先生成 `longctx/`。自己重跑前先 `mv logs logs.article`，否则 `run.py` 会跳过已有结果。

## 验证与边界

- Claude 通过 `claude -p` 调用：替换系统提示、关闭工具和 MCP、不读 settings、在空目录运行，除提示词外多约 600 个缓存前缀 token。延迟用 CLI 报告的 `duration_api_ms`，`wall_s` 是含进程启动的总耗时。Gemini 走公开 API 标准层，两边的网络路径和排队情况不同，延迟只能当量级看。
- 成本 `cost_usd` 一律按基础输入价计，不算缓存，方便两边对比；CLI 会自动写 1 小时缓存（每百万 token 8 美元），实际按价目表折算的金额记在 `billed_usd`。Claude 这边走的是订阅，并没有真按 API 计费。
- 价格取自 2026-11-26 的官方价目页：Neon 输入 3、输出 15 美元每百万 token（思考 token 按输出计）；Opus 5.5 输入 4、输出 20。
- 同一段文本两边的 token 数不同：长上下文题 Claude 计出的 token 比 Gemini 多约 35%，所以「100k / 300k / 600k」是按 Gemini 的分词定的名字。
- 编程题由 `go test -race -count=3` 判分，并发题对部分错误实现结果不稳定，三遍都过才算过；整包卡死或 panic 时逐个测试单独重跑，算部分得分。Claude 的 parmap 第 3 轮那份答案在不同次判分里通过 6 或 7 个测试，`logs/coding-tests.jsonl` 记的是其中一次。
- Neon 的 expr 第 3 轮把 65,536 个输出 token 全用在思考上，以 `MAX_TOKENS` 结束、没有给出代码，按 0 分算，没有重试。
- low 强度对照只在编程和推理上各跑 1 遍，长上下文没跑。
- 推理题每类只有 6 道，偏计数和枚举，题型对模型的熟悉程度会影响结果。
