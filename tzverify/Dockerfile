ARG BASE_IMAGE=ubuntu:26.04
ARG GO_IMAGE=golang:1.27

FROM ${GO_IMAGE} AS build
WORKDIR /src
COPY go.mod main.go ./
RUN CGO_ENABLED=0 go build -trimpath -o /tz-verify .

FROM ${BASE_IMAGE}
ARG TZ_PKGS="tzdata tzdata-legacy"
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends ${TZ_PKGS} \
 && ln -sf /usr/share/zoneinfo/Asia/Shanghai /etc/localtime \
 && rm -rf /var/lib/apt/lists/*
COPY --from=build /tz-verify /usr/local/bin/tz-verify
# 构建期校验：系统时区数据里每个别名都能加载且与标准名一致，否则构建失败
RUN /usr/local/bin/tz-verify
