# review-gates：把审核结论绑到内容摘要上

配套文章：[审核后补了 3 行代码，内容摘要让旧批准失效，摘要之外的改动要靠树比较拦住](https://costalong.com/2026/11/23/agent-development-review-gates/)。

一个约 430 行的 Go 命令行 `gate`，把三类审核结论绑定到内容摘要：

| 关卡 | 摘要计算范围 |
| --- | --- |
| `design` | `review-gates.json` 里 `design` 列出的规格文件内容 |
| `tests` | `tests` 列出的测试文件内容，加上 `test_cmd -json` 的逐用例结果（去掉耗时） |
| `code` | 合并基点，以及 `code` 路径下每个文件 `merge-base..HEAD` 的 diff；这些路径有未提交改动时拒绝计算 |

批准记录以 JSON 存在 `.review/<关卡>.json`（被 `.gitignore` 排除，不进入提交树），同时记下批准时的 `HEAD` 和树对象。

```text
gate approve <design|tests|code> --by NAME   # 计算当前摘要并写入批准记录；测试失败时拒绝
gate check                                    # 重算三项摘要，列出变化的组成部分
gate merge-check                              # check + 主分支是否为祖先 + 在临时 worktree 生成 squash 候选，比较其树与 code 批准时的树
```

## 目录

- `main.go`、`gate.go`：命令行实现，只用标准库和本机 `git`。
- `gate_test.go`：表驱动测试，包括“无改动”在内的 10 种情形下 `check` / `merge-check` 应报告哪些关卡失效。
- `sample/`：被审核的小项目。`promote` 包把 `current` 符号链接切到恢复出来的副本，规格见 `sample/SPEC.md`。`promote_test.go` 是完整测试，`promote_weak_test.go`（`-tags weak`）只断言有没有返回错误。
- `mutation/`：变异测试。把整个目录复制到临时目录，逐个改源码，再跑对应测试，测试失败即算发现。9 个 `M*` 变异针对 `sample/promote`，6 个 `G*` 变异针对 `gate` 自身。
- `scenario/run.sh`：在临时 git 仓库里重放一次交接：实现、批准、实现者补错误分支、旧批准被拒、重新复核、只改 README、主分支前进、变基。`scenario/error-branch.patch` 是实现者补的那次改动。
- `results/`：下面运行的原始输出。

## 运行

Go 1.25+、git 2.x：

```bash
go test -count=1 -v ./...      # gate 测试 + 变异测试，约 13 秒
scenario/run.sh                 # 端到端交接场景，约 3 秒
```

`sample/` 有自己的 `go.mod`，不在 `./...` 里；单独运行：`cd sample && go test ./... && go test -tags weak ./...`。

2026-11-24 在 Linux x86_64、Go 1.27.4、git 2.53.0 上运行，输出在 `results/`：

- `results/scenario.txt`：场景全程。提交号和含合并基点的 `code` 摘要每次运行都不同（提交带时间戳），文件摘要和树对象不变。
- `results/go-test-v.txt`：`go test -count=1 -v ./...` 的完整输出。
- `results/mutation-run1-before-fix.txt`：第一次跑变异测试的汇总，`G3` 存活；之后给 `gate_test.go` 补了“测试目录外新增测试包”的用例。

变异测试结果：完整测试发现 9/9 个 `M*` 变异，只断言错误的弱测试发现 6/9（漏掉 M5、M6、M9）；补用例后 `gate_test.go` 发现 6/6 个 `G*` 变异。

## 边界

- 摘要只说明计算范围内的内容没变，不说明代码正确，也不证明是谁批准的：`--by` 是自报名字，`.review/` 是本地文件，任何能写工作区的人都能改。
- `.review/` 不进提交树，所以批准记录不随分支传给别人；要共享，需要放到服务端（CI 状态、PR 审核）或单独的存储里。
- `tests` 摘要不含被测代码。只改代码、测试照样全过时，`tests` 关卡保持有效，由 `code` 关卡负责这次变化。
- `code` 摘要包含合并基点，变基后即使 diff 不变也要重新批准；这是有意的选择，代价是每次变基都多一次批准。
- `sample/` 的权限错误用例依赖 `chmod 000`，以 root 运行时该用例不成立。
