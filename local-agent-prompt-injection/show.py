#!/usr/bin/env python3
"""Print one case from a log: tool calls and the final answer, tool data elided.

usage: show.py LOG CASE_ID [--data]
"""
import json, sys

path, cid = sys.argv[1], sys.argv[2]
for line in open(path):
    r = json.loads(line)
    if r["id"] != cid:
        continue
    print(f"## {r['model']} mit={r['mit']} case={cid}")
    print(f"user> {r['user']}")
    for m in r["messages"][2:]:
        if m["role"] == "assistant":
            for tc in m.get("tool_calls") or []:
                f = tc["function"]
                print(f"call> {f['name']}({json.dumps(f.get('arguments'), ensure_ascii=False)})")
            if m.get("content") and not m.get("tool_calls"):
                print("final> " + m["content"].strip().replace("\n", "\n       "))
        elif m["role"] == "tool":
            c = m["content"]
            if "--data" in sys.argv or c.startswith('{"ok"') or c.startswith('{"error"') or len(c) < 80:
                print(f"tool< {c}")
            else:
                print(f"tool< [{m['tool_name']} 返回 {len(c)} 字符]")
