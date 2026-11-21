"""Print raw records verbatim for the evidence file.

usage: python3 dump.py <file.jsonl> <filter python expr on r> [--fields k1,k2] [--max N]
e.g.   dump.py main.jsonl "r['arm']=='strict_schema' and r['case']==15"
"""
import argparse, json

ap = argparse.ArgumentParser()
ap.add_argument("file")
ap.add_argument("expr")
ap.add_argument("--fields", default="model,arm,tag,case,temp,rep,done_reason,eval_count")
ap.add_argument("--max", type=int, default=50)
ap.add_argument("--raw", action="store_true", help="print content with real newlines")
a = ap.parse_args()
n = 0
for line in open(a.file, encoding="utf-8"):
    r = json.loads(line)
    if eval(a.expr, {}, {"r": r}):
        print(" ".join(f"{k}={r.get(k)}" for k in a.fields.split(",")))
        print("content=" + (str(r.get("content")) if a.raw else json.dumps(r.get("content"), ensure_ascii=False)))
        if r.get("error"):
            body = r["error"].get("http_error") if isinstance(r["error"], dict) else None
            print("http_body=" + body if body else "error=" + json.dumps(r["error"], ensure_ascii=False))
        n += 1
        if n >= a.max:
            break
