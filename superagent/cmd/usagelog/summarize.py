"""Summarize live coding-demo runs: one row per run from <dir>/live-NN.jsonl + .out + .err.

usage: python3 summarize.py RUNS_DIR > results.csv
Prices are DeepSeek deepseek-flash USD per 1M tokens (2026-11), peak vs off-peak.
"""
import csv, glob, json, os, sys
from datetime import datetime

PEAK = {"hit": 0.006, "miss": 0.3, "out": 1.2}
OFF = {k: v / 2 for k, v in PEAK.items()}
TEST = 'go test -count=1 ./...'


def peak(ts):
    t = datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ")
    return t.weekday() < 5 and (1 <= t.hour < 4 or 6 <= t.hour < 10)


def final_state(path):
    text = open(path).read()
    i = text.find('{\n  "state"')
    return json.loads(text[i:])["state"] if i >= 0 else None


rows = []
for log in sorted(glob.glob(os.path.join(sys.argv[1], "live-*.jsonl"))):
    run = os.path.basename(log)[5:7]
    recs = [json.loads(l) for l in open(log)]
    worker = [r for r in recs if r["role"] == "worker"]
    coord = [r for r in recs if r["role"] == "coordinator"]
    hit = miss = out = reasoning = 0
    cost = 0.0
    for r in recs:
        u = r.get("usage") or {}
        h, m, o = u.get("prompt_cache_hit_tokens", 0), u.get("prompt_cache_miss_tokens", 0), u.get("completion_tokens", 0)
        p = PEAK if peak(r["time"]) else OFF
        cost += (h * p["hit"] + m * p["miss"] + o * p["out"]) / 1e6
        hit, miss, out = hit + h, miss + m, out + o
        reasoning += (u.get("completion_tokens_details") or {}).get("reasoning_tokens", 0)
    calls = [c for r in worker for c in (r.get("tool_calls") or [])]
    refused = [c for c in calls if c.startswith("run_command") and json.loads(c[len("run_command"):]).get("command") != TEST]
    err = open(log[:-6] + ".err").read().strip()
    st = final_state(log[:-6] + ".out")
    status = verified = ""
    if st:
        t = next(iter(st["tickets"].values()))
        status = t["status"]
        ev = t.get("evidence") or {}
        verified = ev.get("test_output", "").startswith("ok")
    # A false "done" is a worker reply that ends the loop while the host check rejects it.
    caught = 1 if worker and worker[-1].get("finish_reason") == "stop" and ("host verification rejected" in err or "did not change" in err) else 0
    rows.append(dict(run=run, ok=bool(status == "ready" and verified), status=status or "error", worker_turns=len(worker),
                     coordinator_calls=len(coord), coord_accept="".join("Y" if '"accept":true' in r.get("content", "").replace(" ", "") else "N" for r in coord),
                     tool_calls=len(calls), refused_commands=len(refused), false_done_caught=caught,
                     cache_hit=hit, cache_miss=miss, output=out, reasoning=reasoning, cost_usd=round(cost, 5),
                     refused=" ; ".join(json.loads(c[len("run_command"):])["command"] for c in refused), error=err[:160]))
w = csv.DictWriter(sys.stdout, fieldnames=list(rows[0]))
w.writeheader()
w.writerows(rows)
