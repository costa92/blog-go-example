#!/usr/bin/env python3
"""Run every (variant, task, rep) through `claude -p` in a fresh copy of proj/.

Usage: run.py --variants none,claude-50,... --reps 1 [--jobs 4] [--model haiku]
Set RUNS_DIR to a directory under $HOME: in Claude Code 2.1.331 a project
under /tmp did not get its CLAUDE.md loaded. Each run lives in runs/<variant>/<task>-r<rep>/ with repo/ (the working copy)
and stream.jsonl (claude's stream-json output). Existing runs are skipped.
Stops launching new runs once the summed total_cost_usd passes --budget.
"""
import argparse
import json
import os
import shutil
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
CLAUDE = os.environ.get("CLAUDE_BIN", "claude")
SUFFIX = ("\n\nWhen you are done, make sure `go build ./... && go test ./...` passes, "
          "then commit all your changes with git.")
GIT_ENV = {"GIT_AUTHOR_NAME": "dev", "GIT_AUTHOR_EMAIL": "dev@example.com",
           "GIT_COMMITTER_NAME": "dev", "GIT_COMMITTER_EMAIL": "dev@example.com"}

# do not leak the parent Claude Code session's variables into the child
CLEAN_ENV = {k: v for k, v in os.environ.items() if not k.startswith("CLAUDE")}

HOOK_SETTINGS = {
    "hooks": {
        "PreToolUse": [{
            "matcher": "Bash",
            "hooks": [{"type": "command", "if": "Bash(git commit *)",
                       "command": "python3 \"$CLAUDE_PROJECT_DIR\"/.claude/check_commit.py"}],
        }]
    }
}
HOOK_SCRIPT = r'''import json, re, sys
cmd = json.load(sys.stdin).get("tool_input", {}).get("command", "")
if "git commit" not in cmd:
    sys.exit(0)
m = re.search(r"-m\s+(\$\(cat <<'?\"?EOF'?\"?\s*\n)?[\"']?(.*)", cmd, re.S)
msg = (m.group(2) if m else "").lstrip()
if msg.startswith("[gw] "):
    sys.exit(0)
print("blocked: commit message must start with '[gw] ' (example: git commit -m \"[gw] add TTL\")", file=sys.stderr)
sys.exit(2)
'''


def variant_files(variant):
    """Map of relative path -> content for the variant's instruction files."""
    v = os.path.join(HERE, "variants")
    read = lambda n: open(os.path.join(v, n)).read()
    if variant == "none":
        return {}
    if variant == "import":
        return {"CLAUDE.md": read("import-main.md"), "docs/subsystems.md": read("import-filler.md")}
    if variant == "claude-500-hook":
        rules = json.load(open(os.path.join(v, "rules.json")))["rules"]
        text = read("claude-500.md").replace(f"- {rules['R1']}\n", "")
        return {"CLAUDE.md": text, ".claude/settings.json": json.dumps(HOOK_SETTINGS, indent=2),
                ".claude/check_commit.py": HOOK_SCRIPT}
    return {"CLAUDE.md": read(f"{variant}.md")}


def prepare(repo, variant):
    shutil.copytree(os.path.join(HERE, "proj"), repo)
    for rel, content in variant_files(variant).items():
        p = os.path.join(repo, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w") as f:
            f.write(content)
    env = {**os.environ, **GIT_ENV}
    for cmd in (["git", "init", "-q", "-b", "main"], ["git", "config", "user.name", "dev"],
                ["git", "config", "user.email", "dev@example.com"], ["git", "add", "-A"],
                ["git", "commit", "-q", "-m", "init"], ["git", "tag", "base"]):
        subprocess.run(cmd, cwd=repo, check=True, env=env)


def cost_of(stream):
    try:
        for line in open(stream):
            if '"type":"result"' in line.replace(" ", ""):
                return json.loads(line).get("total_cost_usd") or 0.0
    except FileNotFoundError:
        pass
    return 0.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--variants", required=True)
    ap.add_argument("--tasks", default="")
    ap.add_argument("--reps", type=int, default=1)
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--model", default="haiku")
    ap.add_argument("--budget", type=float, default=15.0)
    a = ap.parse_args()
    tasks = json.load(open(os.path.join(HERE, "tasks.json")))
    if a.tasks:
        tasks = [t for t in tasks if t["id"] in a.tasks.split(",")]
    runs_dir = os.environ.get("RUNS_DIR", os.path.join(HERE, "runs"))
    spent = sum(cost_of(os.path.join(dp, f)) for dp, _, fs in os.walk(runs_dir) for f in fs if f == "stream.jsonl")
    lock = threading.Lock()
    state = {"spent": spent}
    print(f"already spent ${spent:.2f}")

    def one(variant, task, rep):
        d = os.path.join(runs_dir, variant, f"{task['id']}-r{rep}")
        stream = os.path.join(d, "stream.jsonl")
        if os.path.exists(stream) and cost_of(stream) > 0:
            return
        with lock:
            if state["spent"] > a.budget:
                print("budget reached, skipping", d)
                return
        shutil.rmtree(d, ignore_errors=True)
        os.makedirs(d)
        repo = os.path.join(d, "repo")
        prepare(repo, variant)
        cmd = [CLAUDE, "-p", task["prompt"] + SUFFIX, "--model", a.model,
               "--output-format", "stream-json", "--verbose", "--max-budget-usd", "1",
               "--no-session-persistence", "--setting-sources", "project", "--strict-mcp-config",
               "--dangerously-skip-permissions"]
        with open(stream, "w") as out:
            subprocess.run(cmd, cwd=repo, stdout=out, stderr=subprocess.DEVNULL,
                           env={**CLEAN_ENV, **GIT_ENV}, timeout=900)
        c = cost_of(stream)
        with lock:
            state["spent"] += c
            print(f"{variant} {task['id']} r{rep} ${c:.3f} total ${state['spent']:.2f}", flush=True)

    jobs = [(v, t, r) for r in range(1, a.reps + 1) for v in a.variants.split(",") for t in tasks]
    with ThreadPoolExecutor(a.jobs) as ex:
        for f in [ex.submit(one, *j) for j in jobs]:
            f.result()


if __name__ == "__main__":
    main()
