"""打印一道题的原始对话：python3 show.py logs/<文件>.jsonl fact-05 [条件 ...]，条件默认全部。"""
import json, sys
import grade

path, tid, conds = sys.argv[1], sys.argv[2], sys.argv[3:] or ["base", "reflect", "doubt", "external", "verifier"]
rows = {json.loads(l)["cond"]: json.loads(l) for l in open(path) if json.loads(l)["id"] == tid}
print("题目:", grade.TASKS[tid]["prompt"])
for c in conds:
    r = rows.get(c)
    if not r:
        continue
    print(f"\n## {c}  判定={'对' if r['ok'] else '错'}")
    if r.get("skipped"):
        print("<base 已经答对，不追问>")
        continue
    if c == "verifier":
        print("[审查] " + r["verify"]["out"].strip())
        if r.get("kept"):
            print("<审查没有判错误，保留 base 答案>")
            continue
        print("[改后]")
    print((r.get("out") or "").strip())
    if r.get("err") and not r["ok"]:
        print(f"[测试] {r['err']}")
