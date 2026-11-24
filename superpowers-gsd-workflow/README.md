# Superpowers 计划导入 GSD 的实测

配套文章：[Superpowers + GSD：Claude Code 两套工作流怎么分工和衔接](https://costalong.com/2026/04/14/superpowers-gsd-workflow/)。

用一个 30 多行的 Go 命令行 `tally`（从 stdin 数行数和词数）当靶子，给它加一个 `-top N` 参数。全程用 `claude -p` 非交互调用：

1. Superpowers 的 brainstorming 和 writing-plans 写出设计文档和计划；
2. GSD 的 `/gsd-import --from <计划>` 分别在三种状态下导入：没有 `.planning/`、有 ROADMAP 但不指定 phase、指定一个 ROADMAP 里没有的 phase；
3. 把导入后的计划交给 `/gsd-execute-phase 2`，同时在另一份副本上用 `superpowers:executing-plans` 直接执行 Superpowers 原计划，记录耗时、轮次、费用，并独立跑 `go test ./...`。

运行日期 2026-11-24。Claude Code 2.1.331，主模型 `--model sonnet`；Superpowers 7.0.2，GSD 用 npm 包 `get-shit-done-cc` 1.42.3，Go 1.27.4。

## 目录

| 路径 | 内容 |
|---|---|
| `tally/` | 改动前的项目 |
| `planning-seed/.planning/` | 手写的最小 GSD 项目：PROJECT、ROADMAP（3 个 phase，Phase 1 已完成）、STATE、config（`mode: yolo`） |
| `outputs/` | brainstorming 的设计文档、writing-plans 的计划、两版导入后的 `02-01-PLAN.md`、三次导入的最终输出、第一次 plan-checker 报告 |
| `run.sh` / `summ.py` | 跑一次 `claude -p` 并从 stream-json 里汇总轮次、费用、token、工具调用 |
| `run_all.sh` | 按顺序重跑全部步骤 |
| `results.json` | 11 次运行的汇总数据 |

## 运行

```sh
WORK=/tmp/sp-gsd ./run_all.sh
```

需要本机已装 Superpowers 插件和 GSD。`/gsd-execute-phase` 和 `/gsd-import` 的工作流会调用 `gsd-sdk`，如果它不在 PATH 上，模型会退回手工读写 `.planning/`（见 `results.json` 里的 `10-exec-gsd-nosdk`）。不想全局安装时可以装在临时目录：

```sh
npm install --prefix /tmp/gsdpkg --ignore-scripts get-shit-done-cc@1.42.3
export PATH=/tmp/gsdpkg/node_modules/.bin:$PATH
```

第 5 步（回答导入时留下的问题）依赖第 3 步 plan-checker 的具体输出，没法写死。实测时用的提示词大意是：列出 checker 报的问题，告诉它需求 ID 用 `[TOP-01, TOP-02]`，要求按 import 工作流修正、重跑 checker、更新 ROADMAP 并提交。

## 结果

| 运行 | 墙钟 秒 | 轮次 | 费用 USD | go test |
|---|---|---|---|---|
| brainstorming + writing-plans | 48 | 8 | 0.27 | - |
| import，无 `.planning/` | 16 | 3 | 0.20 | BLOCKER，不写文件 |
| import，有 ROADMAP | 67 | 10 | 0.43 | 推断 Phase 2，checker 不过，未提交 |
| import，指定 Phase 5 | 20 | 5 | 0.22 | BLOCKER，不写文件 |
| import 补完 | 93 | 11 | 0.46 | checker 通过，提交 |
| execute-phase，无 gsd-sdk | 59 | 10 | 0.43 | 通过 |
| execute-phase #1 | 81 | 10 | 0.57 | 通过（派了 gsd-executor） |
| execute-phase #2 | 61 | 12 | 0.40 | 通过（主会话内联） |
| execute-phase #3 | 60 | 13 | 0.48 | 通过（主会话内联） |
| executing-plans #1 | 43 | 9 | 0.29 | 通过 |
| executing-plans #2 | 100 | 12 | 0.68 | 通过（多了一次 opus 审查子代理） |

费用取 stream-json 最后一个 `result` 事件的 `total_cost_usd`，包含子代理；轮次是所有 `result` 事件的 `num_turns` 之和（主会话等后台子代理时会产生两个 `result`）。每种执行方式只跑了 2 到 3 次，样本很小，只能说明量级。

## 边界

- 这是一个两任务的小计划，GSD 的 wave 并行在这里没有用武之地，结论不能外推到多计划、多 phase 的项目。
- `.planning/` 是手写的最小版本，不是 `/gsd-new-project` 生成的，没有 REQUIREMENTS.md。
- 所有运行都加了「不能回答问题，按推荐项继续」的提示，没有触发 AskUserQuestion；交互式使用时流程会在提问处停下。
- 原始 stream-json 日志含本机路径，没有提交。
