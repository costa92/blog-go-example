"""判分 + 各种路由策略的离线模拟。只读 logs/，不调模型。

    python3 grade.py            # 各模型准确率、路由策略对比、信号的区分度、把握的校准
    python3 grade.py sweep      # 两种置信度阈值从低到高扫一遍
"""
import collections
import json
import sys
from pathlib import Path

from judge import ANS, by_fallback, canon, confidence, correct, correct_lenient, has_answer_line, valid

TASKS = {t["id"]: t for t in map(json.loads, Path("tasks.jsonl").read_text().splitlines())}
TIERS = ["easy", "medium", "hard"]


def load(name):
    p = Path("logs") / f"{name}.jsonl"
    return {r["id"]: r for r in map(json.loads, p.read_text().splitlines())} if p.exists() else None


def answer_logprob(r):
    """答案行里那几个 token 的最小 logprob；没有答案行返回 None。"""
    toks = r.get("logprobs") or []
    text = "".join(t or "" for t, _ in toks)
    ms = list(ANS.finditer(text))
    if not ms:
        return None
    start, end = ms[-1].start(1), ms[-1].end(1)
    pos, lps = 0, []
    for tok, lp in toks:
        nxt = pos + len(tok or "")
        if nxt > start and pos < end and (tok or "").strip() and lp is not None:
            lps.append(lp)
        pos = nxt
    return min(lps) if lps else None


def gen(r):
    """一次调用的耗时，扣掉 Ollama 报告的加载时间（每个日志的第一题含冷加载）。"""
    return r.get("wall", 0) - (r.get("load_duration") or 0) / 1e9


def acc(ids, ok):
    return sum(ok[i] for i in ids)


def auroc(scores, labels):
    """scores 越高越应该是对的；labels True=对。有并列时取平均。"""
    pos = [s for s, l in zip(scores, labels) if l]
    neg = [s for s, l in zip(scores, labels) if not l]
    if not pos or not neg:
        return float("nan")
    win = sum((p > n) + 0.5 * (p == n) for p in pos for n in neg)
    return win / (len(pos) * len(neg))


def tier_str(ids, ok):
    return " / ".join(f"{sum(ok[i] for i in ids if TASKS[i]['tier'] == t):2d}" for t in TIERS)


