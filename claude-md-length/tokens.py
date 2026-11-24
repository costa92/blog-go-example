#!/usr/bin/env python3
"""Measure how many context tokens each instruction layout adds at session start.

Usage: tokens.py [--model haiku] [--reps 2]
For each layout a fresh copy of proj/ gets the files, then `claude -p "Reply OK"`
runs with the default tools; with `--tools ""` CLAUDE.md was not loaded at all in 2.1.331.
Context = input_tokens + cache_creation_input_tokens + cache_read_input_tokens
of the first assistant message. Appends to tokens.jsonl.
"""
import argparse
import json
import os
import shutil
import subprocess
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
CLAUDE = os.environ.get("CLAUDE_BIN", "claude")


def layouts():
    v = lambda n: open(os.path.join(HERE, "variants", n)).read()
    filler = v("import-filler.md")
    scoped = "---\npaths:\n  - \"internal/routing/**\"\n---\n\n" + filler
    return {
        "none": {},
        "claude-50": {"CLAUDE.md": v("claude-50.md")},
        "claude-200": {"CLAUDE.md": v("claude-200.md")},
        "claude-500": {"CLAUDE.md": v("claude-500.md")},
        "claude-1500": {"CLAUDE.md": v("claude-1500.md")},
        "import": {"CLAUDE.md": v("import-main.md"), "docs/subsystems.md": filler},
        "rules-unscoped": {"CLAUDE.md": v("claude-50.md"), ".claude/rules/subsystems.md": filler},
        "rules-paths": {"CLAUDE.md": v("claude-50.md"), ".claude/rules/subsystems.md": scoped},
        "html-comment": {"CLAUDE.md": v("claude-50.md") + "\n<!--\n" + filler + "\n-->\n"},
    }


def first_ctx(repo, model):
    out = subprocess.run([CLAUDE, "-p", "Reply OK", "--model", model,
                          "--output-format", "stream-json", "--verbose", "--no-session-persistence",
                          "--setting-sources", "project", "--strict-mcp-config", "--max-budget-usd", "1"],
                         cwd=repo, capture_output=True, text=True).stdout
    for line in out.split("\n"):
        try:
            d = json.loads(line)
        except ValueError:
            continue
        if d.get("type") == "assistant":
            u = d["message"]["usage"]
            return u["input_tokens"] + u.get("cache_creation_input_tokens", 0) + u.get("cache_read_input_tokens", 0)
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="haiku")
    ap.add_argument("--reps", type=int, default=2)
    ap.add_argument("--only", default="", help="comma-separated layout names")
    a = ap.parse_args()
    rows = []
    for name, files in layouts().items():
        if a.only and name not in a.only.split(","):
            continue
        for rep in range(a.reps):
            tmp = tempfile.mkdtemp(prefix="cmd-tok-")
            repo = os.path.join(tmp, "gw")
            shutil.copytree(os.path.join(HERE, "proj"), repo)
            for rel, content in files.items():
                os.makedirs(os.path.dirname(os.path.join(repo, rel)), exist_ok=True)
                open(os.path.join(repo, rel), "w").write(content)
            subprocess.run("git init -q -b main && git add -A && git -c user.name=dev -c user.email=dev@example.com commit -qm init",
                           shell=True, cwd=repo, check=True)
            ctx = first_ctx(repo, a.model)
            shutil.rmtree(tmp)
            rows.append({"layout": name, "rep": rep + 1, "first_ctx": ctx})
            print(name, rep + 1, ctx, flush=True)
    with open(os.path.join(HERE, "tokens.jsonl"), "a") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


if __name__ == "__main__":
    main()
