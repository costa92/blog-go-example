"""汇总 logs/*.jsonl。python3 stats.py [cond...]"""
import collections, json, re, sys
from pathlib import Path

J = ["gemma4:latest", "llama3.1:8b", "qwen2.5-coder:7b"]

def reparse(r):
    # reason 模式：只在最后两行非空文本里找“结论：X”或“答案是 X”，分析中间的小标题不算结论
    if r.get("mode") == "reason":
        tail = "\n".join([x for x in r["out"].splitlines() if x.strip()][-2:])
        m = re.findall(r"结论[*\s]*[：:][*\s]*(?:回答\s*)?([AB])", tail) or re.findall(r"答案是\s*(?:回答\s*)?([AB])", tail)
        r["pick"] = m[-1] if m else None
    return r

def load(cond):
    p = Path(f"logs/{cond}.jsonl")
    return [reparse(json.loads(l)) for l in p.read_text().splitlines()] if p.exists() else []

def pair_summary(rows):
    """rows: 同一 judge/mode/variant/temp/seed 的 64 条。"""
    n = len(rows)
    acc = sum(r["pick"] == r["good_pos"] for r in rows)
    arate = sum(r["pick"] == "A" for r in rows)
    none = sum(r["pick"] is None for r in rows)
    by = collections.defaultdict(dict)
    for r in rows:
        by[r["item"]][r["order"]] = r["pick"] == r["good_pos"]   # True = 选了 good 一侧
    cons = ok = wrong = 0
    for d in by.values():
        if len(d) < 2:
            continue
        if d["GB"] == d["BG"]:
            cons += 1
            ok += d["GB"]
            wrong += not d["GB"]
    return dict(n=n, acc=acc, A=arate, none=none, items=len(by), cons=cons, agg_ok=ok, agg_tie=len(by) - cons, agg_wrong=wrong)

def fmt(s):
    return (f"n={s['n']:3d} 选对={s['acc']:3d} ({100*s['acc']/s['n']:.0f}%) 选A={s['A']:3d} ({100*s['A']/s['n']:.0f}%) 未解析={s['none']} | "
            f"两序一致={s['cons']}/{s['items']} 交换聚合: 对={s['agg_ok']} 平={s['agg_tie']} 错={s['agg_wrong']}")

def pairs(cond):
    g = collections.defaultdict(list)
    for r in load(cond):
        g[(r["judge"], r["mode"], r["variant"], r["temp"], r["seed"], r["think"])].append(r)
    print(f"== {cond}  （tie 变体里 good=纯文本侧，“选对”=选纯文本）")
    for k in sorted(g, key=lambda k: (J.index(k[0]), k[2], k[4])):
        print(f"{k[0]:18s} {k[1]:6s} {k[2]:7s} T={k[3]} seed={k[4]} think={k[5]}: {fmt(pair_summary(g[k]))}")

def temp_flip():
    base = {(r["judge"], r["item"], r["order"]): r["pick"] for r in load("naive") if r["variant"] == "base"}
    g = collections.defaultdict(dict)
    for r in load("temp07"):
        g[(r["judge"], r["item"], r["order"])][r["seed"]] = r["pick"]
    print("== temp07 翻转：同一 (题, 顺序) 3 个 seed 结果不全相同的比例；以及与 T=0 不同的调用比例")
    for j in J:
        ks = [k for k in g if k[0] == j]
        if not ks:
            continue
        unstable = sum(len(set(g[k].values())) > 1 for k in ks)
        diff = sum(v != base.get(k) for k in ks for v in g[k].values())
        tot = sum(len(g[k]) for k in ks)
        print(f"{j:18s} 不稳定 {unstable}/{len(ks)}  与T=0不同 {diff}/{tot}")
        # 多数票
        maj = collections.defaultdict(dict)
        for k in ks:
            vals = list(g[k].values())
            maj[k[1]][k[2]] = max(set(vals), key=vals.count)
        ok = sum(1 for it, d in maj.items() if d.get("GB") == "A" and d.get("BG") == "B")
        print(f"{'':18s} 3 seed 多数票 + 交换聚合: 对={ok}/{len(maj)}")

