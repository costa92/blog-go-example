# HTTP / gRPC 客户端停止等待后，服务端还会执行吗

本文是 [配套文章](https://github.com/costa92/hexo_blog/blob/master/source/_posts/go-http-timeout-cancellation.md)的协议补充。代码使用真实 loopback TCP；HTTP/2 通过 httptest TLS 服务器协商并记录 `r.Proto`，gRPC 使用固定版本 grpc-go 和 protobuf 的 unary RPC。不是 mock，不需部署外部服务；测试服务器和客户端由命令自动启动、清理。

这个程序用 20 个、每个名义 10ms 的等待步骤模拟慢操作，记录任务是否退出，不测 CPU 性能。原来的 SHA-256 CPU 程序仍由 `go run .` 运行，数据不互换。

## 直接运行

```sh
cd http-timeout-cancellation
go test ./...
go test -race ./...

# 33 组：HTTP/1.1、HTTP/2 各 12 组，gRPC 9 组
go run ./cmd/protocols

# 客户端 gRPC deadline 到期，业务忽略 context，最后仍完成 20 步
go run ./cmd/protocols -protocol grpc -trigger deadline -mode ignore

# 相同调用，业务 select ctx.Done()，提前退出
go run ./cmd/protocols -protocol grpc -trigger deadline -mode cooperate

# 原生 HTTP Client.Timeout：服务端没有收到数值 deadline，但会收到取消
go run ./cmd/protocols -protocol http2 -trigger client-timeout -mode cooperate

# 只让本地等待超时，不取消底层 RPC：后者最后仍正常返回
go run ./cmd/protocols -protocol grpc -trigger wait-only -mode cooperate

# 从请求 context 脱离，但给任务设置独立 80ms 上限
go run ./cmd/protocols -protocol grpc -trigger cancel -mode detached -background-limit 80ms

# A 花 20ms，再调用 gRPC B；对比传入请求 context 与 Background
go run ./cmd/protocols -chain

# 读取并校验随文保存的真实结果
python3 summarize_protocols.py protocol_results.json
```

Go 环境的 `GOROOT` 与编译器不匹配时，参照 [README](README.md) 中的本机说明，用 `env -u GOROOT go ...` 运行；没有修改全局 Go 配置。

`-timeout` 默认 50ms，`-steps` 默认 20，`-step` 默认 10ms，`-background-limit` 默认 1s。连接先预热，并确认每个正式请求确实进入业务；排除尚未到服务端就超时的情况。主动 `cancel` 在业务进入后等待 `-timeout` 再触发。链路命令中 A 的 `-forward-delay` 默认 20ms，须短于客户端 timeout。

## 对照的是什么

| trigger | 客户端行为 |
|---|---|
| `deadline` | 创建 `context.WithTimeout`，传给 HTTP 请求或 gRPC 方法 |
| `client-timeout` | 原生 `http.Client.Timeout`，只适用于 HTTP/1.1、HTTP/2 |
| `cancel` | 调用已传入底层请求的 context 的 `cancel()` |
| `wait-only` | 底层请求没有 deadline，外层计时器到点后停止接收结果；故意不取消底层调用 |

| mode | 服务端工作方式 |
|---|---|
| `ignore` | `time.Sleep` 逐步执行，不检查工作 context，任务完成时才观察 context 的状态 |
| `cooperate` | 每一步通过 `select` 同时等待计时器和 `ctx.Done()` |
| `detached` | 先用 `context.WithoutCancel`，再 `WithTimeout` 设置任务自己的上限；handler 可先返回，任务独立运行 |

默认 33 组观察中，正常取消的 `ignore` 全部完成，`cooperate` 提前退出；`wait-only` 下三种协议的 `cooperate` 全部完成且底层调用成功。`detached` 的独立 1s 上限足够做完任务；另存的独立 80ms 上限示例在工作未完成时退出。

所有独立任务在驱动退出前也会被等待。这里不提供持久化、崩溃恢复、生产队列或真实数据库写入；解除取消不能保证任务最终可靠交付，也不撤销已经发生的副作用。

## Deadline 和取消信号分开看

原生 HTTP 客户端的 context deadline 或 Client.Timeout 不会自动序列化成服务端的 Go deadline。实际请求取消可让服务端 `ctx.Done()` 关闭；在测试的直接连接里，HTTP/1.1、HTTP/2 均观察到此行为。HTTP/2 不是简单地“一条请求等于一条 TCP 连接”。

gRPC 将 deadline 编码进协议元数据，服务端因此可以看到 deadline。但应用仍需要响应 context；Go 不会因为一个 RPC 到期就强杀任意 goroutine。本次客户端得到 `DeadlineExceeded` 的同时，服务端可能因取消帧先到而看到 `context.Canceled`，不能要求两端错误名相同。

有 HTTP 框架主动设置服务端 deadline 时，观察可能与原生 HTTP 不同；有代理、网关、网络分区时，传播路径与延迟也需另测。普通断网不是一个有可靠送达确认的 `cancel()`。本案例不声称这些场景已经验证。

## A → gRPC B

`-chain` 时 A 的入站可以是 HTTP/1.1、HTTP/2 或 gRPC，B 固定为 gRPC，始终合作取消。A 先处理 20ms，再分别执行：

```go
backend.Run(parent, req)                // 沿用父请求
backend.Run(context.Background(), req)  // 故意切断父请求关系
```

六组实测中，沿用父请求的 B 都提前退出；使用 Background 的 B 都做完 20 步。gRPC 入站的剩余约 30ms 会继续传播，HTTP 入站没有数值 deadline，但取消信号仍能沿传入的 context 继续传播。

需要子调用自己的上限时，应从父请求派生 `context.WithTimeout(parent, limit)`；不能每一跳都从 Background 重新计时。`-chain` 没有新增一层业务 deadline，只验证父请求的传播与断开。

## 输出字段

`protocol_results.json` 保存 33 组直接调用、6 组转发和 1 组独立时限观察。环境字段中记录 Go 1.27.2 darwin/arm64、grpc-go v1.76.0 以及任务设置，不包含主机地址、访问日志或凭据。每次运行得到的毫秒数和步数可因调度变化。

- `client_wait_result`：调用方最先看到的结果，含 `DeadlineExceeded`、`Canceled`、`LocalWaitTimeout`。
- `actual_call_result`：底层 HTTP/RPC 最后的结果；`wait-only` 最先退出后，它仍可能是 `OK`。
- `has_request_deadline`：服务端业务入口是否观察到请求 deadline。
- `request_budget_ms`：服务端入口的剩余预算，存在 deadline 时才记录。
- `parent_error_at_task_end`：任务结束时请求 context 的状态。
- `work_context_error_at_task_end`：任务结束时工作 context 的状态；独立任务可与请求不同。
- `work_error`：工作函数实际返回的错误。`ignore` 可以在工作 context 已取消时仍返回成功，因此不能把它和上一个字段合并。
- `completed`、`steps_completed`：工作是否全部执行、完成多少步。
- `task_done_at_client_return`：客户端最先结束等待时工作是否已结束；不把网络与调度延迟当作零。

保存新输出可用：

```sh
go run ./cmd/protocols > /tmp/protocols.jsonl
go run ./cmd/protocols -chain > /tmp/chains.jsonl
```

每条命令输出一行环境和后续观测行。随文 JSON 将环境、直接调用、转发及独立时限的不同参数分别保存在对象中，避免丢失上下文。`summarize_protocols.py` 用于校验随文默认参数那组数据，没有假定精确耗时。

## 代码位置和 protobuf

| 文件 | 职责 |
|---|---|
| `api/worker.proto` | `Worker.Run(WorkRequest) -> WorkReply` 接口 |
| `api/worker.pb.go`、`api/worker_grpc.pb.go` | 已包含的标准生成文件，运行案例无需安装 protoc |
| `internal/protocolcase/transport.go` | HTTP 与 gRPC 的真实客户端、服务端和连接预热 |
| `internal/protocolcase/case.go` | 任务生命周期、取消、独立时限及观测 |
| `internal/protocolcase/chain.go` | A→B 的 context 传播对照 |
| `cmd/protocols/main.go` | 可筛选协议、触发方式和任务模式的运行入口 |

运行时依赖固定在 go.mod/go.sum。如需改接口后重新生成，准备 protoc，并固定安装两个插件：

```sh
GOBIN=/tmp/http-timeout-protoc-tools go install google.golang.org/protobuf/cmd/protoc-gen-go@v1.36.10
GOBIN=/tmp/http-timeout-protoc-tools go install google.golang.org/grpc/cmd/protoc-gen-go-grpc@v1.5.1
protoc --plugin=protoc-gen-go=/tmp/http-timeout-protoc-tools/protoc-gen-go \
  --plugin=protoc-gen-go-grpc=/tmp/http-timeout-protoc-tools/protoc-gen-go-grpc \
  --go_out=. --go_opt=paths=source_relative \
  --go-grpc_out=. --go-grpc_opt=paths=source_relative api/worker.proto
```

四个原 CPU 行为测试仍保留，新增协议与转发测试验证“收到取消”和“停止工作”是不同条件、HTTP/2 确已协商、纯等待超时不会取消请求、独立任务有自己的上限。`go test -race ./...` 同时覆盖观测数据和任务协作的竞态检查。
