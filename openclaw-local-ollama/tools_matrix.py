"""For each tools config: write it with `openclaw config set tools`, run one agent turn,
and record which tools OpenClaw actually sent to Ollama (seen by proxy.py)."""
import json, os, subprocess, sys, time

OC = os.environ["OC"]
PROXY_LOG = os.environ["PROXY_LOG"]
OUT = sys.argv[1]
MODEL = os.environ.get("MODEL", "ollama/qwen2.5-coder:3b")

VARIANTS = [
    ("full (onboard default)", {"profile": "full"}),
    ("unset", {}),
    ("messaging", {"profile": "messaging"}),
    ("coding", {"profile": "coding"}),
    ("minimal", {"profile": "minimal"}),
    ("messaging + allow [exec, read]", {"profile": "messaging", "allow": ["exec", "read"]}),
    ("messaging + allow [discord, exec, fs]", {"profile": "messaging", "allow": ["discord", "exec", "fs"]}),
    ("messaging + alsoAllow [exec, group:fs]", {"profile": "messaging", "alsoAllow": ["exec", "group:fs"]}),
    ("coding + deny [exec]", {"profile": "coding", "deny": ["exec"]}),
    ("allow + alsoAllow same scope", {"profile": "messaging", "allow": ["read"], "alsoAllow": ["exec"]}),
    ("allow [exec, read] (no profile)", {"allow": ["exec", "read"]}),
    ("full + allow [exec, read]", {"profile": "full", "allow": ["exec", "read"]}),
    ("coding + allow [exec, read]", {"profile": "coding", "allow": ["exec", "read"]}),
]
if len(sys.argv) > 2:
    VARIANTS = [v for v in VARIANTS if v[0] in sys.argv[2:]]

def sh(args):
    p = subprocess.run(args, capture_output=True, text=True, timeout=900)
    return p.returncode, p.stdout, p.stderr

def proxy_lines():
    try:
        return open(PROXY_LOG).read().splitlines()
    except FileNotFoundError:
        return []

with open(OUT, "w") as out:
    for i, (name, tools) in enumerate(VARIANTS):
        rec = {"variant": name, "config": tools}
        rc, so, se = sh([OC, "config", "set", "tools", json.dumps(tools), "--strict-json"])
        rec["config_set_rc"] = rc
        rec["config_set_msg"] = (so + se).strip().splitlines()[-3:]
        rc, so, se = sh([OC, "config", "validate", "--json"])
        try:
            rec["validate"] = json.loads(so)
        except Exception:
            rec["validate"] = (so + se).strip()[-400:]
        if rec["config_set_rc"] == 0:
            before = len(proxy_lines())
            rc, so, se = sh([OC, "agent", "--local", "--agent", "main", "--model", MODEL,
                             "--session-id", f"tools-{int(time.time())}-{i}",
                             "-m", "Reply with the single word: pong", "--json"])
            rec["agent_rc"] = rc
            reqs = [json.loads(l) for l in proxy_lines()[before:]]
            rec["requests"] = [{"tools": r["tools"], "prompt_eval_count": r.get("prompt_eval_count")} for r in reqs]
            try:
                m = json.loads(so)["meta"]
                rep = m["systemPromptReport"]["tools"]
                rec["report_tools"] = [e["name"] for e in rep["entries"]]
                rec["report_deferred"] = [e["name"] for e in rep.get("deferred", {}).get("entries", [])]
                rec["reply"] = m.get("finalAssistantVisibleText")
            except Exception:
                rec["agent_tail"] = (so + se).strip()[-800:]
        out.write(json.dumps(rec, ensure_ascii=False) + "\n"); out.flush()
        print(name, rec.get("config_set_rc"), [r["tools"] for r in rec.get("requests", [])][:1], rec.get("reply"), flush=True)
