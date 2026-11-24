"""Long-context retrieval under different KV cache types.

The registry is sent once per config; questions only change the tail, so the
prefix cache keeps the per-question cost low. Every question asks for a 5-digit
door code from a record at a different depth; answers are exact-match graded.

usage: exp_quality.py MODEL NUM_CTX N_RECORDS N_QUESTIONS OUT.jsonl [label ...]
"""
import os
import re
import sys

import lib

MODEL, CTX, NREC, NQ, OUT = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4]), sys.argv[5]
ALL = {
    "default": {},
    "q8_0": {"OLLAMA_FLASH_ATTENTION": "1", "OLLAMA_KV_CACHE_TYPE": "q8_0"},
    "q4_0": {"OLLAMA_FLASH_ATTENTION": "1", "OLLAMA_KV_CACHE_TYPE": "q4_0"},
}
labels = sys.argv[6:] or list(ALL)
SEED = int(os.environ.get("HAYSTACK_SEED", "7"))
recs = lib.haystack(NREC, SEED)
body = lib.doc(recs, "fixed")
# evenly spaced depths, first and last record included
targets = [recs[round(i * (NREC - 1) / (NQ - 1))] for i in range(NQ)]

for label in labels:
    NG = os.environ.get("BENCH_NUM_GPU", "")
    log = f"logs/server-quality-{label}-{CTX}-s{SEED}{'-ngl' + NG if NG else ''}.log"
    with lib.Server(ALL[label], log):
        info = lib.load(MODEL, CTX, log)
        right = 0
        for q in targets:
            r = lib.gen(MODEL, body + lib.question(q), CTX, num_predict=12)
            got = re.findall(r"\d{5}", r["response"])
            ok = bool(got) and got[0] == q["code"]
            right += ok
            lib.jsonl(OUT, {"exp": "quality", "model": MODEL, "config": label + (f"-ngl{NG}" if NG else ""), "num_ctx": CTX, "seed": SEED,
                            "record": q["i"], "depth": round(q["i"] / (NREC - 1), 3),
                            "expected": q["code"], "response": r["response"].strip()[:60],
                            "correct": ok, **lib.rates(r)})
        lib.jsonl(OUT, {"exp": "quality_summary", "model": MODEL, "config": label + (f"-ngl{NG}" if NG else ""), "num_ctx": CTX, "seed": SEED,
                        "n_records": NREC, "questions": NQ, "correct": right,
                        "ps": info["ps"], "offloaded": info.get("offloaded"),
                        "kv_size": info.get("kv_size"), "vram_delta_mib": info["vram_delta_mib"]})
        print(label, CTX, SEED, f"{right}/{NQ}", info["ps"], flush=True)
        lib.unload(MODEL)
