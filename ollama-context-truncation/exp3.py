"""Exp3: same 9051-token prompt through three endpoints, default context."""
import json, time
from ctxlib import *
M = "qwen2.5-coder:7b"
out = open("exp3.jsonl", "a")
p = build_prompt(300)
calls = [
    ("/api/chat", lambda: chat(M, p, {"temperature": 0})),
    ("/api/generate", lambda: generate(M, p, {"temperature": 0})),
    ("/v1/chat/completions", lambda: openai_chat(M, p)),
    ("/v1/chat/completions + options.num_ctx=16384", lambda: openai_chat(M, p, {"options": {"num_ctx": 16384}})),
    ("/v1/chat/completions + num_ctx=16384 (top level)", lambda: openai_chat(M, p, {"num_ctx": 16384})),
]
for label, f in calls:
    t = time.time(); code, r = f(); time.sleep(1.5)
    j = journal_since(t); txt = content(r)
    body = {k: v for k, v in r.items() if k not in ("context",)}
    if "message" in body: body["message"] = {**body["message"], "content": txt[:60] + "..."}
    if "response" in body: body["response"] = txt[:60] + "..."
    if "choices" in body: body["choices"] = [{**c, "message": {**c["message"], "content": txt[:60] + "..."}} for c in body["choices"]]
    out.write(json.dumps({"endpoint": label, "http": code, "correct": correct(txt), "body": body, "journal": j}, ensure_ascii=False) + "\n")
    print(f"== {label} http={code} correct={correct(txt)}")
    print(json.dumps(body, ensure_ascii=False, indent=1))
    for l in j: print("   ", l[l.find("msg="):])
