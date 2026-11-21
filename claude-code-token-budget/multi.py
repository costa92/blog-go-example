#!/usr/bin/env python3
"""Send user turns one by one to a single headless claude process; wait for each result.
usage: multi.py NAME TURNS.jsonl -- <claude args>"""
import json, os, shutil, subprocess, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
name, turns_file = sys.argv[1], sys.argv[2]
assert sys.argv[3] == "--"
args = sys.argv[4:]
env = {k: os.environ[k] for k in ("HOME", "PATH", "LANG", "TERM", "USER") if k in os.environ}
p = subprocess.Popen([os.environ.get("CLAUDE_BIN") or shutil.which("claude"), *args], cwd=HERE / "proj", env=env,
                     stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
keep, total = [], 0.0
prev_cost = 0.0
for ti, line in enumerate(open(turns_file)):
    p.stdin.write(line); p.stdin.flush()
    seen = set()
    while True:
        m = json.loads(p.stdout.readline())
        if m.get("type") == "system":
            keep.append({"type": "system", "subtype": m.get("subtype")}); continue
        keep.append(m)
        if m.get("type") == "assistant" and m["message"]["id"] not in seen:
            seen.add(m["message"]["id"]); u = m["message"]["usage"]
            ctx = u["input_tokens"] + u["cache_creation_input_tokens"] + u["cache_read_input_tokens"]
            print(f"turn{ti+1}: input={u['input_tokens']} cache_create={u['cache_creation_input_tokens']} "
                  f"cache_read={u['cache_read_input_tokens']} context={ctx}")
        if m.get("type") == "result":
            c = m["total_cost_usd"]
            print(f"  result turn{ti+1}: total_cost_usd={c} (this turn ${c - prev_cost:.4f}) text={m['result'][:60]!r}")
            prev_cost = c; break
p.stdin.close(); p.wait()
(HERE / "runs").mkdir(exist_ok=True)
(HERE / "runs" / f"{name}.jsonl").write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in keep))
with open(HERE / "ledger.tsv", "a") as f:
    f.write(f"{name}\t{prev_cost}\n")
print(f"cumulative=${sum(float(l.split(chr(9))[1]) for l in open(HERE / 'ledger.tsv') if l.split(chr(9))[1].strip() not in ('None','')):.4f}")
