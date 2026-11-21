import json, sys
from collections import defaultdict
d = defaultdict(list)
for l in open(sys.argv[1]):
    r = json.loads(l)
    if r["temp"] == 0: d[(r["model"], r["task"])].append(r)
for (m, t), v in d.items():
    ids = {}
    pat = "".join(chr(65 + ids.setdefault(r["raw"], len(ids))) for r in v)
    pas = "".join("P" if r["passed"] else "." for r in v)
    print(f"{m.split(':',1)[1]:20s} {t:10s} raw={pat} pass={pas} first_load_s={v[0]['load_ns']/1e9:.2f}")
