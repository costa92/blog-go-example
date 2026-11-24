"""按当前 grade.py 和 tasks.jsonl 重新判分并改写日志里的 ok / err：python3 regrade.py logs/*.jsonl
第一轮判分后补过常识题的可接受写法，补完有的首答从错变成对。按实验规则首答对的题不追问 external，
所以这类题原来的 external 追问（当时告诉了模型“答案不正确”）作废，记成 skipped，原回答保存在 voided 字段里。
会执行代码题里模型生成的代码（同 grade.py，没有沙箱）。"""
import json, sys
import grade

for p in sys.argv[1:]:
    rows = [json.loads(l) for l in open(p)]
    base = {}
    for r in rows:
        if r["cond"] == "base":
            r["ok"], r["err"] = grade.check(r["id"], r["out"])
            base[r["id"]] = r["ok"]
    n = 0
    for r in rows:
        if r["cond"] == "base":
            continue
        if r["cond"] == "verifier" and r.get("kept"):
            r["ok"] = base[r["id"]]
            continue
        if r["cond"] == "external" and base[r["id"]]:
            if not r.get("skipped"):
                n += 1
                r["voided"] = {k: r.pop(k) for k in list(r) if k in ("out", "thinking", "wall", "eval_count", "prompt_eval_count", "done_reason", "err")}
                r["skipped"] = True
            r["ok"] = True
            continue
        if r.get("skipped"):
            continue
        r["ok"], r["err"] = grade.check(r["id"], r["out"])
    open(p, "w").write("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
    print(p, "作废的 external 追问", n)
