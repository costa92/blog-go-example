"""固定 seed 在 T=0.7 下的抽样：同一提示词换 seed、重复 seed，并打印第一个 token 的 A/B 对数概率。
python3 seedq.py <judge> <item>"""
import json, math, sys, urllib.request
import run
judge, item = sys.argv[1], sys.argv[2]
for t in run.pair_tasks(["base"]):
    if t["item"] != item:
        continue
    for seed in (1, 2, 3, 1, 2, 3):
        body = {"model": judge, "messages": [{"role": "user", "content": t["prompt"]}], "stream": False,
                "logprobs": True, "top_logprobs": 2, "options": {"temperature": 0.7, "seed": seed, "num_predict": 1}}
        r = json.load(urllib.request.urlopen(urllib.request.Request(run.URL, json.dumps(body).encode(), {"Content-Type": "application/json"})))
        top = {x["token"]: x["logprob"] for x in r["logprobs"][0]["top_logprobs"]}
        a, b = top.get("A", -50), top.get("B", -50)
        pa = 1 / (1 + math.exp((b - a) / 0.7))
        good = "A" if t["order"] == "GB" else "B"
        print(f"order={t['order']} good={good} seed={seed} pick={r['message']['content']!r:5} logprob A={a:.3f} B={b:.3f}  T=0.7 时 P(A)={pa:.3f}")
