"""OLLAMA_NUM_PARALLEL vs concurrent clients: throughput, per-request latency, VRAM.

usage: exp_parallel.py MODEL NUM_CTX OUT.jsonl [NUM_PARALLEL ...]
Extra server env (e.g. OLLAMA_KV_CACHE_TYPE) is taken from BENCH_KV.
"""
import concurrent.futures as cf
import os
import statistics
import sys
import time
import uuid

import lib

MODEL, CTX, OUT = sys.argv[1], int(sys.argv[2]), sys.argv[3]
PARALLEL = [int(x) for x in sys.argv[4:]] or [1, 2, 4]
KV = os.environ.get("BENCH_KV", "")
EXTRA = {"OLLAMA_FLASH_ATTENTION": "1", "OLLAMA_KV_CACHE_TYPE": KV} if KV else {}
CLIENTS = [1, 2, 4, 8]
ROUNDS = 3
NPRED = 200
recs = lib.haystack(400)


def one(k):
    # each request gets its own slice of records and nonce: no shared prefix
    rs = recs[(k * 12) % 380:(k * 12) % 380 + 12]
    p = lib.doc(rs, uuid.uuid4().hex[:8]) + "\n\nWrite a detailed status report covering every project above."
    t = time.time()
    r = lib.gen(MODEL, p, CTX, num_predict=NPRED)
    return {"latency_s": time.time() - t, **lib.rates(r)}


for npar in PARALLEL:
    log = f"logs/server-parallel-{npar}{'-' + KV if KV else ''}.log"
    with lib.Server({"OLLAMA_NUM_PARALLEL": str(npar), **EXTRA}, log):
        info = lib.load(MODEL, CTX, log)
        print("np", npar, info.get("ps"), info.get("n_ctx_slot"), info.get("kv_size"),
              info["vram_delta_mib"], flush=True)
        for nc in CLIENTS:
            for rnd in range(ROUNDS):
                t = time.time()
                with cf.ThreadPoolExecutor(nc) as ex:
                    res = list(ex.map(one, range(rnd * 8, rnd * 8 + nc)))
                wall = time.time() - t
                toks = sum(x["gen_tokens"] for x in res)
                row = {"exp": "parallel", "model": MODEL, "num_ctx": CTX, "num_parallel": npar, "kv": KV or "f16",
                       "clients": nc, "round": rnd, "wall_s": round(wall, 2),
                       "total_gen_tokens": toks, "throughput_tps": round(toks / wall, 1),
                       "latency_median_s": round(statistics.median(x["latency_s"] for x in res), 2),
                       "latency_max_s": round(max(x["latency_s"] for x in res), 2),
                       "per_req_gen_tps_median": statistics.median(x["gen_tps"] for x in res),
                       "vram_mib": lib.gpu_used_mib(), "load": info if rnd == 0 and nc == 1 else None,
                       "requests": res}
                lib.jsonl(OUT, row)
                print(npar, nc, rnd, row["throughput_tps"], row["latency_median_s"], row["latency_max_s"], flush=True)
        lib.unload(MODEL)
