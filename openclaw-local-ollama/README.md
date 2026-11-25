# OpenClaw 接本地 Ollama 小模型：固定开销、任务成功率和 tools 配置实测

配套文章：[OpenClaw 接本地 Ollama 小模型](https://costalong.com/2026/03/04/openclaw-usage-guide/)。

在 OpenClaw 和 Ollama 之间放一个只用 Python 标准库写的记录代理（`proxy.py`），把 OpenClaw 每次发给 `/api/chat` 的工具列表、系统提示词长度、`num_ctx`，以及 Ollama 返回的 `prompt_eval_count` 和模型发出的原生 `tool_calls` 记下来。在这个基础上测三件事：

- 一句 `Reply with the single word: pong` 之前 OpenClaw 固定塞了多少 token，分别砍掉 bundled skills、`BOOTSTRAP.md`、换 `tools.profile`、精简工作区文件后各少多少（`overhead.py`）；
- 5 道工作区小任务（写文件、求和、用 shell 数 ERROR 行、改 JSON、列目录写索引）× 4 轮 × 模型 × 两种配置，用检查函数按文件内容或回复判对错（`tasks.py`、`run_matrix.sh`）；
- `tools.profile` / `allow` / `alsoAllow` / `deny` 的 13 种写法下，OpenClaw 实际发给模型的工具名单（`tools_matrix.py`）。

另外两个对照脚本绕开 OpenClaw 直接调 Ollama，看模型在第一轮是否发原生工具调用：`control_native_calls.py`（OpenClaw 原请求 / 换一行系统提示词 / 只留 4 个工具）和 `control_runtime_msg.py`（OpenClaw 原样消息 / 去掉尾部 runtime 消息）。

这是教学用的复现脚本，不是基准。成功率只有 5 题 × 4 轮，温度用的是 Ollama 默认值，差一两题在噪声范围内。

## 文件

| 文件 | 作用 |
|---|---|
| `proxy.py` | 监听 `127.0.0.1:11435`，转发到 Ollama，写 `PROXY_LOG`（jsonl）；设 `DUMP_DIR` 时把完整请求体存下来（里面有主机名和本机路径，不要提交） |
| `overhead.py` | `overhead.py OUT.jsonl models` 测 4 个模型的默认开销；`overhead.py OUT.jsonl ablation` 依次叠加精简步骤（会改工作区文件，先备份） |
| `tools_matrix.py` | `tools_matrix.py OUT.jsonl [变体名 ...]`，每种 `tools` 写法跑一轮 pong |
| `tasks.py` | 5 道任务和检查函数；`CONFIG_LABEL`、`MODELS`、`N` 由环境变量给 |
| `run_matrix.sh` | default（非交互 onboard 写出的配置）和 slim（`coding` + `skills.allowBundled: []` + 删 `BOOTSTRAP.md`）两组各跑一遍 |
| `stats.py` | 汇总 `logs/tasks.jsonl`：每题通过数、失败类型、中位耗时和每轮 prompt token |
| `logs/` | 文章里的原始结果（2026-11-25，OpenClaw 2026.11.9，Ollama 0.35.0，RTX 3060 12GB），本机路径已替换成 `/home/user` |

## 运行

```sh
# 隔离安装，不装全局
# 把本目录拷成 bench/code，结果写到 bench/logs
mkdir -p bench/home bench/logs && cp -r openclaw-local-ollama bench/code && cd bench && chmod go-w . home
npm init -y && npm install openclaw@2026.11.9
export HOME=$PWD/home OC=$PWD/node_modules/.bin/openclaw
$OC onboard --non-interactive --accept-risk --mode local --auth-choice ollama \
  --skip-channels --skip-daemon --no-install-daemon --skip-health --skip-hooks --skip-search --skip-skills --skip-ui
cp -a home/.openclaw/workspace ws-backup

# 代理放在 OpenClaw 和 Ollama 中间
PROXY_LOG=$PWD/logs/proxy.jsonl python3 code/proxy.py &
$OC config set models.providers.ollama.baseUrl http://127.0.0.1:11435

export PROXY_LOG=$PWD/logs/proxy.jsonl
python3 code/overhead.py logs/overhead_models.jsonl models
python3 code/tools_matrix.py logs/tools_matrix.jsonl
code/run_matrix.sh         # 读 bench/ws-backup，写 bench/logs/tasks.jsonl
python3 code/stats.py logs/tasks.jsonl

# 对照：先用 DUMP_DIR 抓一份 OpenClaw 的首轮请求，再直连 Ollama 重放
python3 code/control_native_calls.py dumps/req-XXXX.json qwen2.5-coder:3b,qwen2.5-coder:7b,llama3.1:8b logs/task_prompts.json 2
python3 code/control_runtime_msg.py dumps/req-XXXX.json llama3.1:8b logs/task_prompts.json 2
```

`BOOTSTRAP.md` 只在首次引导完成前注入。`overhead.py ablation` 删过一次之后，即使把文件拷回来，OpenClaw 也不再注入它（`logs/overhead_steady.jsonl`），所以任务矩阵里的 default 组实际是"引导已完成"的状态。

`HOME` 指向的目录及其上级如果是组可写的，OpenClaw 2026.11.9 会拒绝读配置（`No safe OpenClaw temp root is available`），所以先 `chmod go-w`。全程只用 `agent --local`，不起网关、不连任何聊天渠道。

## 边界

- 只测了 OpenClaw 2026.11.9 的 `agent --local` 嵌入式运行，没测网关模式和渠道消息。
- 模型是 Ollama 库里的 qwen2.5-coder:3b / 7b、llama3.1:8b、gemma4（8B，Q4_K_M），OpenClaw 自动写入的 `contextTokens` 是 32768，请求里的 `num_ctx` 也是 32768。
- token 数是各模型自己的分词器算的，不同模型之间不能直接比字符数。
