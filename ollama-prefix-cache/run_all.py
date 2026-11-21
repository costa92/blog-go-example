#!/usr/bin/env python3
"""run_all.py MODEL CASE...  -> logs/<model>-<case>.jsonl (one JSON per call)"""
import json, os, random, subprocess, sys, time, datetime
import lib

M = sys.argv[1]; CASES = sys.argv[2:]
CTX = {"num_ctx": 8192}
SP = lib.handbook(80)
Q = "支付服务错误率 12% 持续 5 分钟，没有发布，按手册该怎么做？"
TOOLS = [{"type": "function", "function": {"name": n, "description": d + "。调用前确认告警编号和服务名，结果会写入值班记录，失败时返回错误码和原因。",
          "parameters": {"type": "object", "properties": {"service": {"type": "string", "description": "服务名，例如 支付、订单"},
                                                          "alert_id": {"type": "string", "description": "告警编号"}},
                         "required": ["service"]}}}
         for n, d in [("restart_service", "重启指定服务的全部实例"), ("scale_service", "把服务副本数调整到指定值"),
                      ("rollback_release", "回滚到上一个发布版本"), ("enable_degrade", "打开服务降级开关"),
                      ("set_rate_limit", "设置入口限流阈值"), ("drain_traffic", "把服务从负载均衡摘除"),
                      ("failover_db", "数据库主从切换"), ("flush_cache", "清空服务的本地和分布式缓存")]]

def gpu():
    return subprocess.run(["nvidia-smi", "--query-gpu=memory.used,utilization.gpu", "--format=csv,noheader"],
                          capture_output=True, text=True).stdout.strip()

def ps():
    j = json.loads(lib.urllib.request.urlopen(lib.H + "/api/ps").read())
    return [(m["name"], m.get("context_length")) for m in j["models"]]

out = None
def rec(case, label, r, **extra):
    r = dict(case=case, label=label, **extra, **r)
    print(json.dumps(r, ensure_ascii=False), flush=True)
    out.write(json.dumps(r, ensure_ascii=False) + "\n"); out.flush()

def base(sys_text=SP, q=Q):
    return [{"role": "system", "content": sys_text}, {"role": "user", "content": q}]

def warm():
    lib.chat(M, base(), CTX)

def case_cold():
    for i in range(5):
        lib.unload(M)
        rec("cold", "after_unload", lib.chat(M, base(), CTX), rep=i)
        rec("cold", "repeat", lib.chat(M, base(), CTX), rep=i)

def case_same():
    warm()
    for i in range(6):
        rec("same", "identical", lib.chat(M, base(), CTX), rep=i)

def stamp():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")

def case_stamp():
    for where in ("start", "end", "user"):
        warm()
        for i in range(5):
            s = f"当前时间：{stamp()}，请求编号 req-{random.randrange(10**8):08d}。"
            if where == "start": m = base(s + "\n" + SP)
            elif where == "end": m = base(SP + "\n" + s)
            else: m = base(SP, s + "\n" + Q)
            rec("stamp", where, lib.chat(M, m, CTX), rep=i)

def case_tools():
    for mode in ("fixed", "shuffled"):
        lib.chat(M, base(), CTX, tools=TOOLS)
        for i in range(5):
            t = TOOLS[:]
            if mode == "shuffled": random.Random(i).shuffle(t)
            rec("tools", mode, lib.chat(M, base(), CTX, tools=t), rep=i)

def case_turns():
    for mode in ("append", "window3"):
        warm()
        hist = []
        qs = [f"{s}服务错误率 {p}% 持续 {m} 分钟，{'有' if m % 2 else '没有'}发布，按手册该怎么做？"
              for s, p, m in [("支付", 12, 5), ("订单", 8, 7), ("库存", 15, 3), ("网关", 4, 9), ("搜索", 18, 6), ("通知", 9, 4), ("风控", 6, 8)]]
        for i, q in enumerate(qs):
            hist.append({"role": "user", "content": q})
            if mode == "window3": h = hist[-5:]
            else: h = hist
            r = lib.chat(M, [{"role": "system", "content": SP}] + h, CTX, num_predict=60)
            rec("turns", mode, r, turn=i + 1, msgs=len(h))
            hist.append({"role": "assistant", "content": r["text"]})


def case_opts():
    warm()
    for i in range(5):
        rec("opts", "temp0", lib.chat(M, base(), dict(CTX, temperature=0)), rep=i)
        rec("opts", "temp0.8", lib.chat(M, base(), dict(CTX, temperature=0.8)), rep=i)
    warm()
    for i in range(5):
        rec("opts", "ctx16384", lib.chat(M, base(), {"num_ctx": 16384}), rep=i, ps=ps())
        rec("opts", "ctx8192", lib.chat(M, base(), CTX), rep=i, ps=ps())

def case_other():
    for other in ("qwen2.5-coder:0.5b", "llama3.1:8b"):
        warm()
        for i in range(5):
            lib.chat(other, [{"role": "user", "content": "你好"}], num_predict=4)
            p = ps()
            rec("other", other, lib.chat(M, base(), CTX), rep=i, ps_after_other=p, gpu=gpu())
        lib.unload(other)

