"""Exp1: truncation rule. usage: python3 exp1.py <out.jsonl> <spec>... ; spec = num_ctx:lines[:num_predict[:num_keep]]"""
import json, sys, time
from ctxlib import *
M = "qwen2.5-coder:7b"
out = open(sys.argv[1], "a")
for spec in sys.argv[2:]:
    p = spec.split(":")
    nc = None if p[0] == "default" else int(p[0]); lines = int(p[1])
    npred = int(p[2]) if len(p) > 2 and p[2] else 128
    opts = {"temperature": 0, "num_predict": npred}
    if nc: opts["num_ctx"] = nc
    if len(p) > 3: opts["num_keep"] = int(p[3])
    t = time.time(); code, r = chat(M, build_prompt(lines), opts); time.sleep(1.5)
    j = journal_since(t)
    txt = content(r)
    rec = {"num_ctx": nc, "lines": lines, "options": opts, "http": code, **short(r), "correct": correct(txt),
           "head": txt[:120], "journal": j}
    out.write(json.dumps(rec, ensure_ascii=False) + "\n"); out.flush()
    print(f"num_ctx={nc} lines={lines} opts={opts} http={code} prompt_eval_count={r.get('prompt_eval_count')} correct={rec['correct']}")
    for l in j: print("   ", l[l.find("level="):] if "level=" in l else l)
