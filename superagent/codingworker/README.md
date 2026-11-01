# CSV 编码 Worker：GoAgent Harness 执行案例

这是 [Super-agent 协调层案例](../README.md)的可选执行适配器。原有默认模式只生成方案；开启 `-coding` 后，Worker 在独立的教学工作区真实读取和编辑文件、运行回归测试，再把证据交回 Ticket 等待人工评审。

依赖固定为 GoAgent `v0.33.0` 与 GoAgent Harness `v0.0.0-20261030153904-11520f497ae3`（提交 `11520f4`）。Harness 尚无版本标签，本项目没有使用浮动分支或本地 replace。

## 运行一次完整案例

需要 Go 1.25+、Git 和 Docker。默认镜像是 `golang:1.26.6-alpine`，可先用 `docker pull golang:1.26.6-alpine` 准备；也可用 `-coding-image` 选择已安装且包含 Go 1.25+ 的镜像。

在案例仓库根目录运行：

```bash
mkdir -p .superagent
coding_state="$(mktemp -d "$PWD/.superagent/csv.XXXXXX")"
go run ./superagent/cmd/superagent -mode coding-demo -state-dir "$coding_state"
```

默认不需要 API Key。固定脚本模型通过 GoAgent 原生工具流依次发出测试、读取、编辑、重测请求，实际工具来自 Harness。文件确实被改写，测试确实执行；修复策略是预先写好的，不代表真实模型已经学会定位故障。

输出中的 `state.tickets` 包含 Ticket ID 与 `evidence`：

- `before_tests`：宿主独立复现的原始失败，包含 `TestExportRows`。
- `test_output`：模型结束后，宿主独立执行的测试结果。
- `diff`、`source_sha256`：待评审改动与对应源码指纹。
- `workspace`、`executor`、`image`：实际工作目录和执行环境。
- `tools`：持久化工作流保存的工具调用名称。

复制 Ticket ID 后查看可读的评审内容，再决定是否验收：

```bash
go run ./superagent/cmd/superagent -mode review -ticket TICKET_ID -state-dir "$coding_state"
# 人工阅读 diff 与测试结果，确认后执行；此命令再次验证源码、固定测试与执行环境：
go run ./superagent/cmd/superagent -mode accept -coding -ticket TICKET_ID -state-dir "$coding_state"
# 等待至少 1 秒后，可在独立进程重试演示中故意超时的结果通知：
go run ./superagent/cmd/superagent -mode deliver -state-dir "$coding_state"
```

`ready` 表示可评审；`accept` 成功后才是 `accepted`。没有创建 PR，没有提交或推送工作区代码。人工验收不会隐式执行 Git 发布。

Docker 必须能够访问宿主的工作区目录。Docker Desktop／Colima 通常共享用户目录，但未必共享 `/var/folders` 或 `/tmp`；因此命令把状态放在项目内已忽略的 `.superagent/`。若项目本身不在共享路径，请先配置共享或把状态放到已共享的用户目录。读不到文件、Docker 不可用、镜像缺失或测试失败都会报错，不降级为宿主执行。

## 缺陷是什么

`testdata/csvbug/export.go` 故意遗漏 `csv.Writer.Flush()`：`Write` 将行留在缓冲中，函数却立即返回底层 Buffer，因此小数据导出为空。

固定测试检查普通多行、空输入与带引号／逗号／换行的 Unicode 内容。模板中的 `go.mod.txt` 在创建工作区时写成 `go.mod`；它是教学输入，不作为案例仓库自身的 Go 包运行。

每个任务版本都有独立工作区。新的版本从同一教学基线建立修复提案；这是固定 CSV 练习，不是通用 Git worktree 管理器，也不承诺把上一版本的任意仓库改动自动合并进来。

## 接入流程

1. Engine 将任务版本交给 `CodeWorker`；只有 `csv-export` Mandate 可以进入本适配器。
2. 宿主复制嵌入的已知故障模板，确认原始回归确实失败，并保存基线结果。
3. `preset.Build` 装配 Harness 的 workspace、coding-tools 和 permissions。
4. `preset.Configure` 将装配结果接入 GoAgent Builder；`Assembly.PinManifest` 固定装配清单，外层持久图记录模型与工具执行。
5. 模型结束后，宿主检查受保护文件、独立运行测试、生成 diff 与源码哈希。验证失败不进入 ready。
6. 人工评审后，`accept` 再核对证据并执行测试；状态或源码变化会拒绝旧结果。