def case_keepalive():
    warm()
    for i in range(5):
        lib.chat(M, base(), CTX, keep_alive="5s")
        time.sleep(8)
        p = ps()
        rec("keepalive", "expired_5s", lib.chat(M, base(), CTX), rep=i, ps_before=p)

def case_interleave():
    sp2 = lib.handbook(80, seed=11)
    warm()
    for i in range(6):
        rec("interleave", "P1", lib.chat(M, base(SP), CTX), rep=i)
        rec("interleave", "P2", lib.chat(M, base(sp2), CTX), rep=i)

def case_interleave3():
    sps = [SP, lib.handbook(80, seed=11), lib.handbook(80, seed=23)]
    warm()
    for i in range(5):
        for k, s in enumerate(sps):
            rec("interleave3", f"P{k+1}", lib.chat(M, base(s), CTX), rep=i)

QS = [f"{s}服务错误率 {p}% 持续 {m} 分钟，{'有' if m % 2 else '没有'}发布，按手册该怎么做？"
      for s, p, m in [("支付", 12, 5), ("订单", 8, 7), ("库存", 15, 3), ("网关", 4, 9), ("搜索", 18, 6), ("通知", 9, 4), ("风控", 6, 8)]]

def case_turns_tools():
    lib.chat(M, base(), CTX, tools=TOOLS)
    hist = []
    for i, q in enumerate(QS):
        hist.append({"role": "user", "content": q})
        r = lib.chat(M, [{"role": "system", "content": SP}] + hist, CTX, tools=TOOLS, num_predict=60)
        rec("turns_tools", "append+tools", r, turn=i + 1, msgs=len(hist))
        hist.append({"role": "assistant", "content": r["text"]})

def v1(messages, extra=None):
    b = {"model": M, "messages": messages, "stream": True, "max_tokens": 24, "temperature": 0, "seed": 1,
         "stream_options": {"include_usage": True}}
    b.update(extra or {})
    res = lib.post("/v1/chat/completions", b)
    u = (res["last"] or {}).get("usage", {})
    return {"ttft_ms": round((res["ttft"] or 0) * 1000, 1), "wall_ms": round(res["wall"] * 1000, 1),
            "prompt_eval_count": u.get("prompt_tokens"), "cached": (u.get("prompt_tokens_details") or {}).get("cached_tokens"),
            "prompt_eval_ms": None, "load_ms": None, "usage": u, "text": res["text"]}

SHORT = lib.handbook(35)

def case_v1():
    m = base(SHORT)
    lib.chat(M, m)
    for i in range(5):
        rec("v1", "native_default_ctx", lib.chat(M, m), rep=i, ps=ps())
        rec("v1", "v1", v1(m), rep=i, ps=ps())
    for i in range(5):
        rec("v1", "native_ctx8192", lib.chat(M, m, CTX), rep=i, ps=ps())
        rec("v1", "v1", v1(m), rep=i, ps=ps())

def gen(system, prompt, opts=None):
    o = {"temperature": 0, "seed": 1, "num_predict": 24}; o.update(opts or {})
    return lib.summarize(lib.post("/api/generate", {"model": M, "system": system, "prompt": prompt, "stream": True, "options": o}))

def case_generate():
    lib.chat(M, base(), CTX)
    for i in range(5):
        rec("generate", "generate_after_chat", gen(SP, Q, CTX), rep=i)
        rec("generate", "chat_after_generate", lib.chat(M, base(), CTX), rep=i)

def case_agent():
    lib.chat(M, base(), CTX, tools=TOOLS)
    hist = []
    for i, q in enumerate(QS[:5]):
        hist.append({"role": "user", "content": q})
        for step in range(3):
            r = lib.chat(M, [{"role": "system", "content": SP}] + hist, CTX, tools=TOOLS, num_predict=60)
            kind = "tool_call" if r["tool_calls"] else "answer"
            rec("agent", kind, r, turn=i + 1, step=step, msgs=len(hist), last_role=hist[-1]["role"])
            if r["tool_calls"]:
                hist.append({"role": "assistant", "content": "", "tool_calls": r["tool_calls"]})
                hist.append({"role": "tool", "content": "执行成功，告警已记录。"})
            else:
                hist.append({"role": "assistant", "content": r["text"]})
                break

case_fns = {k[5:]: v for k, v in globals().items() if k.startswith("case_")}
os.makedirs("logs", exist_ok=True)
for c in CASES:
    with open(f"logs/{M.replace(':', '_')}-{c}.jsonl", "w") as out:
        print(f"# {c} gpu={gpu()} ps={ps()}", flush=True)
        out.write(json.dumps({"meta": c, "model": M, "gpu": gpu(), "ps": ps(), "at": stamp()}) + "\n")
        since = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        case_fns[c]()
        time.sleep(1)
        j = subprocess.run(["journalctl", "-u", "ollama", "--no-pager", "-o", "cat", "--since", since], capture_output=True, text=True).stdout
        keep = [l for l in j.splitlines() if any(k in l for k in ("cached n_tokens", "prompt eval time", "srv ", "truncating", "llama-server started", "level=INFO source=sched", "level=INFO source=server"))]
        open(f"logs/{M.replace(':', '_')}-{c}.journal", "w").write("\n".join(keep) + "\n")
