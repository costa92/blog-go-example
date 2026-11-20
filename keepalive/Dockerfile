FROM golang:1.27 AS build
WORKDIR /src
COPY go.mod ./
COPY server ./server
COPY client ./client
RUN CGO_ENABLED=0 go build -trimpath -ldflags=-s -o /out/server ./server && \
    CGO_ENABLED=0 go build -trimpath -ldflags=-s -o /out/client ./client

FROM scratch
COPY --from=build /out/ /