def point():
    rows = load("point")
    if not rows:
        return
    s = {(r["judge"], r["variant"], r["item"]): r["score"] for r in rows}
    items = sorted({r["item"] for r in rows})
    print("== pointwise 平均分与两两比较（good vs X：高/平/低）")
    for j in J:
        means = {}
        for v in ("good", "bad", "padded", "badmd", "goodmd"):
            xs = [s[(j, v, i)] for i in items if s.get((j, v, i)) is not None]
            means[v] = f"{sum(xs)/len(xs):.2f}" if xs else "-"
        print(f"{j:18s} 平均分 {means}  未解析 {sum(1 for r in rows if r['judge']==j and r['score'] is None)}")
        for a, b in (("good", "bad"), ("good", "padded"), ("good", "badmd"), ("goodmd", "bad")):
            hi = sum(s.get((j, a, i), -1) > s.get((j, b, i), -1) for i in items)
            eq = sum(s.get((j, a, i)) == s.get((j, b, i)) for i in items)
            print(f"{'':18s} {a} vs {b}: 高={hi} 平={eq} 低={len(items)-hi-eq}")

def selfpref():
    rows = load("selfjudge")
    if not rows:
        return
    print("== 自我偏好：每个裁判在含自己答案的对局里选自己的比例，对比第三方裁判在同样对局里选它的比例")
    for j in J:
        own = [r for r in rows if r["judge"] == j and j in r["variant"].split("|")]
        def picked(r):
            x, y = r["variant"].split("|")
            first, second = (x, y) if r["order"] == "XY" else (y, x)
            return {"A": first, "B": second}.get(r["pick"])
        self_rate = sum(picked(r) == j for r in own)
        third = [r for r in rows if r["judge"] != j and j in r["variant"].split("|") and r["judge"] not in r["variant"].split("|")]
        third_rate = sum(picked(r) == j for r in third)
        arate = sum(r["pick"] == "A" for r in rows if r["judge"] == j)
        print(f"{j:18s} 自评选自己 {self_rate}/{len(own)}  第三方选它 {third_rate}/{len(third)}  该裁判选A {arate}/{sum(r['judge']==j for r in rows)}")


import math

def pg(r, temp=1.0):
    """第一 token 只看 A/B 两项，按温度缩放后归一化，返回选中 good 一侧的概率。"""
    a, b = r["top"].get("A", -50), r["top"].get("B", -50)
    ea, eb = math.exp(a / temp), math.exp(b / temp)
    pa = ea / (ea + eb)
    return pa if r["good_pos"] == "A" else 1 - pa

def lp(cond="lp"):
    rows = load(cond)
    if not rows:
        return
    g = collections.defaultdict(list)
    for r in rows:
        g[(r["judge"], r["variant"])].append(r)
    print(f"== {cond}：第一个 token 的 A/B 概率（tie 里 good=纯文本侧）")
    for k in sorted(g, key=lambda k: (J.index(k[0]), k[1])):
        rs = g[k]
        mass = sum(math.exp(r["top"].get("A", -50)) + math.exp(r["top"].get("B", -50)) for r in rs) / len(rs)
        argmax = sum(pg(r) > 0.5 for r in rs)
        e07 = sum(pg(r, 0.7) for r in rs)
        pa = sum((pg(r) if r["good_pos"] == "A" else 1 - pg(r)) for r in rs) / len(rs)
        by = collections.defaultdict(list)
        for r in rs:
            by[r["item"]].append(pg(r))
        avg_ok = sum(sum(v) / len(v) > 0.5 for v in by.values())
        print(f"{k[0]:18s} {k[1]:7s} argmax对={argmax}/{len(rs)} T0.7期望对={e07:.1f} 平均P(A)={pa:.2f} "
              f"两序概率平均对={avg_ok}/{len(by)} A/B质量={mass:.3f}")


if __name__ == "__main__":
    conds = sys.argv[1:] or ["naive", "rubric", "reason", "temp07", "think"]
    for c in conds:
        if c in ("naive", "rubric", "reason", "temp07", "think"):
            pairs(c)
    if not sys.argv[1:]:
        temp_flip(); point(); selfpref(); lp("lp"); lp("lprubric")
