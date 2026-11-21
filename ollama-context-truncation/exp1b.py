"""Exp1b: shift/truncate request flags, and whole-message dropping in multi-turn chat."""
import json, sys, time
from ctxlib import *
M = "qwen2.5-coder:7b"
out = open("exp1b.jsonl", "a")
def run(label, body_extra, opts, msgs=None):
    body = {"model": M, "stream": False, "options": opts}
    body["messages"] = msgs or [{"role": "system", "content": SYSTEM}, {"role": "user", "content": build_prompt(300)}]
    body.update(body_extra)
    t = time.time(); code, r = post("http://127.0.0.1:11434/api/chat", body); time.sleep(1.5)
    j = journal_since(t); txt = content(r) if code == 200 else ""
    rec = {"label": label, "extra": body_extra, "options": opts, "http": code, **short(r), "head": txt[:200], "journal": j}
    out.write(json.dumps(rec, ensure_ascii=False) + "\n"); out.flush()
    print(f"[{label}] http={code} prompt_eval_count={r.get('prompt_eval_count')} error={r.get('error')}")
    print("   reply:", txt[:160].replace("\n", " | "))
    for l in j: print("   ", l[l.find("level="):] if "level=" in l else l)

o = {"temperature": 0, "num_predict": 128, "num_ctx": 4096}
run("shift=false", {"shift": False}, o)
run("truncate=false", {"truncate": False}, o)
rule = ("Project rule: every function you write must be named with the prefix `cv_`, "
        "e.g. `cv_checksum`. Acknowledge with OK.\n\nChangelog part 1:\n\n" + filler(60))
part2 = "Changelog part 2:\n\n" + filler(70) + "\nNow write a Python function that returns the sum of all bytes modulo 251. " + FMT
msgs = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": rule},
        {"role": "assistant", "content": "OK"}, {"role": "user", "content": part2}]
run("multi-turn ctx=4096", {}, o, msgs)
run("multi-turn ctx=8192", {}, {**o, "num_ctx": 8192}, msgs)
