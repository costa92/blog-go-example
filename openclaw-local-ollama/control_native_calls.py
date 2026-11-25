"""Control: does the model emit a native tool_call on the first turn when the request is NOT OpenClaw's?
Replays OpenClaw's captured request (A), the same request with the system prompt swapped for one line (B),
and one line + only the read/write/edit/exec schemas taken from it (C). Talks to Ollama directly."""
import copy, json, os, sys, urllib.request

OLLAMA = os.environ.get("OLLAMA", "http://127.0.0.1:11434")
dump = json.load(open(sys.argv[1]))          # a captured OpenClaw /api/chat request body (first turn)
models = sys.argv[2].split(",")
prompts = json.load(open(sys.argv[3]))       # list of task prompts
n = int(sys.argv[4]) if len(sys.argv) > 4 else 2
SHORT = "You are a coding agent working in the user's workspace. Use the provided tools to act on files; do not describe tool calls in text."
KEEP = {"read", "write", "edit", "exec"}

def variant(kind, prompt):
    j = copy.deepcopy(dump)
    msgs = [m for m in j["messages"] if m["role"] == "system"]
    if kind != "A_openclaw":
        msgs = [{"role": "system", "content": SHORT}]
    j["messages"] = msgs + [{"role": "user", "content": prompt}]
    if kind == "C_short_4tools":
        j["tools"] = [t for t in j["tools"] if t["function"]["name"] in KEEP]
    j["stream"] = False
    j["options"] = {"num_ctx": 32768, "num_predict": 512}
    return j

for model in models:
    for kind in ("A_openclaw", "B_short_same_tools", "C_short_4tools"):
        for i in range(n):
            for k, p in enumerate(prompts):
                j = variant(kind, p); j["model"] = model
                req = urllib.request.Request(OLLAMA + "/api/chat", data=json.dumps(j).encode(), headers={"Content-Type": "application/json"})
                d = json.load(urllib.request.urlopen(req, timeout=600))
                calls = [c["function"]["name"] for c in d["message"].get("tool_calls") or []]
                print(json.dumps({"model": model, "variant": kind, "run": i, "task": k, "n_tools": len(j["tools"]),
                                  "prompt_eval_count": d.get("prompt_eval_count"), "native_tool_calls": calls,
                                  "text_head": (d["message"].get("content") or "")[:120]}, ensure_ascii=False), flush=True)
