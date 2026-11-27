# MCP 2026-07-28 无状态重构实测

配套文章：[拆解 MCP 2026 架构重构：会话没了，状态搬去了哪里](https://costalong.com/2026/11/27/mcp-2026-stateless-architecture/)。

在本机起 3 个 MCP 副本，前面放一个反向代理（轮询，或按 `Mcp-Session-Id` 做会话保持），用官方 Go SDK 的客户端分别以 `2025-11-25` 和 `2026-07-28` 访问，记录代理看到的每个 HTTP 请求。另用同一个服务端接一次真实的 Claude Code，看它发出的请求。

这是教学用的演示代码，不是生产实现。副本在同一个进程里，「共享存储」是一个进程内的 map，用来代替 Redis 一类的外部存储。

## 文件

| 文件 | 作用 |
|---|---|
| `lab/main.go` | 场景表 `scenarios`、3 个工具（`whoami`、`cart_add`、`delete_branch`）、反向代理和请求记录 |
| `report.py` | 只读 `logs/`，打印文章里的全部数字；加 `--chart` 画 `chart.png`（需要 matplotlib 和 Noto Sans CJK） |
| `logs/scenarios.jsonl` | 每个场景、每类操作的成功数、失败数和第一个错误 |
| `logs/wire.jsonl` | 代理看到的每个请求：落到哪个副本、JSON-RPC 方法、`Mcp-Protocol-Version` / `Mcp-Session-Id` / `Mcp-Method` / `Mcp-Name` 头、`_meta` 里的键、请求体字节数、状态码 |
| `logs/claude-wire.jsonl` | Claude Code 2.1.332 连接 `-serve` 模式时发出的请求，两次运行（第二次起多记了声明的能力和 MRTR 的 `action`） |

三个工具：

- `whoami`：返回处理请求的副本编号，看请求怎么分布。
- `cart_add`：第一次调用时铸造一个购物车句柄，之后由调用方把句柄作为参数传回来，这是规范推荐的替代会话的写法。句柄背后的数据放副本内存（`local`）或共享存储（`shared`）。
- `delete_branch`：第一次调用返回 `input_required`，要求用户确认，客户端带着答复重发（MRTR，SEP-2322）。待确认状态放副本内存（`local`），或者用 HMAC 签进 `requestState`（`signed`），后者任何持有密钥的副本都能验证。

## 运行

依赖：Go 1.25+，`github.com/modelcontextprotocol/go-sdk` v1.8.0（见仓库根目录 `go.mod`）。

```bash
cd mcp-2026-stateless
go run ./lab               # 约 2 秒，重写 logs/scenarios.jsonl 和 logs/wire.jsonl
python3 report.py --chart
```

接 Claude Code（会产生一次模型调用的费用）：

```bash
go run ./lab -serve 127.0.0.1:8931 -log logs/claude-wire.jsonl &
echo '{"mcpServers":{"lab":{"type":"http","url":"http://127.0.0.1:8931/"}}}' > /tmp/mcp.json
claude -p --mcp-config /tmp/mcp.json --strict-mcp-config \
  --allowedTools "mcp__lab__delete_branch" \
  "调用 lab 的 delete_branch 删除分支 feat-y，把工具的原始返回逐字贴出来" < /dev/null
```

## 结果（2026-11-27，Go 1.27.4，go-sdk v1.8.0，Claude Code 2.1.332）

| 场景 | 建连 | 普通调用 | 句柄串状态 | MRTR 确认 |
|---|---|---|---|---|
| 2025-11-25 有会话，轮询 | 0/1 | 未执行 | 未执行 | 未执行 |
| 2025-11-25 有会话，会话保持 | 1/1 | 30/30 | 10/10 | 30/30 |
| 2026-07-28 无状态，轮询 | 1/1 | 30/30 | 10/10 | 30/30 |
| 同上，待确认状态存副本内存 | 1/1 | 30/30 | 10/10 | 0/30 |
| 同上，句柄背后是副本内存 | 1/1 | 30/30 | 0/10 | 30/30 |
| 同上，`tools/list` 带 `ttlMs` | 1/1 | 30/30 | 10/10 | 30/30 |
| 旧客户端 → 无状态服务端 | 1/1 | 30/30 | 10/10 | 0/30 |

## 边界

- 代理是严格轮询，3 个副本、请求串行，所以 MRTR 的重试和句柄的下一次调用必然落到另一台副本，失败率是 100%。随机分发或请求并发时失败率会低一些，但不会是 0。
- 「旧客户端 → 无状态服务端」里需要确认的工具失败，是因为无状态模式没有通道把服务端发起的 `elicitation/create` 送回旧客户端，SDK 报 `client does not support elicitation`。这是 go-sdk v1.8.0 的行为，其他 SDK 的处理方式本仓库没有测过。
- Claude Code 用 `-p` 非交互模式运行，没有人可以点确认，MRTR 的答复是 `cancel`。交互模式下的表现没有测。
- 延迟没有测，本机回环上的毫秒数对生产部署没有参考价值。
