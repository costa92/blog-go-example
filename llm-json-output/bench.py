"""JSON extraction bench.

usage: python3 bench.py <backend:model> <arm[,arm]> <out.jsonl> [--temp T] [--reps N] [--num-predict N] [--cases i,j]
backend: ollama | minimax
"""
import argparse, copy, json, os, sys, time, urllib.error, urllib.request

from cases import CASES

OLLAMA = "http://localhost:11434/api/chat"
MINIMAX = "https://api.minimaxi.com/v1/chat/completions"

SYSTEM = "You extract order information from customer support messages."

DESCRIBED = """Extract these fields from the message and reply with a JSON object only, no other text.
- order_id: the 5-digit order number as a string without '#' or 'No.', or null if not given
- customer: the customer's name as written, or null if not given
- intent: one of "refund", "exchange", "cancel", "shipping", "other" (shipping = delivery status or shipping changes; other = anything else)
- items: list of {{"sku": product code like "KB-204", "qty": integer}}; qty is 1 if not stated; [] if no product code is mentioned
- urgent: true only if the customer explicitly asks for urgency (urgent, ASAP, today, 尽快, 急, priority=high), else false
- days_waiting: integer number of days the customer says they have waited for delivery or since delivery, or null if not stated
- summary: one short English sentence
{extra}
Message:
{text}"""

BARE = """Extract the order information from this customer message as JSON.

Message:
{text}"""

REASONING_LINE = "- reasoning: one or two sentences thinking through the fields before giving them\n"

NULLABLE_STR = {"type": ["string", "null"]}
SCHEMA = {
    "type": "object",
    "properties": {
        "order_id": NULLABLE_STR,
        "customer": NULLABLE_STR,
        "intent": {"type": "string", "enum": ["refund", "exchange", "cancel", "shipping", "other"]},
        "items": {"type": "array", "items": {
            "type": "object",
            "properties": {"sku": {"type": "string"}, "qty": {"type": "integer"}},
            "required": ["sku", "qty"], "additionalProperties": False}},
        "urgent": {"type": "boolean"},
        "days_waiting": {"type": ["integer", "null"]},
        "summary": {"type": "string"},
    },
    "required": ["order_id", "customer", "intent", "items", "urgent", "days_waiting", "summary"],
    "additionalProperties": False,
}


def strict_schema():
    s = copy.deepcopy(SCHEMA)
    s["properties"]["order_id"] = {"type": "string"}
    s["properties"]["customer"] = {"type": "string"}
    s["properties"]["days_waiting"] = {"type": "integer"}
    return s


def with_reasoning(first):
    s = copy.deepcopy(SCHEMA)
    props = list(s["properties"].items())
    r = ("reasoning", {"type": "string"})
    s["properties"] = dict([r] + props if first else props + [r])
    s["required"] = list(s["properties"])
    return s


def anyof(schema):
    """Rewrite {"type": [a, b]} as anyOf, for APIs that reject type arrays."""
    if isinstance(schema, dict):
        if isinstance(schema.get("type"), list):
            return {"anyOf": [{"type": t} for t in schema["type"]]}
        return {k: anyof(v) for k, v in schema.items()}
    if isinstance(schema, list):
        return [anyof(v) for v in schema]
    return schema


# arm -> (prompt template, extra prompt line, ollama format / minimax response_format kind, schema)
ARMS = {
    "prompt":          (DESCRIBED, "", None, None),
    "json":            (DESCRIBED, "", "json", None),
    "schema":          (DESCRIBED, "", "schema", SCHEMA),
    "bare_json":       (BARE, "", "json", None),
    "bare_schema":     (BARE, "", "schema", SCHEMA),
    "strict_schema":   (DESCRIBED, "", "schema", strict_schema()),
    "reason_first":    (DESCRIBED, REASONING_LINE, "schema", with_reasoning(True)),
    "reason_last":     (DESCRIBED, REASONING_LINE, "schema", with_reasoning(False)),
    "schema_anyof":    (DESCRIBED, "", "schema", anyof(SCHEMA)),
    "bare_schema_anyof": (BARE, "", "schema", anyof(SCHEMA)),
}


def build_prompt(arm, text):
    tpl, extra, _, _ = ARMS[arm]
    return tpl.format(text=text, extra=extra)


