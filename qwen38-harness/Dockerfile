FROM node:22.19.0-bookworm-slim AS node-runtime

FROM golang:1.27.2-bookworm AS build
WORKDIR /build
COPY go.mod *.go ./
COPY tasks ./tasks
RUN CGO_ENABLED=0 go build -trimpath -o /out/harness-experiment .

FROM golang:1.27.2-bookworm
COPY --from=node-runtime /usr/local/bin/node /usr/local/bin/node
COPY --from=node-runtime /usr/local/lib/node_modules/npm /opt/npm
RUN node /opt/npm/bin/npm-cli.js install --prefix /opt/pi --ignore-scripts --no-audit --no-fund \
      @earendil-works/pi-coding-agent@1.5.2 \
    && useradd --create-home --uid 10001 experiment
COPY --from=build /out/harness-experiment /usr/local/bin/harness-experiment
USER experiment
WORKDIR /tmp
ENV GOCACHE=/tmp/go-build GOPATH=/tmp/gopath
ENTRYPOINT ["harness-experiment"]
