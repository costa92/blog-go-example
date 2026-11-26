"""生成推理与数学题 reasoning.jsonl：5 类各 6 道，答案全部由暴力枚举得到。

固定随机种子，重跑逐字节相同。题目是现场生成的，不可能出现在训练数据里。
"""
import datetime as dt
import itertools
import json
import random
from fractions import Fraction

rng = random.Random(20261126)
FOOT = "\n\n请先推理，最后单独一行输出「答案：<答案>」。"


def grid_paths():
    for i in range(6):
        h, w = rng.randint(9, 12), rng.randint(9, 12)
        cells = [(r, c) for r in range(h) for c in range(w) if (r, c) not in ((0, 0), (h - 1, w - 1))]
        blocked = sorted(rng.sample(cells, rng.randint(8, 14)))
        dp = [[0] * w for _ in range(h)]
        for r in range(h):
            for c in range(w):
                if (r, c) in blocked:
                    continue
                dp[r][c] = 1 if (r, c) == (0, 0) else (dp[r - 1][c] if r else 0) + (dp[r][c - 1] if c else 0)
        bl = "、".join(f"({r + 1},{c + 1})" for r, c in blocked)
        q = (f"一个 {h} 行 {w} 列的方格，从左上角 (1,1) 走到右下角 ({h},{w})，每步只能向下或向右走一格。"
             f"以下格子是障碍，不能进入（坐标为 (行,列)）：{bl}。一共有多少条不同的路径？")
        yield f"grid-{i}", q, str(dp[h - 1][w - 1])


def digits():
    for i in range(6):
        n = rng.randint(2_000_000, 9_000_000)
        s = rng.randint(18, 30)
        d = rng.choice([3, 5, 7])
        cnt = sum(1 for x in range(1, n + 1) if sum(map(int, str(x))) == s and str(d) not in str(x))
        q = f"在 1 到 {n}（含）之间，有多少个整数的各位数字之和恰好等于 {s}，并且十进制写法里不含数字 {d}？"
        yield f"digits-{i}", q, str(cnt)


def order_puzzle():
    names = list("ABCDEF")
    for i in range(6):
        truth = names[:]
        rng.shuffle(truth)
        pos = {p: k + 1 for k, p in enumerate(truth)}
        perms = list(itertools.permutations(names))
        cons = []
        while True:
            kind = rng.choice(["before", "adjacent", "notat", "gap", "notadj"])
            x, y = rng.sample(names, 2)
            if kind == "before":
                if pos[x] > pos[y]:
                    x, y = y, x
                text, f = f"{x} 排在 {y} 前面（不一定相邻）", (lambda P, x=x, y=y: P[x] < P[y])
            elif kind == "adjacent":
                if abs(pos[x] - pos[y]) != 1:
                    continue
                text, f = f"{x} 和 {y} 相邻", (lambda P, x=x, y=y: abs(P[x] - P[y]) == 1)
            elif kind == "notadj":
                if abs(pos[x] - pos[y]) == 1:
                    continue
                text, f = f"{x} 和 {y} 不相邻", (lambda P, x=x, y=y: abs(P[x] - P[y]) != 1)
            elif kind == "notat":
                k = rng.choice([k for k in range(1, 7) if k != pos[x]])
                text, f = f"{x} 不在第 {k} 位", (lambda P, x=x, k=k: P[x] != k)
            else:
                g = abs(pos[x] - pos[y]) - 1
                if g < 1:
                    continue
                text, f = f"{x} 和 {y} 之间恰好隔着 {g} 个人", (lambda P, x=x, y=y, g=g: abs(P[x] - P[y]) - 1 == g)
            if text in (c[0] for c in cons):
                continue
            cons.append((text, f))
            sols = [p for p in perms if all(c[1]({q: k + 1 for k, q in enumerate(p)}) for c in cons)]
            if len(sols) == 1:
                break
        lines = "\n".join(f"{k + 1}. {c[0]}" for k, c in enumerate(cons))
        q = (f"A、B、C、D、E、F 六个人排成一队，从队头到队尾依次是第 1 到第 6 位。已知：\n{lines}\n"
             f"请给出从第 1 位到第 6 位的完整顺序，答案写成 6 个连续字母，例如 ABCDEF。")
        yield f"order-{i}", q, "".join(truth)


def dice():
    for i in range(6):
        k, faces = rng.choice([(3, 8), (4, 6), (4, 8), (5, 6), (3, 10), (4, 10)])
        kind = rng.choice(["ge", "prime"])
        outcomes = list(itertools.product(range(1, faces + 1), repeat=k))
        if kind == "ge":
            t = rng.randint(int(k * (faces + 1) / 2) + 2, k * faces - 3)
            hit = sum(1 for o in outcomes if sum(o) >= t)
            cond = f"点数之和不小于 {t}"
        else:
            primes = {p for p in range(2, k * faces + 1) if all(p % d for d in range(2, int(p ** 0.5) + 1))}
            hit = sum(1 for o in outcomes if sum(o) in primes)
            cond = "点数之和是质数"
        fr = Fraction(hit, len(outcomes))
        q = f"同时掷 {k} 枚均匀的 {faces} 面骰子（每枚点数 1 到 {faces}），{cond}的概率是多少？用最简分数 p/q 表示。"
        yield f"dice-{i}", q, f"{fr.numerator}/{fr.denominator}"


def calendar():
    for i in range(6):
        start = dt.date(2027, 1, 1) + dt.timedelta(days=rng.randint(0, 300))
        hol = sorted({start + dt.timedelta(days=rng.randint(1, 60)) for _ in range(5)})
        step, n = rng.randint(2, 4), rng.randint(6, 10)
        # 第 1 次会议在 start 当天或之后的第一个工作日，之后每隔 step 个工作日一次
        work, d = [], start
        while len(work) < 1 + (n - 1) * step:
            if d.weekday() < 5 and d not in hol:
                work.append(d)
            d += dt.timedelta(days=1)
        ans = work[(n - 1) * step]
        hs = "、".join(h.isoformat() for h in hol)
        q = (f"工作日指周一到周五，且不是以下节假日：{hs}。某团队在 {start.isoformat()} 当天或之后的第一个工作日开第 1 次会，"
             f"之后每次会议都安排在上一次会议之后的第 {step} 个工作日（例如间隔 2 表示跳过 1 个工作日）。"
             f"第 {n} 次会议是哪一天？答案写成 YYYY-MM-DD。")
        yield f"cal-{i}", q, ans.isoformat()


if __name__ == "__main__":
    with open("reasoning.jsonl", "w") as f:
        for gen in (grid_paths, digits, order_puzzle, dice, calendar):
            for tid, q, a in gen():
                f.write(json.dumps({"id": tid, "prompt": q + FOOT, "answer": a}, ensure_ascii=False) + "\n")
