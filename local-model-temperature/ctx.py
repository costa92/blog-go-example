"""num_ctx truncation probe. usage: python3 ctx.py <model> <out.jsonl>"""
import json, sys
from bench import gen_ollama
model, out = sys.argv[1], sys.argv[2]
head = ("Write a Python function named `checksum_v7(data: bytes) -> int` that returns "
        "the sum of all bytes modulo 251.\n\nBelow is the project's changelog for context.\n\n")
filler = "".join(f"- release 1.{i // 10}.{i % 10}: fixed a minor issue in module util_{i}, updated docs for helper_{i}\n"
                 for i in range(300))
tail = "\nReply with only the code in a single ```python block."
fo = open(out, "a")
for num_ctx in [int(x) if x != "default" else None for x in (sys.argv[3] if len(sys.argv) > 3 else "default,8192").split(",")]:
    for i in range(2):
        extra = {"num_ctx": num_ctx} if num_ctx else {}
        raw, meta = gen_ollama(model, head + filler + tail, 0.0, None, extra)
        ok = "checksum_v7" in raw and "251" in raw
        rec = {"model": model, "num_ctx": num_ctx, "i": i, "follows_instruction": ok, "raw": raw, **meta}
        fo.write(json.dumps(rec, ensure_ascii=False) + "\n"); fo.flush()
        print(model, "num_ctx", num_ctx, "prompt_eval_count", meta["prompt_eval_count"], "ok", ok, raw[:160].replace("\n", " | "), flush=True)
