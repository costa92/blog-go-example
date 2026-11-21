"""Score bench jsonl files.

usage: python3 score.py <file.jsonl>... [--by model,tag,arm,temp] [--fields]
"""
import argparse, json, re, statistics
from collections import Counter, defaultdict

import jsonschema

from bench import ARMS, SCHEMA
from cases import CASES, Any

FIELDS = ["order_id", "customer", "intent", "items", "urgent", "days_waiting"]


def parse_strict(content):
    try:
        v = json.loads(content)
        return v if isinstance(v, dict) else None
    except (TypeError, ValueError):
        return None


def parse_lenient(content):
    if content is None:
        return None
    t = re.sub(r"<think>.*?</think>", "", content, flags=re.S).strip()
    m = re.search(r"```(?:json)?\s*\n(.*?)```", t, flags=re.S)
    if m:
        t = m.group(1)
    a, b = t.find("{"), t.rfind("}")
    return parse_strict(t[a:b + 1]) if a >= 0 and b > a else None


def items_key(v):
    if not isinstance(v, list):
        return None
    out = []
    for it in v:
        if not isinstance(it, dict) or "sku" not in it or "qty" not in it:
            return None
        try:
            out.append((str(it["sku"]).strip().upper(), int(it["qty"])))
        except (TypeError, ValueError):
            return None
    return sorted(out)


def same(field, pred, gt):
    if isinstance(gt, Any):
        return any(same(field, pred, g) for g in gt)
    if field == "items":
        return items_key(pred) == sorted(gt)
    if gt is None or isinstance(gt, bool):
        return pred is gt
    if field == "days_waiting":
        return type(pred) is int and pred == gt
    if not isinstance(pred, str):
        return False
    if field == "order_id":
        return pred.strip().lstrip("#") == gt
    return pred.strip().lower() == gt.lower()


def score(rec):
    content = rec.get("content")
    obj = parse_lenient(content)
    schema = ARMS[rec["arm"]][3] or SCHEMA
    valid = False
    if obj is not None:
        valid = jsonschema.Draft202012Validator(schema).is_valid(obj)
    gt = CASES[rec["case"]]["gt"]
    ok = {f: obj is not None and f in obj and same(f, obj[f], gt[f]) for f in FIELDS}
    return {"strict": parse_strict(content) is not None, "parsed": obj is not None,
            "valid": valid, "fields": ok, "all": all(ok.values()), "obj": obj}


def load(paths):
    rows = []
    for p in paths:
        rows += [json.loads(l) for l in open(p, encoding="utf-8")]
    return rows


def pct(n, d):
    return f"{100 * n / d:.1f}" if d else "-"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+")
    ap.add_argument("--by", default="model,tag,arm,temp")
    ap.add_argument("--fields", action="store_true")
    a = ap.parse_args()
    keys = a.by.split(",")
    groups = defaultdict(list)
    for r in load(a.files):
        groups[tuple(str(r.get(k)) for k in keys)].append((r, score(r)))
    hdr = keys + ["n", "strict%", "parse%", "valid%", "field%", "all6%", "tok", "tok/s", "wall_s"]
    if a.fields:
        hdr += FIELDS
    print("\t".join(hdr))
    for g, rs in sorted(groups.items()):
        n = len(rs)
        sc = [s for _, s in rs]
        fc = sum(sum(s["fields"].values()) for s in sc)
        toks = [r["eval_count"] for r, _ in rs if r.get("eval_count")]
        rates = [r["eval_count"] / r["eval_ns"] * 1e9 for r, _ in rs if r.get("eval_ns")]
        walls = [r["wall_s"] for r, _ in rs]
        row = list(g) + [n, pct(sum(s["strict"] for s in sc), n), pct(sum(s["parsed"] for s in sc), n),
                         pct(sum(s["valid"] for s in sc), n), pct(fc, 6 * n), pct(sum(s["all"] for s in sc), n),
                         f"{statistics.mean(toks):.0f}" if toks else "-",
                         f"{statistics.median(rates):.1f}" if rates else "-",
                         f"{statistics.median(walls):.2f}"]
        if a.fields:
            row += [pct(sum(s["fields"][f] for s in sc), n) for f in FIELDS]
        print("\t".join(map(str, row)))


if __name__ == "__main__":
    main()
