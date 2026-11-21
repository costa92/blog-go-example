"""Exp2: task at head vs tail of a truncated prompt (qwen2.5-coder:7b, T=0, 3 runs each)."""
import json, time
from ctxlib import *
M = "qwen2.5-coder:7b"
out = open("exp2.jsonl", "a")
for lines in (300, 663):
    for pos in ("head", "tail"):
        for i in range(3):
            t = time.time(); code, r = chat(M, build_prompt(lines, pos), {"temperature": 0, "num_predict": 512}); time.sleep(1.5)
            j = journal_since(t); txt = content(r); ok = correct(txt)
            out.write(json.dumps({"lines": lines, "pos": pos, "i": i, "http": code, **short(r), "correct": ok,
                                  "raw": txt, "journal": j}, ensure_ascii=False) + "\n"); out.flush()
            print(f"lines={lines} pos={pos} i={i} prompt_eval_count={r.get('prompt_eval_count')} correct={ok} | {txt[:110]!r}")
            for l in j: print("   ", l[l.find("msg="):])
