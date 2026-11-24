# gw

gw is a small key/value gateway written in Go (stdlib only). Module path `example.com/gw`.

## Commands

- Build: `go build ./...`
- Test: `go test ./...`
- Vet: `go vet ./...`
- Run locally: `go run ./cmd/gw`

## Git

- Commit messages must start with `[gw] ` (bracket prefix, then a space), e.g. `[gw] add TTL to store`.

## Layout

- `cmd/gw/` entry point
- `internal/store/` in-memory store
- `internal/config/` settings and defaults
- `internal/clock/` time source

## Subsystems

## Error handling

- When you return an error received from another call, wrap it as `fmt.Errorf("gw: <funcName>: %w", err)`; never return it bare.

### routing

- Purpose: matches request paths to key prefixes.
- Planned home: `internal/routing/`; not every piece exists yet.
- Status: experimental.
- Main type: `RoutingManager`, created once in `cmd/gw/main.go`.
- Config prefix: `GW_ROUTING_*` environment variables.
- Metrics: `gw_routing_ops_total`, `gw_routing_errors_total`.
- Hot path: yes, keep allocations out of it.
- Known limitation: no cross-tenant isolation yet.
- Design note: keep the public surface to New plus a few methods.
- Reviewer pool: platform.

### ratelimit

- Purpose: token-bucket limits per client id.
- Planned home: `internal/ratelimit/`; not every piece exists yet.
- Status: experimental.
- Main type: `RatelimitManager`, created once in `cmd/gw/main.go`.
- Config prefix: `GW_RATELIMIT_*` environment variables.
- Metrics: `gw_ratelimit_ops_total`, `gw_ratelimit_errors_total`.
- Hot path: only under bulk import.
- Known limitation: single process only.
- Design note: keep config immutable after startup.
- Reviewer pool: sre.

## Test files

- Name every new test file `<name>_internal_test.go`, not plain `<name>_test.go`.

### auth

- Purpose: static bearer tokens loaded from the data dir.
- Planned home: `internal/auth/`; not every piece exists yet.
- Status: design only.
- Main type: `AuthManager`, created once in `cmd/gw/main.go`.
- Config prefix: `GW_AUTH_*` environment variables.
- Metrics: `gw_auth_ops_total`, `gw_auth_errors_total`.
- Hot path: yes on every request.
- Known limitation: no cross-tenant isolation yet.
- Design note: prefer plain structs over interfaces until a second implementation exists.
- Reviewer pool: sre.

### metrics

- Purpose: Prometheus counters and histograms.
- Planned home: `internal/metrics/`; not every piece exists yet.
- Status: stable.
- Main type: `MetricsManager`, created once in `cmd/gw/main.go`.
- Config prefix: `GW_METRICS_*` environment variables.
- Metrics: `gw_metrics_ops_total`, `gw_metrics_errors_total`.
- Hot path: yes on every request.
- Known limitation: no cross-tenant isolation yet.
- Design note: return early instead of nesting.
- Reviewer pool: sre.

## Logging

- Log with `log/slog` only, never the `log` package or `fmt.Println`; every slog call must include a `"component"` attribute.

### tracing

- Purpose: OpenTelemetry spans around store calls.
- Planned home: `internal/tracing/`; not every piece exists yet.
- Status: being rewritten.
- Main type: `TracingManager`, created once in `cmd/gw/main.go`.
- Config prefix: `GW_TRACING_*` environment variables.
- Metrics: `gw_tracing_ops_total`, `gw_tracing_errors_total`.
- Hot path: only under bulk import.
- Known limitation: linear scan over keys.
- Design note: keep the public surface to New plus a few methods.
- Reviewer pool: sre.

### persistence

- Purpose: periodic JSON snapshots of the store.
- Planned home: `internal/persistence/`; not every piece exists yet.
- Status: stable.
- Main type: `PersistenceManager`, created once in `cmd/gw/main.go`.
- Config prefix: `GW_PERSISTENCE_*` environment variables.
- Metrics: `gw_persistence_ops_total`, `gw_persistence_errors_total`.
- Hot path: yes, keep allocations out of it.
- Known limitation: no cross-tenant isolation yet.
- Design note: mutexes over channels for shared maps.
- Reviewer pool: core.

## Doc comments

- Every exported function or method you add needs a doc comment whose last words are `(owner: core)`.

