#!/usr/bin/env python3
"""Send every request once per condition to Ollama /api/chat with a tool catalog.

usage: run.py --model M --out logs/x.jsonl [--n 5,10,20,50,100] [--level name,short,full]
              [--order shuffle] [--nb 1] [--num-ctx 16384] [--think false]

Catalog for request r at size N: the correct tool, its three hard neighbours (--nb 1) and
filler tools taken in a fixed per-request order, so smaller catalogs are prefixes of larger
ones. --nb 0 fills with unrelated tools only. --order shuffle puts the correct tool at a
fixed pseudo-random position; first / last pin it. --num-ctx 0 sends no num_ctx at all.
Conditions already in the output file are skipped, so a run can be resumed.
"""
import argparse, json, random, time, urllib.request

from catalog import TOOLS, render
from cases import REQUESTS, SYSTEM

OLLAMA = "http://127.0.0.1:11434/api/chat"
ALL = [t[0] for t in TOOLS]


def catalog(rid, gold, neighbours, n, nb, order):
    seed = int(rid[1:])
    rest = [t for t in ALL if t != gold and t not in neighbours]
    random.Random(seed).shuffle(rest)
    near = list(neighbours) if nb else []
    tools = [gold] + near + rest[:n - 1 - len(near)]
    assert len(tools) == n and len(set(tools)) == n
    others = tools[1:]
    random.Random(seed * 1000 + n).shuffle(others)
    if order == "first":
        return [gold] + others
    if order == "last":
        return others + [gold]
    tools = others[:]
    tools.insert(random.Random(seed * 7 + n).randrange(n), gold)
    return tools


def call(model, tools, user, num_ctx, think):
    opts = {"temperature": 0, "seed": 1, "num_predict": 512}
    if num_ctx:
        opts["num_ctx"] = num_ctx
    body = {"model": model, "stream": False, "options": opts, "tools": tools,
            "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}]}
    if think is not None:
        body["think"] = think
    req = urllib.request.Request(OLLAMA, json.dumps(body).encode(), {"Content-Type": "application/json"})
    t = time.time()
    with urllib.request.urlopen(req, timeout=600) as r:
        out = json.load(r)
    out["wall_s"] = round(time.time() - t, 3)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--n", default="5,10,20,50,100")
    ap.add_argument("--level", default="name,short,full")
    ap.add_argument("--order", default="shuffle")
    ap.add_argument("--nb", type=int, default=1)
    ap.add_argument("--num-ctx", type=int, default=16384)
    ap.add_argument("--think", choices=["true", "false"])
    ap.add_argument("--only", help="comma separated request ids")
    a = ap.parse_args()
    think = None if a.think is None else a.think == "true"
    done = set()
    try:
        for line in open(a.out):
            r = json.loads(line)
            done.add((r["model"], r["rid"], r["n"], r["level"], r["order"], r["nb"], r["num_ctx"], r["think"]))
    except FileNotFoundError:
        pass
    only = set(a.only.split(",")) if a.only else None
    with open(a.out, "a") as f:
        for n in map(int, a.n.split(",")):
            for level in a.level.split(","):
                for order in a.order.split(","):
                    for rid, user, gold, args, neighbours in REQUESTS:
                        if only and rid not in only:
                            continue
                        key = (a.model, rid, n, level, order, a.nb, a.num_ctx, think)
                        if key in done:
                            continue
                        names = catalog(rid, gold, neighbours, n, a.nb, order)
                        out = call(a.model, [render(x, level) for x in names], user, a.num_ctx, think)
                        msg = out.get("message", {})
                        rec = {"model": a.model, "rid": rid, "n": n, "level": level, "order": order, "nb": a.nb,
                               "num_ctx": a.num_ctx, "think": think, "pos": names.index(gold), "catalog": names,
                               "tool_calls": msg.get("tool_calls") or [], "content": msg.get("content", ""),
                               "thinking": msg.get("thinking", ""),
                               "prompt_eval_count": out.get("prompt_eval_count"), "eval_count": out.get("eval_count"),
                               "prompt_eval_ms": round(out.get("prompt_eval_duration", 0) / 1e6),
                               "eval_ms": round(out.get("eval_duration", 0) / 1e6),
                               "load_ms": round(out.get("load_duration", 0) / 1e6), "wall_s": out["wall_s"]}
                        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                        f.flush()
                        tc = rec["tool_calls"][0]["function"]["name"] if rec["tool_calls"] else "-"
                        print(rid, n, level, order, rec["pos"], tc, rec["prompt_eval_count"], rec["wall_s"], flush=True)


if __name__ == "__main__":
    main()
