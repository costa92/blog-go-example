"""num_ctx x KV cache type: VRAM, CPU/GPU split, load time, prompt/gen speed.

usage: exp_ctx_kv.py MODEL OUT.jsonl
"""
import sys
import time
import uuid

import lib

MODEL, OUT = sys.argv[1], sys.argv[2]
CTXS = [4096, 8192, 16384, 32768, 65536]
CONFIGS = [  # label, server env
    ("fa-off-f16", {"OLLAMA_FLASH_ATTENTION": "0"}),
    ("default", {}),
    ("q8_0", {"OLLAMA_FLASH_ATTENTION": "1", "OLLAMA_KV_CACHE_TYPE": "q8_0"}),
    ("q4_0", {"OLLAMA_FLASH_ATTENTION": "1", "OLLAMA_KV_CACHE_TYPE": "q4_0"}),
]
REPS = 3
recs = lib.haystack(1100)
short_doc = recs[:80]  # about 3.5k tokens

for label, env in CONFIGS:
    log = f"logs/server-{label}.log"
    with lib.Server(env, log):
        for ctx in CTXS:
            info = lib.load(MODEL, ctx, log)
            row = {"exp": "ctx_kv", "model": MODEL, "config": label, "env": env, "num_ctx": ctx,
                   **info, "runs": []}
            prompts = [("short", short_doc, 128)]
            if ctx >= 32768:  # long prompt fills about two thirds of the window
                n = 500 if ctx == 32768 else 1000
                prompts.append(("long", recs[:n], 64))
            for kind, rs, npred in prompts:
                for rep in range(REPS):
                    p = lib.doc(rs, uuid.uuid4().hex[:8]) + "\n\nSummarize the registry in a long paragraph."
                    r = lib.gen(MODEL, p, ctx, num_predict=npred)
                    row["runs"].append({"kind": kind, "rep": rep, **lib.rates(r),
                                        "vram_mib": lib.gpu_used_mib()})
            lib.jsonl(OUT, row)
            print(label, ctx, info.get("ps"), info.get("offloaded"), info["vram_delta_mib"],
                  [(x["kind"], x["prompt_tps"], x["gen_tps"]) for x in row["runs"]], flush=True)
        lib.unload(MODEL)
