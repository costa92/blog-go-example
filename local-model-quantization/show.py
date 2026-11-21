"""打印某道题在几个量化版本下的原始输出：python3 show.py json-00 fp16 q3_K_M imat-q3_K_M"""
import json, sys, grade
i, tags = sys.argv[1], sys.argv[2:]
print("题目:", grade.TASKS[i]["prompt"].split("\n")[-1][:90])
for t in tags:
    r = {x["id"]: x for x in grade.load(t)}[i]
    ok, why, _ = grade.grade(r)
    print(f"\n## {t}  判定={'对' if ok else '错'}{'' if ok or not why else ' (' + why + ')'}")
    print(r["out"] if r["out"] else f"<空输出，服务端报错：{r.get('error')}>")
