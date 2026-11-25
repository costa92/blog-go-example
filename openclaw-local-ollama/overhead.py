"""Fixed per-request overhead: run a one-word turn under several configs and record
Ollama's prompt_eval_count (seen by proxy.py) plus OpenClaw's own systemPromptReport."""
import json, os, shutil, subprocess, sys, time

OC = os.environ["OC"]
PROXY_LOG = os.environ["PROXY_LOG"]
WS = os.path.expanduser("~/.openclaw/workspace")
OUT = sys.argv[1]
MSG = "Reply with the single word: pong"

def cset(path, value):
    p = subprocess.run([OC, "config", "set", path, json.dumps(value), "--strict-json"], capture_output=True, text=True)
    assert p.returncode == 0, p.stdout + p.stderr

def cunset(path):
    subprocess.run([OC, "config", "unset", path], capture_output=True, text=True)

def slim_workspace():
    for f in ("AGENTS.md", "SOUL.md", "IDENTITY.md", "USER.md", "BOOTSTRAP.md"):
        p = os.path.join(WS, f)
        if os.path.exists(p): os.remove(p)
    open(os.path.join(WS, "AGENTS.md"), "w").write("You are a helpful assistant.\n")

# (label, model, setup steps)
VARIANTS = [
    ("default full", "qwen2.5-coder:3b", []),
    ("full, bundled skills off", "qwen2.5-coder:3b", [("set", "skills.allowBundled", [])]),
    ("full, skills off, no BOOTSTRAP.md", "qwen2.5-coder:3b", [("rm", "BOOTSTRAP.md")]),
    ("coding, skills off, no BOOTSTRAP.md", "qwen2.5-coder:3b", [("set", "tools.profile", "coding")]),
    ("minimal, skills off, no BOOTSTRAP.md", "qwen2.5-coder:3b", [("set", "tools.profile", "minimal")]),
    ("minimal, skills off, 1-line AGENTS.md only", "qwen2.5-coder:3b", [("slim",)]),
]
MODELS_DEFAULT = ["qwen2.5-coder:3b", "qwen2.5-coder:7b", "llama3.1:8b", "gemma4:latest"]

def run(label, model):
    before = len(open(PROXY_LOG).read().splitlines()) if os.path.exists(PROXY_LOG) else 0
    p = subprocess.run([OC, "agent", "--local", "--agent", "main", "--model", f"ollama/{model}",
                        "--session-id", f"oh-{int(time.time()*1000)}", "-m", MSG, "--json"],
                       capture_output=True, text=True, timeout=900)
    reqs = [json.loads(l) for l in open(PROXY_LOG).read().splitlines()[before:]]
    rec = {"label": label, "model": model, "rc": p.returncode,
           "prompt_eval_count": [r.get("prompt_eval_count") for r in reqs],
           "n_tools_sent": [len(r["tools"]) for r in reqs],
           "tools_json_chars": [r["tools_json_chars"] for r in reqs],
           "system_chars": [r["system_chars"] for r in reqs],
           "num_ctx": [(r.get("options") or {}).get("num_ctx") for r in reqs]}
    try:
        m = json.loads(p.stdout)["meta"]; rep = m["systemPromptReport"]
        rec.update({"reply": m.get("finalAssistantVisibleText"),
                    "sp_chars": rep["systemPrompt"]["chars"],
                    "project_context_chars": rep["systemPrompt"]["projectContextChars"],
                    "skills_prompt_chars": rep["skills"]["promptChars"], "n_skills": len(rep["skills"]["entries"]),
                    "openclaw_input_tokens": m["agentMeta"]["usage"]["input"],
                    "estimated_prompt_tokens": m["agentMeta"].get("contextBudgetStatus", {}).get("estimatedPromptTokens"),
                    "duration_ms": m.get("durationMs")})
    except Exception:
        rec["tail"] = (p.stdout + p.stderr)[-600:]
    return rec

if __name__ == "__main__":
    mode = sys.argv[2] if len(sys.argv) > 2 else "ablation"
    with open(OUT, "a") as out:
        if mode == "models":
            for model in MODELS_DEFAULT:
                rec = run("default full", model); out.write(json.dumps(rec, ensure_ascii=False) + "\n"); out.flush(); print(rec, flush=True)
        else:
            for label, model, steps in VARIANTS:
                for st in steps:
                    if st[0] == "set": cset(st[1], st[2])
                    elif st[0] == "rm": os.remove(os.path.join(WS, st[1]))
                    elif st[0] == "slim": slim_workspace()
                rec = run(label, model); out.write(json.dumps(rec, ensure_ascii=False) + "\n"); out.flush(); print(rec, flush=True)
