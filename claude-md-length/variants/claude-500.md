# gw

gw is a small key/value gateway written in Go (stdlib only). Module path `example.com/gw`.

## Commands

- Build: `go build ./...`
- Test: `go test ./...`
- Vet: `go vet ./...`
- Run locally: `go run ./cmd/gw`

## Layout

- `cmd/gw/` entry point
- `internal/store/` in-memory store
- `internal/config/` settings and defaults
- `internal/clock/` time source

## Subsystems

### routing

- Purpose: matches request paths to key prefixes.
- Planned home: `internal/routing/`; not every piece exists yet.
- Status: stable.
- Main type: `RoutingManager`, created once in `cmd/gw/main.go`.
- Config prefix: `GW_ROUTING_*` environment variables.
- Metrics: `gw_routing_ops_total`, `gw_routing_errors_total`.
- Hot path: only under bulk import.
- Known limitation: not tested on Windows.
- Design note: keep the public surface to New plus a few methods.
- Reviewer pool: platform.

## Git

- Commit messages must start with `[gw] ` (bracket prefix, then a space), e.g. `[gw] add TTL to store`.

### ratelimit

- Purpose: token-bucket limits per client id.
- Planned home: `internal/ratelimit/`; not every piece exists yet.
- Status: design only.
- Main type: `RatelimitManager`, created once in `cmd/gw/main.go`.
- Config prefix: `GW_RATELIMIT_*` environment variables.
- Metrics: `gw_ratelimit_ops_total`, `gw_ratelimit_errors_total`.
- Hot path: yes, keep allocations out of it.
- Known limitation: no backpressure.
- Design note: keep config immutable after startup.
- Reviewer pool: sre.

### auth

- Purpose: static bearer tokens loaded from the data dir.
- Planned home: `internal/auth/`; not every piece exists yet.
- Status: being rewritten.
- Main type: `AuthManager`, created once in `cmd/gw/main.go`.
- Config prefix: `GW_AUTH_*` environment variables.
- Metrics: `gw_auth_ops_total`, `gw_auth_errors_total`.
- Hot path: yes on every request.
- Known limitation: not tested on Windows.
- Design note: keep the public surface to New plus a few methods.
- Reviewer pool: core.

## Error handling

- When you return an error received from another call, wrap it as `fmt.Errorf("gw: <funcName>: %w", err)`; never return it bare.

### metrics

- Purpose: Prometheus counters and histograms.
- Planned home: `internal/metrics/`; not every piece exists yet.
- Status: experimental.
- Main type: `MetricsManager`, created once in `cmd/gw/main.go`.
- Config prefix: `GW_METRICS_*` environment variables.
- Metrics: `gw_metrics_ops_total`, `gw_metrics_errors_total`.
- Hot path: yes, keep allocations out of it.
- Known limitation: state is lost on restart.
- Design note: prefer plain structs over interfaces until a second implementation exists.
- Reviewer pool: storage.

### tracing

- Purpose: OpenTelemetry spans around store calls.
- Planned home: `internal/tracing/`; not every piece exists yet.
- Status: frozen until 0.3.
- Main type: `TracingManager`, created once in `cmd/gw/main.go`.
- Config prefix: `GW_TRACING_*` environment variables.
- Metrics: `gw_tracing_ops_total`, `gw_tracing_errors_total`.
- Hot path: only under bulk import.
- Known limitation: linear scan over keys.
- Design note: prefer plain structs over interfaces until a second implementation exists.
- Reviewer pool: platform.

### persistence

- Purpose: periodic JSON snapshots of the store.
- Planned home: `internal/persistence/`; not every piece exists yet.
- Status: design only.
- Main type: `PersistenceManager`, created once in `cmd/gw/main.go`.
- Config prefix: `GW_PERSISTENCE_*` environment variables.
- Metrics: `gw_persistence_ops_total`, `gw_persistence_errors_total`.
- Hot path: yes on every request.
- Known limitation: no backpressure.
- Design note: prefer plain structs over interfaces until a second implementation exists.
- Reviewer pool: storage.

