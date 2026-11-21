"""Determinism probes. usage: python3 det.py <ollama-model> <out.jsonl>"""
import json, sys
from bench import gen_ollama, score
from tasks import TASKS, SUFFIX

model, out = sys.argv[1], sys.argv[2]
T = {t["id"]: t for t in TASKS}
fo = open(out, "a")


def run(exp, tid, temp, seed=None, extra=None):
    raw, meta = gen_ollama(model, T[tid]["prompt"] + SUFFIX, temp, seed, extra)
    rec = {"exp": exp, "model": model, "task": tid, "temp": temp, "seed": seed,
           "extra": extra, "raw": raw, **meta, **score(T[tid], raw)}
    fo.write(json.dumps(rec, ensure_ascii=False) + "\n"); fo.flush()
    return raw


def pattern(raws):
    ids = {}
    return "".join(chr(65 + ids.setdefault(r, len(ids))) for r in raws)


for tid in ["roman", "brackets", "spiral", "wrap"]:
    # same prompt six times in a row (prompt cache warm after the first)
    rep = [run("repeat", tid, 0.0) for _ in range(6)]
    # alternate with another prompt so the cached prefix keeps changing
    inter = []
    for _ in range(6):
        run("filler", "semver", 0.0)
        inter.append(run("interleave", tid, 0.0))
    print(tid, "repeat", pattern(rep), "interleave", pattern(inter),
          "repeat[0]==interleave[0]", rep[0] == inter[0], flush=True)

for tid in ["roman", "wrap"]:
    for seed in [None, 42]:
        for temp in [0.0, 0.8]:
            raws = [run("seed", tid, temp, seed) for _ in range(6)]
            print(tid, "seed", seed, "temp", temp, pattern(raws), flush=True)
