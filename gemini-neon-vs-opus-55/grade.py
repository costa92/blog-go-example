"""只读 logs/，打印文章里的全部数字：python3 grade.py [reasoning|longctx|coding|cost]"""
import collections
import json
import re
import sys
from fractions import Fraction

MODELS = ["gemini", "claude", "gemini-low"]


def rows(suite):
    try:
        return [r for r in map(json.loads, open(f"logs/{suite}.jsonl")) if "error" not in r]
    except FileNotFoundError:
        return []


def extract(text):
    m = re.findall(r"答案\s*[:：]\s*(.+)", text)
    if not m:
        return None
    a = m[-1].strip().strip("*`「」。. ")
    return re.sub(r"[\s,，*`]", "", a)


def same(got, want):
    if got is None:
        return False
    if "/" in want:
        try:
            return Fraction(got) == Fraction(want)
        except (ValueError, ZeroDivisionError):
            return False
    return got.upper() == want.upper()


def reasoning():
    want = {t["id"]: t["answer"] for t in map(json.loads, open("reasoning.jsonl"))}
    by = collections.defaultdict(list)
    for r in rows("reasoning"):
        by[(r["model"], r["id"].split("-")[0])].append(same(extract(r["text"]), want[r["id"]]))
    cats = sorted({c for _, c in by})
    print("类别".ljust(8), *(m.ljust(12) for m in MODELS))
    tot = collections.Counter(), collections.Counter()
    for c in cats:
        cells = []
        for m in MODELS:
            v = by[(m, c)]
            tot[0][m] += sum(v)
            tot[1][m] += len(v)
            cells.append(f"{sum(v)}/{len(v)}".ljust(12))
        print(c.ljust(8), *cells)
    print("合计".ljust(8), *(f"{tot[0][m]}/{tot[1][m]}".ljust(12) for m in MODELS))
    # 两轮都对 / 只对一轮 / 都错
    per = collections.defaultdict(list)
    for r in rows("reasoning"):
        per[(r["model"], r["id"])].append(same(extract(r["text"]), want[r["id"]]))
    for m in MODELS:
        c = collections.Counter(sum(v) for (mm, _), v in per.items() if mm == m)
        print(m, "两轮都对", c[2], "只对一轮", c[1], "都错", c[0])
    for m in MODELS:
        wrong = sorted(i for (mm, i), v in per.items() if mm == m and not all(v))
        print(m, "有错的题：", " ".join(wrong))


def parse_json(text):
    m = re.search(r"\{.*\}", text, re.S)
    try:
        return json.loads(m.group(0)) if m else None
    except json.JSONDecodeError:
        return None


def longctx():
    want = {}
    import glob
    for p in sorted(glob.glob("longctx/*.json")):
        d = json.load(open(p))
        want[d["id"]] = d["answer"]
    for r in sorted(rows("longctx"), key=lambda r: (r["id"], r["model"], r["run"])):
        w, got = want[r["id"]], parse_json(r["text"])
        if got is None:
            print(r["id"], r["model"], r["run"], "无法解析", r["text"][:200])
            continue
        q = {str(k).lower(): v for k, v in got.get("quotas", {}).items()}
        hit = sum(1 for s, v in w["quotas"].items() if q.get(s) == v)
        extra = sorted(set(q) - set(w["quotas"]))
        print(r["id"], r["model"], r["run"], f"配额对 {hit}/8", "多报:" + ",".join(extra) if extra else "",
              "总和对" if got.get("total") == w["total"] else f"总和错({got.get('total')} vs {w['total']})",
              "最大对" if got.get("max_service") == w["max_service"] else "最大错",
              f"输入 {r['input_tokens']} tok", f"{r['latency_s']:.1f}s", f"${r['cost_usd']:.3f}")


def coding():
    res = [json.loads(l) for l in open("logs/coding-tests.jsonl")]
    tasks = sorted({r["id"] for r in res})
    print("题目".ljust(12), *(m.ljust(22) for m in MODELS))
    tot = {m: [0, 0, 0, 0] for m in MODELS}  # 全过次数, 回答数, 通过测试数, 测试总数
    for t in tasks:
        cells = []
        for m in MODELS:
            rs = [r for r in res if r["id"] == t and r["model"] == m]
            full = sum(r["passed"] == r["tests"] for r in rs)
            pt, tt = sum(r["passed"] for r in rs), sum(r["tests"] for r in rs)
            for i, v in enumerate((full, len(rs), pt, tt)):
                tot[m][i] += v
            cells.append(f"全过 {full}/{len(rs)} 测试 {pt}/{tt}".ljust(22))
        print(t.ljust(12), *cells)
    print("合计".ljust(12), *(f"全过 {v[0]}/{v[1]} 测试 {v[2]}/{v[3]}".ljust(22) for v in tot.values()))
    for r in res:
        if r["passed"] < r["tests"]:
            print("  未全过:", r["id"], r["model"], r["run"], r["status"], ",".join(r.get("failed_tests", [])), r.get("stderr", "")[:150].replace("\n", " "))


def median(v):
    v = sorted(v)
    return (v[len(v) // 2] + v[(len(v) - 1) // 2]) / 2 if v else 0


def cost():
    print("套题".ljust(10), "模型".ljust(7), "调用", "延迟中位数s", "输出tok中位数", "其中思考", "总成本$", "每次$")
    for s in ("coding", "reasoning", "longctx"):
        for m in MODELS:
            rs = [r for r in rows(s) if r["model"] == m]
            if s == "longctx":  # 第二轮命中提示缓存，延迟只看冷启动的第一轮
                lat = [r["latency_s"] for r in rs if r["run"] == 0]
            else:
                lat = [r["latency_s"] for r in rs]
            print(s.ljust(10), m.ljust(7), len(rs), f"{median(lat):.1f}".rjust(10),
                  f"{median([r['output_tokens'] for r in rs]):.0f}".rjust(12),
                  f"{median([r['thinking_tokens'] for r in rs]):.0f}".rjust(8),
                  f"{sum(r['cost_usd'] for r in rs):.2f}".rjust(9),
                  f"{sum(r['cost_usd'] for r in rs) / max(len(rs), 1):.4f}".rjust(8))


if __name__ == "__main__":
    {"reasoning": reasoning, "longctx": longctx, "coding": coding, "cost": cost}[sys.argv[1] if len(sys.argv) > 1 else "reasoning"]()