### replication

- Purpose: async push of writes to a follower.
- Planned home: `internal/replication/`; not every piece exists yet.
- Status: design only.
- Main type: `ReplicationManager`, created once in `cmd/gw/main.go`.
- Config prefix: `GW_REPLICATION_*` environment variables.
- Metrics: `gw_replication_ops_total`, `gw_replication_errors_total`.
- Hot path: yes on every request.
- Known limitation: state is lost on restart.
- Design note: mutexes over channels for shared maps.
- Reviewer pool: core.

### admin

- Purpose: operator endpoints under /admin.
- Planned home: `internal/admin/`; not every piece exists yet.
- Status: being rewritten.
- Main type: `AdminManager`, created once in `cmd/gw/main.go`.
- Config prefix: `GW_ADMIN_*` environment variables.
- Metrics: `gw_admin_ops_total`, `gw_admin_errors_total`.
- Hot path: yes, keep allocations out of it.
- Known limitation: no backpressure.
- Design note: prefer plain structs over interfaces until a second implementation exists.
- Reviewer pool: core and sre.

### cli

- Purpose: the gwctl command line client.
- Planned home: `internal/cli/`; not every piece exists yet.
- Status: frozen until 0.3.
- Main type: `CliManager`, created once in `cmd/gw/main.go`.
- Config prefix: `GW_CLI_*` environment variables.
- Metrics: `gw_cli_ops_total`, `gw_cli_errors_total`.
- Hot path: only under bulk import.
- Known limitation: linear scan over keys.
- Design note: keep the public surface to New plus a few methods.
- Reviewer pool: sre.

## Test files

- Name every new test file `<name>_internal_test.go`, not plain `<name>_test.go`.

### packaging

- Purpose: container image and systemd unit.
- Planned home: `internal/packaging/`; not every piece exists yet.
- Status: frozen until 0.3.
- Main type: `PackagingManager`, created once in `cmd/gw/main.go`.
- Config prefix: `GW_PACKAGING_*` environment variables.
- Metrics: `gw_packaging_ops_total`, `gw_packaging_errors_total`.
- Hot path: yes on every request.
- Known limitation: single process only.
- Design note: return early instead of nesting.
- Reviewer pool: core and sre.

### quota

- Purpose: per-tenant key count limits.
- Planned home: `internal/quota/`; not every piece exists yet.
- Status: frozen until 0.3.
- Main type: `QuotaManager`, created once in `cmd/gw/main.go`.
- Config prefix: `GW_QUOTA_*` environment variables.
- Metrics: `gw_quota_ops_total`, `gw_quota_errors_total`.
- Hot path: yes, keep allocations out of it.
- Known limitation: no backpressure.
- Design note: keep the public surface to New plus a few methods.
- Reviewer pool: platform.

### tenancy

- Purpose: tenant id extraction from headers.
- Planned home: `internal/tenancy/`; not every piece exists yet.
- Status: frozen until 0.3.
- Main type: `TenancyManager`, created once in `cmd/gw/main.go`.
- Config prefix: `GW_TENANCY_*` environment variables.
- Metrics: `gw_tenancy_ops_total`, `gw_tenancy_errors_total`.
- Hot path: no.
- Known limitation: not tested on Windows.
- Design note: keep the public surface to New plus a few methods.
- Reviewer pool: core and sre.

### backup

- Purpose: nightly snapshot upload.
- Planned home: `internal/backup/`; not every piece exists yet.
- Status: experimental.
- Main type: `BackupManager`, created once in `cmd/gw/main.go`.
- Config prefix: `GW_BACKUP_*` environment variables.
- Metrics: `gw_backup_ops_total`, `gw_backup_errors_total`.
- Hot path: no.
- Known limitation: state is lost on restart.
- Design note: mutexes over channels for shared maps.
- Reviewer pool: core.

### alerts

