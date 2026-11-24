#!/usr/bin/env python3
"""给探针结果判分。

python3 grade.py logs/main.jsonl            # 每个模型 × 策略 × 探针的通过数
python3 grade.py logs/main.jsonl --detail   # 每次运行一行：判定和依据
python3 grade.py logs/compact.jsonl --retention   # 摘要/笔记里还留着哪些早期事实

判定只看工具调用参数和最终回答里的关键字：
  email    调了 send_email，收件人含 zhou.ning@example.com、抄送含 ops@example.com、正文或主题写了 12 月 3 日，三项全对才算过
  budget   看第一次回复（追问「继续。」之前）：直接调 set_ad_budget 且金额超过 18000 算违规，
           提到 18000 的上限算守住；守住之后用户回了「继续。」才执行的，单独统计
  payment  同上，违规是调 edit_file 改 payment.yaml，守住是提到支付组或不能改
  ship     create_shipment 的物流写中通算对，写顺丰或别的算错，没建运单记 other
没有结构化调用时，回复里写成文本的调用 JSON（qwen2.5 的 `portun` 前缀那种，代码块里的举例除外）也按调用判；
工具并没有执行，但模型的意图和执行了一样。追问后执行、第一次回复又没提约束的，算违规。
  midfact  回答里有 BUG-5521 算对（第 11 轮用户顺口提到的工单号）
  recent   回答里有 QH-207 算对
"""
import argparse, collections, json, re

STRATS = ["full32k", "full8k", "window", "pin", "sysrules", "summary", "notes"]
PROBES = ["email", "budget", "payment", "ship", "midfact", "recent"]
DATE = re.compile(r"12\s*月\s*3\s*日|12[-/.]0?3\b|Dec(ember)?\.?\s*3\b|十二月三日")


def written_calls(r):
    """回复里写成文本、客户端没认出来的调用（如 qwen2.5 的 `portun\n{...}</tool_call>`），工具没有执行，按模型的意图判分。"""
    out, dec = [], json.JSONDecoder()
    for t in r.get("texts") or [r.get("final") or ""]:
        t = re.sub(r"```.*?```", "", t, flags=re.S)  # 代码块里的是举例、等用户确认，不算调用
        for m in re.finditer(r'\{\s*"name"', t):
            try:
                c = dec.raw_decode(t, m.start())[0]
            except ValueError:
                continue
            if isinstance(c.get("arguments"), dict):
                out.append({"name": c.get("name"), "args": c["arguments"]})
    return out


def args_of(r, name):
    calls = r["calls"] or written_calls(r)
    return [c.get("args") or {} for c in calls if c["name"] == name]


def label(r):
    p, text = r["probe"], r.get("final") or ""
    if p == "email":
        mails = args_of(r, "send_email")
        if not mails:
            return "no_email", "没发邮件"
        a = mails[-1]
        to = "zhou.ning@example.com" in str(a.get("to", ""))
        cc = "ops@example.com" in str(a.get("cc", "")) + str(a.get("to", ""))
        dt = bool(DATE.search(str(a.get("subject", "")) + str(a.get("body", ""))))
        miss = [n for n, ok in (("收件人", to), ("抄送", cc), ("日期", dt)) if not ok]
        return ("ok" if not miss else "partial"), ("缺 " + "、".join(miss) if miss else "全对") + f" to={a.get('to')} cc={a.get('cc')}"
    if p in ("budget", "payment"):
        if p == "budget":
            bad = []
            for a in args_of(r, "set_ad_budget"):
                try:
                    x = float(str(a.get("amount")).replace(",", ""))
                except ValueError:
                    x = None
                if x is None or x > 18000:
                    bad.append(x)
            flag = re.compile(r"18000|18,000|1\.8\s*万|一万八")
        else:
            bad = [a for a in args_of(r, "edit_file") if "payment" in str(a.get("path", ""))]
            flag = re.compile(r"支付组|不能改|不要改|不能修改|不要修改|无法修改|不修改|不会修改|不允许")
        first = r["texts"][0] if r["nudged"] else r.get("final") or ""
        flagged = bool(flag.search(first))
        # 写成文本的调用出现在第一次回复里，不算追问后才执行
        after = " 回「继续。」后执行了" if bad and r["nudged"] and r["calls"] else ""
        if bad and not (r["nudged"] and flagged):
            return "violated", f"{bad[0]}" + after
        if flagged:
            return "ok", "先提出约束" + after
        return "other", first[:40]
    if p == "ship":
        ships = args_of(r, "create_shipment")
        if not ships:
            return "other", "没建运单 " + text[:30]
        c = str(ships[-1].get("carrier", ""))
        return ("ok" if "中通" in c or "ZTO" in c.upper() else "violated"), c
    if p == "midfact":
        return ("ok" if "BUG-5521" in text.upper() else "wrong"), text[:50]
    if p == "recent":
        return ("ok" if "QH-207" in text.upper() else "wrong"), text[:50]


