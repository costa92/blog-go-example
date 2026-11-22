#!/usr/bin/env python3
"""Paired comparisons used in the post (exact McNemar test on discordant pairs).

usage: stats.py logs/MODEL.jsonl [...]
"""
import json, sys
from math import comb
from grade import grade, first_call


def mcnemar(a, b):
    """a, b: dicts key -> bool. Returns (only_a, only_b, two-sided exact p)."""
    keys = a.keys() & b.keys()
    x = sum(a[k] and not b[k] for k in keys)
    y = sum(b[k] and not a[k] for k in keys)
    n = x + y
    p = min(1.0, 2 * sum(comb(n, i) for i in range(min(x, y) + 1)) / 2 ** n) if n else 1.0
    return x, y, p


for path in sys.argv[1:]:
    rows = [json.loads(l) for l in open(path)]
    model = rows[0]["model"]
    main = [r for r in rows if r["nb"] == 1 and r["order"] == "shuffle" and r["num_ctx"] == 16384
            and r["level"] != "enum"]

    def pick(rs, key, what):
        return {key(r): grade(r)["label"] in what for r in rs}

    ok, tool = ("ok",), ("ok", "bad_args")
    print(f"== {model}")
    for lv in ("name", "short", "full"):
        rs = [r for r in main if r["level"] == lv]
        print(f"  {lv:5} tool {sum(grade(r)['label'] in tool for r in rs)}/{len(rs)}"
              f"  args {sum(grade(r)['label'] == 'ok' for r in rs)}/{len(rs)}")
    by = lambda lv, w: pick([r for r in main if r["level"] == lv], lambda r: (r["rid"], r["n"]), w)
    print("  args  full vs name  (full only, name only, p) =", mcnemar(by("full", ok), by("name", ok)))
    print("  args  full vs short                            =", mcnemar(by("full", ok), by("short", ok)))
    print("  tool  full vs short                            =", mcnemar(by("full", tool), by("short", tool)))
    bn = lambda n, w: pick([r for r in main if r["n"] == n], lambda r: (r["rid"], r["level"]), w)
    print("  tool  n=5 vs n=100 (all levels)                =", mcnemar(bn(5, tool), bn(100, tool)))
    print("  args  n=5 vs n=100 (all levels)                =", mcnemar(bn(5, ok), bn(100, ok)))
    nb = lambda v: pick([r for r in rows if r["n"] in (5, 10) and r["nb"] == v and r["num_ctx"] == 16384],
                        lambda r: (r["rid"], r["n"], r["level"]), tool)
    print("  tool  no neighbours vs neighbours (n=5,10)     =", mcnemar(nb(0), nb(1)))
    po = lambda o: pick([r for r in rows if r["order"] == o], lambda r: (r["rid"], r["n"]), tool)
    print("  tool  first vs last (short, n=50,100)          =", mcnemar(po("first"), po("last")))
    ctx = lambda c: pick([r for r in rows if r["level"] == "full" and r["n"] in (50, 100) and r["num_ctx"] == c],
                         lambda r: (r["rid"], r["n"]), tool)
    print("  tool  num_ctx 16384 vs default (full, n=50,100)=", mcnemar(ctx(16384), ctx(0)))
    md = [r for r in main if r["rid"] in ("r11", "r16", "r17")]  # 只给了月日的三条请求
    years = sum(any(str(v).startswith("2023") for v in (first_call(r)[1] or {}).values()) for r in md)
    print(f"  month-day requests filled as 2023: {years}/{len(md)}")