- Purpose: alert rules shipped with the chart.
- Planned home: `internal/alerts/`; not every piece exists yet.
- Status: frozen until 0.3.
- Main type: `AlertsManager`, created once in `cmd/gw/main.go`.
- Config prefix: `GW_ALERTS_*` environment variables.
- Metrics: `gw_alerts_ops_total`, `gw_alerts_errors_total`.
- Hot path: yes, keep allocations out of it.
- Known limitation: state is lost on restart.
- Design note: return early instead of nesting.
- Reviewer pool: storage.

### featureflags

- Purpose: boolean flags read at startup.
- Planned home: `internal/featureflags/`; not every piece exists yet.
- Status: experimental.
- Main type: `FeatureflagsManager`, created once in `cmd/gw/main.go`.
- Config prefix: `GW_FEATUREFLAGS_*` environment variables.
- Metrics: `gw_featureflags_ops_total`, `gw_featureflags_errors_total`.
- Hot path: only under bulk import.
- Known limitation: state is lost on restart.
- Design note: accept interfaces, return concrete types.
- Reviewer pool: platform.

## Logging

- Log with `log/slog` only, never the `log` package or `fmt.Println`; every slog call must include a `"component"` attribute.

### migrations

- Purpose: snapshot format upgrades.
- Planned home: `internal/migrations/`; not every piece exists yet.
- Status: experimental.
- Main type: `MigrationsManager`, created once in `cmd/gw/main.go`.
- Config prefix: `GW_MIGRATIONS_*` environment variables.
- Metrics: `gw_migrations_ops_total`, `gw_migrations_errors_total`.
- Hot path: yes, keep allocations out of it.
- Known limitation: linear scan over keys.
- Design note: keep the public surface to New plus a few methods.
- Reviewer pool: core.

### fuzzing

- Purpose: go-fuzz corpora for the parser.
- Planned home: `internal/fuzzing/`; not every piece exists yet.
- Status: being rewritten.
- Main type: `FuzzingManager`, created once in `cmd/gw/main.go`.
- Config prefix: `GW_FUZZING_*` environment variables.
- Metrics: `gw_fuzzing_ops_total`, `gw_fuzzing_errors_total`.
- Hot path: yes, keep allocations out of it.
- Known limitation: state is lost on restart.
- Design note: accept interfaces, return concrete types.
- Reviewer pool: sre.

### benchmarks

- Purpose: store and handler micro benchmarks.
- Planned home: `internal/benchmarks/`; not every piece exists yet.
- Status: experimental.
- Main type: `BenchmarksManager`, created once in `cmd/gw/main.go`.
- Config prefix: `GW_BENCHMARKS_*` environment variables.
- Metrics: `gw_benchmarks_ops_total`, `gw_benchmarks_errors_total`.
- Hot path: yes on every request.
- Known limitation: no backpressure.
- Design note: mutexes over channels for shared maps.
- Reviewer pool: sre.

## Doc comments

- Every exported function or method you add needs a doc comment whose last words are `(owner: core)`.

### security

- Purpose: threat model and hardening notes.
- Planned home: `internal/security/`; not every piece exists yet.
- Status: experimental.
- Main type: `SecurityManager`, created once in `cmd/gw/main.go`.
- Config prefix: `GW_SECURITY_*` environment variables.
- Metrics: `gw_security_ops_total`, `gw_security_errors_total`.
- Hot path: yes on every request.
- Known limitation: state is lost on restart.
- Design note: accept interfaces, return concrete types.
- Reviewer pool: core and sre.

### docs

- Purpose: operator guide and API reference.
- Planned home: `internal/docs/`; not every piece exists yet.
- Status: design only.
- Main type: `DocsManager`, created once in `cmd/gw/main.go`.
- Config prefix: `GW_DOCS_*` environment variables.
- Metrics: `gw_docs_ops_total`, `gw_docs_errors_total`.
- Hot path: only under bulk import.
- Known limitation: not tested on Windows.
- Design note: return early instead of nesting.
- Reviewer pool: sre.

### release

