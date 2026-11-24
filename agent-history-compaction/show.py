#!/usr/bin/env python3
"""打印原始记录。

python3 show.py logs/main.jsonl llama3.1:8b window budget        # 某个策略某个探针的每次运行
python3 show.py logs/compact.jsonl llama3.1:8b notes 1           # 某个 seed 最后的笔记或摘要
python3 show.py logs/compact.jsonl llama3.1:8b summary 1 --all   # 回放中每次生成的摘要
"""
import json, sys

path, model, strategy, arg = sys.argv[1:5]
for line in open(path):
    r = json.loads(line)
    if r["model"] != model or r["strategy"] != strategy:
        continue
    if "compact" in path:
        if r["seed"] != int(arg):
            continue
        evs = r["events"] if "--all" in sys.argv else r["events"][-1:]
        for e in evs:
            print(f"## after round {e['after_round']}  prompt={e['prompt_tokens']} out={e['out_tokens']} {e['secs']}s"
                  + (f"  folded={e['folded']}" if "folded" in e else ""))
            print(e["text"])
        print(f"## kept rounds: {[j + 1 for j in r['kept']]}" if r["kept"] else "")
        continue
    if r["probe"] != arg:
        continue
    s0 = r["steps"][0]
    print(f"## seed={r['seed']} prompt_tokens={s0['prompt_tokens']} nudged={r['nudged']}")
    texts = r.get("texts") or ([r["final"]] if r["final"] else [])
    if r["nudged"] and "texts" in r:  # 追问前的那次回复没有工具调用，先打印它，再打印追问
        for l in texts[0].splitlines():
            print("  > " + l)
        print("  [用户] 继续。")
        texts = texts[1:]
    for c in r["calls"]:
        print(f"  call {c['name']} {json.dumps(c['args'], ensure_ascii=False)}")
    for l in "\n".join(texts).splitlines():
        print("  > " + l)
