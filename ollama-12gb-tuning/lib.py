"""Shared helpers: start a throwaway `ollama serve`, send requests, read VRAM."""
import json
import os
import random
import signal
import subprocess
import time
import urllib.request

PORT = int(os.environ.get("BENCH_PORT", "11500"))
BASE = f"http://127.0.0.1:{PORT}"
MODELS_DIR = os.environ.get("OLLAMA_MODELS", "/mnt/data/ollama/models")


def post(path, body, timeout=900):
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def get(path):
    with urllib.request.urlopen(BASE + path, timeout=30) as r:
        return json.loads(r.read())


def gpu_used_mib():
    out = subprocess.check_output(
        ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"])
    return int(out.decode().split()[0])


class Server:
    """A second ollama server on its own port, so the system service is left alone."""

    def __init__(self, env, log_path):
        self.env = dict(os.environ, OLLAMA_HOST=f"127.0.0.1:{PORT}",
                        OLLAMA_MODELS=MODELS_DIR, OLLAMA_NOPRUNE="1",
                        OLLAMA_KEEP_ALIVE="30m", **env)
        self.log_path = log_path

    def __enter__(self):
        self.log = open(self.log_path, "w")
        self.p = subprocess.Popen(["ollama", "serve"], env=self.env, stdout=self.log,
                                  stderr=subprocess.STDOUT, start_new_session=True)
        for _ in range(100):
            try:
                get("/api/version")
                return self
            except Exception:
                time.sleep(0.2)
        raise RuntimeError("server did not start")

    def __exit__(self, *a):
        os.killpg(self.p.pid, signal.SIGTERM)
        self.p.wait(timeout=60)
        self.log.close()
        time.sleep(2)


def ps(model):
    for m in get("/api/ps").get("models", []):
        if m["name"].startswith(model):
            size, vram = m["size"], m["size_vram"]
            return {"size_gb": round(size / 1e9, 2), "vram_gb": round(vram / 1e9, 2),
                    "gpu_pct": round(100 * vram / size), "ctx": m.get("context_length")}
    return None


def unload(model):
    post("/api/generate", {"model": model, "keep_alive": 0})
    for _ in range(60):
        if not ps(model):
            break
        time.sleep(0.5)
    time.sleep(1)


def gen(model, prompt, num_ctx, num_predict=128, seed=1):
    opts = {"num_ctx": num_ctx, "num_predict": num_predict, "temperature": 0, "seed": seed}
    if os.environ.get("BENCH_NUM_GPU"):  # force partial offload for the control run
        opts["num_gpu"] = int(os.environ["BENCH_NUM_GPU"])
    t = time.time()
    r = post("/api/generate", {"model": model, "prompt": prompt, "stream": False, "raw": False,
                               "options": opts})
    r["wall_s"] = time.time() - t
    return r


def rates(r):
    return {
        "prompt_tokens": r.get("prompt_eval_count", 0),
        "prompt_tps": round(r["prompt_eval_count"] / (r["prompt_eval_duration"] / 1e9), 1)
        if r.get("prompt_eval_duration") else None,
        "gen_tokens": r.get("eval_count", 0),
        "gen_tps": round(r["eval_count"] / (r["eval_duration"] / 1e9), 1)
        if r.get("eval_duration") else None,
        "load_s": round(r.get("load_duration", 0) / 1e9, 2),
        "wall_s": round(r["wall_s"], 2),
    }


# ---- synthetic long document with retrievable facts ----
ADJ = ["amber", "silent", "copper", "lunar", "rapid", "hollow", "crimson", "frozen", "golden",
       "hidden", "iron", "jade", "misty", "noble", "polar", "quiet", "rusty", "solar", "velvet",
       "wild", "azure", "brisk", "cobalt", "dusty", "ember"]
NOUN = ["falcon", "river", "anchor", "lantern", "maple", "harbor", "comet", "willow", "badger",
        "canyon", "dagger", "fjord", "glacier", "heron", "island", "jungle", "kestrel", "meadow",
        "nebula", "orchid", "pebble", "quarry", "raven", "summit", "tundra"]
FIRST = ["Dana", "Liam", "Mina", "Omar", "Priya", "Tomas", "Yuki", "Elena", "Kofi", "Sara"]
LAST = ["Whitfield", "Okafor", "Lindqvist", "Moreau", "Tanaka", "Haddad", "Novak", "Reyes"]


def haystack(n_records, rng_seed=7):
    rng = random.Random(rng_seed)
    names = rng.sample([f"{a}-{n}-{k}" for a in ADJ for n in NOUN for k in range(2, 10)], n_records)
    recs = []
    for i, name in enumerate(names):
        code = rng.randint(10000, 99999)
        lead = f"{rng.choice(FIRST)} {rng.choice(LAST)}"
        budget = rng.randint(100, 9999)
        recs.append({"i": i, "name": name.upper(), "code": str(code), "text":
                     f"Record {i}: The project codenamed {name.upper()} is led by {lead}, "
                     f"has a budget of {budget} thousand dollars, and its server room door "
                     f"code is {code}."})
    return recs


def doc(recs, nonce=""):
    head = f"Session {nonce}.\n" if nonce else ""
    return head + "Below is the internal project registry.\n\n" + "\n".join(r["text"] for r in recs)


def question(rec):
    return (f"\n\nQuestion: What is the server room door code for the project codenamed "
            f"{rec['name']}? Reply with the five-digit number only.")


def last_load_info(log_path):
    """Pull the numbers llama-server prints at load time from the server log."""
    import re
    text = open(log_path, errors="replace").read()
    start = text.rfind("starting llama-server")
    seg = text[start:]
    info = {}
    m = re.search(r'cmd="([^"]+)"', seg)
    if m:
        info["cmd_flags"] = " ".join(t for t in m.group(1).split()
                                     if t.startswith("-") or not t.startswith("/"))
    for key, pat in {"offloaded": r"offloaded (\d+/\d+) layers",
                     "kv_size": r"llama_kv_cache: size = +([\d.]+ MiB)",
                     "kv_types": r"K \((\w+)\): +[\d.]+ MiB, V \((\w+)\)",
                     "flash_attn": r"llama_context: flash_attn += (\w+)",
                     "n_ctx_slot": r"n_slots = (\d+), n_ctx_slot = (\d+)",
                     "projected": r"projected to use (\d+) MiB of device memory vs\. (\d+) MiB"}.items():
        mm = re.search(pat, seg)
        if mm:
            info[key] = mm.groups() if len(mm.groups()) > 1 else mm.group(1)
    info["flash_attn_enabled"] = "Flash Attention enabled" in seg or info.get("flash_attn") == "enabled"
    return info


def load(model, num_ctx, log_path):
    """Unload, read baseline VRAM, load with a tiny request, return load facts."""
    unload(model)
    base = gpu_used_mib()
    r = gen(model, "Say OK.", num_ctx, num_predict=2)
    time.sleep(1)
    return {"vram_base_mib": base, "vram_loaded_mib": gpu_used_mib(),
            "vram_delta_mib": gpu_used_mib() - base, "load_s": rates(r)["load_s"],
            "ps": ps(model), **last_load_info(log_path)}


def jsonl(path, obj):
    with open(path, "a") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")