- Purpose: tagging and changelog flow.
- Planned home: `internal/release/`; not every piece exists yet.
- Status: experimental.
- Main type: `ReleaseManager`, created once in `cmd/gw/main.go`.
- Config prefix: `GW_RELEASE_*` environment variables.
- Metrics: `gw_release_ops_total`, `gw_release_errors_total`.
- Hot path: only under bulk import.
- Known limitation: linear scan over keys.
- Design note: accept interfaces, return concrete types.
- Reviewer pool: core and sre.

### ci

- Purpose: lint, test and build jobs.
- Planned home: `internal/ci/`; not every piece exists yet.
- Status: experimental.
- Main type: `CiManager`, created once in `cmd/gw/main.go`.
- Config prefix: `GW_CI_*` environment variables.
- Metrics: `gw_ci_ops_total`, `gw_ci_errors_total`.
- Hot path: only under bulk import.
- Known limitation: linear scan over keys.
- Design note: accept interfaces, return concrete types.
- Reviewer pool: storage.

### compaction

- Purpose: removal of expired keys.
- Planned home: `internal/compaction/`; not every piece exists yet.
- Status: experimental.
- Main type: `CompactionManager`, created once in `cmd/gw/main.go`.
- Config prefix: `GW_COMPACTION_*` environment variables.
- Metrics: `gw_compaction_ops_total`, `gw_compaction_errors_total`.
- Hot path: yes on every request.
- Known limitation: state is lost on restart.
- Design note: prefer plain structs over interfaces until a second implementation exists.
- Reviewer pool: core.

## Table-driven tests

- Table-driven tests: name the slice `cases` and the loop variable `tc` (`for _, tc := range cases`).

## Environment variables

