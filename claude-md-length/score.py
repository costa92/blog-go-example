#!/usr/bin/env python3
"""Score every run under runs/ against the rules its task exercises.

Usage: score.py [--out results.jsonl]
Prints compliance per variant x rule and writes one JSON line per run.
A rule is only scored on tasks listed for it in tasks.json.
"""
import argparse
import collections
import json
import os
import re
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))


def git(repo, *args):
    return subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True).stdout


def changes(repo):
    """Committed and uncommitted changes relative to the base tag."""
    git(repo, "add", "-A")
    names = git(repo, "diff", "--cached", "--name-status", "base").split("\n")
    added_files, changed = [], []
    for n in names:
        if not n.strip():
            continue
        st, path = n.split("\t", 1)
        if path.startswith(".claude/") or path.startswith("docs/"):
            continue
        changed.append(path)
        if st == "A":
            added_files.append(path)
    added = collections.defaultdict(list)
    cur = None
    for line in git(repo, "diff", "--cached", "-U0", "base").split("\n"):
        if line.startswith("+++ "):
            cur = line[6:] if line.startswith("+++ b/") else None
        elif line.startswith("+") and cur:
            added[cur].append(line[1:])
    return added_files, changed, added


def final(repo, path):
    try:
        return open(os.path.join(repo, path)).read()
    except OSError:
        return ""


def check(rule, repo, ctx):
    added_files, changed, added = ctx["added_files"], ctx["changed"], ctx["added"]
    go_src = {p: l for p, l in added.items() if p.endswith(".go") and not p.endswith("_test.go")}
    go_test = {p: l for p, l in added.items() if p.endswith("_test.go")}
    src_text = "\n".join("\n".join(l) for l in go_src.values())
    if rule == "R1":
        subs = [s for s in git(repo, "log", "--format=%s", "base..HEAD").split("\n") if s]
        return bool(subs) and all(s.startswith("[gw] ") for s in subs)
    if rule == "R2":
        calls = re.findall(r'fmt\.Errorf\((.*)', src_text)
        wraps = [c for c in calls if "%w" in c]
        good = [c for c in wraps if re.match(r'"gw: [\w.]+: [^"]*%w', c)]
        return bool(wraps) and len(good) == len(wraps)
    if rule == "R3":
        new_tests = [p for p in added_files if p.endswith("_test.go")]
        return bool(new_tests) and all(p.endswith("_internal_test.go") for p in new_tests)
    if rule == "R4":
        uses_slog = "slog." in src_text or "*slog.Logger" in src_text
        std_log = re.search(r'^\s*"log"\s*$', src_text, re.M) or re.search(r'\blog\.(Print|Fatal|Panic)', src_text)
        prints = re.search(r'fmt\.Print', src_text)
        return bool(uses_slog and not std_log and not prints and '"component"' in src_text)
    if rule == "R5":
        ok, seen = True, 0
        for p in go_src:
            lines = final(repo, p).split("\n")
            for i, l in enumerate(lines):
                m = re.match(r'func (\([^)]*\) )?([A-Z]\w*)\(', l)
                if not m or l not in go_src[p]:
                    continue
                seen += 1
                j, doc = i - 1, []
                while j >= 0 and lines[j].startswith("//"):
                    doc.append(lines[j])
                    j -= 1
                if "(owner: core)" not in "\n".join(doc):
                    ok = False
        return ok and seen > 0
    if rule == "R6":
        text = "\n".join("\n".join(l) for l in go_test.values())
        return bool(re.search(r'\bcases\s*:?=', text)) and "range cases" in text and \
            bool(re.search(r'for _, tc := range cases', text)) and \
            not re.search(r"for _, (tt|test) := range (tests|cases|tt)\b", text)
    if rule == "R7":
        cl = final(repo, "CHANGELOG.md")
        m = re.search(r'## Unreleased\n(.*?)\n## 0\.1\.0', cl, re.S)
        return bool(m and re.search(r'^- \S', m.group(1), re.M))
    if rule == "R8":
        return "time.Now()" not in src_text and "clock.Now()" in src_text
    raise ValueError(rule)


def usage(stream):
    """First request's context size, turns, cost, and hook blocks."""
    first, cost, turns, blocked, model = None, 0.0, 0, 0, None
    for line in open(stream):
        try:
            d = json.loads(line)
        except ValueError:
            continue
        if d.get("type") == "assistant" and first is None:
            u = d["message"].get("usage", {})
            first = u.get("input_tokens", 0) + u.get("cache_creation_input_tokens", 0) + u.get("cache_read_input_tokens", 0)
            model = d["message"].get("model")
        if d.get("type") == "user":
            for c in d.get("message", {}).get("content", []) or []:
                if isinstance(c, dict) and c.get("type") == "tool_result" and "commit message must start" in json.dumps(c.get("content")):
                    blocked += 1
        if d.get("type") == "result":
            cost, turns = d.get("total_cost_usd") or 0.0, d.get("num_turns") or 0
    return {"first_ctx": first, "cost": cost, "turns": turns, "hook_blocks": blocked, "model": model}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(HERE, "results.jsonl"))
    a = ap.parse_args()
    tasks = {t["id"]: t for t in json.load(open(os.path.join(HERE, "tasks.json")))}
    rows = []
    runs = os.environ.get("RUNS_DIR", os.path.join(HERE, "runs"))
    for variant in sorted(os.listdir(runs)):
        for run in sorted(os.listdir(os.path.join(runs, variant))):
            d = os.path.join(runs, variant, run)
            repo, stream = os.path.join(d, "repo"), os.path.join(d, "stream.jsonl")
            if not os.path.exists(stream):
                continue
            tid, rep = run.split("-r")
            ctx = dict(zip(("added_files", "changed", "added"), changes(repo)))
            build = subprocess.run("go build ./... && go test ./...", shell=True, cwd=repo,
                                   capture_output=True).returncode == 0
            res = {r: check(r, repo, ctx) for r in tasks[tid]["rules"]}
            rows.append({"variant": variant, "task": tid, "rep": int(rep), "build_ok": build,
                         "rules": res, **usage(stream)})
    with open(a.out, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    agg = collections.defaultdict(lambda: [0, 0])
    for r in rows:
        for rule, ok in r["rules"].items():
            agg[(r["variant"], rule)][0] += ok
            agg[(r["variant"], rule)][1] += 1
    variants = sorted({r["variant"] for r in rows})
    rules = sorted({k[1] for k in agg})
    print("variant".ljust(18) + "".join(x.ljust(8) for x in rules) + "all".ljust(10) + "runs  ctx    cost")
    for v in variants:
        tot = [sum(agg[(v, x)][0] for x in rules), sum(agg[(v, x)][1] for x in rules)]
        vr = [r for r in rows if r["variant"] == v]
        ctxs = sorted(r["first_ctx"] or 0 for r in vr)
        print(v.ljust(18) + "".join(f"{agg[(v, x)][0]}/{agg[(v, x)][1]}".ljust(8) for x in rules) +
              f"{tot[0]}/{tot[1]}".ljust(10) + f"{len(vr)}".ljust(6) + f"{ctxs[len(ctxs) // 2]}".ljust(7) +
              f"{sum(r['cost'] for r in vr):.2f}")


if __name__ == "__main__":
    main()