def post(url, body, headers=None, timeout=300):
    req = urllib.request.Request(url, json.dumps(body).encode(),
                                 {"Content-Type": "application/json", **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, {"http_error": e.read().decode(errors="replace")[:500]}


THINK = {}  # {"think": bool} from --think


def gen_ollama(model, arm, text, temp, num_predict):
    _, _, fmt, schema = ARMS[arm]
    body = {"model": model, "stream": False,
            "options": {"temperature": temp, "num_predict": num_predict},
            "messages": [{"role": "system", "content": SYSTEM},
                         {"role": "user", "content": build_prompt(arm, text)}]}
    if fmt == "json":
        body["format"] = "json"
    elif fmt == "schema":
        body["format"] = schema
    body.update(THINK)
    t0 = time.time()
    status, r = post(OLLAMA, body)
    meta = {"status": status, "wall_s": round(time.time() - t0, 3)}
    if status != 200:
        return None, {**meta, "error": r}
    return r["message"]["content"], {**meta,
        "eval_count": r.get("eval_count"), "eval_ns": r.get("eval_duration"),
        "prompt_eval_count": r.get("prompt_eval_count"), "prompt_eval_ns": r.get("prompt_eval_duration"),
        "load_ns": r.get("load_duration"), "total_ns": r.get("total_duration"),
        "done_reason": r.get("done_reason"), "thinking_chars": len(r["message"].get("thinking") or "")}


MINIMAX_EXTRA = {}  # set from --minimax-extra JSON


def gen_minimax(model, arm, text, temp, num_predict):
    _, _, fmt, schema = ARMS[arm]
    body = {"model": model, "max_completion_tokens": num_predict,
            "messages": [{"role": "system", "content": SYSTEM},
                         {"role": "user", "content": build_prompt(arm, text)}]}
    if fmt == "json":
        body["response_format"] = {"type": "json_object"}
    elif fmt == "schema":
        body["response_format"] = {"type": "json_schema",
                                   "json_schema": {"name": "order", "strict": True, "schema": schema}}
    body.update(MINIMAX_EXTRA)
    t0 = time.time()
    status, r = post(MINIMAX, body, {"Authorization": "Bearer " + os.environ["MINIMAX_CN_API_KEY"]})
    meta = {"status": status, "wall_s": round(time.time() - t0, 3)}
    if status != 200 or "choices" not in r:
        return None, {**meta, "error": r}
    u = r.get("usage", {})
    msg = r["choices"][0]["message"]
    return msg.get("content"), {**meta,
        "eval_count": u.get("completion_tokens"),
        "reasoning_tokens": (u.get("completion_tokens_details") or {}).get("reasoning_tokens"),
        "has_reasoning_content": bool(msg.get("reasoning_content")),
        "done_reason": r["choices"][0].get("finish_reason"), "model_returned": r.get("model")}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("target")
    ap.add_argument("arms")
    ap.add_argument("out")
    ap.add_argument("--temp", type=float, default=0.0)
    ap.add_argument("--reps", type=int, default=1)
    ap.add_argument("--num-predict", type=int, default=512)
    ap.add_argument("--cases", default="")
    ap.add_argument("--tag", default="")
    ap.add_argument("--minimax-extra", default="{}")
    ap.add_argument("--think", choices=["true", "false"])
    a = ap.parse_args()
    if a.think:
        THINK["think"] = a.think == "true"
    MINIMAX_EXTRA.update(json.loads(a.minimax_extra))
    backend, model = a.target.split(":", 1)
    gen = {"ollama": gen_ollama, "minimax": gen_minimax}[backend]
    idx = [int(i) for i in a.cases.split(",")] if a.cases else range(len(CASES))
    with open(a.out, "a", encoding="utf-8") as f:
        for arm in a.arms.split(","):
            for rep in range(a.reps):
                for i in idx:
                    content, meta = gen(model, arm, CASES[i]["text"], a.temp, a.num_predict)
                    rec = {"backend": backend, "model": model, "arm": arm, "case": i, "temp": a.temp,
                           "rep": rep, "num_predict": a.num_predict, "tag": a.tag, "think": a.think,
                           "content": content, **meta}
                    f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                    f.flush()
            print(f"{model} {arm} done", file=sys.stderr, flush=True)


if __name__ == "__main__":
    main()
