# AI-Native：批准与执行之间的检查

配套文章：[AI-Native 进阶：批准之后，变更怎样安全执行](https://costalong.com/2026/11/22/ai-native-change-gate/)。

这是单进程、内存中的教学模型，不连接模型、Kubernetes、数据库或身份服务。它验证一份批准与某次具体写操作的对应关系，不实现生产授权系统，也不实现完整 GitOps 交付。

## 运行

Go 1.25+，无第三方依赖：

```bash
go test -race -count=1 ./...
go vet ./...
go run .
```

若本机 GOROOT 与 PATH 中的 Go 不一致，可针对这些命令使用 `env -u GOROOT go ...`，不要为此修改全局工具链配置。

2026-11-22 在 macOS arm64、Go 1.27.2 实际运行输出：

```text
stale approval: error=target state changed image=v18 gate_applied=0
lost reply (simulated): replay=true receipt_version=42 gate_applied=1
same ID, changed target: error=operation ID reused with different content
new policy: error=policy revision changed gate_applied=0
32 concurrent calls: applied=1 replayed=31 errors=0 final_version=42 gate_applied=1
```

“回复丢失”通过丢弃第一次成功调用的返回值模拟，没有制造网络故障。32 次并发调用使用同一个操作号、同一份内容。

## 设计与验证范围

- `Plan` 的固定结构绑定操作号、执行者、服务、资源 UID、起始修订、前后镜像、政策版本与到期时间。
- `Approve` 模拟可信审批服务，将计划摘要保存到服务端；不暴露为 Agent 工具。`reviewer` 与 `caller` 都代表由外部可信认证层给出的身份，不是 HTTP 参数中的自报身份。示例只检查非空与不同人，没有实现角色、审批资格或身份认证。
- 摘要由 Go `encoding/json` 对固定结构编码后计算 SHA-256；这是本示例的比较方式，不是跨语言 JSON 规范化协议或签名凭证。
- `Execute` 先核对调用者，再检查已有回执。同号同内容返回历史回执，同号不同内容拒绝。只有未执行的操作进入批准匹配、执行开关、到期、政策版本和资源条件检查。
- `policy_revision` 只让旧政策下的批准失效，没有实现真正的策略求值器或生产权限检查。
- 检查、状态更新与回执写入由同一把锁保护。`Version` 是模型中的本地递增计数，不是 Kubernetes `resourceVersion` 的实现。
- `ExternalChange` 与 `SetPolicy` 供场景准备使用，模拟其他操作者、撤权和政策更新；不是给 Agent 的能力。
- 重放旧回执不证明当前资源仍为旧目标或处于健康状态。身份匹配后可以查询已完成记录，不会因批准过期或停止新执行而重新产生副作用。

测试覆盖旧批准覆盖热修复、批准内容被改、操作号复用、过期边界、政策变化、执行关闭、换调用者、资源重建、历史回执与当前状态不同、64 次相同调用并发，以及两份批准竞争同一修订。

## 不能由这个例子推导的结论

状态、批准和回执均在内存中，进程退出就丢失。这里没有远程调用、崩溃恢复、事务 Outbox、真实分支保护、部署控制器或业务验收。一个 mutex 无法把数据库和 Kubernetes 组成原子事务，分布式锁也不能自行消除“远端执行完成、结果尚未持久化”的空档。

部署到真实系统时，需要持久化执行意图、下游条件写入或幂等接口、可信结果查询、结果未知时的对账流程，以及独立的身份和策略执行。这些是文章讨论的设计要求，本示例没有声称已经实现。
