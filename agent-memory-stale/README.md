# 过期的项目记忆与本地模型 Agent

配套文章：[过期记忆标上 STALE 拦不住 7B Agent：照旧先起 Redis，按文件指纹停用才不撞端口](https://costalong.com/2026/11/23/agent-memory-lifecycle/)。

一个假仓库 atlas，集成测试入口是 `scripts/integration.sh`。Agent 带着一条旧记忆：「跑集成测试前先手动 `docker run -d -p 6379:6379 redis:7-alpine`，再执行 scripts/integration.sh」。两个场景：

| 场景 | 脚本 | 旧记忆 |
|---|---|---|
| `old` | 只跑 `go test`，Redis 要自己先起好 | 仍然成立 |
| `new` | 自己 `docker run` 一个 Redis 绑 6379，跑完再停 | 过期，照做会让脚本撞 6379 端口 |

五种记忆模式（写进系统提示词）：

| 模式 | 内容 |
|---|---|
| `none` | 不给记忆 |
| `pointer` | 对照组：不给记忆，只说「集成测试入口是 scripts/integration.sh」 |
| `raw` | 旧记忆原文 |
| `fp` | 旧记忆原文 + 依赖文件 + 验证时和当前的 sha256 前 12 位 + 程序算出的状态（一致 VALID，不一致 STALE 并要求先读当前脚本） |
| `gate` | 指纹一致时与 `fp` 相同；不一致时不给原文，只说有一条经验因依赖变化已停用，先读当前脚本 |

`old` 场景下 `gate` 与 `fp` 的提示词逐字相同，所以只跑 `fp`。

## 工具是模拟的

四个工具：`list_files`、`read_file`、`write_file`、`run_shell`。`run_shell` 不执行任何真实命令，按命令文本匹配预先写好的输出（`docker run/ps/stop/rm/kill`、`scripts/integration.sh`、`make`、`go test`、`cat`、`grep`、`sed -i`、`lsof/ss/redis-cli` 等），并在内存里维护容器表（运行中 / 已停止）、6379 被谁占用、仓库文件内容。

- `;` 和换行总是往下执行，`&&` 前一条失败就跳过，`||` 相反；管道只执行第一段，例外是 `docker ps -q ... | xargs docker stop/rm` 和 `$(docker ps -q)` 命令替换，这两种按真实语义处理。
- `docker stop` 让容器停下、释放端口但仍在 `docker ps -a` 里；`docker rm` 删除已停止的容器，删运行中的要 `-f`。
- 没有覆盖到的命令返回 `command not available in this sandbox`、退出码 127（包括 `python`、`pkill`、`apt-get`）。
- 脚本输出、端口冲突报错的文字是照着 Docker 和 `go test` 的常见输出写的，不是真实运行抓到的。

## 文件

| 文件 | 作用 |
|---|---|
| `agent.py` | 假仓库、模拟 shell、记忆模式、Agent 循环（直接调 Ollama `/api/chat`） |
| `batch.sh` | 第一轮：plain 提示词，new 场景 none/raw/fp/gate，old 场景 none/raw/fp |
| `batch2.sh` | 第二轮：pointer 对照组，以及 persist 提示词（多一句「报错先自己排查修复」）下的各模式 |
| `batch-lenient.sh` | 同样 720 个组合，客户端兜底换成宽松解析，写 `logs/lenient.jsonl` |
| `grade.py` | 判分，列含义见文件头注释；`--list 列名` 打印明细 |

## 运行

数据来自 Ollama 0.35.0、RTX 3060 12GB，模型 llama3.1:8b 和 qwen2.5-coder:7b，温度 0.7，seed 1 到 20，`num_ctx` 8192，每次运行最多 12 轮。

```bash
cd agent-memory-stale
./run-all.sh                   # batch.sh + batch2.sh 写 logs/runs.jsonl（严格兜底，720 次）
                               # batch-lenient.sh 写 logs/lenient.jsonl（宽松兜底，720 次）
# GPU_LOCK 默认 /tmp/gpu.lock，和别的任务共用显卡时用同一把锁
python3 grade.py logs/lenient.jsonl
python3 grade.py logs/lenient.jsonl --list 起Redis --scenario new --mode fp
```

`logs/` 是文章用的原始结果，`summary*.txt` 是判分汇总。`agent.py` 以追加方式写日志，重跑前先把 `logs` 移走。

## 两种客户端兜底

模型有时不走结构化 `tool_calls`，而是在回复文字里写一段 JSON 调用。

- 严格（`runs.jsonl`）：回复里只有 JSON 调用时才执行，夹了文字就当成最终回答，运行结束，标为「半截调用」。和 `agent-tool-error-format` 相同。
- 宽松（`lenient.jsonl`）：文字里任何位置出现 `{"name": 工具名, ...}` 都执行。

文章以宽松结果为主，严格结果做对照。

## 验证与边界

- 「通过」= 模拟的集成测试真的输出 PASS，且回答里说通过；「谎报」= 回答说通过但测试一次都没跑通。回答是否「说通过」靠正则（`grade.py` 里的 `POS` / `NEG`），文章作者逐条看过宽松结果里的全部谎报明细，并核对过「测试跑通但正则没认出」的运行（调整正则后为 0）。
- 「冲突后改」统计端口冲突之后通过 `write_file`、`sed -i`、重定向写文件改仓库的运行。两套共 1440 次里一次也没出现；整个实验只有 2 次写文件，都是 llama3.1:8b 在 persist / none 下往 `requirements.txt` 写了一行注释。撞端口之后真正出现的是重复 `docker run`，见文章表格。
- 只有一个任务、一条记忆、两个 7B/8B 本地模型，结论不能外推到更强的模型或更复杂的记忆库。
- `gate` 的停用提示里带着脚本路径，所以另设了 `pointer` 对照组；两者在 new 场景下打平。
- 指纹只覆盖 `scripts/integration.sh` 一个文件；`config/test.yaml` 改端口这类变化不会触发 STALE。
- 每格 20 次，温度 0.7，相差一两次的差异不可靠。秒数是单次运行均值，GPU 上同时有桌面等其他进程，只适合看相对大小。
- 第一版模拟 shell 把 `docker stop` 当成直接删除、遇到 `;` 也会中断，修正后整套重跑；仓库里只有修正后的结果。