| Variable | Default | Meaning |
|---|---|---|
| `GW_ROUTING_ENABLED` | `true` | turn routing on or off |
| `GW_ROUTING_TIMEOUT` | `1s` | upper bound for one routing call |
| `GW_RATELIMIT_ENABLED` | `false` | turn ratelimit on or off |
| `GW_RATELIMIT_TIMEOUT` | `5s` | upper bound for one ratelimit call |
| `GW_AUTH_ENABLED` | `false` | turn auth on or off |
| `GW_AUTH_TIMEOUT` | `1s` | upper bound for one auth call |
| `GW_METRICS_ENABLED` | `false` | turn metrics on or off |
| `GW_METRICS_TIMEOUT` | `30s` | upper bound for one metrics call |
| `GW_TRACING_ENABLED` | `true` | turn tracing on or off |
| `GW_TRACING_TIMEOUT` | `30s` | upper bound for one tracing call |
| `GW_PERSISTENCE_ENABLED` | `false` | turn persistence on or off |
| `GW_PERSISTENCE_TIMEOUT` | `5s` | upper bound for one persistence call |
| `GW_REPLICATION_ENABLED` | `true` | turn replication on or off |
| `GW_REPLICATION_TIMEOUT` | `1s` | upper bound for one replication call |
| `GW_ADMIN_ENABLED` | `false` | turn admin on or off |
| `GW_ADMIN_TIMEOUT` | `5s` | upper bound for one admin call |
| `GW_CLI_ENABLED` | `true` | turn cli on or off |
| `GW_CLI_TIMEOUT` | `30s` | upper bound for one cli call |
| `GW_PACKAGING_ENABLED` | `false` | turn packaging on or off |
| `GW_PACKAGING_TIMEOUT` | `5s` | upper bound for one packaging call |
| `GW_QUOTA_ENABLED` | `false` | turn quota on or off |
| `GW_QUOTA_TIMEOUT` | `1s` | upper bound for one quota call |
| `GW_TENANCY_ENABLED` | `true` | turn tenancy on or off |
| `GW_TENANCY_TIMEOUT` | `1s` | upper bound for one tenancy call |
| `GW_BACKUP_ENABLED` | `true` | turn backup on or off |
| `GW_BACKUP_TIMEOUT` | `1s` | upper bound for one backup call |
| `GW_ALERTS_ENABLED` | `false` | turn alerts on or off |
| `GW_ALERTS_TIMEOUT` | `1s` | upper bound for one alerts call |
| `GW_FEATUREFLAGS_ENABLED` | `true` | turn featureflags on or off |
| `GW_FEATUREFLAGS_TIMEOUT` | `1s` | upper bound for one featureflags call |
| `GW_MIGRATIONS_ENABLED` | `true` | turn migrations on or off |
| `GW_MIGRATIONS_TIMEOUT` | `30s` | upper bound for one migrations call |
| `GW_FUZZING_ENABLED` | `false` | turn fuzzing on or off |
| `GW_FUZZING_TIMEOUT` | `1s` | upper bound for one fuzzing call |
| `GW_BENCHMARKS_ENABLED` | `true` | turn benchmarks on or off |
| `GW_BENCHMARKS_TIMEOUT` | `30s` | upper bound for one benchmarks call |
| `GW_SECURITY_ENABLED` | `true` | turn security on or off |
| `GW_SECURITY_TIMEOUT` | `5s` | upper bound for one security call |
| `GW_DOCS_ENABLED` | `true` | turn docs on or off |
| `GW_DOCS_TIMEOUT` | `5s` | upper bound for one docs call |
| `GW_RELEASE_ENABLED` | `true` | turn release on or off |
| `GW_RELEASE_TIMEOUT` | `30s` | upper bound for one release call |
| `GW_CI_ENABLED` | `false` | turn ci on or off |
| `GW_CI_TIMEOUT` | `5s` | upper bound for one ci call |
| `GW_COMPACTION_ENABLED` | `true` | turn compaction on or off |
| `GW_COMPACTION_TIMEOUT` | `1s` | upper bound for one compaction call |
| `GW_TTL_ENABLED` | `false` | turn ttl on or off |
| `GW_TTL_TIMEOUT` | `5s` | upper bound for one ttl call |
| `GW_HEALTHZ_ENABLED` | `true` | turn healthz on or off |
| `GW_HEALTHZ_TIMEOUT` | `5s` | upper bound for one healthz call |
| `GW_CONFIG_ENABLED` | `true` | turn config on or off |
| `GW_CONFIG_TIMEOUT` | `30s` | upper bound for one config call |
| `GW_DASHBOARDS_ENABLED` | `true` | turn dashboards on or off |
| `GW_DASHBOARDS_TIMEOUT` | `1s` | upper bound for one dashboards call |
| `GW_ONCALL_ENABLED` | `false` | turn oncall on or off |
| `GW_ONCALL_TIMEOUT` | `1s` | upper bound for one oncall call |

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
- **lease**: a time-bound ownership claim.
- **shard**: a future split of the key space.
- **op**: one store call.
- **quota**: max keys per tenant.
- **drain**: graceful shutdown phase.
- **compaction**: removal of expired keys.
- **tombstone**: a marker for deleted keys.

## Runbook

1. Check `/healthz` returns 200.
2. Check the error counter for the failing subsystem.
3. Look at the last snapshot epoch in the admin endpoint.
4. If the follower lags, restart replication, not the leader.
5. If memory grows, compare key count with the tenant quota.
6. If latency rises, look at the store mutex wait histogram.
7. If auth fails for everyone, check the token file timestamp.
8. Escalate to the storage reviewers if snapshots fail twice.
9. Write a short incident note in docs/incidents/.
10. Never edit snapshot files by hand.

## Changelog

- Every change adds one bullet line under `## Unreleased` in CHANGELOG.md.

## Decision log

