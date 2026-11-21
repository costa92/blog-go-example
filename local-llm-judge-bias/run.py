"""本地模型当裁判的偏差实验。用法: python3 run.py <cond> [judge...]
每条调用写一行 jsonl 到 logs/<cond>.jsonl；已有的 key 会跳过，可断点续跑。"""
import json, re, sys, time, urllib.request
from pathlib import Path
import items as I

URL = "http://127.0.0.1:11434/api/chat"
JUDGES = ["gemma4:latest", "llama3.1:8b", "qwen2.5-coder:7b"]

PAIR = "下面是一个问题和两个回答。\n\n问题：{q}\n\n回答 A：\n{a}\n\n回答 B：\n{b}\n\n哪个回答更好？只输出 A 或 B，不要输出其他内容。"
REASON = ("下面是一个问题和两个回答。\n\n问题：{q}\n\n回答 A：\n{a}\n\n回答 B：\n{b}\n\n"
          "请按这个标准评判：事实是否正确最重要，其次是否直接回答了问题；篇幅和格式不加分。"
          "先逐条检查两个回答里的说法是否正确，写出你的分析，最后单独一行写“结论：A”或“结论：B”。")
RUBRIC = ("下面是一个问题和两个回答。\n\n问题：{q}\n\n回答 A：\n{a}\n\n回答 B：\n{b}\n\n"
          "请按这个标准评判：事实是否正确最重要，其次是否直接回答了问题；篇幅和格式不加分。只输出 A 或 B，不要输出其他内容。")
POINT = ("下面是一个问题和一个回答。\n\n问题：{q}\n\n回答：\n{a}\n\n"
         "请给这个回答打分，1 到 10 分的整数。标准：事实是否正确最重要，其次是否直接回答了问题；篇幅和格式不加分。只输出分数。")

def chat(model, prompt, temp=0.0, seed=1, num_predict=8, think=False, logprobs=False):
    body = {"model": model, "messages": [{"role": "user", "content": prompt}], "stream": False,
            "options": {"temperature": temp, "seed": seed, "num_predict": num_predict}}
    if logprobs:
        body.update(logprobs=True, top_logprobs=10)
    if model.startswith("gemma4"):
        body["think"] = think
    req = urllib.request.Request(URL, json.dumps(body).encode(), {"Content-Type": "application/json"})
    t = time.time()
    r = json.load(urllib.request.urlopen(req, timeout=900))
    if logprobs:
        top = r["logprobs"][0]["top_logprobs"]
        return r["message"]["content"], {x["token"]: x["logprob"] for x in top}, round(time.time() - t, 2)
    return r["message"]["content"], r["message"].get("thinking", ""), round(time.time() - t, 2)

def parse_pair(out, reason=False):
    if reason:
        m = re.findall(r"结论[*\s]*[：:][*\s]*([AB])", out)
        return m[-1] if m else None
    s = out.strip().strip("*` \n")
    if s[:1] in ("A", "B"):
        return s[0]
    m = re.findall(r"\b([AB])\b", out)
    return m[-1] if len(set(m)) == 1 else None

def parse_score(out):
    m = re.search(r"\d+", out)
    return int(m.group()) if m else None

# 每种变体返回 (good 一侧文本, bad 一侧文本)；fmt-tie 两边内容都是 good，"good" 侧放纯文本、"bad" 侧放 markdown
VARIANTS = {
    "base": lambda it: (I.plain(it["good"]), I.plain(it["bad"])),
    "length": lambda it: (I.plain(it["good"]), I.padded(it)),
    "badmd": lambda it: (I.plain(it["good"]), I.md(it["bad"])),
    "goodmd": lambda it: (I.md(it["good"]), I.plain(it["bad"])),
    "tie": lambda it: (I.plain(it["good"]), I.md(it["good"])),
}

def pair_tasks(variants, mode="naive", temps=((0.0, 1),), think=False):
    for v in variants:
        for it in I.ITEMS:
            g, b = VARIANTS[v](it)
            for order in ("GB", "BG"):
                a, bb = (g, b) if order == "GB" else (b, g)
                for temp, seed in temps:
                    yield dict(kind="pair", mode=mode, variant=v, item=it["id"], order=order, temp=temp, seed=seed,
                               think=think, prompt={"reason": REASON, "rubric": RUBRIC, "lprubric": RUBRIC}.get(mode, PAIR).format(q=it["q"], a=a, b=bb))

