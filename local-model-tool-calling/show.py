#!/usr/bin/env python3
"""show.py LOG.jsonl [model] [task] [variant] : print each matching run as a compact trace."""
import json, sys
from grade import label

path, *flt = sys.argv[1:]
keys = ("model", "task", "variant")
for line in open(path):
    r = json.loads(line)
    if any(f and r[k] != f for k, f in zip(keys, flt)):
        continue
    lab = label(r)
    tag = r["variant"] + (("+parse" + (r.get("parser") or "v1")) if r.get("textparse") else "") + ("" if r.get("think") is None else f" think={r['think']}")
    print(f"## {r['model']} {r['task']} seed={r['seed']} {tag}  -> {lab}  ({r['secs']}s)")
    for c in r["calls"]:
        res = json.dumps(c["result"], ensure_ascii=False)
        print(f"  [{c['turn']}] {c['name']}({json.dumps(c['args'], ensure_ascii=False)}) -> {res[:110]}")
    fin = (r["final"] or "").replace("\n", " ")
    print(f"  answer: {fin[:160]!r}")
