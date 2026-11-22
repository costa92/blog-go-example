#!/usr/bin/env python3
"""Grade logs/*.jsonl written by run.py.

usage: grade.py logs/a.jsonl [logs/b.jsonl ...] [--by n,level] [--text]

Only the first tool call counts. Labels, in order of checking:
  no_call    no native tool call and no call written as text
  text_call  no native tool call, but the reply text holds one (counted as a failure
             unless --text is given, then the parsed call is graded like a native one)
  unknown    called a tool that is not in the catalog
  wrong_tool called another tool from the catalog
  bad_args   right tool, arguments wrong
  ok         right tool, arguments right
"valid" is checked separately against the full schema: required keys present, no unknown
keys, JSON types and enums.
"""
import argparse, collections, json, re, statistics, sys
from datetime import datetime

from catalog import BY_NAME
from cases import REQUESTS

GOLD = {r[0]: (r[2], r[3]) for r in REQUESTS}
LABELS = ["ok", "bad_args", "wrong_tool", "unknown", "text_call", "no_call"]


def parse_text_call(text):
    """A call written into the reply text: a JSON object with name + arguments/parameters."""
    for m in re.finditer(r"\{", text):
        depth = 0
        for j in range(m.start(), len(text)):
            depth += {"{": 1, "}": -1}.get(text[j], 0)
            if depth == 0:
                try:
                    obj = json.loads(text[m.start():j + 1])
                except ValueError:
                    break
                if isinstance(obj, dict) and isinstance(obj.get("name"), str):
                    args = obj.get("arguments", obj.get("parameters", {}))
                    return obj["name"], args if isinstance(args, dict) else {}
                break
    return None


def first_call(r):
    if r["tool_calls"]:
        f = r["tool_calls"][0]["function"]
        args = f.get("arguments") or {}
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except ValueError:
                args = {}
        return f["name"], args, "native"
    got = parse_text_call(r["content"])
    if got:
        return got[0], got[1], "text"
    return None, {}, None


def norm(v):
    return str(v).strip().casefold()


def to_dt(v):
    s = str(v).strip().replace("/", "-")
    s = re.sub(r"(Z|[+-]\d{2}:?\d{2})$", "", s).replace(" ", "T")
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            pass
    return None


def match(want, got):
    if isinstance(want, str):
        return norm(want) == norm(got)
    kind, x = want
    if kind == "num":
        try:
            return float(got) == float(x)
        except (TypeError, ValueError):
            return False
    if kind == "has":
        return isinstance(got, str) and norm(x) in norm(got)
    if kind == "any":
        return norm(got) in {norm(a) for a in x}
    a, b = to_dt(got), to_dt(x)
    if a is None:
        return False
    return a.date() == b.date() if kind == "date" else a.replace(second=0) == b


TYPES = {"string": lambda v: isinstance(v, str),
         "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
         "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
         "boolean": lambda v: isinstance(v, bool)}


def valid(name, args):
    _, _, _, params, required = BY_NAME[name]
    if any(k not in args for k in required) or any(k not in params for k in args):
        return False
    for k, v in args.items():
        t, _, enum = params[k]
        if not TYPES[t](v) or (enum and v not in enum):
            return False
    return True


def grade(r, text=False):
    gold, want = GOLD[r["rid"]]
    name, args, how = first_call(r)
    if name is None:
        return {"label": "no_call", "valid": False, "name": None}
    if how == "text" and not text:
        return {"label": "text_call", "valid": False, "name": name}
    if name not in r["catalog"]:
        return {"label": "unknown", "valid": False, "name": name}
    ok_valid = valid(name, args)
    if name != gold:
        return {"label": "wrong_tool", "valid": ok_valid, "name": name}
    good = all(k in args and match(v, args[k]) for k, v in want.items())
    return {"label": "ok" if good else "bad_args", "valid": ok_valid, "name": name}


def load(paths):
    for p in paths:
        for line in open(p):
            yield json.loads(line)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("logs", nargs="+")
    ap.add_argument("--by", default="n,level")
    ap.add_argument("--text", action="store_true", help="grade calls written as text too")
    a = ap.parse_args()
    keys = ["model"] + a.by.split(",")
    groups = collections.defaultdict(list)
    for r in load(a.logs):
        groups[tuple(r[k] for k in keys)].append((r, grade(r, a.text)))
    print("\t".join(keys + ["runs", "tool_ok", "args_ok", "valid"] + LABELS[1:] + ["prompt_tok", "wall_s"]))
    for k in sorted(groups, key=lambda k: [str(x).zfill(4) if isinstance(x, int) else str(x) for x in k]):
        rows = groups[k]
        c = collections.Counter(g["label"] for _, g in rows)
        n = len(rows)
        tool_ok = c["ok"] + c["bad_args"]
        cols = [str(x) for x in k] + [str(n), f"{tool_ok}", f"{c['ok']}",
                                      f"{sum(g['valid'] for _, g in rows)}"] + [str(c[l]) for l in LABELS[1:]]
        cols += [str(int(statistics.median(r["prompt_eval_count"] or 0 for r, _ in rows))),
                 f"{statistics.median(r['wall_s'] for r, _ in rows):.2f}"]
        print("\t".join(cols))


if __name__ == "__main__":
    sys.exit(main())