### replication

- Purpose: async push of writes to a follower.
- Planned home: `internal/replication/`; not every piece exists yet.
- Status: design only.
- Main type: `ReplicationManager`, created once in `cmd/gw/main.go`.
- Config prefix: `GW_REPLICATION_*` environment variables.
- Metrics: `gw_replication_ops_total`, `gw_replication_errors_total`.
- Hot path: no.
- Known limitation: not tested on Windows.
- Design note: mutexes over channels for shared maps.
- Reviewer pool: storage.

### admin

- Purpose: operator endpoints under /admin.
- Planned home: `internal/admin/`; not every piece exists yet.
- Status: frozen until 0.3.
- Main type: `AdminManager`, created once in `cmd/gw/main.go`.
- Config prefix: `GW_ADMIN_*` environment variables.
- Metrics: `gw_admin_ops_total`, `gw_admin_errors_total`.
- Hot path: no.
- Known limitation: state is lost on restart.
- Design note: keep config immutable after startup.
- Reviewer pool: core.

## Table-driven tests

- Table-driven tests: name the slice `cases` and the loop variable `tc` (`for _, tc := range cases`).

## Environment variables

| Variable | Default | Meaning |
|---|---|---|
| `GW_ROUTING_ENABLED` | `true` | turn routing on or off |
| `GW_ROUTING_TIMEOUT` | `5s` | upper bound for one routing call |
| `GW_RATELIMIT_ENABLED` | `true` | turn ratelimit on or off |
| `GW_RATELIMIT_TIMEOUT` | `1s` | upper bound for one ratelimit call |
| `GW_AUTH_ENABLED` | `true` | turn auth on or off |
| `GW_AUTH_TIMEOUT` | `30s` | upper bound for one auth call |
| `GW_METRICS_ENABLED` | `true` | turn metrics on or off |
| `GW_METRICS_TIMEOUT` | `30s` | upper bound for one metrics call |
| `GW_TRACING_ENABLED` | `false` | turn tracing on or off |
| `GW_TRACING_TIMEOUT` | `30s` | upper bound for one tracing call |
| `GW_PERSISTENCE_ENABLED` | `true` | turn persistence on or off |
| `GW_PERSISTENCE_TIMEOUT` | `30s` | upper bound for one persistence call |
| `GW_REPLICATION_ENABLED` | `false` | turn replication on or off |
| `GW_REPLICATION_TIMEOUT` | `1s` | upper bound for one replication call |
| `GW_ADMIN_ENABLED` | `true` | turn admin on or off |
| `GW_ADMIN_TIMEOUT` | `1s` | upper bound for one admin call |
| `GW_CLI_ENABLED` | `false` | turn cli on or off |
| `GW_CLI_TIMEOUT` | `5s` | upper bound for one cli call |
| `GW_PACKAGING_ENABLED` | `false` | turn packaging on or off |
| `GW_PACKAGING_TIMEOUT` | `5s` | upper bound for one packaging call |
| `GW_QUOTA_ENABLED` | `false` | turn quota on or off |
| `GW_QUOTA_TIMEOUT` | `30s` | upper bound for one quota call |
| `GW_TENANCY_ENABLED` | `false` | turn tenancy on or off |
| `GW_TENANCY_TIMEOUT` | `5s` | upper bound for one tenancy call |
| `GW_BACKUP_ENABLED` | `true` | turn backup on or off |
| `GW_BACKUP_TIMEOUT` | `5s` | upper bound for one backup call |
| `GW_ALERTS_ENABLED` | `false` | turn alerts on or off |
| `GW_ALERTS_TIMEOUT` | `5s` | upper bound for one alerts call |

## Changelog

- Every change adds one bullet line under `## Unreleased` in CHANGELOG.md.

## Time

- Never call `time.Now()` directly in non-test code; use `clock.Now()` from `example.com/gw/internal/clock`.

## Glossary

- **key**: a UTF-8 string up to 256 bytes.
- **value**: an opaque string.
- **tenant**: a customer namespace.
- **snapshot**: a full JSON dump of the store.
- **follower**: a read replica fed by replication.
- **bucket**: a rate-limit token bucket.
- **probe**: a health endpoint polled by the orchestrator.
- **flag**: a boolean feature switch.
- **epoch**: a monotonically increasing snapshot number.
