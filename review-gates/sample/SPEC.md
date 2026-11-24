# 放行恢复副本（示例规格）

目录布局：

- `current`：指向当前服务目录的符号链接，例如 `replicas/r1`。
- `old.lock`：旧实例运行期间存在。
- `intent`：正在切换的副本名，切换完成后删除。
- `replicas/<name>/STATUS`：内容为 `ready` 时副本可以放行。

`Promote(root, name)` 的验收条件：

1. AC1 `old.lock` 存在时拒绝，`current` 不变。
2. AC2 读取 `current` 指向的旧目录时遇到“不存在”以外的错误（例如权限错误），拒绝，`current` 不变。
3. AC3 副本 `STATUS` 不是 `ready` 时拒绝，`current` 不变。
4. AC4 `intent` 记录了另一个副本时拒绝，`current` 和 `intent` 不变。
5. AC5 先写 `intent`，再切换 `current`；切换后进程中断，`intent` 仍在。
6. AC6 成功后 `current` 指向新副本，`intent` 被删除。
7. AC7 `Resume(root)` 按 `intent` 继续未完成的切换，且同样遵守 AC1 到 AC3。
8. AC8 切换 `current` 失败时返回错误，`intent` 保留。
