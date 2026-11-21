import json, sys
from collections import defaultdict
model = sys.argv[1]; files = sys.argv[2:]
d = defaultdict(lambda: [0, 0, 0])
temps, tasks = set(), []
for f in files:
    for l in open(f):
        r = json.loads(l)
        if r["model"] != model: continue
        k = (r["task"], r["temp"]); temps.add(r["temp"])
        if r["task"] not in tasks: tasks.append(r["task"])
        d[k][0] += r["passed"]; d[k][1] += 1; d[k][2] += (not r["syntax_ok"])
temps = sorted(temps)
print("| task | " + " | ".join(f"T={t}" for t in temps) + " |")
print("|---" * (len(temps) + 1) + "|")
for t in tasks:
    print(f"| {t} | " + " | ".join(f"{d[(t,x)][0]}/{d[(t,x)][1]}" + (f" (语法错 {d[(t,x)][2]})" if d[(t,x)][2] else "") for x in temps) + " |")
