import json, time, urllib.request, random
H = "http://127.0.0.1:11434"

def handbook(n_rules=120, seed=7):
    """Deterministic ops handbook text used as a long system prompt."""
    r = random.Random(seed)
    svcs = ["订单", "支付", "库存", "网关", "搜索", "推荐", "账单", "通知", "风控", "报表"]
    verbs = ["重启", "扩容", "回滚", "降级", "限流", "摘流量", "切主", "清缓存"]
    lines = ["你是值班助手。下面是运维手册，回答时只依据手册，引用规则编号。", ""]
    for i in range(1, n_rules + 1):
        s, v = r.choice(svcs), r.choice(verbs)
        lines.append(f"规则 {i:03d}：{s}服务在错误率连续 {r.randint(2,9)} 分钟超过 {r.randint(1,20)}% 时，"
                     f"先检查最近 {r.randint(10,90)} 分钟的发布记录；若有发布则{v}，若无发布则联系{r.choice(svcs)}服务负责人，"
                     f"并在值班频道记录告警编号、开始时间和处理人。处理时限 {r.randint(5,60)} 分钟，超时升级到二线。")
    return "\n".join(lines)

def post(path, body, stream=True):
    req = urllib.request.Request(H + path, json.dumps(body).encode(), {"Content-Type": "application/json"})
    t0 = time.perf_counter(); ttft = None; last = None; chunks = []; text = []; calls = []
    with urllib.request.urlopen(req, timeout=600) as r:
        for line in r:
            line = line.strip()
            if not line: continue
            if path.startswith("/v1"):
                if not line.startswith(b"data:"): continue
                d = line[5:].strip()
                if d == b"[DONE]": break
                j = json.loads(d)
                c = (j["choices"][0].get("delta") or {}).get("content") if j.get("choices") else None
                if c: text.append(c)
                if ttft is None and c:
                    ttft = time.perf_counter() - t0
                if j.get("usage"): last = j
                chunks.append(j)
            else:
                j = json.loads(line)
                msg = j.get("message", {}).get("content") if "message" in j else j.get("response")
                for tc in (j.get("message") or {}).get("tool_calls") or []: calls.append(tc)
                if msg: text.append(msg)
                if ttft is None and msg: ttft = time.perf_counter() - t0
                last = j
    wall = time.perf_counter() - t0
    return {"ttft": ttft, "wall": wall, "last": last, "text": "".join(text), "tool_calls": calls}

def chat(model, messages, opts=None, tools=None, keep_alive=None, num_predict=24):
    o = {"temperature": 0, "seed": 1, "num_predict": num_predict}
    o.update(opts or {})
    b = {"model": model, "messages": messages, "stream": True, "options": o}
    if tools is not None: b["tools"] = tools
    if keep_alive is not None: b["keep_alive"] = keep_alive
    return summarize(post("/api/chat", b))

def summarize(res):
    l = res["last"] or {}
    ns = lambda k: round(l.get(k, 0) / 1e6, 1)
    return {"ttft_ms": round((res["ttft"] or 0) * 1000, 1), "wall_ms": round(res["wall"] * 1000, 1),
            "prompt_eval_count": l.get("prompt_eval_count"), "cached": l.get("prompt_eval_cached_count"), "done_reason": l.get("done_reason"), "prompt_eval_ms": ns("prompt_eval_duration"),
            "load_ms": ns("load_duration"), "eval_count": l.get("eval_count"), "total_ms": ns("total_duration"), "text": res["text"], "tool_calls": res.get("tool_calls")}

def unload(model):
    urllib.request.urlopen(urllib.request.Request(H + "/api/generate", json.dumps({"model": model, "keep_alive": 0}).encode(),
                                                  {"Content-Type": "application/json"}), timeout=120).read()
    for _ in range(60):
        ps = json.loads(urllib.request.urlopen(H + "/api/ps").read())["models"]
        if not any(m["name"] == model for m in ps): return
        time.sleep(0.5)
