"""Five fixed workspace tasks x N runs x models x configs through `openclaw agent --local`.
Each run resets task/ in the workspace, then a checker decides pass/fail from files or the reply."""
import json, os, random, re, shutil, subprocess, sys, time

OC = os.environ["OC"]
PROXY_LOG = os.environ["PROXY_LOG"]
WS = os.path.expanduser("~/.openclaw/workspace")
T = os.path.join(WS, "task")
OUT = sys.argv[1]
RUNS_DIR = os.path.join(os.path.dirname(OUT), "runs")
os.makedirs(RUNS_DIR, exist_ok=True)

rng = random.Random(42)
NUMBERS = [rng.randint(100, 999) for _ in range(12)]
LOG_LINES = [rng.choice(["INFO request ok", "WARN slow upstream", "ERROR upstream timeout", "DEBUG cache hit"]) for _ in range(200)]
N_ERROR = sum("ERROR" in l for l in LOG_LINES)
NOTES = ["redis.md", "alpha.md", "kafka.md", "nginx.md"]

def setup():
    shutil.rmtree(T, ignore_errors=True)
    os.makedirs(os.path.join(T, "notes"))
    open(os.path.join(T, "numbers.txt"), "w").write("\n".join(map(str, NUMBERS)) + "\n")
    open(os.path.join(T, "app.log"), "w").write("\n".join(f"2026-11-25T10:{i//60:02d}:{i%60:02d} {l}" for i, l in enumerate(LOG_LINES)) + "\n")
    json.dump({"name": "demo", "port": 8080, "debug": True}, open(os.path.join(T, "config.json"), "w"), indent=2)
    for n in NOTES: open(os.path.join(T, "notes", n), "w").write(f"# {n[:-3]}\n")
    open(os.path.join(T, "notes", "README.txt"), "w").write("not a markdown file\n")

def read(p):
    try: return open(os.path.join(T, p)).read()
    except FileNotFoundError: return None

def only_number(reply, n):
    return reply is not None and str(n) in re.findall(r"\d+", reply.replace(",", ""))

def check_config(_):
    try: c = json.loads(read("config.json") or "")
    except ValueError: return False
    return c == {"name": "demo", "port": 9090, "debug": True}

TASKS = [
    ("write_file", "Create a file at task/hello.txt (relative to your workspace) whose entire content is exactly: hello openclaw",
     lambda r: (read("hello.txt") or "").strip() == "hello openclaw"),
    ("sum_numbers", "Read task/numbers.txt in your workspace and reply with only the sum of all the numbers in it.",
     lambda r: only_number(r, sum(NUMBERS))),
    ("count_errors", "Use a shell command to count how many lines in task/app.log (in your workspace) contain the word ERROR. Reply with only the number.",
     lambda r: only_number(r, N_ERROR)),
    ("edit_json", "In task/config.json (in your workspace), change the port from 8080 to 9090. Keep every other field unchanged.",
     check_config),
    ("index_notes", "List the .md files in the task/notes directory of your workspace and write their file names, sorted alphabetically, one per line, into task/index.txt.",
     lambda r: (read("index.txt") or "").split() == sorted(NOTES)),
]

def proxy_lines():
    return open(PROXY_LOG).read().splitlines() if os.path.exists(PROXY_LOG) else []

def run_one(config, model, task, i):
    name, prompt, check = task
    setup()
    before = len(proxy_lines())
    sid = f"{config}-{model.replace(':', '_')}-{name}-{i}-{int(time.time())}"
    t0 = time.time()
    try:
        p = subprocess.run([OC, "agent", "--local", "--agent", "main", "--model", f"ollama/{model}",
                            "--session-id", sid, "-m", prompt, "--json", "--timeout", "300"],
                           capture_output=True, text=True, timeout=420)
        stdout, stderr, rc = p.stdout, p.stderr, p.returncode
    except subprocess.TimeoutExpired as e:
        stdout, stderr, rc = (e.stdout or b"").decode() if isinstance(e.stdout, bytes) else (e.stdout or ""), "", "timeout"
    wall = round(time.time() - t0, 1)
    reqs = [json.loads(l) for l in proxy_lines()[before:]]
    reply, ok_tools = None, None
    try:
        m = json.loads(stdout)["meta"]
        reply = m.get("finalAssistantVisibleText")
        ok_tools = m.get("agentMeta", {}).get("terminalReceipt", {}).get("successfulToolNames")
        m.pop("systemPromptReport", None)
        json.dump(m, open(os.path.join(RUNS_DIR, sid + ".json"), "w"), ensure_ascii=False, indent=1)
    except Exception:
        open(os.path.join(RUNS_DIR, sid + ".err.txt"), "w").write((stdout + stderr)[-3000:])
    passed = bool(check(reply))
    return {"config": config, "model": model, "task": name, "run": i, "pass": passed, "rc": rc, "wall_s": wall,
            "reply": (reply or "")[:300], "successful_tools": ok_tools,
            "model_calls": len(reqs), "tool_calls": [c for r in reqs for c in r.get("tool_calls") or []],
            "prompt_eval_first": reqs[0].get("prompt_eval_count") if reqs else None,
            "prompt_eval_total": sum(r.get("prompt_eval_count") or 0 for r in reqs)}

if __name__ == "__main__":
    config = os.environ["CONFIG_LABEL"]
    models = os.environ["MODELS"].split(",")
    n = int(os.environ.get("N", "4"))
    with open(OUT, "a") as out:
        for i in range(n):
            for model in models:
                for task in TASKS:
                    rec = run_one(config, model, task, i)
                    out.write(json.dumps(rec, ensure_ascii=False) + "\n"); out.flush()
                    print(json.dumps({k: rec[k] for k in ("config", "model", "task", "run", "pass", "wall_s", "tool_calls")}, ensure_ascii=False), flush=True)
