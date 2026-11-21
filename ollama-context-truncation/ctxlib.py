"""Shared helpers for the Ollama context-truncation experiments."""
import getpass, json, re, subprocess, time, urllib.request, urllib.error

SYSTEM = "You are a careful Python programmer."
TASK = ("Write a Python function named `checksum_v7(data: bytes) -> int` that returns "
        "the sum of all bytes modulo 251.")
FMT = "Reply with only the code in a single ```python block."


def filler(n):
    return "".join(f"- release 1.{i // 10}.{i % 10}: fixed a minor issue in module util_{i}, updated docs for helper_{i}\n"
                   for i in range(n))


def build_prompt(n_lines, pos="head"):
    if pos == "head":
        return TASK + "\n\nBelow is the project's changelog for context.\n\n" + filler(n_lines) + "\n" + FMT
    # task after the reference material
    return "Below is the project's changelog for context.\n\n" + filler(n_lines) + "\n" + TASK + "\n" + FMT


def post(url, body, timeout=600):
    req = urllib.request.Request(url, json.dumps(body).encode(), {"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def chat(model, prompt, options=None, port=11434, extra=None):
    body = {"model": model, "stream": False, "options": options or {},
            "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}]}
    body.update(extra or {})
    return post(f"http://127.0.0.1:{port}/api/chat", body)


def generate(model, prompt, options=None, port=11434):
    return post(f"http://127.0.0.1:{port}/api/generate",
                {"model": model, "stream": False, "system": SYSTEM, "prompt": prompt, "options": options or {}})


def openai_chat(model, prompt, extra=None, port=11434):
    body = {"model": model, "temperature": 0,
            "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}]}
    body.update(extra or {})
    return post(f"http://127.0.0.1:{port}/v1/chat/completions", body)


def content(resp):
    if "message" in resp:
        return resp["message"]["content"]
    if "response" in resp:
        return resp["response"]
    if "choices" in resp:
        return resp["choices"][0]["message"]["content"]
    return json.dumps(resp)[:300]


def correct(text):
    """Run the returned checksum_v7 against two inputs in a subprocess."""
    m = re.findall(r"```(?:python|py)?\s*\n(.*?)```", text, flags=re.S)
    code = m[0] if m else text
    if "def checksum_v7" not in code:
        return False
    test = code + "\nassert checksum_v7(b'') == 0\nassert checksum_v7(bytes(range(256))*3) == sum(range(256))*3 % 251\n"
    try:
        r = subprocess.run(["python3", "-I", "-c", test], capture_output=True, timeout=10)
        return r.returncode == 0
    except subprocess.TimeoutExpired:
        return False


def journal_since(ts):
    out = subprocess.run(["journalctl", "-u", "ollama", "--no-pager", "-o", "short", "--since", f"@{int(ts)}"],
                         capture_output=True, text=True).stdout
    out = out.replace(getpass.getuser(), "host")
    return [l for l in out.splitlines() if "truncating" in l or "vram-based" in l]


def ps(port=11434):
    import os
    env = {**os.environ, "OLLAMA_HOST": f"127.0.0.1:{port}"}
    return subprocess.run(["ollama", "ps"], capture_output=True, text=True, env=env).stdout.strip()


def short(resp):
    keep = {k: resp.get(k) for k in ("prompt_eval_count", "eval_count", "prompt_eval_duration", "eval_duration",
                                     "done_reason", "usage", "error") if k in resp}
    if "choices" in resp:
        keep["finish_reason"] = resp["choices"][0].get("finish_reason")
    return keep
