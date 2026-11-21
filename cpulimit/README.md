# CPU limit 与 Go 服务的尾延迟

配套文章：[CPU 只用一半，Go 服务 p99 为何按 100ms 往上跳](https://costalong.com/2026/11/21/go-cpu-limit-latency/)。

`server` 是一个每个请求固定消耗 5ms 线程 CPU 时间的 HTTP 服务，`loadgen` 是开环压测器：按计划时刻发请求，不等前面的回复，延迟从计划时刻算起。`scripts/` 把两者放进 kind 集群，按不同的 CPU limit、`GOMAXPROCS`、`GOGC` 和到达方式逐组运行，记录延迟分位数和容器 cgroup `cpu.stat` 的差值。

这是教学用的复现程序，只用来观察 CFS 带宽控制和 Go 调度对延迟的影响，不是性能基准。

## 文件

| 文件 | 作用 |
|---|---|
| `server/main.go` | `/work` 分配垃圾后按线程 CPU 时间烧满 `WORK`；`/cpustat` 返回容器的 `cpu.stat`、`GOMAXPROCS` 和 GC 次数。参数见文件头注释 |
| `loadgen/main.go` | 开环压测器，`RPS`、`BURST`、`POISSON`、`DURATION` 等走环境变量，输出 `RESULT`、`HIST`，可选 `SLOW` 和 `LATS` 行 |
| `Dockerfile` | 两个二进制打进同一个 `FROM scratch` 镜像 `cpulim:v1` |
| `scripts/server.sh` | 生成服务端 Deployment 和 Service；`LIMIT`、`REQUEST`、`SERVER_ENV` 控制资源和运行时参数 |
| `scripts/run.sh` | 新建服务端 Pod，连跑若干次压测 Pod，日志写到 `logs/NAME.log` |
| `scripts/set-burst.sh` | 直接在 kind 节点上给 Pod 和容器 cgroup 写 `cpu.max.burst`（Kubernetes 没有对应字段） |
| `scripts/batch-*.sh` | 文章各小节对应的实验批次 |
| `scripts/summarize.py` | 每个日志一行：p50、p99 中位数和范围、限流周期、CPU 使用率、GC 次数 |

## 运行

需要 Docker、[kind](https://kind.sigs.k8s.io/) 和 kubectl。文章数据来自 kind v0.24.0、节点镜像 `kindest/node:v1.31.0`，节点 cgroup v2。

```bash
cd cpulimit

# 1. 建集群，kubeconfig 单独写一份，不碰默认的 ~/.kube/config
kind create cluster --name cpulim --image kindest/node:v1.31.0 --kubeconfig ./kubeconfig

# 2. 构建镜像并载入集群（需要 Go 1.27 工具链镜像）
docker build -t cpulim:v1 .
kind load docker-image --name cpulim cpulim:v1

# 3. 跑实验，结果在 logs/ 下
scripts/batch-burst.sh    # 1 核 limit，突发大小 × GOMAXPROCS
scripts/batch-gc.sh       # GOGC=off + GOMEMLIMIT
scripts/batch-limits.sh   # 0.5/1/2/4 核 limit 与只设 request，泊松到达
scripts/batch-extra.sh    # cpu.max.burst、突发 40 不设 limit、gctrace
scripts/batch-fine.sh     # 突发 40 的逐请求延迟（DUMP=1）
scripts/batch-trace.sh    # 偶发长停顿的复现尝试
python3 scripts/summarize.py logs/*.log

# 4. 清理
kind delete cluster --name cpulim
docker rmi cpulim:v1
```

`set-burst.sh` 通过 `docker exec cpulim-control-plane` 写节点上的 cgroup，集群名不同时用 `KIND_NODE` 指定节点容器。kubeconfig 默认读 `cpulimit/kubeconfig`，也可以用 `KUBECONFIG_FILE` 指定。

单独跑一组，例如 1 核 limit、`GOMAXPROCS=26`、每 400ms 来 40 个请求，跑 1 次：

```bash
LIMIT=1 SERVER_ENV="GOMAXPROCS=26" scripts/run.sh demo 100 40 1
python3 scripts/summarize.py logs/demo.log
```

不进集群也能先看程序输出（服务端读不到 cgroup 限制时 `cpu.stat` 里没有限流字段）：

```bash
ADDR=:18089 go run ./server &
TARGET=http://127.0.0.1:18089 RPS=100 BURST=10 DURATION=5s WARMUP=1s go run ./loadgen
```

## 验证与边界

- `RESULT` 行里的 `periods`、`throttled`、`throttled_ms`、`usage_ms`、`bursts`、`burst_ms` 是测量窗口前后两次读取 `cpu.stat` 的差值；`throttled_ms` 会超过墙上时间，看起来是按 CPU 运行队列分别累加的。
- 每组默认跑 3 次，共用同一个服务端 Pod。主机上的其他负载会造成个别离群值，相差几毫秒的结果不要当成结论。
- 服务端是纯 CPU 计算，没有 I/O 等待；真实服务的突发形状不同。
- 脚本里 `GOMAXPROCS` 等于主机核数的那组，日志文件名用 `$(nproc)` 生成，文章的主机是 26 核，所以叫 `*-p26.log`；换一台机器跑会是 `*-p8.log` 之类。
