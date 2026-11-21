"""打印原始判决。python3 show.py <cond> <judge> <item> [variant] [--prompt]
--prompt 同时打印发给裁判的提示词（由 run.py 按同样规则重建）。"""
import json, sys
from pathlib import Path
args = [a for a in sys.argv[1:] if not a.startswith("--")]
cond, judge, item = args[:3]
variant = args[3] if len(args) > 3 else None
prompts = {}
if "--prompt" in sys.argv:
    import run
    for t in run.CONDS[cond]():
        prompts[(t["variant"], t["item"], t["order"], t["temp"], t["seed"])] = t["prompt"]
for l in Path(f"logs/{cond}.jsonl").read_text().splitlines():
    r = json.loads(l)
    if r["judge"] != judge or r["item"] != item or (variant and r["variant"] != variant):
        continue
    tag = f"## {r['mode']} {r['variant']} order={r['order']} T={r['temp']} seed={r['seed']}"
    if "good_pos" in r:
        tag += f" good={r['good_pos']} pick={r['pick']}"
    if "score" in r:
        tag += f" score={r['score']}"
    print(tag)
    p = prompts.get((r["variant"], r["item"], r["order"], r["temp"], r["seed"]))
    if p:
        for line in p.splitlines():
            if line.strip():
                print("  > " + line)
        print("  输出：")
    for line in r["out"].strip().splitlines():
        if line.strip():
            print("  " + line)
