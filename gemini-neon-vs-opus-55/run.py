"""跑一套题：python3 run.py <coding|reasoning|longctx> <gemini|claude|both|gemini-low> [--runs N] [--jobs N]

每次调用写一行到 logs/<suite>.jsonl（含原始回答），已存在的 (id, model, run) 会跳过，可中断续跑。
"""
import argparse
import concurrent.futures as cf
import glob
import json
import os
import threading

from clients import CALL


def load(suite):
    if suite == "reasoning":
        return [json.loads(l) for l in open("reasoning.jsonl")]
    if suite == "longctx":
        return [json.load(open(p)) for p in sorted(glob.glob("longctx/*.json"))]
    tasks = []
    for d in sorted(glob.glob("coding/*/prompt.md")):
        tasks.append({"id": d.split("/")[1], "prompt": open(d).read()})
    return tasks


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("suite", choices=["coding", "reasoning", "longctx"])
    ap.add_argument("model", choices=["gemini", "claude", "both", "gemini-low"])
    ap.add_argument("--runs", type=int, default=1)
    ap.add_argument("--jobs", type=int, default=4)
    a = ap.parse_args()
    os.makedirs("logs", exist_ok=True)
    path = f"logs/{a.suite}.jsonl"
    done = set()
    if os.path.exists(path):
        for l in open(path):
            r = json.loads(l)
            if "error" not in r:
                done.add((r["id"], r["model"], r["run"]))
    models = ["gemini", "claude"] if a.model == "both" else [a.model]
    jobs = [(t, m, k) for k in range(a.runs) for t in load(a.suite) for m in models if (t["id"], m, k) not in done]
    print(f"{len(jobs)} calls to make")
    lock = threading.Lock()

    def one(job):
        t, m, k = job
        r = CALL[m](t["prompt"])
        r.update(id=t["id"], model=m, run=k)
        with lock, open(path, "a") as f:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
        print(t["id"], m, k, "ERROR " + r["error"][:120] if "error" in r else f"{r['latency_s']:.1f}s", flush=True)

    with cf.ThreadPoolExecutor(a.jobs) as ex:
        list(ex.map(one, jobs))


if __name__ == "__main__":
    main()
