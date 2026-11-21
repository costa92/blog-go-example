import json, sys
from collections import defaultdict
rows = [json.loads(l) for f in sys.argv[1:] for l in open(f)]
g = defaultdict(list)
for r in rows: g[(r["model"], r["temp"])].append(r)
print("| model | temp | n | pass@1 | syntax err | empty/err | distinct code / task | distinct raw / task | tasks all-pass | tasks all-fail | tok/s | mean out tokens |")
print("|---|---|---|---|---|---|---|---|---|---|---|---|")
for (m, t), rs in sorted(g.items()):
    n = len(rs)
    p = sum(r["passed"] for r in rs) / n
    se = sum(not r["syntax_ok"] and bool(r["raw"]) for r in rs) / n
    empty = sum(not r["raw"] for r in rs)
    bt = defaultdict(list)
    for r in rs: bt[r["task"]].append(r)
    dc = sum(len({r["norm"] or ("BAD"+r["raw"]) for r in v}) for v in bt.values()) / len(bt)
    dr = sum(len({r["raw"] for r in v}) for v in bt.values()) / len(bt)
    allp = sum(all(r["passed"] for r in v) for v in bt.values())
    allf = sum(not any(r["passed"] for r in v) for v in bt.values())
    tps = [r["eval_count"] / r["eval_ns"] * 1e9 for r in rs if r.get("eval_ns")]
    tps = f"{sum(tps)/len(tps):.1f}" if tps else "-"
    ec = [r["eval_count"] for r in rs if r.get("eval_count")]
    print(f"| {m.split(':',1)[1]} | {t} | {n} | {p:.1%} | {se:.1%} | {empty} | {dc:.2f} | {dr:.2f} | {allp} | {allf} | {tps} | {sum(ec)/max(len(ec),1):.0f} |")
