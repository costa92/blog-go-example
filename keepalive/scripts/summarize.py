#!/usr/bin/env python3
"""summarize.py LOG... : per-pod share after the action.

"old" pods are those that answered in the first AT seconds (default 20).
The after-window is t > AT+5 (give new pods time to become ready).
new_share = requests answered by pods not seen before / all 200 responses.
"""
import os, re, sys

AT = int(os.environ.get("AT", 20))
for path in sys.argv[1:]:
    rows = []
    for line in open(path):
        m = re.match(r"t=(\d+)s dials=(\d+)(.*)", line)
        if not m:
            continue
        t, dials, rest = int(m[1]), int(m[2]), m[3]
        pods = dict(re.findall(r" (echo-[\w-]+)=(\d+)", rest))
        errs = re.findall(r" (ERR\[[^\]]*\]|HTTP\d+)=(\d+)", rest)
        rows.append((t, dials, {k: int(v) for k, v in pods.items()}, errs))
    old = {p for t, _, pods, _ in rows if t <= AT for p in pods}
    after = [r for r in rows if r[0] > AT + 5]
    tot = {}
    for _, _, pods, _ in after:
        for p, n in pods.items():
            tot[p] = tot.get(p, 0) + n
    allreq = sum(tot.values())
    new = sum(n for p, n in tot.items() if p not in old)
    dials_after = sum(r[1] for r in after)
    secs = max(len(after), 1)
    errs = {}
    for _, _, _, es in rows:
        for k, v in es:
            errs[k] = errs.get(k, 0) + int(v)
    per_pod = " ".join(f"{p[-5:]}{'*' if p not in old else ''}={n*100//max(allreq,1)}%" for p, n in sorted(tot.items()))
    print(f"{os.path.basename(path)}: after t>{AT+5}s reqs={allreq} new_share={new*100/max(allreq,1):.1f}% "
          f"dials/s={dials_after/secs:.1f} errs={errs or 0} | {per_pod}")
