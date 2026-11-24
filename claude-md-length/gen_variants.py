#!/usr/bin/env python3
"""Generate CLAUDE.md variants of different lengths that carry the same 8 rules.

Usage: gen_variants.py OUTDIR
Writes OUTDIR/claude-50.md, claude-200.md, claude-500.md, claude-1500.md,
claude-500-buried.md (same rules hidden inside bullet lists), the 450-line filler
used by the @import variant (import-main.md + import-filler.md), and rules.json.
The filler is synthetic but shaped like a real project file: overview, commands,
subsystem notes, env vars, glossary, runbook. It never contradicts a rule.
"""
import json
import os
import random
import sys

HEADINGS = {"R1": "Git", "R2": "Error handling", "R3": "Test files", "R4": "Logging",
            "R5": "Doc comments", "R6": "Table-driven tests", "R7": "Changelog", "R8": "Time"}
RULES = [
    ("R1", "Commit messages must start with `[gw] ` (bracket prefix, then a space), e.g. `[gw] add TTL to store`."),
    ("R2", "When you return an error received from another call, wrap it as `fmt.Errorf(\"gw: <funcName>: %w\", err)`; never return it bare."),
    ("R3", "Name every new test file `<name>_internal_test.go`, not plain `<name>_test.go`."),
    ("R4", "Log with `log/slog` only, never the `log` package or `fmt.Println`; every slog call must include a `\"component\"` attribute."),
    ("R5", "Every exported function or method you add needs a doc comment whose last words are `(owner: core)`."),
    ("R6", "Table-driven tests: name the slice `cases` and the loop variable `tc` (`for _, tc := range cases`)."),
    ("R7", "Every change adds one bullet line under `## Unreleased` in CHANGELOG.md."),
    ("R8", "Never call `time.Now()` directly in non-test code; use `clock.Now()` from `example.com/gw/internal/clock`."),
]
# relative depth of each rule inside the file (0 = first line, 1 = last line)
DEPTH = {"R1": 0.06, "R2": 0.12, "R3": 0.28, "R4": 0.45, "R5": 0.55, "R6": 0.72, "R7": 0.88, "R8": 0.95}

SUBSYSTEMS = [
    ("routing", "matches request paths to key prefixes"),
    ("ratelimit", "token-bucket limits per client id"),
    ("auth", "static bearer tokens loaded from the data dir"),
    ("metrics", "Prometheus counters and histograms"),
    ("tracing", "OpenTelemetry spans around store calls"),
    ("persistence", "periodic JSON snapshots of the store"),
    ("replication", "async push of writes to a follower"),
    ("admin", "operator endpoints under /admin"),
    ("cli", "the gwctl command line client"),
    ("packaging", "container image and systemd unit"),
    ("quota", "per-tenant key count limits"),
    ("tenancy", "tenant id extraction from headers"),
    ("backup", "nightly snapshot upload"),
    ("alerts", "alert rules shipped with the chart"),
    ("featureflags", "boolean flags read at startup"),
    ("migrations", "snapshot format upgrades"),
    ("fuzzing", "go-fuzz corpora for the parser"),
    ("benchmarks", "store and handler micro benchmarks"),
    ("security", "threat model and hardening notes"),
    ("docs", "operator guide and API reference"),
    ("release", "tagging and changelog flow"),
    ("ci", "lint, test and build jobs"),
    ("compaction", "removal of expired keys"),
    ("ttl", "per-key expiry bookkeeping"),
    ("healthz", "liveness and readiness probes"),
    ("config", "loading and validating settings"),
    ("dashboards", "Grafana boards for operators"),
    ("oncall", "pager rotation and escalation"),
]

FACT_TEMPLATES = [
    "- Purpose: {desc}.",
    "- Planned home: `internal/{name}/`; not every piece exists yet.",
    "- Status: {status}.",
    "- Main type: `{Title}Manager`, created once in `cmd/gw/main.go`.",
    "- Config prefix: `GW_{NAME}_*` environment variables.",
    "- Metrics: `gw_{name}_ops_total`, `gw_{name}_errors_total`.",
    "- Hot path: {hot}.",
    "- Known limitation: {limit}.",
    "- Design note: {design}.",
    "- Reviewer pool: {reviewers}.",
]
STATUS = ["stable", "experimental", "design only", "being rewritten", "frozen until 0.3"]
HOT = ["yes, keep allocations out of it", "no", "only under bulk import", "yes on every request"]
LIMIT = ["single process only", "no cross-tenant isolation yet", "linear scan over keys",
         "state is lost on restart", "not tested on Windows", "no backpressure"]
