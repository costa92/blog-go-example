"""Exp4: where num_ctx comes from. usage: python3 exp4.py <port> <logfile|journal> <label>"""
import json, sys, time, re
from ctxlib import *
port, logsrc, tag = int(sys.argv[1]), sys.argv[2], sys.argv[3]
out = open("exp4.jsonl", "a")
p = build_prompt(300)
def logs_since(t, pos):
    if logsrc == "journal":
        return journal_since(t)
    with open(logsrc, errors="replace") as f:
        f.seek(pos); return [l.rstrip() for l in f if "truncating" in l]
cases = [
    ("qwen2.5-coder:7b, no options", lambda: chat("qwen2.5-coder:7b", p, {"temperature": 0, "num_predict": 64}, port)),
    ("qwen-ctx16k-tmp (Modelfile num_ctx 16384), no options", lambda: chat("qwen-ctx16k-tmp", p, {"temperature": 0, "num_predict": 64}, port)),
    ("qwen-ctx16k-tmp + options.num_ctx=4096", lambda: chat("qwen-ctx16k-tmp", p, {"temperature": 0, "num_predict": 64, "num_ctx": 4096}, port)),
    ("qwen-ctx16k-tmp via /v1/chat/completions", lambda: openai_chat("qwen-ctx16k-tmp", p, {"max_tokens": 64}, port)),
    ("qwen2.5-coder:7b via /v1/chat/completions", lambda: openai_chat("qwen2.5-coder:7b", p, {"max_tokens": 64}, port)),
]
for label, f in cases:
    pos = 0
    if logsrc != "journal":
        import os; pos = os.path.getsize(logsrc)
    t = time.time(); code, r = f(); time.sleep(1.5)
    n = r.get("prompt_eval_count") or (r.get("usage") or {}).get("prompt_tokens")
    psout = ps(port); j = logs_since(t, pos)
    out.write(json.dumps({"server": tag, "case": label, "http": code, "prompt_tokens": n, "ps": psout, "journal": j}, ensure_ascii=False) + "\n")
    print(f"[{tag}] {label}: prompt tokens={n}")
    print("   " + psout.splitlines()[-1] if psout else "   (ps empty)")
    for l in j: print("   ", l[l.find("msg="):])
