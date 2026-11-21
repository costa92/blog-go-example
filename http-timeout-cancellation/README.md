# HTTP 超时与业务取消

配套文章：博客仓库的 [go-http-timeout-cancellation.md](https://github.com/costa92/hexo_blog/blob/master/source/_posts/go-http-timeout-cancellation.md)，题目为“Go 请求已经超时，为什么后台还在消耗 CPU”。

根目录 CPU 程序只依赖 Go 标准库，使用 loopback 上的真实 HTTP/1.1 连接。`getrusage` 进程 CPU 统计支持 Linux、macOS；没有 Kubernetes、代理、数据库或外部 API 依赖。

另提供 [HTTP/1.1、HTTP/2、gRPC 的完整取消案例](PROTOCOLS.md)：真实网络连接、33 组直接调用、6 组 A→B 转发、独立后台任务及其超时约束。新增命令固定依赖 grpc-go v1.76.0、protobuf v1.36.10，见本目录 go.mod/go.sum；不改动原来的 CPU 数值结果。

## 运行

```sh
cd http-timeout-cancellation
go test ./...
go test -race ./...
go run . -runs 3 -requests 8 -deadline 100ms -work 400ms -procs 2

# 协议行为对照（另一个程序，不输出 CPU 性能数据）
go run ./cmd/protocols
go run ./cmd/protocols -chain
python3 summarize_protocols.py protocol_results.json
```

独立 go.mod 声明 Go 1.25；随文数据实测工具链为 Go 1.27.2 darwin/arm64。程序只绑定 `httptest` 分配的本机随机端口，退出前等待本轮所有业务计算结束。输出首行为环境和校准参数，后续每行为一个场景的 JSON 结果。不要将编译、测试或校准阶段的 CPU 时间混入场景结果。

本机原先的 `GOROOT` 指向 Go 1.27.1，和 PATH 上的 1.27.2 不一致，直接运行会报编译器版本不匹配。本次实际命令在 `go` 前加了 `env -u GOROOT`，让当前命令使用工具链自己的标准库目录，没有修改全局 Go 配置。环境正常时不需要这个前缀。

## 三种场景

| mode | HTTP 超时 | 计算循环 |
|---|---|---|
| `client-timeout` | `Client.Timeout=100ms` | 忽略请求 context |
| `handler-timeout` | `TimeoutHandler(...,100ms,...)`，客户端兜底 20s | 忽略请求 context |
| `cooperative` | `Client.Timeout=100ms` | 每 1024 次 SHA-256 检查一次请求 context |

每轮启动 8 个请求，全部进入业务 handler 后才放开计算门闩。先用单 goroutine 的进程 CPU 时间校准约 400ms 的 SHA-256 次数，三种场景使用相同的次数；不是“循环跑到墙钟 400ms”。结果中记录真实哈希次数、完整工作数及因取消提前退出的工作数。

客户端与服务端在同一进程，进程 CPU 包含 HTTP 客户端、服务端及 Go 运行时，不能把它解释为线上 handler 的纯 CPU。两个 P 允许并行计算，CPU 时间相加可以大于墙钟时间；`GOMAXPROCS=2` 不等于容器的 2 核 CPU limit。

## 结果字段

- `client_done_ms`：放开计算门闩后，到所有客户端完成或收到错误的墙钟时间。
- `active_at_return`：客户端全部结束时，仍在业务 handler 内的请求数。
- `drain_ms`：客户端全部结束后，等所有业务 handler 发出完成信号的额外墙钟时间。
- `total_cpu_ms`：从请求发出前到所有业务结束的进程 user+system CPU 差值。
- `after_return_cpu_ms`：从客户端全部结束到业务全部结束的同一 CPU 差值。
- `full_work_completed` / `work_canceled`：完整算完与因取消提前退出的任务数。
- `late_write_errors`：业务结束时向超时包装器写响应，得到 `http.ErrHandlerTimeout` 的次数；不等同于所有网络写入失败。

`results.json` 保存 2026-11-21 运行的环境和 9 组数值结果，不包含访问日志、凭据或真实业务数据。`summarize.py` 校验结果关系并输出三轮中位数及范围：

```sh
python3 summarize.py results.json
```

## 查看截图中的输出字段

文章的终端输出截图来自另外一次重新运行，未覆盖 `results.json` 和 `protocol_results.json`。
`views/` 中的 jq 文件只筛选和排版原始 JSON Lines，不修改数值。安装 jq 后，例如：

```sh
go run ./cmd/protocols > /tmp/http-timeout-protocols.jsonl
jq -nr -f views/protocols.jq /tmp/http-timeout-protocols.jsonl | column -t
```

CPU、转发和独立任务分别使用 `views/cpu.jq`、`views/chain.jq`、`views/detached.jq`。
CPU、协议和转发表格使用 `jq -nr`，独立任务 JSON 使用 `jq -f`。本机 GOROOT 冲突时，
按前面的说明在 `go` 命令前加 `env -u GOROOT`。原始输出可保存在临时目录，不应提交运行日志。

## 验证范围

根目录四个测试分别验证计算响应预先取消、忽略取消仍算完、超时包装器返回 503 后原 handler 仍能继续、HTTP/1.1 客户端取消能传到服务端 context。数值实验进一步观察运行中的计算是否提前结束。

本机 3 轮 CPU 结果说明取消机制的区别，不是容量压测，不能据此推导生产 QPS、数据库驱动取消延迟、代理的 deadline 传递或 Kubernetes cgroup 性能。HTTP/2 与 gRPC 的行为另外由 internal/protocolcase 测试及协议命令验证。计时器、网络取消和调度都有延迟，配置 100ms 不是实际返回或停止工作的硬保证。
