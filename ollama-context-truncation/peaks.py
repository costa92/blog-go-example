import json, sys, datetime
rows = []
for l in open("vram_exp5.log"):
    p = [x.strip() for x in l.split(",")]
    try:
        ts = datetime.datetime.strptime(p[0], "%Y/%m/%d %H:%M:%S.%f").timestamp()
        rows.append((ts, int(p[1].split()[0])))
    except Exception: pass
base = min(v for t, v in rows[:3]) if rows else None
print("baseline(first samples) MiB:", base)
for f in sys.argv[1:]:
    for l in open(f):
        r = json.loads(l)
        w = [v for t, v in rows if r["t_start"] <= t <= r["t_end"]]
        print(f'{r.get("model","qwen2.5-coder:7b")} num_ctx={r["num_ctx"]} samples={len(w)} peak={max(w) if w else None} MiB  ps={r["ps"]}')
