# CLAUDE.md 长度与规则遵守率

配套文章：[CLAUDE.md 写到 1500 行，规则照样守：真正让规则失效的是放错位置](https://costalong.com/2026/07/06/claude-md-configuration-playbook/)。

用 `claude -p` 在一个虚构的小 Go 模块 `proj/`（模块名 `example.com/gw`）里跑 10 个小任务，CLAUDE.md 换成不同长度、不同写法的版本，每个版本都带同样 8 条能用脚本判定的规则，再按 git 提交和代码 diff 给每条规则打分。另外测了每种写法在会话开场占多少 token，以及把一条规则从 CLAUDE.md 挪进 PreToolUse hook 之后的效果。

这是教学用的测量，数字只对文章里的 Claude Code 版本（2.1.331）、模型（haiku 和 sonnet 当时的版本）和这份合成的 CLAUDE.md 成立。

## 文件

| 文件 | 作用 |
|---|---|
| `proj/` | 被改动的 Go 模块：一个内存 KV 存储、配置、时钟包和 `main.go`，没有测试 |
| `gen_variants.py` | 生成 `variants/` 下各版本 CLAUDE.md 和 `rules.json`（规则原文、每条规则所在行号） |
| `tasks.json` | 10 个任务的提示词，以及每个任务检查哪几条规则 |
| `run.py` | 对每个「版本 × 任务 × 重复」复制一份 `proj/`、放入该版本的指令文件、`git init`，然后跑 `claude -p` |
| `score.py` | 从每次运行的 git 历史和 diff 判定规则，输出汇总表和逐次结果 |
| `tokens.py` | 每种写法跑一次 `Reply OK`，取第一次请求的上下文 token 数 |
| `results-haiku.jsonl` / `results-sonnet.jsonl` | 每次运行一行：版本、任务、各规则是否通过、首轮上下文、轮数、费用、hook 拦截次数 |
| `tokens.jsonl` | 各写法的首轮上下文 token |

## 8 条规则

| 编号 | 规则 | 判定 |
|---|---|---|
| R1 | 提交信息以 `[gw] ` 开头 | `git log base..HEAD` 的每条标题 |
| R2 | 错误包装成 `fmt.Errorf("gw: <函数名>: %w", err)` | 新增非测试代码里每个带 `%w` 的 `fmt.Errorf` |
| R3 | 新测试文件命名为 `<name>_internal_test.go` | 新增的 `_test.go` 文件名 |
| R4 | 只用 `log/slog`，每次调用带 `"component"` | 新增代码里不出现 `log` 包和 `fmt.Print`，有 `"component"` |
| R5 | 新增导出函数/方法的文档注释以 `(owner: core)` 结尾 | 新增的每个导出 `func` 上方注释 |
| R6 | 表驱动测试切片叫 `cases`、循环变量叫 `tc` | 测试里有 `for _, tc := range cases` |
| R7 | 每次改动在 CHANGELOG.md 的 `## Unreleased` 下加一行 | `## Unreleased` 与 `## 0.1.0` 之间有 `- ` 行 |
| R8 | 非测试代码不直接调 `time.Now()`，用 `clock.Now()` | 新增非测试代码 |

规则都故意选了模型不会自己猜到的写法，所以没有 CLAUDE.md 时大多是 0 分。R8 例外：`proj/internal/clock` 包本身就摆在那里，模型看了代码会自己用。

## 版本

| 版本 | 内容 |
|---|---|
| `none` | 没有 CLAUDE.md |
| `claude-50` / `-200` / `-500` / `-1500` | 同样 8 条规则，每条自成一个二级标题小节，按固定相对深度（6%、12%、28%、45%、55%、72%、88%、95%）插进合成的项目说明里 |
| `claude-500-buried` | 同一份 500 行填充，规则不加标题，直接塞进某个子系统小节的列表中间 |
| `import` | 50 行主文件（含全部规则）+ `@docs/subsystems.md` 导入 472 行填充 |
| `claude-500-hook` | `claude-500` 去掉 R1 那一行，改由 `.claude/settings.json` 里的 PreToolUse hook 拦截不合规的 `git commit` |

填充内容是脚本生成的：命令、目录、28 个子系统说明、环境变量表、术语表、运维步骤、决策日志。它像真项目文件，但重复度比真文件高，也不和任何规则冲突。

## 运行

```bash
cd claude-md-length
python3 gen_variants.py variants

# 项目必须放在 $HOME 下面：2.1.331 里放在 /tmp 下的项目，CLAUDE.md 没有被自动加载
export RUNS_DIR=$HOME/.cache/cmd-length/runs CLAUDE_BIN=$(command -v claude)
python3 run.py --variants none,claude-50,claude-200,claude-500,import,claude-500-hook --reps 4 --jobs 4
python3 run.py --variants claude-500-buried,claude-1500 --reps 3 --jobs 4
python3 score.py --out results-haiku.jsonl

RUNS_DIR=$HOME/.cache/cmd-length/runs-sonnet python3 run.py --variants claude-50,claude-500,claude-1500 --reps 1 --model sonnet
RUNS_DIR=$HOME/.cache/cmd-length/runs-sonnet python3 score.py --out results-sonnet.jsonl

TMPDIR=$HOME/.cache/cmd-length/tmp python3 tokens.py --reps 2
```

`run.py` 的固定参数：`--model haiku --output-format stream-json --verbose --max-budget-usd 1 --no-session-persistence --setting-sources project --strict-mcp-config --dangerously-skip-permissions`，并去掉父进程里以 `CLAUDE` 开头的环境变量。`--setting-sources project` 在 2.1.331 里同时挡掉了用户级 `~/.claude/CLAUDE.md`、用户级插件和 hook（让模型列出上下文里的 CLAUDE.md 路径：带这个参数回答 NONE，不带则列出用户级文件）。旧版本不一定如此。

跑过的结果目录会被跳过，`--budget` 按已有 `stream.jsonl` 里的 `total_cost_usd` 累计，超过就不再发起新运行。

## 结果（2026-11-24）

haiku，共 300 次；sonnet，共 30 次。分子是通过次数，分母是该规则适用的次数。

| 版本 | 首轮上下文 | R1 | R2 | R3 | R4 | R5 | R6 | R7 | R8 | 合计 |
|---|---|---|---|---|---|---|---|---|---|---|
| none | 22,287 | 0/40 | 0/16 | 0/20 | 0/12 | 0/32 | 0/20 | 9/40 | 12/12 | 21/192 |
| claude-50 | 22,887 | 40/40 | 16/16 | 20/20 | 12/12 | 28/32 | 20/20 | 40/40 | 12/12 | 188/192 |
| claude-200 | 25,774 | 40/40 | 16/16 | 20/20 | 12/12 | 27/32 | 20/20 | 40/40 | 12/12 | 187/192 |
| claude-500 | 32,006 | 40/40 | 16/16 | 20/20 | 12/12 | 28/32 | 20/20 | 40/40 | 12/12 | 188/192 |
| claude-1500 | 61,775 | 30/30 | 12/12 | 15/15 | 9/9 | 20/24 | 15/15 | 28/30 | 9/9 | 138/144 |
| import | 32,079 | 40/40 | 16/16 | 20/20 | 12/12 | 28/32 | 20/20 | 40/40 | 12/12 | 188/192 |
| claude-500-hook | 31,972 | 40/40 | 16/16 | 20/20 | 12/12 | 28/32 | 20/20 | 40/40 | 12/12 | 188/192 |
| claude-500-buried | 31,973 | 30/30 | 12/12 | 3/15 | 9/9 | 1/24 | 15/15 | 30/30 | 9/9 | 109/144 |

sonnet：claude-50、claude-500、claude-1500 各 47/48，三次漏掉的都是 R5。

R5 在正常版本里的漏分全部来自任务 T05：模型给未导出的 `statusRecorder` 类型写了 `WriteHeader` / `Write` 方法（实现 `http.ResponseWriter` 接口），没给它们加 `(owner: core)`。按规则字面算漏，按意图可以争论。

首轮上下文（`Reply OK`，两次取值几乎相同）：none 22,212；50 行 22,810；200 行 25,695；500 行 31,935；1500 行 61,697；`@import` 32,020；`.claude/rules/` 不带 `paths` 32,010；带 `paths` 22,814；块级 HTML 注释包住 472 行填充 22,814。

## 边界

- 任务都很短（haiku 平均 7 到 9 轮），单会话，没有触发压缩。长会话、压缩之后的表现没测。
- 规则措辞清楚、互不冲突，填充里没有与之矛盾的内容。真实文件里规则模糊或打架的情况没测。
- 每个格子 30 到 40 次，1500 行版本多出的 3 次漏分（两次 R7、一次 R5）样本太小，只能算迹象。
- 订阅登录下 `total_cost_usd` 是按标价估算的值，不是真实扣款。
