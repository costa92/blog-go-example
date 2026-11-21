import json
from bench import gen_minimax, score, extract
from tasks import TASKS, SUFFIX
T = {t["id"]: t for t in TASKS}
fo = open("det_minimax.jsonl", "a")
def pattern(xs):
    ids = {}; return "".join(chr(65 + ids.setdefault(x, len(ids))) for x in xs)
for model, temp, seed in [("MiniMax-M3", 0.0, 42), ("MiniMax-M2.5", 0.0, None), ("MiniMax-M2.5", 1.0, None)]:
    for tid in ["roman", "wrap"]:
        raws, codes = [], []
        for _ in range(5):
            try:
                raw, meta = gen_minimax(model, T[tid]["prompt"] + SUFFIX, temp, seed)
            except Exception as e:
                raw, meta = "", {"error": str(e)[:300]}
            s = score(T[tid], raw)
            fo.write(json.dumps({"model": model, "task": tid, "temp": temp, "seed": seed, "raw": raw, **meta, **s}, ensure_ascii=False) + "\n"); fo.flush()
            raws.append(raw); codes.append(s["norm"])
        print(model, tid, "temp", temp, "seed", seed, "raw", pattern(raws), "code", pattern(codes), flush=True)