工具只开放 `read_file`、`edit_file`、只读 `glob` 和 `run_command`。可信宿主的 Authorize 钩子限制文件与目录范围：只读三个模板文件、在根目录内查找文件、只编辑 `export.go`。命令进入 Harness 审批管线后，只有完整等于 `go test -count=1 ./...` 且在根目录执行时才获准。测试文件和 go.mod 必须与嵌入模板一致；增加、删除或替换文件也会被验证拒绝。

固定测试命令由任务宿主预先授权，Harness Approver 每次只允许该命令，不是交互式人工命令审批。`ls/find` 等命令不会执行，其拒绝原因作为工具反馈交回模型，使其可以改用 `glob/read_file`；越界文件操作仍会终止运行。最终代码验收始终由独立的 `accept` 操作完成。运行真实模型时，CLI 仅允许 Docker 执行器；默认容器断网，不注入模型 API Key。`-coding-executor local` 仅供离线固定脚本练习，不提供命令隔离。

编码 Worker 最多 12 次模型请求、10 轮执行，每次测试最多 90 秒，Agent 最多 3 分钟，整个编码命令最多 10 分钟。请求次数是执行预算，不是固定金额保证。

## 真实模型

沿用主案例的 `GOAGENT_API_KEY`、`GOAGENT_BASE_URL` 和 `GOAGENT_MODEL`，配置支持原生工具调用的 OpenAI-compatible 模型，然后选择新的共享状态目录：

如果已有 `DEEPSEEK_API_KEY`（例如配置在 `~/.zshrc`），可只在当前终端映射，不改配置文件：

```bash
source ~/.zshrc
export GOAGENT_API_KEY="$DEEPSEEK_API_KEY"
export GOAGENT_BASE_URL="https://api.deepseek.com"
export GOAGENT_MODEL="deepseek-flash"
```

```bash
live_state="$(mktemp -d "$PWD/.superagent/csv-live.XXXXXX")"
go run ./superagent/cmd/superagent -mode coding-demo -live -state-dir "$live_state"
```

后续 `event`／`work` 需同时使用 `-coding -live`；`review`、`status` 和通知投递不调用模型。`accept` 使用 `-coding` 进行宿主验证，不需要模型密钥。若使用非默认 Docker 镜像，验收也要传入相同的 `-coding-image`。

图版本绑定模型配置标识、装配摘要和适配器版本，恢复时不应改变模型或工具配置。加入只读文件发现与可纠正的命令拒绝反馈后，适配器版本为 v2，先前 v1 检查点不能直接用于新版本运行。模型密钥不进入该标识。现有 coding Ticket 不能不带 `-coding` 就退回只生成方案；已有 plan Ticket 也不会悄悄升级为可修改代码的任务。

## 验证与恢复边界

```bash
go test -race ./...
go vet ./...
# 默认测试不要求 Docker；显式运行真实容器工具链：
SUPERAGENT_TEST_DOCKER_IMAGE=golang:1.26.6-alpine go test -run '^TestDockerCodingLoop$' -v ./superagent/codingworker
```

Docker 测试使用用户目录下独立临时目录，结束后清理，避免 Colima 未共享系统临时目录的问题。普通单元测试使用明确的本地执行器和已知脚本，不接外部模型。

已验证：真实模板编辑与测试、完成图重放不重复请求模型、模型虚报成功被宿主拒绝、测试文件与命令限制、被拒绝命令不执行且可由模型纠正、过期证据拒绝、coding 任务不得降级为计划，以及断网容器内的修复流程。

这里只验证完成图的恢复，不承诺任意工具执行中断后都能自动接续。外部副作用仍受 GoAgent 的持久调用与不确定结果契约约束。测试通过也不是任意代码安全或语义正确的证明，仍需人工检查 diff。2026-11-01 使用真实 DeepSeek `deepseek-flash` 调用通过一次 CSV 修复：模型读取代码与测试、补上 `Flush()` 并检查刷新错误，原有三项测试及宿主独立容器验证通过，Ticket 保持 ready 待人工评审。模型带 `2>&1` 的非白名单命令被拒绝后，改用允许的精确命令，未执行被拒绝的命令。该结果仅覆盖固定教学模板，不代表任意仓库修复能力或生产可靠性；未接入 GitHub、PR 或真实通知平台。
