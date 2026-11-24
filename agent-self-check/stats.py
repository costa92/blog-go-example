"""汇总：python3 stats.py [logs/*.jsonl]
每个模型 × 条件：base 正确数 → 追问后正确数，对改错（对→错）、错改对（错→对）、最终答案没变的比例、追加的生成 token 和耗时；
verifier 另外给出审查判定的混淆表。"""
import collections, glob, json, sys
import grade

files = sys.argv[1:] or sorted(glob.glob("logs/*.jsonl"))
KINDS = ("arith", "fact", "code")


def load(p):
    rows = [json.loads(l) for l in open(p)]
    return {(r["id"], r["cond"]): r for r in rows}


for p in files:
    rows = load(p)
    base = {i: r for (i, c), r in rows.items() if c == "base"}
    if not base:
        continue
    m = next(iter(base.values()))
    n = len(base)
    print(f"\n### {m['model']}  temp={m['temp']} seed={m['seed']}  共 {n} 题")
    bk = collections.Counter(r["kind"] for r in base.values() if r["ok"])
    nk = collections.Counter(r["kind"] for r in base.values())
    print(f"base 正确 {sum(r['ok'] for r in base.values())}/{n}（不看格式 {sum(r['ok'] if r['kind'] != 'arith' else grade.check(i, r['out'], True)[0] for i, r in base.items())}）  " + "  ".join(f"{k} {bk[k]}/{nk[k]}" for k in KINDS)
          + f"  平均生成 {sum(r['eval_count'] or 0 for r in base.values()) / n:.0f} token, {sum(r['wall'] for r in base.values()) / n:.1f}s")
    print(f"{'条件':9s} {'最终正确':>8s} {'对→错':>6s} {'错→对':>6s} {'答案没变':>8s} {'追问次数':>6s} {'追加token/题':>10s} {'追加秒/题':>8s}   按题型 对→错/错→对")
    for cond in ("reflect", "doubt", "external", "verifier"):
        rs = {i: rows.get((i, cond)) for i in base}
        if any(v is None for v in rs.values()):
            print(f"{cond:9s} 未跑完 ({sum(v is not None for v in rs.values())}/{n})")
            continue
        ok = sum(r["ok"] for r in rs.values())
        rw = [i for i in base if base[i]["ok"] and not rs[i]["ok"]]
        wr = [i for i in base if not base[i]["ok"] and rs[i]["ok"]]
        asked = [i for i in base if rs[i].get("out")]
        same = sum(grade.final_answer(i, rs[i]["out"]) == grade.final_answer(i, base[i]["out"]) for i in asked)
        tok = sum((rs[i].get("eval_count") or 0) + (rs[i].get("verify", {}).get("eval_count") or 0) for i in base)
        sec = sum((rs[i].get("wall") or 0) + (rs[i].get("verify", {}).get("wall") or 0) for i in base)
        fmt = sum(base[i]["kind"] == "arith" and grade.check(i, base[i]["out"], True)[0] for i in wr)
        lost = sum(rs[i].get("out") and base[i]["kind"] == "arith" and grade.check(i, rs[i]["out"], True)[0] for i in rw)
        per = f"错→对里只补了答案行 {fmt}，对→错里只丢了答案行 {lost}   " + "  ".join(f"{k} {sum(base[i]['kind'] == k for i in rw)}/{sum(base[i]['kind'] == k for i in wr)}" for k in KINDS)
        print(f"{cond:9s} {ok:>4d}/{n:<3d} {len(rw):>6d} {len(wr):>6d} {same:>4d}/{len(asked):<3d} {len(asked):>6d} {tok / n:>10.0f} {sec / n:>8.1f}   {per}")
    vs = [rows[(i, "verifier")] for i in base]
    cm = collections.Counter((base[r["id"]]["ok"], r["verdict"]) for r in vs)
    print("verifier 判定：base 对 → 判正确 {} / 判错误 {} / 没给判定 {}；base 错 → 判正确 {} / 判错误 {} / 没给判定 {}".format(
        cm[(True, "正确")], cm[(True, "错误")], cm[(True, None)], cm[(False, "正确")], cm[(False, "错误")], cm[(False, None)]))
