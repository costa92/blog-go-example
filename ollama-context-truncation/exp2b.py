"""Exp2b: question at the tail, asking about an early vs a late changelog line (9051-token prompt)."""
import json, time
from ctxlib import *
M = "qwen2.5-coder:7b"
out = open("exp2b.jsonl", "a")
for rel, want, nc in (("1.0.3", "util_3", None), ("29.8", "util_298", None), ("1.0.3", "util_3", 16384)):
    p = ("Below is the project's changelog.\n\n" + filler(300) +
         f"\nQuestion: which module did release 1.{rel} fix? Answer with the module name only.")
    if rel == "1.0.3": p = p.replace("release 1.1.0.3", "release 1.0.3")
    opts = {"temperature": 0, "num_predict": 32}
    if nc: opts["num_ctx"] = nc
    t = time.time(); code, r = chat(M, p, opts); time.sleep(1.5)
    txt = content(r).strip(); j = journal_since(t)
    out.write(json.dumps({"release": rel, "want": want, "num_ctx": nc, **short(r), "answer": txt, "journal": j}, ensure_ascii=False) + "\n")
    print(f"ask release={rel if rel!='29.8' else '1.29.8'} want={want} num_ctx={nc} prompt_eval_count={r.get('prompt_eval_count')} answer={txt!r}")
    for l in j: print("   ", l[l.find("msg="):])
