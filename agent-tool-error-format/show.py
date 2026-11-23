#!/usr/bin/env python3
"""打印运行记录：每一步的工具调用、返回内容和最终回答。

用法: show.py logs/x.jsonl MODEL TASK [VARIANT ...] [--seed N ...] [--temp T]
"""
import argparse, json

ap = argparse.ArgumentParser()
ap.add_argument("log")
ap.add_argument("model")
ap.add_argument("task")
ap.add_argument("variant", nargs="*")
ap.add_argument("--seed", type=int, nargs="+")
ap.add_argument("--temp", type=float)
a = ap.parse_args()
for line in open(a.log, encoding="utf-8"):
    r = json.loads(line)
    if r["model"] != a.model or r["task"] != a.task or (a.variant and r["variant"] not in a.variant) \
            or (a.seed and r["seed"] not in a.seed) or (a.temp is not None and r["temp"] != a.temp):
        continue
    print(f"## {r['model']} {r['task']} variant={r['variant']} temp={r['temp']} seed={r['seed']} stop={r['stop']}")
    for c in r["calls"]:
        print(f"→ {c['name']}({json.dumps(c['args'], ensure_ascii=False)})")
        print(f"← {c['result']}")
    print("答:", (r["final"] or "").strip().replace("\n", " "))
    print()
