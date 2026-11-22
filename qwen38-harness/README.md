# Qwen3.8-27B Harness 适配器：Pi 与 DSH 对照实验

配套文章：[Qwen3.8-27B Harness 适配器实测：Pi、DSH 与验收漏测](https://costalong.com/2026/11/22/qwen38-27b-harness-adapters/)。

Go 程序负责准备任务、启动 **真正的 Pi 1.5.2**、收集 JSONL 事件、在外部目录运行验收测试，再汇总基座与 Pi LoRA 的结果。Agent 循环及工具实现由 Pi 提供。本案例不实现 RL 训练，也不重跑 Terminal-Bench 或 SWE-bench。

## 先看验证到了哪里

- 已在 macOS arm64、Go 1.27.2 验证三个判分器：原始错误实现全部被拒绝，参考实现全部通过。
- 已用真实 Pi 1.5.2 和**脚本模型服务**完成集成测试：三题、两个条件，每次执行 `read`、`write`、`bash`，采集 usage 后通过外部验收。脚本直接提供参考答案和模拟 usage；这里只验证宿主工具、协议和统计链路。
- 已在 M4 Pro 48 GB 上真实加载 Qwen3.8-27B Q4_K_M 与官方 F16 Pi LoRA，完成三题、两个条件、各三轮的 18 个计分试次。原验收 V1 为基座 4/9、LoRA 9/9；发现漏测后，用 V2 对原答案离线重判，变为基座 3/9、LoRA 6/9。分别保留[三轮原记录](verification/real-gguf-2026-11-22-repeated.json)、[首轮记录](verification/real-gguf-2026-11-22.json)和 [V2 补测记录](verification/regrade-v2-2026-11-22.json)。这是小样本教学题，不是官方基准复现。
- 尚未进行 BF16/vLLM 复现或 RL 训练。协议测试与真实模型测试分别保留，不能相互替代。

## 三道公开教学题

| 题目 | 修复要求 | 外部验收关注点 |
| --- | --- | --- |
| `bytesize` | 解析 B、KiB、MiB、GiB | 空白、非法输入、uint64 溢出 |
| `retry-delay` | 指数退避并限制上限 | 非法参数、Duration 溢出、极大 attempt |
| `csv-record` | 编码单条 CSV 记录 | 逗号、引号、换行、空字段 |

每次尝试从嵌入的同一份 `go.mod`、`TASK.md`、错误实现和可见测试开始。Agent 只允许修改 `solution.go`；判分器只复制这一个普通文件到新目录，使用自己保管的 go.mod 和验收测试。修改可见测试、添加其他实现文件或依赖，不会被带入验收。`run` 与历史自检继续使用原文件 `acceptance_test.go.txt`（V1）；`regrade` 明确使用独立的 `acceptance_v2_test.go.txt`，不覆盖历史结果。

验收同时检查 `go test -json` 中 `TestAcceptance` 和包级 `pass`，不会只看退出码。测试及参考答案本身在公开仓库中可见，这不是秘密盲测，也不具备对抗性判分的隔离保证。题目很少、难度有限，不能据此推广成通用能力排名。

## 1. 不调用模型的自检

需要 macOS 或 Linux、Go 1.25+；此独立模块没有第三方 Go 依赖。进入案例目录后执行：

```bash
go test ./...
go run . selfcheck
```

本次实际输出：

```text
bytesize: buggy=rejected reference=accepted
retry-delay: buggy=rejected reference=accepted
csv-record: buggy=rejected reference=accepted
selfcheck passed: 3 graders checked; no Pi or model invoked
```

本机曾出现 `compile: version "go1.27.1" does not match go tool version "go1.27.2"`：环境里的 GOROOT 指向旧 gvm 目录，而 PATH 使用 Homebrew 的新 Go。本次仅用 `env -u GOROOT go test ./...` 和 `env -u GOROOT go run . selfcheck` 修正该命令的环境，没有修改全局配置。工具链正常时不需要这个前缀。

## 2. 检查真实 Pi 的接口和工具

需要 Node.js 22.19+。可在临时目录安装固定版本，不覆盖已有 Pi：

```bash
npm install --prefix /tmp/qwen38-pi-runtime --ignore-scripts --no-audit --no-fund \
  @earendil-works/pi-coding-agent@1.5.2

HARNESS_PI_BIN=/tmp/qwen38-pi-runtime/node_modules/.bin/pi \
  go test -run TestRealPiWithScriptedEndpoint -v
```

未设置 `HARNESS_PI_BIN` 时，普通 `go test ./...` 会跳过这项集成测试。脚本服务仅在测试过程中监听随机本地端口；临时结果随测试目录清理。它没有 Qwen 权重，不下载模型，不调用外部模型服务，也不会产生可信的模型 token 用量。

测试覆盖：固定 CLI 版本、JSONL 消费、真正的文件读取与写入、Pi bash 执行 `go test`、外部答案验收、两个条件的请求采样参数、usage 汇总。

## 3. 准备真实模型服务

下面按 [Pi 适配器模型卡](https://huggingface.co/harness-hub/Qwen3.8-27B-pi-adapted#use-with-pi)提供的 vLLM 路径整理。服务脚本语法和参数组合已检查；**本节的 Linux/vLLM 路径未执行**。本机实际执行的是后面的 Mac/llama.cpp/GGUF 路径。

这是 Linux GPU 服务端步骤；Mac 可以运行 Go 驱动器和 Pi，再通过 SSH 隧道连接 GPU 服务。LoRA 仍需加载完整基座及上下文缓存，不能按适配器文件大小估算显存。先按实际硬件确认容量。

服务端安装可选用独立环境中的 `vllm==0.32.0`、`transformers>=5.8.0`，并记录实际 CUDA、驱动与依赖版本；版本和模型支持依据见 [vLLM Qwen3.8 配方](https://recipes.vllm.ai/Qwen/Qwen3.8-27B)与 [LoRA 文档](https://github.com/vllm-project/vllm/blob/v0.32.0/docs/features/lora.md)。仅固定顶层包版本还不等于完整环境锁定。

下载以下固定修订的本地快照。这一步会下载数十 GB 基座权重，按需要在 GPU 主机执行：

```bash
hf download Qwen/Qwen3.8-27B \
  --revision 37561816e66b5b9153b1b64c10968c18c1e6f4a0 \
  --local-dir ./models/qwen38-base

hf download harness-hub/Qwen3.8-27B-pi-adapted \
  --revision 7d42b119e2d4d475fa11270634b1ef98d1cd5aee \
  --local-dir ./models/qwen38-pi

HARNESS_BASE_MODEL="$PWD/models/qwen38-base" \
HARNESS_PI_ADAPTER="$PWD/models/qwen38-pi" \
  bash serve-vllm.sh
```

`serve-vllm.sh` 在同一个 vLLM 服务中暴露 `qwen-base` 和 `qwen-pi` 两个 ID。它沿用适配器卡中的 `qwen3_xml` 工具解析器，开启 LoRA、prefix caching 和 `mamba-cache-mode align`，关闭 thinking，限制同时服务的序列数为 1。默认监听 `127.0.0.1:8000`；不要把本地服务直接当成有鉴权的公开接口。

多 GPU 可设置 `HARNESS_TENSOR_PARALLEL`。脚本接受额外 vLLM 参数，但更改上下文、量化、模板、缓存、输出预算等设置后，须记录实际配置并让两组一致；不能继续视作相同实验条件。

检查 `/v1/models`：

```bash
curl --fail http://127.0.0.1:8000/v1/models
```

两个 ID 都在列表中才开始。ID 是路由名称，不是权重真实性证明；还应核对服务日志、base/adapter 路径与快照修订。程序会保存模型列表，但不能替服务端证明实际加载了哪套权重。

## 4. 让同一个 Pi 分别调用两组模型

在案例目录执行：

```bash
go run . run \
  -pi /tmp/qwen38-pi-runtime/node_modules/.bin/pi \
  -url http://127.0.0.1:8000/v1 \
  -base-model qwen-base -adapter-model qwen-pi \
  -runs 3 -timeout 5m -out results/qwen38-first
```

三题 × 两个条件 × 三次尝试，共 18 次 Agent 运行，每次至多 5 分钟。结果目录必须是新目录，已有目录不会被覆盖。需要 API key 时通过 `HARNESS_EXPERIMENT_API_KEY` 传入；不写在命令参数、配置文件或汇总报告里。

临时任务目录只用于重置题目，**不是操作系统沙箱**。Pi 的 bash 工具拥有当前进程的权限；实际模型实验适合放在专用容器或一次性测试机器里。程序为每次运行新建 `PI_CODING_AGENT_DIR`，不覆盖用户原有 Pi 配置，并禁用扩展、MCP、skills、提示模板和上下文文件发现。

两组共用配置：`openai-completions`、text only、thinking off、temperature 0.8、top_p 1、每次生成最多 4096 token、131072 上下文、read/bash/edit/write 四种工具，禁用自动重试和自动压缩。任务及提示带 SHA-256；执行先后顺序在相邻任务与重复间交替，减轻总是基座先跑带来的偏差。

没有控制服务端随机种子，也没有清空 GPU/KV/系统缓存。这里使用壁钟上限，没有实现官方 100 步预算；采样与结果都不能宣称是官方基准复现。

## 5. 检查结果，再读汇总

| 文件 | 内容 |
| --- | --- |
| `metadata.json` | Pi/Go/平台版本、运行配置、采样参数、随机种子未控制等信息 |
| `server-models.json` | 服务端返回的模型列表 |
| 每次运行的 `events.jsonl` / `stderr.log` | 原始 Pi 事件与诊断 |
| 每次运行的 `solution.go.txt` / `grade.jsonl` | 最终答案与外部测试输出 |
| `results.json` | 逐次状态、判分、使用量、工具次数、时间及哈希 |
| `summary.json` | 分条件通过数、不可评分次数及双方都通过的配对中位数 |

重新生成汇总：

```bash
go run . summarize results/qwen38-first/results.json
```

统计按 [Pi 1.5.2 JSON 事件契约](https://github.com/earendil-works/pi/blob/v1.5.2/packages/coding-agent/docs/json.md)读取 `message_end.message.usage`，忽略流式增量和 `agent_end.messages` 的重复信息。工具次数按 `tool_execution_start.toolCallId` 计数。usage 不完整、全为零或任务被截断时，token 字段记为 `null`，不拿部分值算节省；数值仍依赖服务端和 Pi 的 usage 归一化是否准确。

`agent_wall_ms` 是 Pi 启动到进程退出的壁钟时间，包含工具执行及 CLI 开销，不包含模型服务启动和外部验收；外部验收耗时另记 `grade_wall_ms`。

`completed` 表示 Pi 正常结束，正确与否仍由验收决定。`timeout` 是预算内留下的最终答案，仍参加验收；若超时前已写出正确答案，可以通过，但不会进入完整运行的效率比较。API、CLI、事件格式和判分器启动错误记为不可评分，汇总单列，程序以非零状态退出，不能把这些故障隐去后只展示通过率。

工具次数和耗时的中位数只使用**双方都通过、且都正常结束**的相同题目/重复；token 中位数再要求双方 usage 完整。缺少配对时输出 `null`。这里没有成本换算、显著性结论或预置的“适配器胜出”数据。

原始结果目录已忽略，不默认提交。实验不会把轨迹上传到任何地方；分享前应检查工具输出、代码内容及运行路径是否适合公开。

## Mac 上用同一份 GGUF 关闭／启用 LoRA

`serve-llama.sh` 适用于支持 Qwen3.8 和 LoRA 的 llama.cpp。本机版本为 0.6.0，build 11429，commit `d81235049`。准备下列两个文件；两组必须使用同一个基座文件：

```bash
hf download ggml-org/Qwen3.8-27B-GGUF Qwen3.8-27B-Q4_K_M.gguf \
  --revision c1869413dece09109e55b7dcc2c77ef382b0d0bd --local-dir models/gguf
hf download harness-hub/Qwen3.8-27B-pi-adapted-GGUF Qwen3.8-27B-pi-lora-F16.gguf \
  --revision 19980ce556b41c7b73818083c9adf4b3fa0c72e5 --local-dir models/gguf
```

对应 SHA-256：

```text
d15d4b6de55f662ac40e867702d31afe738d032fa06b829b2b1a21a49d4a48ee  Qwen3.8-27B-Q4_K_M.gguf
a64f91844f19e67da500d8628bdf9383aa334e61b7ab687805802e7d272d7b67  Qwen3.8-27B-pi-lora-F16.gguf
```

启动 Metal 推理服务：

```bash
HARNESS_BASE_MODEL="$PWD/models/gguf/Qwen3.8-27B-Q4_K_M.gguf" \
HARNESS_PI_ADAPTER="$PWD/models/gguf/Qwen3.8-27B-pi-lora-F16.gguf" \
  bash serve-llama.sh
```

脚本只加载一份基座及一个适配器，以 `qwen-base`、`qwen-pi` 为别名。默认 16384 上下文、单个槽位、thinking off，不启用上下文自动滑移。别名本身不会切换 LoRA；驱动器必须加 `-llama-lora`，才能在每次请求中发送 `lora: [{id: 0, scale: 0}]` 或 scale 1。这个功能依据[当前构建的服务接口](https://github.com/ggml-org/llama.cpp/blob/d81235049/tools/server/README.md)。

`/lora-adapters` 显示加载的适配器和全局默认 scale；请求里的 scale 会覆盖默认值，但不会把该全局列表改成上一次请求的配置。程序在 llama 模式下检查 ID 0 存在且只有一个适配器，并保存列表。两组仍需核对相同的模型文件、量化和模板。

可以在单独容器中运行 Pi 与 Go 判分器，避免把宿主机代码目录交给模型的 shell 工具。镜像包含 Go 1.27.2、Node.js 22.19.0、Pi 1.5.2，不包含模型权重：

```bash
docker build -t qwen38-harness-experiment:pi1.5.2 .

docker volume create qwen38-real-results
docker run --rm --user 0 --cap-drop ALL --cap-add CHOWN \
  --entrypoint /bin/chown \
  --mount type=volume,source=qwen38-real-results,target=/results \
  qwen38-harness-experiment:pi1.5.2 10001:10001 /results

docker run -d --name qwen38-real \
  --read-only --tmpfs /tmp:rw,exec,size=2147483648 \
  --mount type=volume,source=qwen38-real-results,target=/results \
  --cap-drop ALL --security-opt no-new-privileges \
  --pids-limit 256 --memory 2g --cpus 2 \
  qwen38-harness-experiment:pi1.5.2 run \
  -pi /opt/pi/node_modules/.bin/pi \
  -url http://host.docker.internal:8091/v1 \
  -base-model qwen-base -adapter-model qwen-pi \
  -llama-lora -context-window 16384 \
  -runs 1 -timeout 5m -out /results/real-gguf-01

docker logs -f qwen38-real
docker wait qwen38-real
mkdir -p results
docker run --rm --read-only --entrypoint tar \
  --mount type=volume,source=qwen38-real-results,target=/results,readonly \
  qwen38-harness-experiment:pi1.5.2 \
  -C /results -cf - real-gguf-01 | tar -xf - -C results
docker rm qwen38-real
```

`host.docker.internal` 是 Docker Desktop 访问 Mac 宿主机的地址。以上容器只挂载临时文件系统和专用结果卷，没有挂载博客、案例源码、个人目录或 Docker socket。结果不能只放在 tmpfs：容器退出后临时挂载不保留，`docker cp` 也不能可靠导出它；上面用独立持久卷保存，并由只读辅助容器导出。复制结果后才删除容器，保留结果卷；改变运行名和输出目录可以保留多轮结果。GGUF、Q4_K_M、Metal 和 16k 上下文的结果应单独报告，不能当成官方 BF16 数据。

需要补做中断的试次时，可以用 `-only-pairs csv-record:base,csv-record:adapter` 只选择未完成的组合，保留原来的题目次序、提示与参数。不要用这个开关重跑失败试次后挑选好结果。

如果第 1 轮已经完整计分，继续追加两轮时使用 `-runs 2 -run-offset 1`，并指定新的输出目录，例如 `/results/real-gguf-03`。这会运行第 2、3 轮的全部六个组合，沿用全局轮次的条件交替顺序。`-run-offset` 只控制编号，不会自动读取或跳过已有结果；先确认旧结果的最大轮次，不能用相同编号重复采样后选择好结果。追加批次应在开始前固定轮数，失败、超时和不可评分结果均保留。

汇总多个分段文件：

```bash
go run . summarize results/part-one/results.json results/part-two/results.json
```

合并命令会拒绝重复的题目／重复编号／条件，也会检查同一条件的模型名称、同一题的任务和提示哈希。推理后端、量化、采样、预算等环境一致性仍需对照各段 `metadata.json` 与服务端记录。中断和重启原因也应保留。

## 2026-11-22 首轮真实运行结果

M4 Pro、48 GB 统一内存，llama.cpp 0.6.0（build 11429，`d81235049`），Metal 推理，单槽位、16384 上下文。Pi 与外部 Go 判分器运行在 Linux arm64 容器中，Node.js 22.19.0、Pi 1.5.2、Go 1.27.2，限 2 CPU／2 GiB；没有挂载宿主机源码。两组读取同一份已验证 SHA-256 的 Q4_K_M 基座，只有请求中的 LoRA ID 0 scale 为 0 或 1。

每题每个条件只有一个计分样本，温度 0.8、top_p 1、thinking off、每次生成最多 4096 token，每次 Agent 壁钟上限 5 分钟。原生推理探针先分别生成 16 token，返回的 `generation_settings.lora` 确认 scale 0 和 1，token 概率输出也有变化。

| 题目 | 条件 | 验收 | Pi 状态 | 工具调用 | 生成 token | Agent 壁钟秒 |
| --- | --- | --- | --- | --- | --- | --- |
| bytesize | 基座 | 未通过 | 300 秒超时 | 17 | null | 300.038 |
| bytesize | Pi LoRA | 通过 | completed | 9 | 1247 | 168.857 |
| retry-delay | 基座 | 未通过 | completed | 7 | 987 | 113.171 |
| retry-delay | Pi LoRA | 通过 | completed | 6 | 707 | 83.361 |
| csv-record | 基座 | 通过 | completed | 7 | 778 | 81.267 |
| csv-record | Pi LoRA | 通过 | completed | 5 | 430 | 69.941 |

字节解析的基座答案留下 `declared and not used: sep`，外部编译失败。退避题的基座答案将 `Delay(2, time.Nanosecond, 10*time.Nanosecond)` 错算为 10ns，正确结果应是 2ns；它自己的可见测试通过了，外部验收仍拒绝。

只有 CSV 一对同时通过且正常结束，因此效率配对的样本数为 1：7／5 次工具调用、778／430 个生成 token、81.267／69.941 秒。失败题和超时题不能混入“同题同结果”的效率比较；以上不能推广成整体节省百分比或统计显著的能力提升。超时试次的 token 记为 null，没有用截至中断的部分计数冒充完整用量。

运行中发现最初使用 tmpfs 保存结果，退出后不能按预定方式导出。四个已完成试次通过运行中的 `docker exec tar` 备份，并核对答案哈希；一次尚未完成的 CSV 基座尝试主动取消，不计分。改用持久卷后，仅用 `-only-pairs` 补做 CSV 两个条件，四个既有结果未重跑。这个额外中止试次及存储修复在[实测记录](verification/real-gguf-2026-11-22.json)单列。

公开记录只保留环境、测量值和原始事件／答案／验收文件的哈希；完整轨迹保存在忽略的 `results/` 中。模型文件在忽略的 `models/` 中保留，推理进程与试验容器已停止／清理，持久结果卷保留供复查。

## 继续采样：追加第 2、3 轮（原验收 V1）

在首轮六个计分试次保留不变的基础上，预先固定追加两轮全部组合，共 12 次。使用 `-runs 2 -run-offset 1`，新目录为 `/results/real-gguf-03`，没有使用 `-only-pairs` 选择题目。两份权重重新计算完整 SHA-256 并通过核对；任务、提示、Pi models 配置、后端默认采样项与原批次一致。模型服务在追加前重启，缓存没有逐试次重置，随机种子仍未控制。

驱动器单元与判分测试、真实 Pi 对脚本端点的协议检查、`go vet ./...` 均通过。协议检查验证了第 2 轮编号与反转后的条件顺序；后面的 12 个试次使用真实 Qwen 权重，二者分别记账。容器镜像仅因续跑编号支持而重建，Pi/Go/Node 版本、工具、资源限制与旧批次一致。

追加批次的真实退出输出为：

```text
base: 3/6 scored attempts passed; 0 unscorable
adapter: 6/6 scored attempts passed; 0 unscorable
```

合并原六个结果后共 18 次，无重复编号、无不可评分结果。首轮事件、答案及验收文件的哈希均未变化。完整记录见 [real-gguf-2026-11-22-repeated.json](verification/real-gguf-2026-11-22-repeated.json)。

| 题目 | 基座通过 | LoRA 通过 |
| --- | --- | --- |
| bytesize | 1/3 | 3/3 |
| retry-delay | 0/3 | 3/3 |
| csv-record | 3/3 | 3/3 |
| 合计 | 4/9 | 9/9 |

字节解析的基座在第 2 轮通过，第 3 轮拒绝了合法输入 `12B`。退避题的基座后两轮都在 `attempt=3, base=2305843009213693952ns, limit=9223372036854775807ns` 时返回溢出的负时长，未通过验收。全部失败和首轮超时均计入累计结果，没有补跑后择优。

双方均通过且正常结束的同题同轮配对共 4 对，分别是三轮 CSV 与第 2 轮 bytesize，usage 均完整：

| 配对指标中位数 | 基座 | LoRA |
| --- | --- | --- |
| 工具调用 | 6.5 | 4.5 |
| 生成 token | 617.5 | 489.5 |
| Agent 壁钟毫秒 | 70125.5 | 66320.5 |

这些是同一配对集合内各组观测值的中位数，不是整体节省比例。LoRA 并非次次更省：第 2 轮 bytesize 的工具调用为 8／13（LoRA／基座），生成 token 却为 2486／2283，耗时 279.447／244.935 秒；第 2 轮 CSV 也出现 LoRA token 更多、耗时更长的情况。三轮仍只有三个公开教学任务，不能把九次尝试当成九道独立题，也不支持通用能力或显著性结论。

重新汇总同一批次：

```bash
go run . summarize \
  results/live-backup/real-gguf-01/results.json \
  results/real-gguf-02/results.json \
  results/real-gguf-03/results.json
```

追加结果从持久卷只读导出后，逐份核对 `result.json`、最终答案哈希以及 18 个预定组合；原始轨迹留在忽略的 `results/real-gguf-03/`，累计副本为 `results/real-repeated-results.json` 与 `results/real-repeated-summary.json`。推理服务已停止，追加容器已移除，模型文件与持久结果卷保留供复查。首轮那一次存储故障导致的主动取消仍单列，不计入上述 18 个计分试次。

## V2：对保存的答案重新验收

原验收存在漏测。例如首轮 LoRA 的退避答案对 `attempt=3, base=(1<<62)+1, limit=(1<<63)-1` 返回 4ns，实际应封顶；它通过了 V1。V2 是在阅读答案后补充的覆盖检查，明确标记 `post_hoc`，不是新的盲测成绩。

V1 测试文件与旧结果保持不变。V2 使用各题独立的 `acceptance_v2_test.go.txt`：

| 题目 | 每份答案的固定用例数 | 补充覆盖 |
| --- | --- | --- |
| bytesize | 58 | 非法数字前缀、单位及乘法溢出边界、内外空白、符号与非法数字格式 |
| retry-delay | 40 | 正数回绕、零回绕、符号位溢出、大 attempt、上限及非正参数 |
| csv-record | 26 | CR/LF、引号、逗号、空字段、前导空白、Unicode、长字段与多字段 |

V2 保留 V1 的已有输入。周围空白按原参考实现的 `strings.TrimSpace` 口径检查，包括纵向制表符、换页符、不换行空格和 em space；数字和单位之间仍只允许 ASCII 空格、tab。退避用受限的 `math/big.Int` 运算独立计算预期值，避免复制被测代码的溢出判断；CSV 按题目要求使用标准库 Writer 作为输出依据。

每个用例对应一个独立 `t.Run`，失败后继续执行其他用例。判分器从固定测试源码的字面量名称读取预定分母，再核对 `go test -json` 中的逐用例、父测试和包级结果。进程退出码为零而没有测试通过事件，不能通过。编译失败时用例记为 `not_run`，保留在预定分母中；运行后失败记为 `failed`，二者分开统计。

本地重判已有结果：

```bash
go run . regrade \
  -evidence verification/real-gguf-2026-11-22-repeated.json \
  -run-dir results/live-backup/real-gguf-01 \
  -run-dir results/real-gguf-02 \
  -run-dir results/real-gguf-03 \
  -out results/regrade-v2-local
```

结果目录必须不存在。程序先核对全部原始事件、验收、结果和答案文件的哈希，拒绝重复编号、缺失配对、多个目录中存在同一答案或内容变化，再用三题参考答案检查 V2。通过后才逐份复制保存的最终源码到新的判分目录。这里不启动 Pi，不连接模型端点，不修改任何原答案。

本次实际在 Linux arm64、Go 1.27.2 的专用容器中执行，限 2 CPU／2 GiB，非特权用户、只读根文件系统，`--network none`。18 份输入的校验副本通过专用只读卷传入，不挂载宿主机源码；V2 输出写入单独新目录。容器已移除，原始输入、输出结果卷和本地原始记录保留。

输出包括：

- `metadata.json`：V2 版本、固定用例名单和测试哈希、原证据哈希、运行环境。
- 每份答案的 `grade-v2.jsonl`、`result-v2.json`：原始验收输出与逐用例状态。
- `results-v2.json`、`summary-v2.json`：逐份结果、整题与用例统计、按 V2 成功配对重算的效率。

本次结果见 [V2 补测记录](verification/regrade-v2-2026-11-22.json)：

| 题目 | 基座整题 | LoRA 整题 | 基座用例 | LoRA 用例 |
| --- | --- | --- | --- | --- |
| bytesize | 0/3 | 1/3 | 94/174 | 166/174 |
| retry-delay | 0/3 | 2/3 | 94/120 | 115/120 |
| csv-record | 3/3 | 3/3 | 78/78 | 78/78 |
| 合计 | 3/9 | 6/9 | 266/372 | 359/372 |

基座用例分母中有 58 项因首轮编译失败未执行；另有 48 项执行后失败。LoRA 的 13 项失败包括两份字节答案各四个周围空白用例，以及首轮退避的五个正数回绕用例。第 2 轮基座字节答案接受 `abc12`、`!12B`、`B12`，三项失败、其余 55 项通过，因此整题未通过。用例分数补充说明失败范围，不能把它解释为生产正确率；372 项是 124 个固定检查对三份答案的评估，各题用例数不等，也不是独立任务样本。

V2 下双方通过且正常结束的配对只剩三轮 CSV。原 Agent 工具次数中位数为基座 6、LoRA 4，生成 token 为 457／430，壁钟为 58984／62700 毫秒。补测耗时不混入 Agent 时间。LoRA 壁钟中位数更高，不能沿用 V1 四配对统计去宣称提速。

`go test ./...`、`go vet ./...`、带真实 Pi 脚本端点集成的 `go test -race ./...` 均通过。测试覆盖参考与错误实现、V1 漏检的正数回绕、编译失败未执行计数、伪退出、事件格式异常、输入哈希变化和配对选择。固定测试仍是有限的事后覆盖检查，全部通过也不能证明答案完整正确。

## 增加 DeepSeek Harness（DSH）

`-harness deepseek-harness` 使用固定版本 **DSH 0.2.2-rc.1** 的真实 headless 运行入口。模型仍是 Qwen3.8-27B 的同一份 Q4_K_M 基座，`adapter` 仍指官方 **Pi 专用 LoRA**；这里检查它向 DSH 迁移后的行为，没有训练或声称存在 DSH 专用适配器。

DSH 负责自己的系统提示、工具定义、执行循环和会话，Go 只准备任务、调用 CLI、采集数据与外部判分。生成的 `dsh.cordis.patch.yml` 为新建的隔离 `DSH_HOME` 配置本地 OpenAI-compatible 路由，并保留原生 `read`、`write`、`edit`、`bash`。关闭 skills、项目指令发现、子 Agent、Web 工具、自动重试、自动压缩、后台命令及遥测。工具名相同不代表参数相同：DSH 文件工具使用 `file_path`，bash 需要 `description`，这些原生定义没有改成 Pi 的格式。

DSH 没有直接暴露本例所需的全部请求采样字段，因此每个试次启动一个仅监听容器回环地址的请求网关：保留 DSH 的提示、历史、原生工具和响应流，只固定 temperature 0.8、top_p 1、每次输出上限 4096、thinking off，以及该条件的 LoRA scale 0／1，并要求流式返回 usage。它不实现 Agent 循环，也不生成参考答案。发往上游的完整请求保存在每次尝试的 `outgoing-requests.jsonl`，可检查实际参数和工具目录；出现四个预定工具之外的目录会被拒绝。

DSH 要求 Node.js 24.9.0+；独立镜像使用 Node 24.9.0、Go 1.27.2，原 Pi 实验仍保留 Node 22.19.0 的记录。模型文件、服务参数、任务、上下文、预算和容器资源限制一致。跨宿主比较仍涉及原生提示、工具签名、Node 运行时及运行时段差异，不能把壁钟差异全部归因于某一个因素。

在案例目录构建专用镜像，再沿用前面的 Metal 服务：

```bash
docker build -f Dockerfile.dsh -t qwen38-harness-experiment:dsh0.2.2-rc.1 .

docker volume create qwen38-dsh-results
docker run --rm --user 0 --cap-drop ALL --cap-add CHOWN \
  --entrypoint /bin/chown \
  --mount type=volume,source=qwen38-dsh-results,target=/results \
  qwen38-harness-experiment:dsh0.2.2-rc.1 10001:10001 /results

docker run -d --name qwen38-dsh \
  --read-only --tmpfs /tmp:rw,exec,size=2147483648 \
  --mount type=volume,source=qwen38-dsh-results,target=/results \
  --cap-drop ALL --security-opt no-new-privileges \
  --pids-limit 256 --memory 2g --cpus 2 \
  qwen38-harness-experiment:dsh0.2.2-rc.1 run \
  -harness deepseek-harness -dsh /opt/dsh/node_modules/.bin/dsh \
  -url http://host.docker.internal:8091/v1 \
  -base-model qwen-base -adapter-model qwen-pi \
  -llama-lora -context-window 16384 \
  -runs 1 -timeout 5m -out /results/dsh-gguf-01
```

此命令预先固定三题、两组各一次，共六个计分试次，全部保留，再用相同的 V2 文件离线判分。Pi 已有每题每组三次，DSH 此批只有一次，样本量不同，分别报告接入结果。增加轮次时另建结果目录，并使用 `-run-offset` 延续编号；不能因结果不好而重新抽取后择优。

DSH 的 JSON 事件与 Pi 不同，`dsh.go` 按 `status/step_end` 汇总已提交的步骤用量，按 `tool_call.callId` 去重计数；`final`、已完成 `turn_end`、进程退出码共同判定正常结束，再检查外部验收。缺失 usage 和超时仍保留为未知，不把退出码 0 当成任务通过。`summarize` 会拒绝将 Pi 和 DSH 混成同一组统计。

协议自检可以在独立临时目录安装固定 CLI，再运行：

```bash
npm install --prefix /tmp/qwen38-dsh-runtime --ignore-scripts --no-audit --no-fund \
  @deepseek-ai/dsh@0.2.2-rc.1
HARNESS_DSH_BIN=/tmp/qwen38-dsh-runtime/node_modules/.bin/dsh \
  go test -run 'TestDSH|TestRealDSH|TestSummarizeDoesNotMixHarnesses' -v
```

这项检查使用脚本服务，给出参考答案，只验证真实 DSH 的读写、bash 执行、请求策略和事件解析；不算真实模型成绩。未设置 `HARNESS_DSH_BIN` 时，普通单元测试会跳过该集成检查。实际模型试次和后续 V2 重判另行保存。

### DSH 在 2026-11-22 的实际结果

六个预定试次全部保留，无不可评分的协议故障。权重完整 SHA-256、任务及用户提示哈希、请求中的四工具目录与采样字段均已核对。V2 测试文件哈希与 DSH 采样前的计划一致，没有根据这些答案增删用例。原始模型运行见 [dsh-gguf-2026-11-22.json](verification/dsh-gguf-2026-11-22.json)，统一 V2 判分见 [dsh-regrade-v2-2026-11-22.json](verification/dsh-regrade-v2-2026-11-22.json)。

| 题目 | 基座 V2 用例／状态 | Pi LoRA V2 用例／状态 |
| --- | --- | --- |
| bytesize | 58/58，通过；超时 | 56/58，未通过；超时 |
| retry-delay | 40/40，通过；超时 | 38/40，未通过；正常结束 |
| csv-record | 26/26，通过；正常结束 | 2/26，未通过；超时 |
| 合计 | 整题 3/3，用例 124/124 | 整题 0/3，用例 96/124 |

四次超时均在 300 秒上限保存原答案，token 总量保持 `null`。两组各只有一次运行正常结束，所以“基座整题 3/3”只表示截止时留存代码通过验收，并不表示三个 Agent 任务都正常完成。V1 为基座 3/3、LoRA 2/3；V2 检出了旧验收未覆盖的边界，旧分数独立保留。

LoRA 的失败对应到实际答案：

- bytesize 手写的空白处理漏掉不换行空格和 em space，共两项失败。
- retry-delay 在 `attempt=2, base=5ns, limit=11ns` 时错误返回 11ns，正确为 10ns；另一项是大数下未到上限却提前封顶。
- csv-record 对已有 LF 的标准库 Writer 输出执行 `TrimSuffix(..., "\r\n")`，再追加 LF，导致普通记录双换行，24/26 项失败。

V2 下没有双方都通过且正常结束的配对，工具、token 与耗时的效率中位数全部为 `null`；没有从单边通过或超时试次计算节省比例。本批只检查 Pi 专用 LoRA 在 DSH 上的接入表现，每题每组一次，不能与 Pi 每组三轮的数据直接排名。DSH 的原生系统提示含所选模型别名和临时工作目录，两组并非系统提示逐字相同的权重消融；完整请求与首个系统提示的哈希均保留供复核。

实际镜像使用 Node 24.9.0；本机脚本端点协议测试使用 Node 25.2.1，二者分开记录。NPM 顶层版本固定，实际依赖锁文件保留在忽略的 `results/dsh-npm-package-lock.json`，其 SHA-256 与镜像内文件一致，运行镜像 ID 也在实测记录中。未来重建仍应核对依赖和版本。

模型原始结果位于 `results/dsh-gguf-01/`，V2 原始输出位于 `results/dsh-regrade-v2-01/`。离线重判可复用前面的 `regrade` 命令，将 evidence 换成 DSH 记录、run-dir 换成 DSH 原始目录，另指定新 out 目录。推理服务、模型试次容器和重判容器均已停止或移除，原始结果卷保留。模型实际修复题目的过程与脚本端点检查分别保存。

`first_system_prompt_sha256` 对首个请求中 role 为 system 的消息数组计算：以 Python `json.dumps(..., ensure_ascii=False, sort_keys=True)` 序列化后取 UTF-8 的 SHA-256。完整请求文件的原始字节哈希另存于 `artifact_sha256`。