def point_tasks():
    texts = {"good": lambda it: I.plain(it["good"]), "bad": lambda it: I.plain(it["bad"]),
             "padded": I.padded, "badmd": lambda it: I.md(it["bad"]), "goodmd": lambda it: I.md(it["good"])}
    for name, f in texts.items():
        for it in I.ITEMS:
            yield dict(kind="point", mode="point", variant=name, item=it["id"], order="-", temp=0.0, seed=1,
                       think=False, prompt=POINT.format(q=it["q"], a=f(it)))

def self_gen_tasks():
    for i, q in enumerate(I.SELF_QS):
        yield dict(kind="gen", mode="gen", variant="self", item=f"s{i}", order="-", temp=0.0, seed=1, think=False,
                   prompt=q + "\n\n请用中文回答，控制在 150 字以内。")

def self_judge_tasks():
    gens = {}
    for l in Path("logs/selfgen.jsonl").read_text().splitlines():
        r = json.loads(l)
        gens[(r["judge"], r["item"])] = r["out"].strip()
    for i, q in enumerate(I.SELF_QS):
        for x in range(3):
            for y in range(x + 1, 3):
                mx, my = JUDGES[x], JUDGES[y]
                for order in ("XY", "YX"):
                    a, b = (gens[(mx, f"s{i}")], gens[(my, f"s{i}")]) if order == "XY" else (gens[(my, f"s{i}")], gens[(mx, f"s{i}")])
                    yield dict(kind="pair", mode="naive", variant=f"{mx}|{my}", item=f"s{i}", order=order, temp=0.0, seed=1,
                               think=False, prompt=PAIR.format(q=q, a=a, b=b))

CONDS = {
    "naive": lambda: pair_tasks(["base", "length", "badmd", "goodmd", "tie"]),
    "reason": lambda: pair_tasks(["base", "length"], mode="reason"),
    "point": point_tasks,
    "temp07": lambda: pair_tasks(["base"], temps=((0.7, 1), (0.7, 2), (0.7, 3))),
    "selfgen": self_gen_tasks,
    "selfjudge": self_judge_tasks,
    "rubric": lambda: pair_tasks(["base", "length", "badmd", "tie"], mode="rubric"),
    "lp": lambda: pair_tasks(["base", "length", "badmd", "tie"], mode="lp"),
    "lprubric": lambda: pair_tasks(["base", "length", "badmd", "tie"], mode="lprubric"),
    "think": lambda: pair_tasks(["base", "length"], think=True),
}

def key(t, judge):
    return "|".join(str(t[k]) for k in ("mode", "variant", "item", "order", "temp", "seed", "think")) + "|" + judge

def main():
    cond = sys.argv[1]
    judges = sys.argv[2:] or JUDGES
    if cond == "think":
        judges = ["gemma4:latest"]
    path = Path(f"logs/{cond}.jsonl")
    done = set()
    if path.exists():
        done = {json.loads(l)["key"] for l in path.read_text().splitlines()}
    path.parent.mkdir(exist_ok=True)
    with path.open("a") as f:
        for judge in judges:
            n = 0
            for t in CONDS[cond]():
                k = key(t, judge)
                if k in done:
                    continue
                npred = {"reason": 700, "gen": 400}.get(t["mode"], 8)
                if t["think"]:
                    npred = 4096
                lpmode = t["mode"].startswith("lp")
                out, thinking, sec = chat(judge, t["prompt"], t["temp"], t["seed"], 1 if lpmode else npred, t["think"], lpmode)
                rec = {**{k2: v for k2, v in t.items() if k2 != "prompt"}, "judge": judge, "key": k, "out": out, "sec": sec}
                if lpmode:
                    # 第一个生成 token 的 top-10 对数概率；Ollama 返回的是未经温度缩放的分布
                    rec["top"], thinking = thinking, ""
                if t["kind"] == "pair":
                    rec["pick"] = parse_pair(out + ("" if t["mode"] != "reason" else ""), t["mode"] == "reason") if not t["think"] else parse_pair(out)
                    if t["variant"] in VARIANTS:
                        # good 一侧在 A 还是 B
                        rec["good_pos"] = "A" if t["order"] == "GB" else "B"
                elif t["kind"] == "point":
                    rec["score"] = parse_score(out)
                if thinking:
                    rec["thinking_chars"] = len(thinking)
                f.write(json.dumps(rec, ensure_ascii=False) + "\n"); f.flush()
                n += 1
            print(cond, judge, "new", n, flush=True)

if __name__ == "__main__":
    main()
