# Go 内存上限在 Kubernetes 里的表现

配套文章：[Go 存活堆 150MiB 为何撑爆 256Mi 容器](https://costalong.com/2026/11/20/go-memlimit-k8s/)。

`memload` 是文章里所有实验用的测试程序：保持一份固定大小的存活堆，持续制造短命垃圾，按固定间隔打印 `runtime/metrics` 和容器 cgroup 的内存读数。`scripts/` 里是把它放进 kind 集群、按不同内存上限和 CPU 限制逐个跑 Pod 的脚本。

这是教学用的负载程序，只用来观察 GC 在容器里的行为，不是性能基准，也不能直接当成生产配置的依据。

## 文件

| 文件 | 作用 |
|---|---|
| `main.go` | 测试程序，参数全部走环境变量，见文件头注释 |
| `Dockerfile` | `GO_IMAGE` 选工具链，`GOMOD_GO` 改写 go.mod 的 `go` 行（它决定 `containermaxprocs` 等 GODEBUG 默认值） |
| `scripts/pod.sh` | 生成 Pod 清单；环境变量写成 `@limits.memory` 或 `@limits.memory/1Mi` 时改用 downward API 注入 |
| `scripts/run.sh` | 跑一个 Pod 指定秒数，保存日志、describe、重启状态和 Pod cgroup 的 `memory.events`，然后删除 |
| `scripts/run-once.sh` | 同上，但 `restartPolicy: Never`，一直跟日志到容器退出，保留被 OOM 杀掉前的最后几行 |
| `scripts/batch-*.sh` | 文章各小节对应的实验批次 |
| `scripts/summarize.py` | 对每次运行 5 秒以后的采样取平均 |

## 运行

需要 Docker、[kind](https://kind.sigs.k8s.io/) 和 kubectl。文章的数据来自 kind v1.31.0 单节点集群，节点 cgroup v2。

```bash
cd gomemlimit

# 1. 建集群，kubeconfig 单独写一份，不碰默认的 ~/.kube/config
kind create cluster --name gomem --image kindest/node:v1.31.0 --kubeconfig ./kubeconfig

# 2. 构建三种镜像：Go 1.24 工具链；Go 1.27 工具链 + go.mod 1.24；Go 1.27 工具链 + go.mod 1.25
docker build -t memload:go1.24        --build-arg GO_IMAGE=golang:1.24 --build-arg GOMOD_GO=1.24 .
docker build -t memload:go1.27-mod1.24 --build-arg GOMOD_GO=1.24 .
docker build -t memload:go1.27-mod1.25 --build-arg GOMOD_GO=1.25 .
kind load docker-image --name gomem memload:go1.24 memload:go1.27-mod1.24 memload:go1.27-mod1.25

# 3. 跑实验，结果在 logs/ 下
scripts/batch-mem.sh      # 默认 GOGC、GOMEMLIMIT、软上限、堆外内存、downward API
scripts/batch-tput.sh     # GOMEMLIMIT 逼近存活堆时的分配吞吐
scripts/batch-cpu.sh      # 不同 CPU limit 下三种构建报告的 GOMAXPROCS
scripts/batch-procs.sh    # GOMAXPROCS 26 与 2 对 GC CPU 的影响
python3 scripts/summarize.py a-default b-limit230 e-spiral

# 4. 清理
kind delete cluster --name gomem
```

脚本通过 `docker exec gomem-control-plane` 读取节点上的 Pod cgroup，所以集群名要用 `gomem`。kubeconfig 默认读 `gomemlimit/kubeconfig`，也可以用 `KUBECONFIG_FILE` 指定。

单独跑一次，看程序输出：

```bash
scripts/run-once.sh demo 30 memload:go1.27-mod1.25 256Mi 2 LIVE_PTR=1 LIVE_MIB=150 GOMEMLIMIT=230MiB INTERVAL=1s
```

## 验证与边界

- 每行输出都带 `live`、`goal`、`gc` 次数和 `gcCPU`。`gcCPU` 是 `/cpu/classes/gc/total` 占 `/cpu/classes/total` 的比例，包含 idle mark 时间，是 GC 开销的上限。
- 结果会随机器核数、内核版本和 Go 版本变化。文章里多数配置只跑了一次，数字之间相差几个百分点不要当成结论。
- 程序会故意把容器推到 OOM，只在本地 kind 这样的一次性集群里运行。
