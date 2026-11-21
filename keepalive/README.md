# Go 长连接与 Kubernetes 扩容后的流量不均

配套文章：[Go 长连接让扩容后的新 Pod 分不到流量](https://costalong.com/2026/11/20/go-keepalive-k8s-imbalance/)。

`server` 是一个回显自己 Pod 名的 HTTP 服务，`client` 按固定速率压它，每秒打印各 Pod 回复的请求数和新建连接数。`scripts/` 把两者放进 kind 集群，在第 20 秒扩容或滚动更新，保存客户端日志。

这是教学用的复现程序，只用来观察连接复用对 Service 负载分配的影响，不是负载均衡方案，也不是性能基准。

## 文件

| 文件 | 作用 |
|---|---|
| `server/main.go` | 回显服务，`MAX_REQS_PER_CONN`、`H2C`、`LATENCY`、`SHUTDOWN_DELAY` 等开关见文件头注释 |
| `client/main.go` | 压测客户端，`http.Transport` 的各项参数、h2c、Headless 轮询都走环境变量，见文件头注释 |
| `Dockerfile` | 两个二进制打进同一个 `FROM scratch` 镜像 `keepalive:v1` |
| `scripts/echo.sh` | 生成 Deployment、ClusterIP Service 和 Headless Service；`READINESS`、`PRESTOP_SLEEP`、`SERVER_ENV` 控制探针、preStop 和服务端开关 |
| `scripts/run.sh` | 部署 2 副本，起一个 60 秒的客户端 Pod，第 20 秒执行 `scale4` 或 `restart`，日志写到 `logs/` |
| `scripts/batch-*.sh` | 文章各小节对应的实验批次 |
| `scripts/summarize.py` | 统计第 26 秒以后新 Pod 的请求占比、每秒新建连接数和错误数 |

## 运行

需要 Docker、[kind](https://kind.sigs.k8s.io/) 和 kubectl。文章数据来自 kind v0.24.0、节点镜像 `kindest/node:v1.31.0`，kube-proxy 为 iptables 模式。

```bash
cd keepalive

# 1. 建集群，kubeconfig 单独写一份，不碰默认的 ~/.kube/config
kind create cluster --name keepalive --image kindest/node:v1.31.0 --kubeconfig ./kubeconfig

# 2. 构建镜像并载入集群（需要 Go 1.27 工具链镜像）
docker build -t keepalive:v1 .
kind load docker-image --name keepalive keepalive:v1

# 3. 跑实验，结果在 logs/ 下
scripts/batch-scale.sh     # 默认配置和各种修复方式，2 → 4 扩容
scripts/batch-extra.sh     # Headless 打印 DNS 结果、32 worker 的两组对照
scripts/batch-rollout.sh   # 滚动更新：探针、preStop、应用内延迟关闭
python3 scripts/summarize.py logs/*.log

# 4. 清理
kind delete cluster --name keepalive
docker rmi keepalive:v1
```

kubeconfig 默认读 `keepalive/kubeconfig`，也可以用 `KUBECONFIG_FILE` 指定。

单独跑一组，例如服务端每 100 个请求关一次连接：

```bash
SERVER_ENV="LATENCY=10ms MAX_REQS_PER_CONN=100" scripts/run.sh demo scale4
python3 scripts/summarize.py logs/demo.log
```

不进集群也能先看程序输出：

```bash
POD_NAME=local MAX_REQS_PER_CONN=100 go run ./server &
TARGET=http://127.0.0.1:8080/ DURATION=5s go run ./client
```

## 验证与边界

- 客户端每行输出 `t=<秒> dials=<新建连接数> <pod>=<请求数> ...`，那一秒有失败请求时在行尾追加 `ERR[<错误>]=<次数>`。
- 新 Pod 是否分到流量取决于开头几条连接被随机分到哪里，以及新 Pod 的启动速度，同一配置两次运行结果可能差很多。文章里多数配置只跑了一次。
- 只覆盖 kube-proxy iptables 模式；IPVS、nftables 或 eBPF 数据面的行为可能不同，没有测试。
