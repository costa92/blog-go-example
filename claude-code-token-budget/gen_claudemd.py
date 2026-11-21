#!/usr/bin/env python3
"""Generate a realistic project CLAUDE.md for a fictional Go service. usage: gen_claudemd.py LINES [zh|en]"""
import sys
n, lang = int(sys.argv[1]), (sys.argv[2] if len(sys.argv) > 2 else "zh")
mods = ["order", "payment", "inventory", "shipping", "coupon", "user", "notify", "report", "search", "audit",
        "refund", "invoice", "cart", "review", "risk", "pricing", "warehouse", "settlement", "promotion", "gateway"]
L = []
if lang == "zh":
    L += ["# CLAUDE.md", "", "orderhub 是一个 Go 1.23 写的订单中台，对外提供 HTTP + gRPC 接口，内部按领域拆成多个模块。", "",
          "## 常用命令", "", "```sh", "make build        # 编译到 bin/orderhub", "make test         # 单元测试，带 -race",
          "make lint         # golangci-lint，配置在 .golangci.yml", "make gen          # 重新生成 protobuf 和 mock",
          "make migrate-up   # 执行 db/migrations 下的迁移", "docker compose up -d mysql redis  # 本地依赖", "```", "",
          "## 代码约定", "",
          "- 错误统一用 internal/errs 包装，带错误码，不直接返回 fmt.Errorf。",
          "- handler 只做参数校验和转换，业务逻辑放在 service 层，service 不感知 HTTP。",
          "- 数据库访问只在 repo 层，禁止在 service 里拼 SQL。",
          "- 所有对外接口必须有 context 超时，默认 3 秒，从配置读取。",
          "- 金额一律用 int64 分，不用 float。", "- 时间统一 UTC 存储，展示层再转时区。",
          "- 新增配置项要同时改 config/example.yaml 和 docs/config.md。",
          "- 日志用 slog，字段名小写下划线，禁止打印手机号、地址等个人信息。",
          "- 写操作接口必须幂等，用 request_id 唯一索引判重。",
          "- 单测表驱动，文件名 *_test.go，和被测代码同目录。", "",
          "## 目录结构", ""]
    for m in mods:
        L += [f"- internal/{m}/：{m} 领域，含 handler、service、repo 三层，入口在 internal/{m}/module.go。"]
    L += ["", "## 错误码", "", "| 码 | 含义 | HTTP 状态 |", "| --- | --- | --- |"]
    for i, m in enumerate(mods):
        for j, (k, h) in enumerate([("参数非法", 400), ("资源不存在", 404), ("状态冲突", 409), ("下游超时", 504)]):
            L += [f"| {10000 + i * 100 + j} | {m} {k} | {h} |"]
    L += ["", "## 模块说明", ""]
    k = 0
    while len(L) < n + 10:
        m = mods[k % len(mods)]; k += 1
        L += [f"### {m}（第 {k} 节）", "",
              f"{m} 模块负责对应领域的读写。对外接口定义在 api/proto/{m}.proto，改动后执行 make gen。",
              f"- 主表 {m}s，按 tenant_id + id 联合主键；历史数据在 {m}s_archive，每月 1 号归档。",
              f"- 缓存 key 前缀 {m}:v2:，TTL 10 分钟，写操作后主动删除而不是更新。",
              f"- 依赖：{mods[(k + 3) % len(mods)]}、{mods[(k + 7) % len(mods)]}，调用走 internal/clients，带重试和熔断。",
              f"- 消息：变更后发 {m}.changed 事件到 Kafka，消费方自己保证幂等。",
              f"- 已知坑：批量接口一次最多 200 条，超过要分页；老版本客户端还在调 /v1/{m}，不要删。",
              f"- 测试数据在 testdata/{m}/，集成测试需要 docker compose 起依赖，标记 //go:build integration。", ""]
else:
    L += ["# CLAUDE.md", "", "orderhub is an order platform written in Go 1.23. It exposes HTTP and gRPC APIs and is split into domain modules.", ""]
    k = 0
    while len(L) < n + 10:
        m = mods[k % len(mods)]; k += 1
        L += [f"### {m} (section {k})", "",
              f"The {m} module owns reads and writes for its domain. Its API is defined in api/proto/{m}.proto; run make gen after editing it.",
              f"- Main table {m}s, composite primary key tenant_id + id; history lives in {m}s_archive, archived on the 1st of each month.",
              f"- Cache key prefix {m}:v2:, TTL 10 minutes; delete the key after writes instead of updating it.",
              f"- Depends on {mods[(k + 3) % len(mods)]} and {mods[(k + 7) % len(mods)]} through internal/clients, with retries and a circuit breaker.",
              f"- Emits a {m}.changed event to Kafka after changes; consumers must be idempotent.",
              f"- Gotcha: batch endpoints accept at most 200 items; old clients still call /v1/{m}, do not remove it.",
              f"- Test data lives in testdata/{m}/; integration tests need docker compose and the //go:build integration tag.", ""]
print("\n".join(L[:n]))