- 2026-01-01 routing: return early instead of nesting (frozen until 0.3).
- 2026-08-12 ratelimit: accept interfaces, return concrete types (stable).
- 2026-03-23 auth: accept interfaces, return concrete types (frozen until 0.3).
- 2026-10-06 metrics: prefer plain structs over interfaces until a second implementation exists (frozen until 0.3).
- 2026-05-17 tracing: return early instead of nesting (being rewritten).
- 2026-12-28 persistence: keep the public surface to New plus a few methods (stable).
- 2026-07-11 replication: return early instead of nesting (frozen until 0.3).
- 2026-02-22 admin: keep config immutable after startup (being rewritten).
- 2026-09-05 cli: keep config immutable after startup (experimental).
- 2026-04-16 packaging: return early instead of nesting (stable).
- 2026-11-27 quota: keep config immutable after startup (stable).
- 2026-06-10 tenancy: accept interfaces, return concrete types (frozen until 0.3).
- 2026-01-21 backup: mutexes over channels for shared maps (design only).
- 2026-08-04 alerts: mutexes over channels for shared maps (design only).
- 2026-03-15 featureflags: accept interfaces, return concrete types (design only).
- 2026-10-26 migrations: keep config immutable after startup (frozen until 0.3).
- 2026-05-09 fuzzing: keep config immutable after startup (frozen until 0.3).
- 2026-12-20 benchmarks: keep config immutable after startup (stable).
- 2026-07-03 security: prefer plain structs over interfaces until a second implementation exists (being rewritten).
- 2026-02-14 docs: keep config immutable after startup (frozen until 0.3).
- 2026-09-25 release: accept interfaces, return concrete types (frozen until 0.3).
- 2026-04-08 ci: mutexes over channels for shared maps (being rewritten).
- 2026-11-19 compaction: keep the public surface to New plus a few methods (frozen until 0.3).
- 2026-06-02 ttl: return early instead of nesting (experimental).
- 2026-01-13 healthz: prefer plain structs over interfaces until a second implementation exists (experimental).
- 2026-08-24 config: return early instead of nesting (frozen until 0.3).
- 2026-03-07 dashboards: mutexes over channels for shared maps (design only).
- 2026-10-18 oncall: keep config immutable after startup (experimental).
- 2026-05-01 routing: return early instead of nesting (design only).
- 2026-12-12 ratelimit: mutexes over channels for shared maps (frozen until 0.3).
- 2026-07-23 auth: accept interfaces, return concrete types (design only).
- 2026-02-06 metrics: mutexes over channels for shared maps (experimental).
- 2026-09-17 tracing: return early instead of nesting (design only).
- 2026-04-28 persistence: accept interfaces, return concrete types (experimental).
- 2026-11-11 replication: mutexes over channels for shared maps (design only).
- 2026-06-22 admin: accept interfaces, return concrete types (being rewritten).
- 2026-01-05 cli: keep config immutable after startup (design only).
- 2026-08-16 packaging: prefer plain structs over interfaces until a second implementation exists (design only).
- 2026-03-27 quota: prefer plain structs over interfaces until a second implementation exists (design only).
- 2026-10-10 tenancy: return early instead of nesting (design only).
- 2026-05-21 backup: mutexes over channels for shared maps (frozen until 0.3).
- 2026-12-04 alerts: accept interfaces, return concrete types (being rewritten).
- 2026-07-15 featureflags: mutexes over channels for shared maps (experimental).
- 2026-02-26 migrations: mutexes over channels for shared maps (frozen until 0.3).
- 2026-09-09 fuzzing: return early instead of nesting (stable).
- 2026-04-20 benchmarks: accept interfaces, return concrete types (stable).
- 2026-11-03 security: mutexes over channels for shared maps (frozen until 0.3).
- 2026-06-14 docs: return early instead of nesting (stable).
- 2026-01-25 release: keep the public surface to New plus a few methods (frozen until 0.3).
- 2026-08-08 ci: mutexes over channels for shared maps (design only).
- 2026-03-19 compaction: prefer plain structs over interfaces until a second implementation exists (being rewritten).
- 2026-10-02 ttl: return early instead of nesting (experimental).
- 2026-05-13 healthz: mutexes over channels for shared maps (frozen until 0.3).
- 2026-12-24 config: keep config immutable after startup (being rewritten).
## Time

- Never call `time.Now()` directly in non-test code; use `clock.Now()` from `example.com/gw/internal/clock`.

