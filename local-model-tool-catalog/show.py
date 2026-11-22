#!/usr/bin/env python3
"""Print what a model called for one request across conditions.

usage: show.py logs/x.jsonl MODEL RID [level] [n]
"""
import json, sys

from grade import grade

path, model, rid = sys.argv[1:4]
level = sys.argv[4] if len(sys.argv) > 4 else None
n = int(sys.argv[5]) if len(sys.argv) > 5 else None
for line in open(path):
    r = json.loads(line)
    if r["model"] != model or r["rid"] != rid or (level and r["level"] != level) or (n and r["n"] != n):
        continue
    g = grade(r)
    print(f"## n={r['n']} level={r['level']} order={r['order']} nb={r['nb']} ctx={r['num_ctx']} pos={r['pos']} "
          f"prompt={r['prompt_eval_count']} -> {g['label']}")
    for c in r["tool_calls"]:
        print("call", c["function"]["name"], json.dumps(c["function"].get("arguments"), ensure_ascii=False))
    if r["content"].strip():
        print("text", r["content"].strip().replace("\n", " ")[:300])
