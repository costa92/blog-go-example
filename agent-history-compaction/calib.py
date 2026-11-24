import json, sys, urllib.request
import session as s
for model in sys.argv[1:]:
    for cut in (4, 14, 28):
        msgs = [{"role": "system", "content": s.SYSTEM}] + [m for r in s.ROUNDS[:cut] for m in r]
        body = {"model": model, "messages": msgs, "tools": s.TOOLS, "stream": False,
                "options": {"num_ctx": 32768, "num_predict": 1}, "think": False}
        r = json.load(urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:11434/api/chat", json.dumps(body).encode()), timeout=600))
        print(model, cut, "est", s.est_tokens(msgs), "real", r["prompt_eval_count"])
