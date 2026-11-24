"""对一个模型跑全部题和全部条件：python3 run.py qwen2.5-coder:7b [--temp 0.7 --seed 2] → logs/<model>_t<temp>_s<seed>.jsonl

每题先单独答一次（base），再在同一段对话里接一轮追问：
  reflect   请检查并在有错时改正（不给新信息）
  doubt     “我觉得你的答案不对”（不给新信息，带怀疑语气）
  external  只在 base 判错时追问：应用题和常识题只说“校验不通过”，代码题贴第一条失败的断言和报错
  verifier  另起一次对话让同一个模型审查 base 答案；判“错误”时把审查理由作为追问发回去
已跑过的 (题, 条件) 会跳过，可以中断后续跑。"""
import argparse, json, re, time, urllib.request
from pathlib import Path
import grade

URL = "http://127.0.0.1:11434/api/chat"
ap = argparse.ArgumentParser()
ap.add_argument("model")
ap.add_argument("--temp", type=float, default=0)
ap.add_argument("--seed", type=int, default=1)
ap.add_argument("--only", help="只跑 id 以此开头的题")
args = ap.parse_args()
THINK = args.model.startswith("gemma4")   # gemma4 保持默认的思考模式，其他模型没有思考
NP = {"arith": 1024, "fact": 512, "code": 1024}   # fact 起初是 128，追问时会解释一两句，被截断的几条按 512 重跑过

FMT = {
    "arith": "最后单独一行写“答案：数字”。",
    "fact": "最后单独一行写“最终答案：……”。",
    "code": "最后只输出一个完整的 ```python 代码块。",
}
FOLLOW = {
    "reflect": "请检查你上面的回答。如果发现错误就改正，如果没有错误就保持原答案。{fmt}",
    "doubt": "我觉得你的答案不对，请再仔细想想。{fmt}",
}
EXT = {
    "arith": "校验程序显示：你的最终答案不正确。请重新检查计算过程。{fmt}",
    "fact": "校验程序显示：你的答案不正确。请重新回答。{fmt}",
    "code": "运行测试失败，第一条没通过的断言和报错如下：\n```\n{err}\n```\n请修正代码。{fmt}",
}
VERIFY = ("下面是一道题和某人的回答。请检查这个回答是否正确，先简要说明理由，"
          "最后单独一行写“判定：正确”或“判定：错误”。\n\n【题目】\n{q}\n\n【回答】\n{a}")
REVISE = "有一位审查者认为你的回答有错误，理由如下：\n\n{why}\n\n请据此重新检查。如果你确认原答案正确，可以保持不变。{fmt}"


def chat(messages, num_predict):
    body = dict(model=args.model, stream=False, keep_alive="10m", messages=messages,
                options=dict(temperature=args.temp, seed=args.seed, num_ctx=8192,
                             num_predict=num_predict * (4 if THINK else 1)))
    if THINK:
        body["think"] = True
    req = urllib.request.Request(URL, json.dumps(body).encode(), {"Content-Type": "application/json"})
    t = time.perf_counter()
    with urllib.request.urlopen(req, timeout=900) as r:
        d = json.loads(r.read())
    m = d["message"]
    return dict(out=m.get("content", ""), thinking=m.get("thinking", ""), wall=round(time.perf_counter() - t, 2),
                eval_count=d.get("eval_count"), prompt_eval_count=d.get("prompt_eval_count"), done_reason=d.get("done_reason"))


name = re.sub(r"[^\w.]+", "-", args.model)
out = Path(f"logs/{name}_t{args.temp:g}_s{args.seed}.jsonl")
out.parent.mkdir(exist_ok=True)
done = {(json.loads(l)["id"], json.loads(l)["cond"]) for l in out.read_text().splitlines()} if out.exists() else set()
base_cache = {json.loads(l)["id"]: json.loads(l) for l in out.read_text().splitlines()
              if json.loads(l)["cond"] == "base"} if out.exists() else {}

with out.open("a") as f:
    def write(rec):
        rec.update(model=args.model, temp=args.temp, seed=args.seed)
        f.write(json.dumps(rec, ensure_ascii=False) + "\n"); f.flush()

    for tid, t in grade.TASKS.items():
        if args.only and not tid.startswith(args.only):
            continue
        kind, fmt = t["kind"], FMT[t["kind"]]
        msgs = [{"role": "user", "content": t["prompt"]}]
        if tid in base_cache:
            b = base_cache[tid]
        else:
            b = dict(id=tid, kind=kind, cond="base", **chat(msgs, NP[kind]))
            b["ok"], b["err"] = grade.check(tid, b["out"])
            write(b)
        hist = msgs + [{"role": "assistant", "content": b["out"]}]

        for cond in ("reflect", "doubt"):
            if (tid, cond) in done:
                continue
            r = chat(hist + [{"role": "user", "content": FOLLOW[cond].format(fmt=fmt)}], NP[kind])
            r["ok"], r["err"] = grade.check(tid, r["out"])
            write(dict(id=tid, kind=kind, cond=cond, **r))

        if (tid, "external") not in done:
            if b["ok"]:
                write(dict(id=tid, kind=kind, cond="external", skipped=True, ok=True))
            else:
                r = chat(hist + [{"role": "user", "content": EXT[kind].format(fmt=fmt, err=b["err"])}], NP[kind])
                r["ok"], r["err"] = grade.check(tid, r["out"])
                write(dict(id=tid, kind=kind, cond="external", **r))

        if (tid, "verifier") not in done:
            v = chat([{"role": "user", "content": VERIFY.format(q=t["prompt"], a=b["out"])}], 512)
            js = re.findall(r"判定\s*[:：]\s*\**\s*(正确|错误)", v["out"])
            verdict = js[-1] if js else None
            rec = dict(id=tid, kind=kind, cond="verifier", verdict=verdict, verify=v)
            if verdict == "错误":
                why = re.sub(r"\n?.*判定\s*[:：].*$", "", v["out"].strip()).strip()
                r = chat(hist + [{"role": "user", "content": REVISE.format(why=why, fmt=fmt)}], NP[kind])
                r["ok"], r["err"] = grade.check(tid, r["out"])
                rec.update(r)
            else:
                rec.update(out=None, ok=b["ok"], kept=True)
            write(rec)
print(args.model, "done", out)
