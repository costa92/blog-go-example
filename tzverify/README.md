# tz-verify：构建期校验镜像里的时区别名

配套文章：[Go 报 unknown time zone Asia/Calcutta：Ubuntu 24.04/26.04 镜像缺 tzdata-legacy 的排查与修复](https://costalong.com/2026/11/16/ubuntu-tzdata-legacy-go-timezone/)。

`tz-verify` 从镜像的 `/usr/share/zoneinfo/tzdata.zi` 读出所有 `L 标准名 别名` 行，逐个用 `time.LoadLocation` 加载，再和标准名比对 1970 到 2037 年每两周一个时间点的偏移与缩写。它不引入 `time/tzdata`，和不内嵌时区数据的服务一样只读系统目录。

有别名加载失败、和标准名不一致、必需别名不在清单里，或者一个别名都没读到时，以退出码 1 结束，让 `docker build` 失败。

## 文件

| 文件 | 作用 |
|---|---|
| `main.go` | 校验程序，只用标准库 |
| `Dockerfile` | 两段式：`GO_IMAGE` 编译，`BASE_IMAGE` 里装 `TZ_PKGS` 后运行 `tz-verify` |

## 运行

需要 Docker。第二段换成你自己的基础镜像即可。

```bash
cd tzverify

# 默认 ubuntu:26.04，装 tzdata 和 tzdata-legacy，应当构建通过
docker build -t tz-verify .

# 只装 tzdata，复现旧名加载失败
docker build --build-arg TZ_PKGS=tzdata -t tz-verify .

# 其他版本；ubuntu:22.04 没有 tzdata-legacy 这个包，要传 TZ_PKGS=tzdata
docker build --build-arg BASE_IMAGE=ubuntu:24.04 --build-arg TZ_PKGS=tzdata -t tz-verify .
docker build --build-arg BASE_IMAGE=ubuntu:22.04 --build-arg TZ_PKGS=tzdata -t tz-verify .
```

## 验证与边界

整理进本仓库时（2026-11-21）重跑的结果，镜像里的 tzdata 都是 2026e：

| 镜像 | `TZ_PKGS` | 输出 | 构建 |
|---|---|---|---|
| `ubuntu:26.04` | `tzdata tzdata-legacy` | 问题 0 个 | 通过 |
| `ubuntu:26.04` | `tzdata` | 别名 162 个，系统缺失 113 个，问题 113 个 | 失败 |
| `ubuntu:24.04` | `tzdata` | 别名 151 个，系统缺失 101 个，问题 101 个 | 失败 |
| `ubuntu:24.04` | `tzdata tzdata-legacy` | 别名 151 个，系统缺失 0 个，问题 0 个 | 通过 |
| `ubuntu:22.04` | `tzdata` | 问题 0 个 | 通过 |

- 每两周取一个点比对，两次切换相隔不到两周的规则差异可能漏掉。
- 不内嵌时区数据时，别名和标准名读的是同一份系统数据，比对这一项几乎不会报错。服务如果 `import _ "time/tzdata"`，给 `tz-verify` 也加上同一行再编译，才能比出内嵌数据和系统数据的偏差。
- 结果依赖镜像里 tzdata 的版本，别名数量会随发行版和稳定更新变化。
