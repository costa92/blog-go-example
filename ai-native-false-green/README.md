# AI-Native：检查什么时候会假绿

配套文章：[AI-Native 的第一步是找出会假绿的检查](https://costalong.com/2026/11/18/ai-native/)。

两组实验：

1. **NetworkPolicy 是否真的执行**：同一份 default-deny 策略分别放进 kindnetd 和 Calico 的 kind 集群，用 Pod 间 curl 看流量，而不是看 `kubectl apply` 的返回值。
2. **服务契约检查漏掉什么**：对一个私有练习项目里的 Golden Path 契约检查跑全部内置负向变异，再加 9 个列表外的变异，看哪些会通过（假绿）。

## 目录

| 路径 | 内容 |
|---|---|
| `manifests/kind-a-kindnetd.yaml` | 默认 CNI（kindnetd）的单节点集群 |
| `manifests/kind-b-calico.yaml` | `disableDefaultCNI: true` + podSubnet 192.168.0.0/16，之后装 Calico |
| `manifests/workload.yaml` | `np-demo` 命名空间、server（nginx）和 client Pod |
| `manifests/default-deny.yaml` | 选中全部 Pod 的 Ingress+Egress 拒绝策略 |
| `manifests/allow-client-to-server.yaml` | 只放行 client → server:80 和 client 的 DNS |
| `run-netpol.sh` | 建集群、三态探测（无策略 / default-deny / 显式放行），输出写进 `results/` |
| `checker/extra-defects.mjs` | 列表外的 9 个变异 |
| `checker/template-contract-report.patch` | 给契约测试加"只记录不中断"模式的补丁 |
| `results/*.txt` | 每次集群实验的完整命令与输出 |
| `results/contract-mutations.csv` | 243 次变异的逐条结果 |

## 运行 NetworkPolicy 实验

需要 Docker、kind、与集群版本匹配的 kubectl。脚本拒绝使用 `~/.kube/config`，务必指定一次性 kubeconfig：

```sh
export KUBECONFIG=$PWD/.kubeconfig
KIND=kind KUBECTL=kubectl ./run-netpol.sh kindnetd
curl -sSfLO https://raw.githubusercontent.com/projectcalico/calico/v3.32.1/manifests/calico.yaml
KIND=kind KUBECTL=kubectl ./run-netpol.sh calico calico.yaml
# 换 kind 版本时用 TAG 区分输出文件和集群名
TAG=kind-v0.23.0 KIND=/path/to/kind-v0.23.0 KUBECTL=kubectl ./run-netpol.sh kindnetd
kind delete cluster --name np-kindnetd; kind delete cluster --name np-calico
rm -f .kubeconfig
```

探测打的是 server 的 Pod IP，不走 Service 名，避免 default-deny 先把 DNS 拦掉、把"DNS 不通"误当成"策略生效"。

## 实测结果（2026-11-24）

| 集群 | 网络插件 | 无策略 | default-deny | 显式放行 | 结果文件 |
|---|---|---|---|---|---|
| kind v0.23.0，node v1.30.0 | kindnetd v20240202-8f1494ea | 200 | **200（没拦住）** | 200 | `results/kindnetd-kind-v0.23.0.txt` |
| kind v0.24.0，node v1.31.0 | kindnetd v20240813-c6f155d6 | 200 | 超时（拦住） | 200 | `results/kindnetd-kind-v0.24.0.txt` |
| kind v0.33.0，node v1.37.0 | kindnetd v20260820-69b56db7 | 200 | 超时（拦住） | 200 | `results/kindnetd-kind-v0.33.0.txt` |
| kind v0.33.0，node v1.37.0 | Calico v3.32.1（manifest 安装） | 200 | 超时（拦住） | 200 | `results/calico.txt` |

四次 `kubectl apply` 都返回 `created`，`kubectl get networkpolicy` 都能查到策略。只有 kind v0.23.0 自带的 kindnetd 不执行它。kind v0.24.0 的 kindnetd 日志里有 `Starting controller kube-network-policies`（`results/kindnetd-kind-v0.24.0-log.txt`）。

## 契约检查实验

被测的检查（`check-golden-path.mjs`）和它的变异测试在作者的私有练习仓库里，这里只发布补丁、额外变异和结果，读者无法直接复跑。复跑方式（在那个仓库的副本里，不改原仓库）：

```sh
git apply template-contract-report.patch
CONTRACT_REPORT=$PWD/report.jsonl EXTRA_DEFECTS=$PWD/extra-defects.mjs \
  node --experimental-strip-types --test platform/backstage/tools/test-go-service-template.mjs
```

结果：两个生成服务共 225 个内置变异全部被拒绝且原因匹配；9 个额外变异在两个服务上各有 8 个通过检查，只有"内存 request 改成 1Mi"被拦下。

这些是教学实验，不代表任何生产系统。
