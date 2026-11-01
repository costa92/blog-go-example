# 用 GoAgent 实现 Super-agent 的协调层

配套文章：[DeepSeek Super-agent：谁来管理多个 Agent 的任务](https://costalong.com/2026/11/01/deepseek-superagent-analysis/)。

这是一个可运行的教学案例，用 [kart-io/goagent v0.33.0](https://github.com/kart-io/goagent/tree/v0.33.0) 实现协调 Agent、独立 Worker、任务记录和通知恢复。该版本对应提交 `da848ae4f5e23460761c95d407483b9e9f2d7ec1`，依赖写入 `go.mod`、`go.sum`，没有本地 `replace`。

案例解释文章中的协调机制，不是 DeepSeek 官方原型的移植。默认 Worker 生成方案；新增的 [Harness 编码 Worker](codingworker/README.md) 可在独立 CSV 教学工作区真实读写代码、执行测试并交付 diff。它不接 GitHub 或飞书，不创建 PR。`ready` 表示方案或代码改动可评审，人工确认后才变为 `accepted`。

## 快速运行

需要 Go 1.25 或更新版本。默认模式不调用外部 API，不需要密钥。

在仓库根目录执行：

```bash
go test -race ./...
go vet ./...

demo_state="$(mktemp -d)"
go run ./superagent/cmd/superagent -mode demo -state-dir "$demo_state"
# 首次通知故意模拟：接收端已经保存，但发送端收到超时。
# 等待至少 1 秒，让首轮重试的退避时间到期，再启动一个新进程：
go run ./superagent/cmd/superagent -mode deliver -state-dir "$demo_state"
go run ./superagent/cmd/superagent -mode status -state-dir "$demo_state"
```

`demo` 要求空状态目录，防止覆盖已有演示。它创建两个独立任务，投递一条评审意见、一条机器人消息和一条范围外要求，再并行运行 Worker。输出包含路由结果、Ticket、Outbox 和模拟接收端回执。第二次进程只重试到期的待发通知；已发送项保持不变。接收端按稳定消息 ID 去重，所以模拟回执不会随重试增加。

`-mode work` 可以在独立进程处理尚未完成的 Worker；重新读取已保存的工作流结果不会重复调用模型。若运行期间有新的人工后续消息，旧版本结果不能覆盖新输入，下一次 `work` 处理新版本。

## 运行可修改代码的版本

参见 [CSV 编码 Worker](codingworker/README.md)：使用 `-mode coding-demo`，默认在断网 Docker 容器中执行固定测试。支持 `review` 查看证据、`accept -coding` 独立验证后验收；不要用旧 plan 状态目录直接切换执行模式。

## 对照代码理解职责

| 部分 | 实现 | 负责什么 |
| --- | --- | --- |
| 协调 Agent 与 Worker | `engine.go` 的 `agent` | `builder.NewSimpleBuilder`、`AsRunnable().Invoke`；每个角色、事件或任务版本有独立上下文 |
| 可恢复 Agent 调用 | `workflow.Graph`、`CompileDurable` | 任务版本的工作流检查点和 Agent 调用日志，完成后可以回放结果 |
| 任务管理 | `engine.go` 的 `Handle`、`RunPending` | 事件去重、订阅、范围、执行版本、并发上限、ready 与人工验收 |
| 应用状态 | `durable.FileStore` | 通过加锁与原子快照一起保存任务结果和待发通知，不在模型调用期间持应用状态锁 |
| 通知投递 | `outbox.go` | 稳定消息 ID、发送记录、指数退避与重试 |
| 模拟接收端 | `DemoReceiver` | 持久回执与幂等处理，制造“远端成功、本地超时”的不确定结果 |
| 无密钥模式 | `model.go` | 固定响应，但仍走真实 GoAgent Agent 循环与工作流；不测试模型能力 |

任务管理逻辑属于宿主程序，GoAgent 提供 Agent 执行、工作流与恢复机制。不要把框架提供的执行能力和案例自行实现的业务规则混为一谈。

## 路由与授权

- `observe` 下，明确且获授权的人工请求仍可接单；推断候选只记录观察结果。
- `auto` 只允许预配置的范围标签，本例只允许 `csv-export`。模型同意不等于有权限。
- 范围内的人工后续消息进入已有 Ticket 并触发新版本执行。
- 机器人消息进入已有 Ticket 的上下文，同时独立进入协调评估；本例不会因机器人消息自动开新任务或重新执行。
- 范围外消息保留在工单记录中并标记 `reroute`，不会扩大 Mandate，也不会交给当前 Worker 执行。需要操作人另行决定与发起新任务。

这里的 `authorized`、`actor` 和 `scope` 是可信宿主传入的教学字段。范围用确定性的业务标签比较，不做自然语言安全判定。事件文件和本地 `accept` 命令都不是可公开暴露的认证接口；接真实协作平台时须由适配器验证身份、签名与权限，不能相信外部 JSON 自报授权。

## 提交自己的事件

```json
{
  "id": "csv-issue-1",
  "thread": "issue/1",
  "text": "检查 CSV 空导出并给出回归测试方案",
  "scope": "csv-export",
  "actor": "human",
  "authorized": true,
  "explicit": true
}
```

将其保存为本地 `event.json`，然后运行：

```bash
go run ./superagent/cmd/superagent -mode event -event event.json -state-dir "$demo_state"
go run ./superagent/cmd/superagent -mode work -state-dir "$demo_state"
# status 输出中找到 Ticket ID，人工审阅方案后：
go run ./superagent/cmd/superagent -mode accept -ticket TICKET_ID -state-dir "$demo_state"
```

重复相同事件 ID 和相同内容会返回先前路由结果；相同 ID 改变内容会报错。先写入一个新线程才能创建另一项独立任务。

## 切换真实模型

已接入 GoAgent 的 OpenAI-compatible Provider。运行前在自己的环境中设置下列变量，密钥不写入仓库：

| 变量 | 内容 |
| --- | --- |
| `GOAGENT_API_KEY` | 模型服务密钥 |
| `GOAGENT_BASE_URL` | 完整兼容 API 基础地址，通常包含 `/v1` |
| `GOAGENT_MODEL` | 服务提供的模型名称 |

选择新的状态目录，避免离线检查点被直接回放：

```bash
live_state="$(mktemp -d)"
go run ./superagent/cmd/superagent -mode demo -live -state-dir "$live_state"
```

`event` 和 `work` 阶段均需带 `-live`；`deliver` 与 `status` 不调用模型。缺少配置直接报错，不自动降级成离线响应。协调器响应须为带布尔 `accept` 的 JSON，格式错误会停止接单。默认方案模式每次 Agent 调用限制 45 秒、命令限制 3 分钟，并发上限默认 2；编码模式的时限见对应说明。超时会消耗已发起的模型请求，不能据此保证固定金额预算。

默认真实模型模式仍只生成方案；编码模式按单独说明开启 Harness 工具。通知仍使用本地模拟接收端。本次验证覆盖离线执行和本地 HTTP 流式接口契约，没有实测外部模型服务，也没有验证真实模型的判断质量。

## 恢复与边界

同一 `state-dir` 保存工作流、应用状态和模拟接收端回执。默认目录 `.superagent/` 已加入忽略规则。使用本地可靠文件系统；文件锁与原子重命名不等于分布式存储。`MaxWorkers` 限制单个 Engine 的并发，演示中一个状态目录只运行一个 Worker 调度进程；不要把多进程数量相加后仍当成同一个全局上限。

本例用 FileStore 的一个应用快照保持任务结果和 Outbox 的共同提交，不使用文章中官方原型的 SQLite。应用保存失败、模型网络请求中断、或者发送后尚未记账等位置仍需区分处理。外部动作不会因为有检查点就自动变成 exactly-once；只有模拟接收端实现了本例的消息 ID 去重。接真实 API 时，需要核对远端状态或使用服务实际支持的幂等协议。

测试覆盖：观察与显式请求、授权拒绝、重复事件、订阅与机器人评估、范围外交回、并发限制与上下文分离、工作途中新输入、损坏状态拒绝覆盖、应用保存失败后的恢复、通知退避与接收端去重，以及本地 OpenAI-compatible SSE 契约。没有执行官方原型部署、真实远端故障演练或性能评测。

若本机存在旧 `GOROOT` 环境变量且出现“compile version does not match go tool version”，先检查工具链是否一致。本地可临时使用 `env -u GOROOT go test ./...` 验证，勿为案例擅自改全局 Go 配置。
