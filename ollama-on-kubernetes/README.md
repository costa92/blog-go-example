# Ollama 在 Kubernetes 里的冷启动和资源限制实验

配套文章：[把 Ollama 放进 Kubernetes：Pod 已 Ready，模型还没到](https://costalong.com/2026/11/20/ollama-on-kubernetes/)。

`scripts/ollama.sh` 按环境变量生成 Ollama 的 Deployment、Service 和可选的 PVC：模型放 emptyDir 还是 PVC、启动时拉不拉模型、要不要预热、就绪探针怎么判断、CPU 和内存限制多少。`scripts/client.sh` 在集群里起一个 curl Pod，按固定间隔请求 `/api/chat`，每行记 HTTP 状态码、耗时和响应体。`batch-*.sh` 是文章各小节的实验批次，结果写到 `logs/`。

这是教学用的复现脚本，只在单节点 kind 集群和 CPU 上跑过，不是 Ollama 的部署方案，也不是性能基准。

## 文件

| 文件 | 作用 |
|---|---|
| `scripts/k` | kubectl 包装，固定用本目录的 `kubeconfig`（或 `KUBECONFIG_FILE`） |
| `scripts/ollama.sh` | 生成清单；`MODEL`、`STORE`、`PULL`、`WARM`、`PROBE`、`CPU`、`MEM`、`ENV`、`STRATEGY` 等开关见文件头注释 |
| `scripts/client.sh` | 客户端 Pod（`curlimages/curl:8.11.1`）；`N`、`SLEEP`、`OPTS`、`PROMPT`、`KA` 控制请求 |
| `scripts/run-cold.sh` | 新建 Deployment 的同时启动客户端，看到几次 200 后停止，用来量冷启动 |
| `scripts/run-steady.sh` | 等 Deployment Ready 后跑完客户端，可在第 `AT` 秒 `rollout restart`，并保存容器的 `cpu.stat` 和 `memory.events` |
| `scripts/collect.sh` | 保存 Pod 时间线、事件、服务端和客户端日志到 `logs/NAME.*` |
| `scripts/term-test.sh` | 删除 Pod 到 Pod 消失的耗时，对比转发与不转发 SIGTERM |
| `scripts/batch-start.sh` | 冷启动：emptyDir、首次填充 PVC、PVC 已有模型仍 `pull`、只预热 |
| `scripts/batch-run.sh` | `keep_alive` 过期后的重新加载等稳态实验，依赖 `batch-start.sh` 填好的 PVC |
| `scripts/batch-cpu.sh` | 不同 CPU limit 下默认线程数与 `num_thread` 等于 limit 的生成速度 |
| `scripts/batch-mem.sh` | 不同内存 limit 与 `num_ctx` 组合下能否加载 |
| `scripts/batch-rollout.sh` | 第 20 秒滚动重启：Recreate 与 RollingUpdate，各配两种就绪判断 |
| `scripts/chatstats.py` | 把客户端日志整理成每个请求一行：加载耗时、预填充和生成速度 |

## 运行

需要 Docker、[kind](https://kind.sigs.k8s.io/) 和 kubectl。文章数据来自 kind v0.24.0，单节点，节点镜像 `kindest/node:v1.31.0`，kube-proxy iptables 模式，StorageClass 用 kind 自带的 local-path；宿主机 i7-14700KF，61 GiB 内存，cgroup v2，没有 GPU 参与。Ollama 镜像 `ollama/ollama:0.40.16`，模型 `qwen2.5-coder:0.5b`。

```bash
cd ollama-on-kubernetes

# 1. 建集群，kubeconfig 单独写一份，不碰默认的 ~/.kube/config
kind create cluster --name ok8s --image kindest/node:v1.31.0 --kubeconfig ./kubeconfig

# 2. 预先把 Ollama 镜像导进节点（约 3.4 GB）
docker pull ollama/ollama:0.40.16
kind load docker-image --name ok8s ollama/ollama:0.40.16
# 如果上一步报 content digest not found，只导出 amd64 一个平台再交给节点里的 ctr
docker save --platform linux/amd64 ollama/ollama:0.40.16 \
  | docker exec -i ok8s-control-plane ctr -n k8s.io images import --snapshotter=overlayfs -

# 3. 跑实验，结果在 logs/ 下
scripts/batch-start.sh      # 冷启动，同时把模型填进 PVC
scripts/batch-run.sh        # keep_alive 等稳态实验
scripts/batch-cpu.sh
scripts/batch-mem.sh
scripts/batch-rollout.sh
scripts/term-test.sh
python3 scripts/chatstats.py logs/*.client.log

# 4. 清理
kind delete cluster --name ok8s
```

`run-steady.sh` 通过 `docker exec ok8s-control-plane` 读节点上的 Pod cgroup，所以集群名要用 `ok8s`。冷启动的几组会在 Pod 里从 Ollama 模型仓库拉约 400 MB 的模型，需要能访问外网。

## 验证与边界

- 每种配置只跑了一次。文章那台机器上偶尔有单个请求慢出一个数量级，原因没查清，结论不要建立在单个请求的数字上。
- 只用了 0.5b 模型和 CPU 推理，换成更大的模型或 GPU 节点，绝对数字都会变。
- `batch-mem.sh` 会故意让容器在内存上限下加载模型，只在本地 kind 这样的一次性集群里运行。
- 多节点、GPU、并发请求（`OLLAMA_NUM_PARALLEL`）、多模型常驻和 HPA 扩缩容都没有测。
