"""对一个模型跑完整题库，写 logs/<模型>_<模式>_t<温度>_s<seed>.jsonl。

    python3 run.py qwen2.5-coder:3b plain            # 直接回答，温度 0、seed 1
    python3 run.py qwen2.5-coder:3b conf             # 回答后再报一个 0-100 的把握
    python3 run.py qwen2.5-coder:3b route            # 当路由器：只判断「简单 / 困难」
    python3 run.py qwen2.5-coder:3b plain 0.7 2      # 温度 0.7、seed 2

已经写进日志的题会跳过，中断后可以接着跑。"""
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

URL = "http://127.0.0.1:11434/api/chat"
model, mode = sys.argv[1], sys.argv[2]
temp = float(sys.argv[3]) if len(sys.argv) > 3 else 0.0
seed = int(sys.argv[4]) if len(sys.argv) > 4 else 1

CONF = "\n答案行之后再单独写一行，以「把握：」开头，后面写一个 0 到 100 的整数，表示你认为这个答案正确的可能性。"
ROUTE = ("下面是用户发给助手的一个请求。判断它对一个 3B 参数的小模型来说是简单还是困难："
         "简单指小模型能直接答对，困难指需要交给更大的模型。只回答「简单」或「困难」两个字，不要解释。\n\n"
         "请求：\n{q}")


def prompt(t):
    if mode == "plain":
        return t["prompt"]
    if mode == "conf":
        return t["prompt"] + CONF
    if mode == "route":
        return ROUTE.format(q=t["prompt"].rsplit("\n\n可以先写推理过程。", 1)[0])
    raise SystemExit(f"unknown mode {mode}")


def chat(content):
    body = dict(model=model, stream=False, keep_alive="30m", logprobs=True,
                messages=[{"role": "user", "content": content}],
                options=dict(temperature=temp, seed=seed, num_ctx=4096, num_predict=8 if mode == "route" else 768))
    req = urllib.request.Request(URL, json.dumps(body).encode(), {"Content-Type": "application/json"})
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=600) as r:
        d = json.loads(r.read())
    d["wall"] = time.perf_counter() - t0
    return d


def unload_others():
    """和别的实验共用一张卡：先卸掉上一个实验留在显存里的模型，否则这个模型可能被挤到 CPU 上一部分。"""
    with urllib.request.urlopen(URL.replace("/api/chat", "/api/ps")) as r:
        for m in json.loads(r.read()).get("models", []):
            if m["name"] != model:
                body = json.dumps(dict(model=m["name"], keep_alive=0)).encode()
                urllib.request.urlopen(urllib.request.Request(URL.replace("chat", "generate"), body,
                                                              {"Content-Type": "application/json"})).read()


unload_others()
Path("logs").mkdir(exist_ok=True)
out = Path(f"logs/{model.replace(':', '-')}_{mode}_t{temp:g}_s{seed}.jsonl")
done = {json.loads(l)["id"] for l in out.read_text().splitlines()} if out.exists() else set()
with out.open("a") as f:
    for line in Path("tasks.jsonl").read_text().splitlines():
        t = json.loads(line)
        if t["id"] in done:
            continue
        rec = dict(id=t["id"], model=model, mode=mode, temp=temp, seed=seed)
        try:
            d = chat(prompt(t))
        except urllib.error.HTTPError as e:
            rec.update(out="", error=e.read().decode()[:300])
        else:
            rec.update(out=d["message"]["content"], done_reason=d.get("done_reason"), wall=round(d["wall"], 4),
                       logprobs=[[x.get("token"), x.get("logprob")] for x in d.get("logprobs") or []],
                       **{k: d.get(k) for k in ("load_duration", "prompt_eval_count", "prompt_eval_duration",
                                                "eval_count", "eval_duration", "total_duration")})
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        f.flush()
print(out, "done")
