#!/usr/bin/env python3
"""Check saved, real-network observations without assuming exact timings."""
import json
import sys
from pathlib import Path

d = json.loads(Path(sys.argv[1] if len(sys.argv) > 1 else "protocol_results.json").read_text())
assert len(d["cases"]) == 33
assert len(d["chains"]) == 6
for r in d["cases"]:
    t = r["task"]
    assert t["observed_protocol"] == {"http1": "HTTP/1.1", "http2": "HTTP/2.0", "grpc": "gRPC/HTTP2"}[r["protocol"]]
    assert t["has_request_deadline"] == (r["protocol"] == "grpc" and r["trigger"] == "deadline")
    if r["trigger"] == "wait-only":
        assert r["client_wait_result"] == "LocalWaitTimeout"
        assert r["actual_call_result"] == "OK"
        assert t["completed"] and not t["parent_error_at_task_end"]
    else:
        expected = "Canceled" if r["trigger"] == "cancel" else "DeadlineExceeded"
        assert r["client_wait_result"] == expected
        assert t["parent_error_at_task_end"] in ("Canceled", "DeadlineExceeded")
        assert t["completed"] == (r["mode"] != "cooperate")
    if r["mode"] == "detached":
        assert t["has_work_deadline"] and not t["work_error"]
    if r["mode"] == "ignore":
        assert t["steps_completed"] == 20 and not t["work_error"]
    print(f"{r['protocol']:5} {r['trigger']:14} {r['mode']:9} client={r['client_wait_result']:17} deadline={str(t['has_request_deadline']):5} steps={t['steps_completed']:2} completed={t['completed']}")

for r in d["chains"]:
    t = r["backend"]
    assert r["client_result"] == "DeadlineExceeded"
    assert r["frontend_has_deadline"] == (r["frontend_protocol"] == "grpc")
    assert t["has_request_deadline"] == (r["passed_request_context"] and r["frontend_protocol"] == "grpc")
    assert t["completed"] == (not r["passed_request_context"])
    if r["frontend_protocol"] == "grpc" and r["passed_request_context"]:
        assert 0 < t["request_budget_ms"] < d["environment"]["timeout_ms"] - r["forward_delay_ms"] + 1
    if not r["passed_request_context"]:
        assert not t["parent_error_at_task_end"]
    print(f"chain {r['frontend_protocol']:5} pass_context={r['passed_request_context']} backend_steps={t['steps_completed']}")

t = d["bounded_detached"]["case"]["task"]
assert not t["completed"] and t["work_error"] == "DeadlineExceeded"
assert t["has_work_deadline"]
print("PASS: 33 direct cases, 6 forwarding cases, and detached task's independent deadline")
