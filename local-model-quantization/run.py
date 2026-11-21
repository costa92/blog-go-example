"""对一个模型跑完整题库：python3 run.py qwen2.5:3b-instruct-q4_K_M  → logs/<tag>.jsonl
温度 0、seed 1、num_ctx 4096，每题单独一次请求，记录输出、逐 token logprob 和 Ollama 的计时字段。"""
import json, sys, time, urllib.error, urllib.request
from pathlib import Path

URL = "http://127.0.0.1:11434/api/chat"
model = sys.argv[1]
tag = model.split("instruct-")[1] if model.startswith("qwen2.5:3b") else model.split(":")[1].split("-")[0] + "-" + model.split("instruct-")[1]  # 3b 的 q4_K_M / imat-q4_K_M，7b 的 7b-q4_K_M
NP = {"fact": 64, "arith": 512, "json": 160, "code": 512}

def chat(prompt, num_predict):
    body = dict(model=model, stream=False, keep_alive="10m", logprobs=True,
                messages=[{"role": "user", "content": prompt}],
                options=dict(temperature=0, seed=1, num_ctx=4096, num_predict=num_predict))
    req = urllib.request.Request(URL, json.dumps(body).encode(), {"Content-Type": "application/json"})
    t = time.perf_counter()
    with urllib.request.urlopen(req, timeout=600) as r:
        d = json.loads(r.read())
    d["wall"] = time.perf_counter() - t
    return d

out = Path(f"logs/{tag}.jsonl")
done = {json.loads(l)["id"] for l in out.read_text().splitlines()} if out.exists() else set()
with out.open("a") as f:
    for line in Path("tasks.jsonl").read_text().splitlines():
        t = json.loads(line)
        if t["id"] in done:
            continue
        try:
            d = chat(t["prompt"], NP[t["kind"]])
        except urllib.error.HTTPError as e:   # 例如 Ollama 检测到 token 无限重复时返回 500
            rec = dict(id=t["id"], kind=t["kind"], model=model, out="", error=json.loads(e.read()).get("error"))
            f.write(json.dumps(rec, ensure_ascii=False) + "\n"); f.flush()
            continue
        rec = dict(id=t["id"], kind=t["kind"], model=model, out=d["message"]["content"],
                   tokens=[x.get("token") for x in d.get("logprobs") or []],
                   lps=[x.get("logprob") for x in d.get("logprobs") or []],
                   done_reason=d.get("done_reason"), wall=d["wall"],
                   **{k: d.get(k) for k in ("load_duration", "prompt_eval_count", "prompt_eval_duration", "eval_count", "eval_duration")})
        f.write(json.dumps(rec, ensure_ascii=False) + "\n"); f.flush()
print(model, "done")
