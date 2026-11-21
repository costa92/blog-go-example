#!/usr/bin/env python3
"""Validate and summarize numeric experiment output; no third-party packages."""
import json
import statistics
import sys
from pathlib import Path

data = json.loads(Path(sys.argv[1] if len(sys.argv) > 1 else "results.json").read_text())
rows = data["runs"]
for mode in ("client-timeout", "handler-timeout", "cooperative"):
    group = [r for r in rows if r["mode"] == mode]
    assert group, mode
    for r in group:
        assert 0 <= r["after_return_cpu_ms"] <= r["total_cpu_ms"]
        assert r["full_work_completed"] + r["work_canceled"] == r["requests"]
        if mode == "handler-timeout":
            assert r["status_503"] == r["requests"]
            assert r["late_write_errors"] == r["requests"]
        else:
            assert r["client_errors"] == r["requests"]
        if mode == "cooperative":
            assert r["work_canceled"] == r["requests"]
        else:
            assert r["full_work_completed"] == r["requests"]
    print(mode)
    for key in ("client_done_ms", "drain_ms", "total_cpu_ms", "after_return_cpu_ms"):
        values = [r[key] for r in group]
        print(f"  {key}: median={statistics.median(values):.3f}, range={min(values):.3f}..{max(values):.3f}")
