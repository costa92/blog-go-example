#!/usr/bin/env python3
"""show.py JSONL [LABEL...] : one compact line per call."""
import json, sys
f, labels = sys.argv[1], sys.argv[2:]
for l in open(f):
    j = json.loads(l)
    if "meta" in j or (labels and j["label"] not in labels): continue
    pe = "-" if j.get("prompt_eval_ms") is None else f'{j["prompt_eval_ms"]:.0f}ms'
    ld = "-" if j.get("load_ms") is None else f'{j["load_ms"]:.0f}ms'
    print(f'{j["label"]:<22} prompt={j["prompt_eval_count"]:<5} cached={j["cached"]:<5} prompt_eval={pe:<7} load={ld:<7} ttft={j["ttft_ms"]:.0f}ms')
