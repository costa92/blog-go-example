"""Exp5: cost of num_ctx for qwen2.5-coder:7b (VRAM sampled separately by nvidia-smi -l 1)."""
import json, subprocess, sys, time, random
from ctxlib import *
M = "qwen2.5-coder:7b"
out = open("exp5.jsonl", "a")
GEN = "Explain in detail, in about 600 words, how a hash table handles collisions. Plain text, no code."
def rate(n, ns): return round(n / (ns / 1e9), 1) if n and ns else None
for nc in [int(x) for x in sys.argv[1].split(",")]:
    subprocess.run(["ollama", "stop", M], capture_output=True); time.sleep(3)
    t0 = time.time()
    rec = {"num_ctx": nc, "t_start": t0}
    o = {"temperature": 0, "num_ctx": nc}
    c, r = chat(M, "hi", {**o, "num_predict": 4}); rec["load_s"] = round(r.get("load_duration", 0) / 1e9, 2)
    rec["ps"] = ps().splitlines()[-1]
    runs = []
    for i in range(2):
        nonce = f"Run {random.randint(0, 1 << 30)}.\n"
        c, r = chat(M, nonce + build_prompt(105), {**o, "num_predict": 32})
        c2, g = chat(M, nonce + GEN, {**o, "num_predict": 400})
        runs.append({"pe_tokens": r.get("prompt_eval_count"), "pe_cached": r.get("prompt_eval_cached_count"),
                     "pe_tok_s": rate(r.get("prompt_eval_count"), r.get("prompt_eval_duration")),
                     "gen_tokens": g.get("eval_count"), "gen_tok_s": rate(g.get("eval_count"), g.get("eval_duration"))})
    rec["runs"] = runs
    if nc >= 32768:
        nonce = f"Run {random.randint(0, 1 << 30)}.\n"
        c, r = chat(M, nonce + build_prompt(663), {**o, "num_predict": 200})
        rec["long"] = {"pe_tokens": r.get("prompt_eval_count"), "pe_tok_s": rate(r.get("prompt_eval_count"), r.get("prompt_eval_duration")),
                       "gen_tokens": r.get("eval_count"), "gen_tok_s": rate(r.get("eval_count"), r.get("eval_duration"))}
    rec["t_end"] = time.time()
    out.write(json.dumps(rec, ensure_ascii=False) + "\n"); out.flush()
    print(json.dumps(rec, ensure_ascii=False))
subprocess.run(["ollama", "stop", M], capture_output=True)
