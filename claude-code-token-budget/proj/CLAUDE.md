# CLAUDE.md

orderhub 是一个 Go 1.23 写的订单中台，对外提供 HTTP + gRPC 接口，内部按领域拆成多个模块。

## 常用命令

```sh
make build        # 编译到 bin/orderhub
make test         # 单元测试，带 -race
make lint         # golangci-lint，配置在 .golangci.yml
make gen          # 重新生成 protobuf 和 mock
make migrate-up   # 执行 db/migrations 下的迁移
docker compose up -d mysql redis  # 本地依赖
```

## 代码约定

- 错误统一用 internal/errs 包装，带错误码，不直接返回 fmt.Errorf。
- handler 只做参数校验和转换，业务逻辑放在 service 层，service 不感知 HTTP。
- 数据库访问只在 repo 层，禁止在 service 里拼 SQL。
- 所有对外接口必须有 context 超时，默认 3 秒，从配置读取。
- 金额一律用 int64 分，不用 float。
- 时间统一 UTC 存储，展示层再转时区。
- 新增配置项要同时改 config/example.yaml 和 docs/config.md。
- 日志用 slog，字段名小写下划线，禁止打印手机号、地址等个人信息。
- 写操作接口必须幂等，用 request_id 唯一索引判重。
- 单测表驱动，文件名 *_test.go，和被测代码同目录。

## 目录结构

- internal/order/：order 领域，含 handler、service、repo 三层，入口在 internal/order/module.go。
- internal/payment/：payment 领域，含 handler、service、repo 三层，入口在 internal/payment/module.go。
- internal/inventory/：inventory 领域，含 handler、service、repo 三层，入口在 internal/inventory/module.go。
- internal/shipping/：shipping 领域，含 handler、service、repo 三层，入口在 internal/shipping/module.go。
- internal/coupon/：coupon 领域，含 handler、service、repo 三层，入口在 internal/coupon/module.go。
- internal/user/：user 领域，含 handler、service、repo 三层，入口在 internal/user/module.go。
- internal/notify/：notify 领域，含 handler、service、repo 三层，入口在 internal/notify/module.go。
- internal/report/：report 领域，含 handler、service、repo 三层，入口在 internal/report/module.go。
- internal/search/：search 领域，含 handler、service、repo 三层，入口在 internal/search/module.go。
- internal/audit/：audit 领域，含 handler、service、repo 三层，入口在 internal/audit/module.go。
- internal/refund/：refund 领域，含 handler、service、repo 三层，入口在 internal/refund/module.go。
- internal/invoice/：invoice 领域，含 handler、service、repo 三层，入口在 internal/invoice/module.go。
- internal/cart/：cart 领域，含 handler、service、repo 三层，入口在 internal/cart/module.go。
- internal/review/：review 领域，含 handler、service、repo 三层，入口在 internal/review/module.go。
- internal/risk/：risk 领域，含 handler、service、repo 三层，入口在 internal/risk/module.go。
- internal/pricing/：pricing 领域，含 handler、service、repo 三层，入口在 internal/pricing/module.go。
- internal/warehouse/：warehouse 领域，含 handler、service、repo 三层，入口在 internal/warehouse/module.go。
- internal/settlement/：settlement 领域，含 handler、service、repo 三层，入口在 internal/settlement/module.go。
- internal/promotion/：promotion 领域，含 handler、service、repo 三层，入口在 internal/promotion/module.go。
- internal/gateway/：gateway 领域，含 handler、service、repo 三层，入口在 internal/gateway/module.go。
