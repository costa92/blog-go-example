import json, glob, statistics as st, sys
rows = {}
for f in sorted(glob.glob("logs/*.jsonl")):
    model = None; prev = ""
    for l in open(f):
        j = json.loads(l)
        if "meta" in j: model = j["model"]; continue
        if j["case"] == "v1" and j["label"] == "v1": j["label"] = "v1_after_" + prev
        prev = j["label"]
        k = (model, j["case"], j["label"])
        rows.setdefault(k, []).append(j)
def fmt(v):
    v = [x for x in v if x is not None]
    if not v: return "-"
    return f"{st.median(v):g} [{min(v):g}-{max(v):g}]"
print("| model | case | label | n | prompt | cached | prompt_eval_ms | ttft_ms | load_ms |")
print("|---|---|---|---|---|---|---|---|---|")
for (m, c, lb), v in rows.items():
    print(f"| {m} | {c} | {lb} | {len(v)} | {fmt([x['prompt_eval_count'] for x in v])} | {fmt([x['cached'] for x in v])} | {fmt([x['prompt_eval_ms'] for x in v])} | {fmt([x['ttft_ms'] for x in v])} | {fmt([x['load_ms'] for x in v])} |")
