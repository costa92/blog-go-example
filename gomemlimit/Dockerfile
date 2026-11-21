# GO_IMAGE picks the toolchain; GOMOD_GO rewrites the `go` line of go.mod,
# which decides the default GODEBUG settings (containermaxprocs etc.).
ARG GO_IMAGE=golang:1.27
FROM ${GO_IMAGE} AS build
ARG GOMOD_GO=1.25
WORKDIR /src
COPY go.mod main.go ./
RUN sed -i "s/^go .*/go ${GOMOD_GO}/" go.mod && CGO_ENABLED=0 go build -trimpath -ldflags=-s -o /memload .

FROM scratch
COPY --from=build /memload /memload
ENTRYPOINT ["/memload"]
