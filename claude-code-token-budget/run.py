#!/usr/bin/env python3
"""Run one headless claude call, save sanitized stream-json, print usage summary.
usage: run.py NAME [--cwd DIR] [--stdin FILE] -- <claude args...>"""
import json, os, shutil, subprocess, sys, time
from pathlib import Path
HERE = Path(__file__).resolve().parent
CLAUDE = os.environ.get("CLAUDE_BIN") or shutil.which("claude")
MINE = ("mcp__tinyops__",)          # my dummy MCP server
BUILTIN_OK = True
args = sys.argv[1:]
name = args.pop(0)
cwd = HERE / "proj"
stdin_data = None
while args[0] in ("--cwd", "--stdin"):
    flag = args.pop(0); val = args.pop(0)
    if flag == "--cwd": cwd = Path(val)
    else: stdin_data = open(val).read()
assert args.pop(0) == "--"
env = {k: os.environ[k] for k in ("HOME", "PATH", "LANG", "TERM", "USER") if k in os.environ}
t0 = time.time()
p = subprocess.run([CLAUDE, *args], cwd=cwd, env=env, capture_output=True, text=True, input=stdin_data)
wall = time.time() - t0
msgs = [json.loads(l) for l in p.stdout.splitlines() if l.strip().startswith("{")]

def clean_init(m):
    out = dict(m)
    for k in ("tools",):
        v = m.get(k) or []
        out[k] = [t if (not t.startswith("mcp__") or t.startswith(MINE)) else "<other-mcp>" for t in v]
    srv = m.get("mcp_servers") or []
    out["mcp_servers"] = [s if s.get("name") == "tinyops" else {"name": "<other>", "status": s.get("status")} for s in srv]
    for k in ("slash_commands", "skills", "agents", "plugins"):
        if k in m:
            v = m[k] or []
            mine = [x for x in v if isinstance(x, str) and x.startswith(("tinyops", "deploy-check", "pg-reviewer"))]
            out[k] = {"count": len(v), "mine": mine}
    for k in list(out):
        if k not in ("type", "subtype", "cwd", "session_id", "tools", "mcp_servers", "model", "permissionMode",
                     "slash_commands", "skills", "agents", "plugins", "claude_code_version", "output_style", "apiKeySource"):
            out[k] = "<dropped>"
    return out

saved = []
for m in msgs:
    if m.get("type") == "system" and m.get("subtype") == "init":
        saved.append(clean_init(m))
    elif m.get("type") == "system":
        saved.append({"type": "system", "subtype": m.get("subtype")})
    else:
        saved.append(m)
(HERE / "runs").mkdir(exist_ok=True)
(HERE / "runs" / f"{name}.jsonl").write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in saved))
seen, rows = set(), []
for m in msgs:
    if m.get("type") == "assistant":
        mid = m["message"]["id"]
        if mid in seen: continue
        seen.add(mid); u = m["message"]["usage"]
        rows.append(u)
res = next((m for m in msgs if m.get("type") == "result"), {})
init = next((m for m in msgs if m.get("subtype") == "init"), {})
print(f"== {name}  wall={wall:.1f}s rc={p.returncode}")
print(f"init: tools={len(init.get('tools', []))} mcp_servers={len(init.get('mcp_servers', []))} "
      f"slash_commands={len(init.get('slash_commands', []) or [])} skills={len(init.get('skills', []) or [])} "
      f"agents={len(init.get('agents', []) or [])} plugins={len(init.get('plugins', []) or [])} model={init.get('model')}")
for i, u in enumerate(rows):
    cc = u.get("cache_creation") or {}
    tot = u.get("input_tokens", 0) + u.get("cache_creation_input_tokens", 0) + u.get("cache_read_input_tokens", 0)
    print(f"req{i+1}: input={u.get('input_tokens')} cache_create={u.get('cache_creation_input_tokens')} "
          f"(5m={cc.get('ephemeral_5m_input_tokens')},1h={cc.get('ephemeral_1h_input_tokens')}) "
          f"cache_read={u.get('cache_read_input_tokens')} output={u.get('output_tokens')} context={tot}")
print(f"result: turns={res.get('num_turns')} cost=${res.get('total_cost_usd')} is_error={res.get('is_error')} "
      f"text={str(res.get('result'))[:120]!r}")
mu = res.get("modelUsage") or {}
for k, v in mu.items():
    print(f"  modelUsage {k}: in={v.get('inputTokens')} out={v.get('outputTokens')} cr={v.get('cacheReadInputTokens')} cc={v.get('cacheCreationInputTokens')} cost={v.get('costUSD')}")
if p.returncode and not msgs:
    print("STDERR:", p.stderr[-800:])
with open(HERE / "ledger.tsv", "a") as f:
    f.write(f"{name}\t{res.get('total_cost_usd')}\n")
tot = sum(float(l.split('\t')[1]) for l in open(HERE / "ledger.tsv") if l.split('\t')[1].strip() not in ("None", ""))
print(f"cumulative=${tot:.4f}")