DESIGN = ["prefer plain structs over interfaces until a second implementation exists",
          "keep the public surface to New plus a few methods",
          "mutexes over channels for shared maps",
          "keep config immutable after startup",
          "return early instead of nesting",
          "accept interfaces, return concrete types"]
REVIEWERS = ["core", "platform", "storage", "sre", "core and sre"]


def subsystem_section(rng, name, desc):
    lines = [f"### {name}", ""]
    for t in FACT_TEMPLATES:
        lines.append(t.format(name=name, NAME=name.upper(), Title=name.capitalize(), desc=desc,
                              status=rng.choice(STATUS), hot=rng.choice(HOT), limit=rng.choice(LIMIT),
                              design=rng.choice(DESIGN), reviewers=rng.choice(REVIEWERS)))
    lines.append("")
    return lines


def head():
    return [
        "# gw",
        "",
        "gw is a small key/value gateway written in Go (stdlib only). Module path `example.com/gw`.",
        "",
    ]


def commands():
    return [
        "## Commands",
        "",
        "- Build: `go build ./...`",
        "- Test: `go test ./...`",
        "- Vet: `go vet ./...`",
        "- Run locally: `go run ./cmd/gw`",
        "",
    ]


def layout():
    return [
        "## Layout",
        "",
        "- `cmd/gw/` entry point",
        "- `internal/store/` in-memory store",
        "- `internal/config/` settings and defaults",
        "- `internal/clock/` time source",
        "",
    ]


def env_table(rng, n):
    lines = ["## Environment variables", "", "| Variable | Default | Meaning |", "|---|---|---|"]
    for name, desc in SUBSYSTEMS[:n]:
        lines.append(f"| `GW_{name.upper()}_ENABLED` | `{rng.choice(['true', 'false'])}` | turn {name} on or off |")
        lines.append(f"| `GW_{name.upper()}_TIMEOUT` | `{rng.choice(['1s', '5s', '30s'])}` | upper bound for one {name} call |")
    lines.append("")
    return lines


def glossary(n):
    words = [("key", "a UTF-8 string up to 256 bytes"), ("value", "an opaque string"),
             ("tenant", "a customer namespace"), ("snapshot", "a full JSON dump of the store"),
             ("follower", "a read replica fed by replication"), ("bucket", "a rate-limit token bucket"),
             ("probe", "a health endpoint polled by the orchestrator"), ("flag", "a boolean feature switch"),
             ("epoch", "a monotonically increasing snapshot number"), ("lease", "a time-bound ownership claim"),
             ("shard", "a future split of the key space"), ("op", "one store call"),
             ("quota", "max keys per tenant"), ("drain", "graceful shutdown phase"),
             ("compaction", "removal of expired keys"), ("tombstone", "a marker for deleted keys")]
    lines = ["## Glossary", ""]
    for w, d in words[:n]:
        lines.append(f"- **{w}**: {d}.")
    lines.append("")
    return lines


def runbook():
    steps = [
        "Check `/healthz` returns 200.",
        "Check the error counter for the failing subsystem.",
        "Look at the last snapshot epoch in the admin endpoint.",
        "If the follower lags, restart replication, not the leader.",
        "If memory grows, compare key count with the tenant quota.",
        "If latency rises, look at the store mutex wait histogram.",
        "If auth fails for everyone, check the token file timestamp.",
        "Escalate to the storage reviewers if snapshots fail twice.",
        "Write a short incident note in docs/incidents/.",
        "Never edit snapshot files by hand.",
    ]
    return ["## Runbook", ""] + [f"{i + 1}. {s}" for i, s in enumerate(steps)] + [""]


def decision_log(rng, n):
    lines = ["## Decision log", ""]
    for i in range(n):
        if n > 100 and i and i % 50 == 0:  # only the 1500-line variant gets sub-headings
            lines += ["", f"### Decisions, part {i // 50 + 1}", ""]
        name, desc = SUBSYSTEMS[i % len(SUBSYSTEMS)]
        month, day = 1 + (i * 7) % 12, 1 + (i * 11) % 28
        lines.append(f"- 2026-{month:02d}-{day:02d} {name}: {rng.choice(DESIGN)} ({rng.choice(STATUS)}).")
    lines.append("")
    return lines