def main():
    small, big = sys.argv[2] if len(sys.argv) > 2 else "qwen2.5-coder-3b", sys.argv[3] if len(sys.argv) > 3 else "qwen2.5-coder-7b"
    ids = list(TASKS)
    print("== 单模型（温度 0，seed 1）: 总分  简单/中等/困难各 50 题  宽松 JSON 判分  未写答案行（其中靠最后一行判对）  平均每题秒数（不含加载）")
    for m in ["qwen2.5-coder-0.5b", "qwen2.5-coder-3b", "qwen2.5-coder-7b", "llama3.1-8b"]:
        for mode in ["plain", "conf"]:
            L = load(f"{m}_{mode}_t0_s1")
            if not L:
                continue
            ok = {i: correct(TASKS[i], L[i]["out"]) for i in ids}
            noans = sum(not has_answer_line(L[i]["out"]) for i in ids)
            fb = sum(by_fallback(L[i]["out"]) and ok[i] for i in ids)
            lenient = sum(correct_lenient(TASKS[i], L[i]["out"]) for i in ids)
            wall = sum(gen(L[i]) for i in ids) / len(ids)
            print(f"{m:20s} {mode:5s} {acc(ids, ok):3d}/150  {tier_str(ids, ok)}  宽松 {lenient:3d}  无答案行 {noans:2d}（判对 {fb}）  {wall:5.2f}s")
    print("\n== 温度 0.7 三个 seed")
    for m in ["qwen2.5-coder-0.5b", "qwen2.5-coder-3b", "qwen2.5-coder-7b"]:
        row = []
        for s in (1, 2, 3):
            L = load(f"{m}_plain_t0.7_s{s}")
            if L:
                row.append(sum(correct(TASKS[i], L[i]["out"]) for i in ids))
        if row:
            print(f"{m:20s} {row}")

    S, B, SC = load(f"{small}_plain_t0_s1"), load(f"{big}_plain_t0_s1"), load(f"{small}_conf_t0_s1")
    RT = {r: load(f"{r}_route_t0_s1") for r in ["qwen2.5-coder-0.5b", "qwen2.5-coder-3b"]}
    sc = [load(f"{small}_plain_t0.7_s{s}") for s in (1, 2, 3)]
    lp = {i: answer_logprob(S[i]) for i in ids}
    wS = {i: gen(S[i]) for i in ids}
    wB = {i: gen(B[i]) for i in ids}

    def strategies(judge, title):
        okS = {i: judge(TASKS[i], S[i]["out"]) for i in ids}
        okB = {i: judge(TASKS[i], B[i]["out"]) for i in ids}
        okSC = {i: judge(TASKS[i], SC[i]["out"]) for i in ids}
        print(f"\n小模型错、大模型对 {sum(not okS[i] and okB[i] for i in ids)} 题；小模型对、大模型错 {sum(okS[i] and not okB[i] for i in ids)} 题；两个都错 {sum(not okS[i] and not okB[i] for i in ids)} 题")

        def strategy(name, esc, first_ok, first_wall, extra_wall=None, route_first=False):
            """esc[i]=True 表示升级到大模型。first_* 是小模型那一步用的答案和耗时。
            route_first=True：先分流再回答，升级的题不再调用小模型作答。"""
            ok = {i: (okB[i] if esc[i] else first_ok[i]) for i in ids}
            wall = sum((0 if route_first and esc[i] else first_wall[i]) + (wB[i] if esc[i] else 0) + (extra_wall[i] if extra_wall else 0) for i in ids)
            n = sum(esc.values())
            need = {i: not okS[i] and okB[i] for i in ids}     # 真正该升级的题
            hit = sum(esc[i] and need[i] for i in ids)
            print(f"{name:34s} {acc(ids, ok):3d}/150  {tier_str(ids, ok)}  升级 {n:3d} ({n / 1.5:4.1f}%)  "
                  f"该升级的 {sum(need.values())} 题里抓到 {hit:2d}  计算耗时 {wall:6.1f}s")

        print(f"\n== 路由策略（{title}；小模型 {small}，大模型 {big}）: 准确率  简单/中等/困难  升级比例  该升级的抓到几题  计算耗时（不含加载和换模型）")
        zero = {i: 0 for i in ids}
        strategy("只用小模型", {i: False for i in ids}, okS, wS)
        strategy("只用大模型", {i: True for i in ids}, okS, zero)
        strategy("理想路由（小模型错才升级）", {i: not okS[i] for i in ids}, okS, wS)
        strategy("按题目难度档：简单给小模型", {i: TASKS[i]["tier"] != "easy" for i in ids}, okS, wS, route_first=True)
        for r, L in RT.items():
            if L:
                esc = {i: "简单" not in L[i]["out"] for i in ids}
                strategy(f"{r} 当分类器", esc, okS, wS, {i: gen(L[i]) for i in ids}, route_first=True)
        strategy("格式校验不过才升级", {i: not valid(TASKS[i], S[i]["out"]) for i in ids}, okS, wS)
        for th in (90, 95, 100):
            esc = {i: (confidence(SC[i]["out"]) or 0) < th for i in ids}
            strategy(f"自报把握 < {th} 升级", esc, okSC, {i: gen(SC[i]) for i in ids})
        for th in (-0.5, -0.1, -0.02):
            esc = {i: lp[i] is None or lp[i] < th for i in ids}
            strategy(f"答案 token 最小 logprob < {th}", esc, okS, wS)
            esc2 = {i: esc[i] or not valid(TASKS[i], S[i]["out"]) for i in ids}
            strategy(f"  同上 + 格式校验", esc2, okS, wS)
        if all(sc):
            # 一致时用第 1 次采样的答案（不是温度 0 的答案），耗时算 3 次采样
            keys = {i: [canon(TASKS[i], L[i]["out"]) for L in sc] for i in ids}
            esc = {i: len(set(keys[i])) > 1 or keys[i][0] is None for i in ids}
            strategy("温度 0.7 采 3 次不一致才升级", esc, {i: judge(TASKS[i], sc[0][i]["out"]) for i in ids},
                     {i: sum(gen(L[i]) for L in sc) for i in ids})
        lab = [okS[i] for i in ids]
        print(f"AUROC  答案 token 最小 logprob {auroc([lp[i] if lp[i] is not None else -99 for i in ids], lab):.3f}"
              f"  自报把握 {auroc([confidence(SC[i]['out']) or 0 for i in ids], [okSC[i] for i in ids]):.3f}"
              f"  格式校验 {auroc([valid(TASKS[i], S[i]['out']) for i in ids], lab):.3f}")
        return okS, okSC

    okS, okSC = strategies(correct, "严格判分：JSON 必须在答案行同一行")
    strategies(correct_lenient, "宽松判分：JSON 取输出里最后一个 {...}")

    print("\n== 信号区分「小模型这题对不对」的能力（AUROC，0.5 等于瞎猜）")
    print("（以下都按严格判分）")
    lab = [okS[i] for i in ids]
    print(f"答案 token 最小 logprob   {auroc([lp[i] if lp[i] is not None else -99 for i in ids], lab):.3f}")
    print(f"自报把握（conf 模式自己的答案） {auroc([confidence(SC[i]['out']) or 0 for i in ids], [okSC[i] for i in ids]):.3f}")
    print(f"格式校验通过             {auroc([valid(TASKS[i], S[i]['out']) for i in ids], lab):.3f}")
    for r, L in RT.items():
        if L:
            print(f"{r} 判为简单    {auroc(['简单' in L[i]['out'] for i in ids], lab):.3f}")
    print(f"题目本身的难度档（理想分类器） {auroc([{'easy': 2, 'medium': 1, 'hard': 0}[TASKS[i]['tier']] for i in ids], lab):.3f}")

    print("\n== 路由器的判断 vs 小模型实际对错")
    for r, L in RT.items():
        if not L:
            continue
        c = collections.Counter()
        for i in ids:
            o = L[i]["out"].strip()
            lab_ = "简单" if "简单" in o else "困难" if "困难" in o else "其他"
            c[(TASKS[i]["tier"], lab_, okS[i])] += 1
        print(r)
        for t in TIERS:
            print(f"  {t:6s} 判简单: 小模型对 {c[(t, '简单', True)]:2d} 错 {c[(t, '简单', False)]:2d} | "
                  f"判困难: 对 {c[(t, '困难', True)]:2d} 错 {c[(t, '困难', False)]:2d} | 其他 {c[(t, '其他', True)] + c[(t, '其他', False)]}")

    print("\n== 自报把握的校准（%s conf 模式）" % small)
    bins = [(0, 79), (80, 89), (90, 94), (95, 99), (100, 100)]
    cs = {i: confidence(SC[i]["out"]) for i in ids}
    print(f"没写把握: {sum(v is None for v in cs.values())} 题")
    print("把握值分布:", collections.Counter(cs.values()).most_common(8))
    for lo, hi in bins:
        g = [i for i in ids if cs[i] is not None and lo <= cs[i] <= hi]
        if g:
            print(f"  {lo:3d}-{hi:3d}: {len(g):3d} 题，实际对 {sum(okSC[i] for i in g):3d}（{100 * sum(okSC[i] for i in g) / len(g):5.1f}%）")
    for t in TIERS:
        g = [i for i in ids if TASKS[i]["tier"] == t and cs[i] is not None]
        print(f"  {t:6s} 平均把握 {sum(cs[i] for i in g) / len(g):5.1f}  实际正确率 {100 * sum(okSC[i] for i in g) / len(g):5.1f}%")

    print("\n== logprob 分档（%s plain）" % small)
    for lo, hi in [(-99, -1), (-1, -0.1), (-0.1, -0.01), (-0.01, 0.01)]:
        g = [i for i in ids if lp[i] is not None and lo <= lp[i] < hi]
        if g:
            print(f"  [{lo:6.2f},{hi:5.2f}): {len(g):3d} 题，实际对 {sum(okS[i] for i in g):3d}（{100 * sum(okS[i] for i in g) / len(g):5.1f}%）")
    print(f"  无答案行: {sum(lp[i] is None for i in ids)} 题")

    if len(sys.argv) > 1 and sys.argv[1] == "sweep":
        print("\n== 阈值扫描: 升级比例 -> 准确率")
        for name, score in [("logprob", {i: lp[i] if lp[i] is not None else -99 for i in ids}),
                            ("把握", {i: confidence(SC[i]["out"]) or 0 for i in ids})]:
            first = okSC if name == "把握" else okS
            okB = {i: correct(TASKS[i], B[i]["out"]) for i in ids}
            for th in sorted(set(score.values())):
                esc = {i: score[i] < th for i in ids}
                ok = {i: (okB[i] if esc[i] else first[i]) for i in ids}
                print(f"{name} < {th:8.4f}  升级 {sum(esc.values()):3d}  对 {acc(ids, ok):3d}")


if __name__ == "__main__":
    main()
