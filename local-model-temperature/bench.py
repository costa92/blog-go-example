"""Sampling-temperature bench: local Ollama models vs MiniMax API.

usage: python3 bench.py <backend:model> <temps comma> <n> <out.jsonl> [seed]
backend: ollama | minimax
"""
import ast, json, os, re, subprocess, sys, tempfile, time, urllib.request

from tasks import TASKS, SYSTEM, SUFFIX

OLLAMA = "http://localhost:11434/api/chat"
MINIMAX = "https://api.minimaxi.com/v1/chat/completions"


def post(url, body, headers=None, timeout=300):
    req = urllib.request.Request(url, json.dumps(body).encode(),
                                 {"Content-Type": "application/json", **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def gen_ollama(model, prompt, temp, seed=None, extra=None):
    opts = {"temperature": temp, "num_predict": 1024}
    if seed is not None:
        opts["seed"] = seed
    opts.update(extra or {})
    r = post(OLLAMA, {"model": model, "stream": False, "options": opts,
                      "messages": [{"role": "system", "content": SYSTEM},
                                   {"role": "user", "content": prompt}]})
    return r["message"]["content"], {
        "eval_count": r.get("eval_count"), "eval_ns": r.get("eval_duration"),
        "prompt_eval_count": r.get("prompt_eval_count"),
        "load_ns": r.get("load_duration"), "total_ns": r.get("total_duration")}


def gen_minimax(model, prompt, temp, seed=None, extra=None):
    body = {"model": model, "max_tokens": 4096, "temperature": temp,
            "messages": [{"role": "system", "content": SYSTEM},
                         {"role": "user", "content": prompt}]}
    if seed is not None:
        body["seed"] = seed
    body.update(extra or {})
    t0 = time.time()
    r = post(MINIMAX, body, {"Authorization": "Bearer " + os.environ["MINIMAX_CN_API_KEY"]})
    if "choices" not in r:
        raise RuntimeError(json.dumps(r, ensure_ascii=False)[:300])
    u = r.get("usage", {})
    return r["choices"][0]["message"]["content"], {
        "eval_count": u.get("completion_tokens"),
        "reasoning_tokens": (u.get("completion_tokens_details") or {}).get("reasoning_tokens"),
        "wall_s": time.time() - t0, "finish": r["choices"][0].get("finish_reason")}


def extract(text):
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S)
    m = re.findall(r"```(?:python|py)?\s*\n(.*?)```", text, flags=re.S)
    return m[0] if m else text


def normalize(code):
    """AST dump without docstrings: ignores comments, whitespace, quotes."""
    tree = ast.parse(code)
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if isinstance(body, list) and body and isinstance(body[0], ast.Expr) \
                and isinstance(getattr(body[0], "value", None), ast.Constant) \
                and isinstance(body[0].value.value, str):
            node.body = body[1:] or [ast.Pass()]
    return ast.dump(tree, annotate_fields=False)


def run_tests(code, tests):
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
        f.write(code + "\n\n" + tests)
        path = f.name
    try:
        p = subprocess.run([sys.executable, "-I", path], capture_output=True, text=True, timeout=5)
        return p.returncode == 0, p.stderr.strip().splitlines()[-1:] if p.returncode else []
    except subprocess.TimeoutExpired:
        return False, ["timeout"]
    finally:
        os.unlink(path)


def score(task, raw):
    code = extract(raw)
    try:
        norm = normalize(code)
    except SyntaxError as e:
        return {"syntax_ok": False, "passed": False, "norm": None, "err": ["SyntaxError: " + str(e)]}
    ok, err = run_tests(code, task["tests"])
    return {"syntax_ok": True, "passed": ok, "norm": norm, "err": err}


def main():
    target, temps, n, out = sys.argv[1], sys.argv[2], int(sys.argv[3]), sys.argv[4]
    seed = int(sys.argv[5]) if len(sys.argv) > 5 else None
    backend, model = target.split(":", 1)
    gen = gen_ollama if backend == "ollama" else gen_minimax
    extra = json.loads(os.environ.get("BENCH_EXTRA", "null"))
    with open(out, "a") as fo:
        for temp in [float(t) for t in temps.split(",")]:
            for task in TASKS:
                for i in range(n):
                    try:
                        raw, meta = gen(model, task["prompt"] + SUFFIX, temp, seed, extra)
                    except Exception as e:
                        raw, meta = "", {"error": str(e)[:300]}
                    rec = {"model": target, "temp": temp, "task": task["id"], "i": i,
                           "seed": seed, "extra": extra, "raw": raw, **meta, **score(task, raw)}
                    fo.write(json.dumps(rec, ensure_ascii=False) + "\n")
                    fo.flush()
                    print(target, temp, task["id"], i, rec["passed"], meta.get("error", ""), flush=True)


if __name__ == "__main__":
    main()