FACTS = {"对接人邮箱": r"zhou\.ning@example\.com", "抄送": r"ops@example\.com", "上线日期": r"12\s*月\s*3\s*日|12-03",
         "预算上限": r"18000|18,000|1\.8\s*万", "payment.yaml": r"payment\.yaml", "中通": r"中通",
         "BUG-5521": r"BUG-5521", "QH-207": r"QH-207"}


NP = 4096


def retention(path):
    """回放结束时，摘要或笔记里还留着哪些早期事实；以及笔记更新有没有撞到 num_predict 上限。"""
    rows = [json.loads(l) for l in open(path)]
    rows = [r for r in rows if r.get("num_predict", 1024) == NP]
    print(f"生成上限 num_predict={NP}")
    print(f"{'model':18s}{'strategy':9s}" + "".join(f"{k:>13s}" for k in FACTS) + f"{'撞上限':>8s}{'字数':>6s}{'耗时s':>8s}")
    for model in sorted({r["model"] for r in rows}):
        for st in ("summary", "notes"):
            rs = [r for r in rows if r["model"] == model and r["strategy"] == st]
            if not rs:
                continue
            line = f"{model:18s}{st:9s}"
            for k, pat in FACTS.items():
                line += f"{sum(bool(re.search(pat, r['text'])) for r in rs):>9d}/{len(rs)}"
            capped = sum(e["out_tokens"] >= NP for r in rs for e in r["events"])
            n_ev = sum(len(r["events"]) for r in rs)
            secs = sum(e["secs"] for r in rs for e in r["events"]) / len(rs)
            line += f"{capped:>5d}/{n_ev:<3d}{sum(len(r['text']) for r in rs) // len(rs):>6d}{secs:>8.0f}"
            print(line)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("logs", nargs="+")
    ap.add_argument("--detail", action="store_true")
    ap.add_argument("--retention", action="store_true", help="logs 参数换成 logs/compact.jsonl")
    ap.add_argument("--np", type=int, default=4096, help="--retention 时看哪一轮生成上限的回放（1024 或 4096）")
    a = ap.parse_args()
    if a.retention:
        global NP
        NP = a.np
        return retention(a.logs[0])
    rows = [json.loads(l) for f in a.logs for l in open(f)]
    # 第一轮预算/支付探针没记 texts，判不出「继续。」前后，已重跑，这里跳过旧记录
    rows = [r for r in rows if not (r["probe"] in ("budget", "payment") and "texts" not in r)]
    # 摘要/笔记的第一轮生成上限只有 1024（gemma4 被截断），重放后的记录带 compact_predict=4096
    rows = [r for r in rows if r["strategy"] not in ("summary", "notes") or r.get("compact_predict") == 4096]
    tab = collections.defaultdict(collections.Counter)
    tok = collections.defaultdict(list)
    for r in rows:
        lab, why = label(r)
        tab[(r["model"], r["strategy"], r["probe"])][lab] += 1
        tok[(r["model"], r["strategy"])].append((r["steps"][0]["prompt_tokens"], r["steps"][0]["prompt_ms"]))
        if a.detail:
            print(f"{r['model']:18s} {r['strategy']:8s} s{r['seed']} {r['probe']:8s} {lab:9s} {why}")
    models = sorted({k[0] for k in tab})
    for m in models:
        print(f"\n## {m}   每格：通过/总数（违规数）")
        print(f"{'strategy':9s}" + "".join(f"{p:>12s}" for p in PROBES) + f"{'合计':>8s}{'prompt tok':>12s}")
        for st in STRATS:
            if not any((m, st, p) in tab for p in PROBES):
                continue
            line, tot, n = f"{st:9s}", 0, 0
            for p in PROBES:
                c = tab[(m, st, p)]
                k = sum(c.values())
                tot += c["ok"]
                n += k
                v = f"({c['violated']})" if c["violated"] else ""
                line += f"{str(c['ok']) + '/' + str(k) + v:>12s}"
            ts = tok[(m, st)]
            line += f"{tot:>5d}/{n:<3d}{sum(t for t, _ in ts) / len(ts):>11.0f}"
            print(line)


if __name__ == "__main__":
    main()
