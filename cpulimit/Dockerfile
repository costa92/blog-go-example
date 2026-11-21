FROM golang:1.27 AS build
WORKDIR /src
COPY go.mod ./
COPY server ./server
COPY loadgen ./loadgen
RUN CGO_ENABLED=0 go build -trimpath -ldflags=-s -o /out/server ./server && \
    CGO_ENABLED=0 go build -trimpath -ldflags=-s -o /out/loadgen ./loadgen

FROM scratch
COPY --from=build /out/ /
