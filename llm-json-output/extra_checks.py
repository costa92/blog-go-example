"""Small checks quoted in the article that score.py does not print."""
import json
from collections import defaultdict
from score import score, load

rows = load(["main.jsonl"])
raw = defaultdict(dict)
for r in rows:
    if r["tag"] == "main":
        raw[(r["model"], r["case"])][r["arm"]] = r["content"]
for m in dict.fromkeys(r["model"] for r in rows):
    same = sum(v["json"] == v["schema"] for (mm, _), v in raw.items() if mm == m)
    print(f"{m:18} T=0 json vs schema identical raw text: {same}/36")
n = sum(score(r)["obj"]["urgent"] is True for r in rows
        if r["model"] == "qwen2.5-coder:7b" and r["arm"] == "bare_schema")
print("qwen2.5-coder:7b bare_schema urgent=true:", n, "/36; ground truth urgent=true: 7")
th = {r["case"]: score(r)["all"] for r in rows if r["tag"] == "think" and r["num_predict"] == 4096}
no = {r["case"]: score(r)["all"] for r in rows
      if r["model"] == "gemma4:latest" and r["tag"] == "main" and r["arm"] == "schema"}
print("gemma4 schema all-6 correct, think(4096) vs think=false, same 8 cases:",
      sum(th.values()), "vs", sum(no[c] for c in th))
