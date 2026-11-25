# execution-line-control-plane

配套文章：[跨过执行线：从 Poppy 协议到 Claude Ship，AI Agent 如何接管真实工作流？](https://costalong.com/2026/11/25/cross-execution-line-poppy-to-claude-ship/)

本目录用单进程、无外部网络依赖的 Go 代码，最小化还原文章拆解的两套“执行线控制面”核心机制：

1. **`poppy/`（Poppy 1.0 协议控制面模型）**
   - 托管 `/.well-known/poppy.json` 服务发现文档。
   - 用标准库 `crypto/ecdsa`（P-256 / `ES256`）签发并校验 `typ: "poppy-session+jwt"` 的 `Poppy-Session` 请求头，包含成对用户标识（`sub`）与目标域名（`aud`）。
   - 演示默认未登录态（Guest）只读查询，以及跨过执行线（`POST /v1/orders/{id}/cancel`）时的双层鉴权：同时校验 `Poppy-Session` JWT 与绑定目标资源 URL 的 OAuth `orders:write` Bearer Token，拦住缺少 Scope 或资源不匹配的混淆代理人请求。
2. **`approvals/`（Claude Ship 审批策略与 PR Steward 护栏模型）**
   - 解析 `.claude/approvals.yml` 风格的 YAML 策略，区分 `observe` 与 `enforce` 模式。
   - 对敏感路径（如 `billing/**`）强制要求非作者本人的人类审批席位（`!pr/author`），对常规路径（如 `src/**`、`docs/**`）在 `claude/code_review` 通过后允许自动批准，同时显式保留 GitHub 分支保护的 CI 独立门禁。
   - 用 `ValidateStewardAction` 演示 PR Steward 禁止执行 `approve_pr` / `merge_pr`，以及收到 `@claude stop` 后立即停机。

## 运行方法

在仓库根目录执行：

```bash
go test -v ./execution-line-control-plane/...
go run ./execution-line-control-plane/cmd/demo
```

## 演示边界

- 本示例是离线单进程 Go 模型，仅用于验证协议字段、签名校验、最小权限拦截和策略求值逻辑。
- 不调用 Meta Muse、Shopify、GitHub API 或 Anthropic Claude Ship 云端服务，也不代表官方完整 SDK 实现。
