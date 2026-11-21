"""速度与显存：python3 bench.py qwen2.5:3b-instruct-q4_K_M  → logs/bench-<tag>.jsonl
1. 卸载所有模型，记录空载显存；2. 冷加载 3 次（每次先卸载），记录 load_duration 和墙钟；
3. 加载后读 nvidia-smi 显存与 /api/ps 的 size_vram；4. 长提示词流式请求 5 次，记首 token 时间和两段速度。
每次长提示词开头放一个不同的编号，避免命中上一次的提示词缓存。"""
import json, subprocess, sys, time, urllib.request
from pathlib import Path

H = "http://127.0.0.1:11434"
model = sys.argv[1]; tag = model.split("instruct-")[1] if model.startswith("qwen2.5:3b") else model.split(":")[1].split("-")[0] + "-" + model.split("instruct-")[1]  # 3b 的 q4_K_M / imat-q4_K_M，7b 的 7b-q4_K_M
OPT = dict(temperature=0, seed=1, num_ctx=4096)

def post(path, body, stream=False):
    req = urllib.request.Request(H + path, json.dumps(body).encode(), {"Content-Type": "application/json"})
    return urllib.request.urlopen(req, timeout=600)

def ps():
    return json.loads(urllib.request.urlopen(H + "/api/ps").read())["models"]

def unload_all():
    for m in ps():
        post("/api/generate", dict(model=m["name"], keep_alive=0)).read()
    for _ in range(60):
        if not ps(): break
        time.sleep(0.5)
    time.sleep(2)

def vram():
    return int(subprocess.check_output(["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"]).split()[0])

PARA = ("Kubernetes 的调度器在为 Pod 选择节点时，先用过滤插件排除资源不足、污点不容忍或亲和性不满足的节点，"
        "再用打分插件给剩下的节点排序，最后把 Pod 绑定到得分最高的节点。")
def long_prompt(i):
    body = "".join(f"第 {k} 段：{PARA}节点编号 n{(i * 37 + k) % 97}，已用 CPU {k * 3 % 17} 核。\n" for k in range(1, 26))
    return f"文档编号 {i}-{time.time_ns() % 100000}\n{body}\n请用大约 300 字概括上面的文档。"

out = Path(f"logs/bench-{tag}.jsonl"); f = out.open("a")
def log(**kw):
    kw.update(model=model, ts=time.time()); f.write(json.dumps(kw, ensure_ascii=False) + "\n"); f.flush(); print(kw)

unload_all(); base = vram(); log(kind="baseline_vram_mib", value=base)
for rep in range(3):
    unload_all()
    t = time.perf_counter()
    d = json.loads(post("/api/generate", dict(model=model, prompt="你好", stream=False, keep_alive="10m",
                                              options=dict(OPT, num_predict=1))).read())
    log(kind="cold", rep=rep, wall=time.perf_counter() - t, load_s=d["load_duration"] / 1e9)
time.sleep(1)
p = [m for m in ps() if m["name"] == model][0]
log(kind="vram", nvidia_mib=vram() - base, size=p["size"], size_vram=p["size_vram"], ctx=p.get("context_length"))
for rep in range(5):
    t = time.perf_counter(); first = None
    with post("/api/generate", dict(model=model, prompt=long_prompt(rep), stream=True, keep_alive="10m",
                                    options=dict(OPT, num_predict=256))) as r:
        for line in r:
            d = json.loads(line)
            if first is None and d.get("response"): first = time.perf_counter() - t
            if d.get("done"): last = d
    log(kind="long", rep=rep, ttft=first, wall=time.perf_counter() - t, prompt_n=last["prompt_eval_count"],
        prompt_tps=last["prompt_eval_count"] / (last["prompt_eval_duration"] / 1e9),
        gen_n=last["eval_count"], gen_tps=last["eval_count"] / (last["eval_duration"] / 1e9))
unload_all()
