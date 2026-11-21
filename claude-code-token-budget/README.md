# Claude Code 无头调用的 token 账

配套文章：[Claude Code 无头调用的 token 账：首轮 45k 从哪来](https://costalong.com/2026/11/20/claude-code-token-budget/)。

`run.py` 执行一次 `claude -p`，只把 `HOME`、`PATH`、`LANG`、`TERM`、`USER` 传给子进程，从 `--output-format stream-json --verbose` 的输出里按请求去重 `usage`，打印每次请求的上下文（`input_tokens + cache_creation_input_tokens + cache_read_input_tokens`）和 `total_cost_usd`。配套的有一个不依赖任何库的 stdio MCP 服务器、一个生成 CLAUDE.md 的脚本和一个虚构的 Go 订单服务 `proj/`，用来逐块测内置工具、MCP、CLAUDE.md、技能、agent 和缓存各占多少。

这是教学用的测量脚本，数字只对文章里的 Claude Code 版本和配置成立，不是计费依据。订阅登录下 `total_cost_usd` 是按标价算的估算值，不是真实扣款。

## 文件

| 文件 | 作用 |
|---|---|
| `run.py` | `run.py NAME [--cwd DIR] [--stdin FILE] -- <claude 参数...>`，默认工作目录是 `proj/`，结果存 `runs/NAME.jsonl` |
| `multi.py` | `multi.py NAME TURNS.jsonl -- <claude 参数...>`，在一个进程里一轮一轮发消息，每轮等 `result` 回来再发下一条 |
| `summarize.py` | `summarize.py NAME...`，从 `runs/` 里重新打印摘要 |
| `gen_claudemd.py` | `gen_claudemd.py 行数 [zh\|en]`，生成虚构项目 orderhub 的 CLAUDE.md，输出到 stdout |
| `tinyops_server.py` | 10 个运维类假工具的 stdio MCP 服务器，参数是暴露几个工具 |
| `mcp1.json` / `mcp3.json` / `mcp10.json` | 分别暴露 1、3、10 个工具的 `--mcp-config` |
| `turns4.jsonl` / `turns6.jsonl` | `multi.py` 用的多轮输入，`--input-format stream-json` 格式 |
| `proj/` | 虚构的 Go 订单服务，`CLAUDE.md` 加 5 个源文件，多步任务读的就是它们 |
| `fixtures/home-project/.claude/` | 项目级技能 `deploy-check` 和 agent `pg-reviewer`，测它们的上下文开销 |

`run.py` 保存初始化消息时，只保留本实验自己的 MCP、技能和 agent 名字，其余的替换成计数，避免把本机装了什么写进结果。

## 运行

文章数据来自 Claude Code 2.1.329，默认模型 claude-opus-5-5，订阅账号 OAuth 登录（`apiKeySource: none`），Ubuntu，Python 3.14。

**工作目录要放在 home 下。** 文章里实验目录在 Claude Code 自己的临时目录 `/tmp/claude-<uid>/` 下面时，项目 CLAUDE.md 没有被加载。把本仓库克隆到 home 下的任意位置即可。

```bash
cd claude-code-token-budget
B=(-p --output-format stream-json --verbose --setting-sources project --strict-mcp-config)

# 内置工具
python3 run.py t-none  -- "${B[@]}" --tools "" "Reply OK"
python3 run.py t-read  -- "${B[@]}" --tools Read "Reply OK"
python3 run.py t-four  -- "${B[@]}" --tools "Bash,Read,Edit,Write" "Reply OK"
python3 run.py t-all   -- "${B[@]}" "Reply OK"

# MCP：有没有 ToolSearch
python3 run.py m10-none -- "${B[@]}" --tools "" --mcp-config mcp10.json "Reply OK"
python3 run.py m10-ts   -- "${B[@]}" --tools "Read,ToolSearch" --mcp-config mcp10.json "Reply OK"

# CLAUDE.md 的边际成本：换一份 200 行的
cp proj/CLAUDE.md proj/CLAUDE.md.orig
python3 gen_claudemd.py 200 zh > proj/CLAUDE.md
python3 run.py md200 -- "${B[@]}" --tools "" "Reply OK"
mv proj/CLAUDE.md.orig proj/CLAUDE.md

# 技能和 agent：复制到 home 下另一个目录
mkdir -p ~/.cache/cc-tokens-home && cp -r fixtures/home-project/.claude ~/.cache/cc-tokens-home/
python3 run.py skills --cwd ~/.cache/cc-tokens-home -- "${B[@]}" "Reply OK"

# 多轮
python3 multi.py turns6 turns6.jsonl -- -p --input-format stream-json --output-format stream-json --verbose \
  --setting-sources project --strict-mcp-config --tools ""

python3 summarize.py t-none t-all md200
```

`claude` 默认从 `PATH` 里找，也可以用 `CLAUDE_BIN` 指定。`mcp*.json` 里服务器路径写的是 `../tinyops_server.py`，相对默认工作目录 `proj/`；用 `--cwd` 换目录时要改成绝对路径。

## 验证与边界

- 每种配置大多只跑一次。缓存状态会影响费用：同一前缀第二次调用读缓存，比较费用时要分清冷启动和缓存已热。
- `--setting-sources project` 只限制 settings 文件，用户级 `~/.claude/CLAUDE.md` 仍会加载；你本机的用户级配置不同，基线数字也会不同。
- 内置工具数量、ToolSearch 的行为和缓存 TTL 都可能随 Claude Code 版本变化。
- 每次调用都会真实消耗额度，批量跑之前先用 `--tools ""` 的小提示词确认环境。