def filler(rng, target):
    """Return filler lines, roughly `target` long."""
    lines = head() + commands() + layout()
    if target > 60:
        lines += ["## Subsystems", ""]
        i = 0
        while len(lines) < target * 0.62 and i < len(SUBSYSTEMS):
            lines += subsystem_section(rng, *SUBSYSTEMS[i])
            i += 1
        lines += env_table(rng, min(len(SUBSYSTEMS), max(4, int(target * 0.07))))
        lines += glossary(16)
        lines += runbook()
        lines += decision_log(rng, max(4, target - len(RULES) * 4 - len(lines) - 2))
    else:
        lines += ["## Notes", ""]
        lines += [f"- {d.capitalize()}: see `internal/{n}/` when it lands." for n, d in SUBSYSTEMS[:max(0, target - len(lines) - 12)]]
        lines.append("")
    return lines[:max(target - len(RULES) * 4, 10)]


def with_rules(lines):
    """Insert each rule as its own small section at a fixed relative depth.

    Sections are only inserted at a heading boundary so a rule never reads as
    part of an unrelated subsystem note. Returns the lines and each rule's line number.
    """
    out = list(lines)
    total = len(out) + len(RULES) * 4
    for rid, text in sorted(RULES, key=lambda r: DEPTH[r[0]]):
        want = DEPTH[rid] * total
        bounds = [i for i, l in enumerate(out) if l.startswith("#") and i > 2] + [len(out)]
        idx = min(bounds, key=lambda i: abs(i - want))
        out[idx:idx] = [f"## {HEADINGS[rid]}", "", f"- {text}", ""]
    positions = {}
    for n, l in enumerate(out, 1):
        for rid, text in RULES:
            if l == f"- {text}":
                positions[rid] = n
    return out, positions


def buried(lines):
    """Insert each rule as one more bullet inside an existing list, with no heading of its own."""
    out = list(lines)
    total = len(out) + len(RULES)
    for rid, text in sorted(RULES, key=lambda r: DEPTH[r[0]]):
        want = DEPTH[rid] * total
        spots = [i for i in range(1, len(out)) if out[i - 1].startswith("- ") and out[i].startswith("- ")]
        idx = min(spots, key=lambda i: abs(i - want))
        out.insert(idx, f"- {text}")
    positions = {rid: out.index(f"- {text}") + 1 for rid, text in RULES}
    return out, positions


def main():
    outdir = sys.argv[1]
    os.makedirs(outdir, exist_ok=True)
    meta = {}
    for target in (50, 200, 500, 1500):
        rng = random.Random(target)
        lines, pos = with_rules(filler(rng, target))
        path = os.path.join(outdir, f"claude-{target}.md")
        with open(path, "w") as f:
            f.write("\n".join(lines) + "\n")
        meta[f"claude-{target}"] = {"lines": len(lines), "bytes": os.path.getsize(path), "rule_line": pos}
    # same 500-line filler, but the rules hide inside subsystem bullet lists
    lines, pos = buried(filler(random.Random(500), 500))
    path = os.path.join(outdir, "claude-500-buried.md")
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")
    meta["claude-500-buried"] = {"lines": len(lines), "bytes": os.path.getsize(path), "rule_line": pos}
    # @import variant: the 500-line content split into a short main file plus an imported filler file.
    rng = random.Random(500)
    big = filler(rng, 500)
    small, pos = with_rules(filler(random.Random(50), 50))
    imported = big[len(head()) + len(commands()) + len(layout()):]
    with open(os.path.join(outdir, "import-main.md"), "w") as f:
        f.write("\n".join(small + ["", "Subsystem notes: @docs/subsystems.md"]) + "\n")
    with open(os.path.join(outdir, "import-filler.md"), "w") as f:
        f.write("\n".join(imported) + "\n")
    meta["import"] = {"main_lines": len(small) + 2, "imported_lines": len(imported), "rule_line": pos}
    with open(os.path.join(outdir, "rules.json"), "w") as f:
        json.dump({"rules": dict(RULES), "variants": meta}, f, indent=2)
    print(json.dumps(meta, indent=2))


if __name__ == "__main__":
    main()
