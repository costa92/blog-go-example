"""真跑一遍级联：小模型先答，不满足规则就把同一题交给大模型。记录每题端到端耗时，写 logs/cascade.jsonl。

    python3 cascade.py <小模型> <大模型> <规则> <大模型 keep_alive>
    规则: small | big | valid | lp:-0.1 | lp+valid:-0.1
    例: python3 cascade.py qwen2.5-coder:3b qwen2.5-coder:7b lp+valid:-0.1 30m

开始前卸掉所有已加载模型，再各预热一次，计时只包括 150 道题本身。
"""
import json
import sys
import time
import urllib.request
from pathlib import Path

from grade import answer_logprob
from judge import correct, valid

HOST = "http://127.0.0.1:11434"
small, big, rule, big_ka = sys.argv[1:5]
big_ka = 0 if big_ka == "0" else big_ka


def post(path, body):
    req = urllib.request.Request(HOST + path, json.dumps(body).encode(), {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as r:
        return json.loads(r.read())


def chat(model, content, ka):
    t0 = time.perf_counter()
    d = post("/api/chat", dict(model=model, stream=False, keep_alive=ka, logprobs=True,
                                messages=[{"role": "user", "content": content}],
                                options=dict(temperature=0, seed=1, num_ctx=4096, num_predict=768)))
    d["wall"] = time.perf_counter() - t0
    d["out"] = d["message"]["content"]
    d["logprobs"] = [[x.get("token"), x.get("logprob")] for x in d.get("logprobs") or []]
    return d


def escalate(t, d):
    if rule == "small":
        return False
    if rule == "big":
        return True
    if rule == "valid":
        return not valid(t, d["out"])
    kind, th = rule.split(":")
    lp = answer_logprob(d)
    bad = lp is None or lp < float(th)
    return bad or (kind == "lp+valid" and not valid(t, d["out"]))


with urllib.request.urlopen(HOST + "/api/ps") as r:
    for m in json.loads(r.read()).get("models", []):
        post("/api/generate", dict(model=m["name"], keep_alive=0))
time.sleep(2)
for m, ka in ((small, "30m"), (big, big_ka)):
    if rule != "small" or m == small:
        chat(m, "你好", ka)

tasks = [json.loads(l) for l in Path("tasks.jsonl").read_text().splitlines()]
total0 = time.perf_counter()
with open("logs/cascade.jsonl", "a") as f:
    ok = esc_n = 0
    for t in tasks:
        t0 = time.perf_counter()
        calls = []
        if rule != "big":
            d = chat(small, t["prompt"], "30m")
            calls.append((small, d))
        if rule == "big" or escalate(t, d):
            d = chat(big, t["prompt"], big_ka)
            calls.append((big, d))
            esc_n += 1
        good = correct(t, d["out"])
        ok += good
        f.write(json.dumps(dict(rule=rule, big_keep_alive=big_ka, id=t["id"], ok=good, escalated=len(calls) > 1 or rule == "big",
                                wall=round(time.perf_counter() - t0, 3),
                                calls=[dict(model=m, wall=round(c["wall"], 3), load=round(c.get("load_duration", 0) / 1e9, 3),
                                            eval_count=c.get("eval_count")) for m, c in calls]), ensure_ascii=False) + "\n")
    total = time.perf_counter() - total0
    f.write(json.dumps(dict(rule=rule, big_keep_alive=big_ka, summary=True, ok=ok, escalated=esc_n, total_wall=round(total, 2)),
                       ensure_ascii=False) + "\n")
print(f"{rule} big_keep_alive={big_ka}: 对 {ok}/150  升级 {esc_n}  总耗时 {total:.1f}s")
