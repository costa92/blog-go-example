"""打印某道题在某个日志里的原始输出：python3 show.py logs/qwen2.5-coder-3b_plain_t0_s1.jsonl m31 [m32 ...]"""
import json
import sys

from judge import answer_line, confidence, correct, valid

tasks = {t["id"]: t for t in map(json.loads, open("tasks.jsonl", encoding="utf-8"))}
log = {r["id"]: r for r in map(json.loads, open(sys.argv[1], encoding="utf-8"))}
for i in sys.argv[2:]:
    t, r = tasks[i], log[i]
    print(f"## {i} {t['kind']}  标准答案={json.dumps(t['answer'], ensure_ascii=False)}")
    print(r["out"].rstrip())
    print(f"-- 取到的答案={answer_line(r['out'])!r}  格式校验={'过' if valid(t, r['out']) else '不过'}  "
          f"判分={'对' if correct(t, r['out']) else '错'}" + (f"  把握={confidence(r['out'])}" if r["mode"] == "conf" else ""))
    print()
