"""Per-case error listing and null-substitution counts.

usage: python3 analyze.py <file.jsonl>... --tag main --arm schema [--temp 0.0]
       python3 analyze.py <file.jsonl>... --nulls --arm strict_schema
"""
import argparse, json
from collections import Counter

from cases import CASES
from score import FIELDS, load, score

ap = argparse.ArgumentParser()
ap.add_argument("files", nargs="+")
ap.add_argument("--tag")
ap.add_argument("--arm")
ap.add_argument("--temp", type=float)
ap.add_argument("--nulls", action="store_true")
a = ap.parse_args()

rows = [r for r in load(a.files)
        if (a.tag is None or r["tag"] == a.tag) and (a.arm is None or r["arm"] == a.arm)
        and (a.temp is None or r["temp"] == a.temp)]

if a.nulls:
    # what the model wrote where the ground truth is null
    for model in dict.fromkeys(r["model"] for r in rows):
        c = Counter()
        n = 0
        for r in rows:
            if r["model"] != model:
                continue
            o = score(r)["obj"] or {}
            for f in ("order_id", "customer", "days_waiting"):
                if CASES[r["case"]]["gt"][f] is None:
                    n += 1
                    c[(f, json.dumps(o.get(f), ensure_ascii=False))] += 1
        print(f"== {model}  null slots={n}")
        for (f, v), k in c.most_common():
            print(f"  {k:3d}  {f}={v}")
else:
    for r in rows:
        s = score(r)
        wrong = [f for f in FIELDS if not s["fields"][f]]
        if wrong:
            o = s["obj"] or {}
            got = {f: o.get(f) for f in wrong}
            exp = {f: CASES[r["case"]]["gt"][f] for f in wrong}
            print(f"{r['model']:18} {r['arm']:14} case={r['case']:2} rep={r['rep']} got={json.dumps(got, ensure_ascii=False)} "
                  f"want={json.dumps(exp, ensure_ascii=False, default=list)}")
