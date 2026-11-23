"""测 Ollama 在小、大两个模型之间来回切换的代价，写 logs/swap.jsonl。

每个场景开始前先把所有已加载模型卸掉，然后交替请求 small / big 各 N 次，
记录每次的 load_duration、总耗时，以及请求后 /api/ps 里两个模型是否还在显存里。

    python3 swap.py qwen2.5-coder:3b qwen2.5-coder:7b
"""
import json
import sys
import time
import urllib.request
from pathlib import Path

HOST = "http://127.0.0.1:11434"
small, big = sys.argv[1], sys.argv[2]
N = 6
PROMPT = "12 + 30 等于多少？只回答数字。"


def call(path, body=None):
    req = urllib.request.Request(HOST + path, json.dumps(body).encode() if body is not None else None,
                                 {"Content-Type": "application/json"})
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=600) as r:
        d = json.loads(r.read())
    return d, time.perf_counter() - t0


def unload_all():
    ps, _ = call("/api/ps")
    for m in ps.get("models", []):
        call("/api/generate", dict(model=m["name"], keep_alive=0))
    for _ in range(50):
        if not call("/api/ps")[0].get("models"):
            return
        time.sleep(0.2)


def resident():
    return {m["name"]: m.get("size_vram") for m in call("/api/ps")[0].get("models", [])}


SCENARIOS = [
    # 名字, 小模型参数, 大模型参数
    ("都常驻（keep_alive 30m，num_ctx 4096）", dict(keep_alive="30m", ctx=4096), dict(keep_alive="30m", ctx=4096)),
    ("大模型用完就卸（keep_alive 0）", dict(keep_alive="30m", ctx=4096), dict(keep_alive=0, ctx=4096)),
    ("大模型 num_ctx 32768", dict(keep_alive="30m", ctx=4096), dict(keep_alive="30m", ctx=32768)),
]

with open("logs/swap.jsonl", "a") as f:
    for name, ps_, pb in SCENARIOS:
        unload_all()
        for k in range(N):
            for model, p in ((small, ps_), (big, pb)):
                d, wall = call("/api/chat", dict(model=model, stream=False, keep_alive=p["keep_alive"],
                                                 messages=[{"role": "user", "content": PROMPT}],
                                                 options=dict(temperature=0, seed=1, num_ctx=p["ctx"], num_predict=8)))
                rec = dict(scenario=name, round=k, model=model, wall=round(wall, 3),
                           load=round(d.get("load_duration", 0) / 1e9, 3), resident=resident(), ts=time.time())
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                f.flush()
                print(f"{name} #{k} {model:20s} load {rec['load']:6.2f}s  wall {wall:6.2f}s  ps={rec['resident']}")
    unload_all()
