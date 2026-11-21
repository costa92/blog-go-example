# encoding/json v1 与 v2 行为对比

配套文章：[Go encoding/json v1 与 v2：行为差异、迁移方式与实测性能](https://costalong.com/2026/11/06/go-json-v1-v2/)。

用测试逐项断言文章中的输出：每个 `Test*` 对应文章的一个小节，测试通过就说明当前 Go 版本的行为与文章一致。

## 运行

需要 Go 1.27 或更新版本（1.27 起默认启用 `encoding/json/v2`）。在仓库根目录执行：

```bash
go test -v ./jsonv2/
go test ./jsonv2/ -bench . -benchmem -count 3
```

文件带有 `//go:build goexperiment.jsonv2 && go1.27` 约束：Go 1.25/1.26 的实验版 v2 使用 `inline`、`unknown`、`format` 等已被改名或移除的 tag，与本案例不兼容，因此在这些版本上该目录会被跳过，不影响仓库其他案例。

想对比旧版 v1 实现的性能，可以用 `GOEXPERIMENT=nojsonv2` 跑 v1 基准，但此时本目录会被跳过，需要把 `BenchmarkV1*` 单独复制出来运行。

## 覆盖的差异

| 测试 | 内容 |
|---|---|
| `TestNilSliceAndMap` | nil 切片/map：`null` 与 `[]`/`{}` |
| `TestCaseSensitiveNames` | 字段名大小写匹配，`case:ignore`，`MatchCaseInsensitiveNames` |
| `TestDuplicateNames` | 重复键报错，`AllowDuplicateNames` |
| `TestInvalidUTF8` | 非法 UTF-8 报错 |
| `TestEscapeHTML` | `<>&` 转义，`EscapeForHTML` |
| `TestOmitEmptyAndOmitZero` | `omitempty` 按 JSON 结果判断，`omitzero` |
| `TestDuration` | `time.Duration` 无默认表示，`FormatDurationAsNano`、`MarshalToFunc` |
| `TestByteArrayAndArrayLength` | `[N]byte` 编码为 base64，数组长度严格匹配 |
| `TestMapOrder` | `Deterministic` |
| `TestPointerReceiverMethod` | 指针接收者的 `MarshalJSON` |
| `TestSemanticError` | `SemanticError` 的 JSON Pointer 与字节偏移 |
| `TestEmbed` | `embed` 内联与兜底字段，`RejectUnknownMembers` |
| `TestMarshalJSONTo` | 流式编码接口 |
| `TestJSONTextStream` | `jsontext` 逐 token 读取与 `Canonicalize` |
| `TestDefaultOptionsV1` | 用 v1 选项渐进迁移 |

## 演示边界

基准数据只代表本案例的数据形状（1000 个含小 map 和字符串切片的对象），不能用来推断其他负载。v2 的 API 仍在演进，结论以所用 Go 版本的 `go doc encoding/json/v2` 为准。
