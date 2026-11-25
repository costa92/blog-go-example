"""Control D: OpenClaw's captured first-turn messages verbatim (system, timestamped user turn, trailing
runtime-context user message), only the task text swapped in. E: same with the trailing message removed."""
import copy, json, os, sys, urllib.request

OLLAMA = os.environ.get("OLLAMA", "http://127.0.0.1:11434")
dump = json.load(open(sys.argv[1])); model = sys.argv[2]
prompts = json.load(open(sys.argv[3])); n = int(sys.argv[4]) if len(sys.argv) > 4 else 2
ORIG = "Reply with the single word: pong"
for kind in ("D_verbatim", "E_no_runtime_msg"):
    for i in range(n):
        for k, p in enumerate(prompts):
            j = copy.deepcopy(dump); j["model"] = model; j["stream"] = False
            j["messages"][1]["content"] = j["messages"][1]["content"].replace(ORIG, p)
            if kind == "E_no_runtime_msg": j["messages"] = j["messages"][:2]
            j["options"]["num_predict"] = 512
            d = json.load(urllib.request.urlopen(urllib.request.Request(OLLAMA + "/api/chat", data=json.dumps(j).encode(),
                                                 headers={"Content-Type": "application/json"}), timeout=600))
            calls = [c["function"]["name"] for c in d["message"].get("tool_calls") or []]
            print(json.dumps({"model": model, "variant": kind, "run": i, "task": k, "prompt_eval_count": d.get("prompt_eval_count"),
                              "native_tool_calls": calls, "text_head": (d["message"].get("content") or "")[:120]}, ensure_ascii=False), flush=True)
