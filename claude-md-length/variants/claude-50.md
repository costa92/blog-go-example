# gw

gw is a small key/value gateway written in Go (stdlib only). Module path `example.com/gw`.

## Error handling

- When you return an error received from another call, wrap it as `fmt.Errorf("gw: <funcName>: %w", err)`; never return it bare.

## Git

- Commit messages must start with `[gw] ` (bracket prefix, then a space), e.g. `[gw] add TTL to store`.

## Test files

- Name every new test file `<name>_internal_test.go`, not plain `<name>_test.go`.

## Commands

- Build: `go build ./...`
- Test: `go test ./...`
- Vet: `go vet ./...`
- Run locally: `go run ./cmd/gw`

## Logging

- Log with `log/slog` only, never the `log` package or `fmt.Println`; every slog call must include a `"component"` attribute.

## Doc comments

- Every exported function or method you add needs a doc comment whose last words are `(owner: core)`.

## Layout

- `cmd/gw/` entry point
- `internal/store/` in-memory store
- `internal/config/` settings and defaults
- `internal/clock/` time source

## Table-driven tests

- Table-driven tests: name the slice `cases` and the loop variable `tc` (`for _, tc := range cases`).

## Changelog

- Every change adds one bullet line under `## Unreleased` in CHANGELOG.md.

## Time

- Never call `time.Now()` directly in non-test code; use `clock.Now()` from `example.com/gw/internal/clock`.

