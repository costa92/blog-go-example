#!/usr/bin/env python3
"""A tiny ticket-system agent loop against Ollama's native /api/chat.

usage: agent.py --model M --task T --runs N --variant V --out logs/x.jsonl
Every run is written as one JSON line: messages, tool calls, timings, labels.
"""
import argparse, json, os, re, time, urllib.request

OLLAMA = "http://127.0.0.1:11434/api/chat"

USERS = {
    "U-03": {"name": "王磊", "email": "wanglei@example.com", "team": "支付组"},
    "U-07": {"name": "李娜", "email": "lina@example.com", "team": "支付组"},
    "U-11": {"name": "陈晨", "email": "chenchen@example.com", "team": "账号组"},
    "U-15": {"name": "赵敏", "email": "zhaomin@example.com", "team": "财务组"},
}
TICKETS = {
    "TK-1042": {"title": "支付回调超时导致订单重复扣款", "status": "open", "assignee": "U-07", "customer": "C-208"},
    "TK-1077": {"title": "企业客户批量导出发票失败", "status": "pending", "assignee": "U-15", "customer": "C-315"},
    "TK-1013": {"title": "发票抬头无法修改", "status": "closed", "assignee": "U-03", "customer": "C-102"},
    "TK-1090": {"title": "短信验证码登录失败", "status": "open", "assignee": "U-11", "customer": "C-421"},
    "TK-1101": {"title": "登录页偶发白屏", "status": "open", "assignee": "U-11", "customer": "C-208"},
}
# deliberately not sorted by date
ORDERS = {
    "C-315": [
        {"order_id": "O-5521", "date": "2026-10-15", "amount": 2210.75},
        {"order_id": "O-5530", "date": "2026-09-12", "amount": 560.00},
        {"order_id": "O-5588", "date": "2026-11-02", "amount": 1280.50},
        {"order_id": "O-5502", "date": "2026-09-30", "amount": 99.90},
        {"order_id": "O-5560", "date": "2026-10-28", "amount": 349.00},
    ],
    "C-208": [{"order_id": "O-5410", "date": "2026-11-01", "amount": 88.00}],
}
STATUSES = ("open", "pending", "closed")


def fn(name, desc, props, required):
    return {"type": "function", "function": {"name": name, "description": desc,
            "parameters": {"type": "object", "properties": props, "required": required}}}


S = lambda d: {"type": "string", "description": d}
TOOLS = [
    fn("search_tickets", "按关键词搜索工单标题，返回匹配工单的 id、标题和状态",
       {"query": S("标题里的关键词")}, ["query"]),
    fn("get_ticket", "按工单 id 读取工单详情，包括负责人 user_id 和客户 customer_id",
       {"ticket_id": S("工单 id")}, ["ticket_id"]),
    fn("get_user", "按 user_id 读取员工的姓名、邮箱和所在团队",
       {"user_id": S("员工 id")}, ["user_id"]),
    fn("list_orders", "按 customer_id 列出客户的全部订单（日期和金额）",
       {"customer_id": S("客户 id")}, ["customer_id"]),
    fn("update_ticket", "修改工单状态并附上备注",
       {"ticket_id": S("工单 id"), "status": S("新状态"), "note": S("备注")}, ["ticket_id", "status"]),
    fn("calc", "计算一个算术表达式，例如 1.5+2*3",
       {"expression": S("算术表达式")}, ["expression"]),
]

# variant "hint": the same tools with ID formats, enums and examples spelled out
HINTS = {
    "get_ticket": ("按工单 id 读取工单详情。ticket_id 形如 TK-0000，只能使用用户给出或 search_tickets 返回的 id。"
                   "返回里的 assignee 是负责人的 user_id（形如 U-00），customer 是客户 id（形如 C-000）"),
    "get_user": "按 user_id 读取员工的姓名、邮箱和所在团队。user_id 形如 U-00，取自 get_ticket 返回的 assignee",
    "list_orders": "按 customer_id 列出客户的全部订单，结果不按日期排序。customer_id 形如 C-000，取自 get_ticket 返回的 customer",
    "update_ticket": "修改工单状态并附上备注。status 只能是 open、pending、closed 三者之一",
}


def tools_for(variant):
    if variant not in ("hint", "hint+sys"):
        return TOOLS
    out = json.loads(json.dumps(TOOLS))
    for t in out:
        f = t["function"]
        if f["name"] in HINTS:
            f["description"] = HINTS[f["name"]]
        if f["name"] == "update_ticket":
            f["parameters"]["properties"]["status"]["enum"] = list(STATUSES)
    return out


SYSTEM = {
    "base": "你是工单系统助手。需要数据时调用工具，拿到结果后用中文简短回答用户。",
}
SYSTEM["hint"] = SYSTEM["base"]
SYSTEM["sys"] = SYSTEM["base"] + (
    "规则：1. 一次只做一步，先调用工具拿到结果再决定下一步。2. 工具参数里的 id 只能来自用户的问题或之前工具返回的内容，"
    "不能猜。3. 工具返回 error 时，不能声称操作成功，要么修正参数重试，要么如实告诉用户失败原因。4. 需要的数据都拿到后再回答。")
SYSTEM["hint+sys"] = SYSTEM["sys"]

TASKS = {
    "t1": {"q": "工单 TK-1042 的负责人叫什么名字？", "need": ["get_ticket", "get_user"]},
    "t2": {"q": "标题里带“发票”的工单中，还没关闭的那张，负责人的邮箱是什么？", "need": ["search_tickets", "get_ticket", "get_user"]},
    "t3": {"q": "工单 TK-1077 对应客户最近三笔订单的总金额是多少？", "need": ["get_ticket", "list_orders"]},
    "t4": {"q": "把标题里有“登录失败”的工单状态改成 resolved，备注写“已修复”。", "need": ["search_tickets", "update_ticket"]},
    "t5": {"q": "TK-1042 和 TK-1090 这两张工单的负责人分别在哪个团队？", "need": ["get_ticket", "get_user"]},
}


def run_tool(name, args, state):
    if not isinstance(args, dict):
        return {"error": "arguments must be an object"}
    def need(*ks):
        miss = [k for k in ks if not isinstance(args.get(k), str) or not args.get(k).strip()]
        return {"error": f"missing required argument: {', '.join(miss)}"} if miss else None
    if name == "search_tickets":
        if e := need("query"): return e
        q = args["query"].strip()
        return {"results": [{"id": k, "title": v["title"], "status": v["status"]} for k, v in TICKETS.items() if q in v["title"]]}
    if name == "get_ticket":
        if e := need("ticket_id"): return e
        t = TICKETS.get(args["ticket_id"].strip())
        return {"id": args["ticket_id"], **t} if t else {"error": f"ticket {args['ticket_id']} not found"}
    if name == "get_user":
        if e := need("user_id"): return e
        u = USERS.get(args["user_id"].strip())
        return {"user_id": args["user_id"], **u} if u else {"error": f"user {args['user_id']} not found"}
    if name == "list_orders":
        if e := need("customer_id"): return e
        o = ORDERS.get(args["customer_id"].strip())
        return {"customer_id": args["customer_id"], "orders": o} if o is not None else {"error": f"customer {args['customer_id']} not found"}
    if name == "update_ticket":
        if e := need("ticket_id", "status"): return e
        tid = args["ticket_id"].strip()
        if tid not in TICKETS: return {"error": f"ticket {tid} not found"}
        if args["status"] not in STATUSES:
            return {"error": f"invalid status '{args['status']}', allowed: open, pending, closed"}
        state["updates"].append({"ticket_id": tid, "status": args["status"], "note": args.get("note")})
        return {"ok": True, "ticket_id": tid, "status": args["status"]}
    if name == "calc":
        if e := need("expression"): return e
        ex = args["expression"]
        if not re.fullmatch(r"[0-9.+\-*/() ]+", ex): return {"error": "only numbers and + - * / ( ) are allowed"}
        try:
            return {"result": round(eval(ex, {"__builtins__": {}}), 4)}
        except Exception as e:
            return {"error": str(e)}
    return {"error": f"unknown tool {name}"}


def chat(model, messages, tools, seed, think):
    messages = [{k: v for k, v in m.items() if k != "text_call_raw"} for m in messages]
    body = {"model": model, "messages": messages, "tools": tools, "stream": False,
            "options": {"temperature": 0.8, "seed": seed, "num_ctx": 8192}, "keep_alive": "10m"}
    if think is not None:
        body["think"] = think
    req = urllib.request.Request(OLLAMA, json.dumps(body).encode(), {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as r:
        return json.load(r)


TOOL_NAMES = {t["function"]["name"] for t in TOOLS}


PARSER = "v2"


def parse_text_calls(content):
    """Client-side fallback: a reply whose text is nothing but JSON tool calls
    (one or several objects, a JSON list, ```json fences or <tool_call> tags)
    is treated as structured calls. Any other text in the reply: no calls."""
    text = re.sub(r"</?tool_call>", "\n", content)
    text = re.sub(r"```(?:json)?", "\n", text).strip()
    dec, pos, objs = json.JSONDecoder(), 0, []
    while pos < len(text):
        while pos < len(text) and text[pos] in " \t\r\n,":
            pos += 1
        if pos >= len(text):
            break
        try:
            obj, pos = dec.raw_decode(text, pos)
        except ValueError:
            return []
        objs.extend(obj if isinstance(obj, list) else [obj])
    out = []
    for o in objs:
        if not isinstance(o, dict) or o.get("name") not in TOOL_NAMES:
            return []
        out.append({"function": {"name": o["name"], "arguments": o.get("arguments", o.get("parameters", {}))}})
    return out


def one_run(model, task, variant, seed, think, textparse=False, max_turns=10):
    msgs = [{"role": "system", "content": SYSTEM[variant]}, {"role": "user", "content": TASKS[task]["q"]}]
    state = {"updates": []}
    text_calls = 0
    calls, t0 = [], time.time()
    final, stop = None, "max_turns"
    for turn in range(max_turns):
        try:
            r = chat(model, msgs, tools_for(variant), seed, think)
        except Exception as e:
            stop = f"http_error: {e}"
            break
        m = r["message"]
        msgs.append({k: v for k, v in m.items() if k in ("role", "content", "tool_calls", "thinking")})
        tcs = m.get("tool_calls") or []
        if not tcs and textparse:
            tcs = parse_text_calls(m.get("content", ""))
            if tcs:
                text_calls += len(tcs)
                # hand it back as a structured call, the way a framework fallback would
                msgs[-1] = {"role": "assistant", "content": "", "tool_calls": tcs, "text_call_raw": m.get("content", "")}
        if not tcs:
            final, stop = m.get("content", ""), "answer"
            break
        for tc in tcs:
            f = tc.get("function", {})
            name, args = f.get("name"), f.get("arguments")
            res = run_tool(name, args, state)
            calls.append({"turn": turn, "name": name, "args": args, "result": res})
            msgs.append({"role": "tool", "tool_name": name, "content": json.dumps(res, ensure_ascii=False)})
    return {"model": model, "task": task, "variant": variant, "seed": seed, "think": think,
            "stop": stop, "turns": turn + 1, "secs": round(time.time() - t0, 2),
            "calls": calls, "text_calls": text_calls, "textparse": textparse, "parser": PARSER if textparse else None, "updates": state["updates"], "final": final, "messages": msgs}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--task", nargs="+", default=list(TASKS))
    ap.add_argument("--runs", type=int, default=5)
    ap.add_argument("--variant", default="base", choices=list(SYSTEM))
    ap.add_argument("--think", choices=["true", "false"])
    ap.add_argument("--out", required=True)
    ap.add_argument("--textparse", action="store_true")
    a = ap.parse_args()
    think = None if a.think is None else a.think == "true"
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    with open(a.out, "a") as fo:
        for task in a.task:
            for seed in range(1, a.runs + 1):
                rec = one_run(a.model, task, a.variant, seed, think, a.textparse)
                fo.write(json.dumps(rec, ensure_ascii=False) + "\n"); fo.flush()
                print(a.model, task, seed, rec["stop"], len(rec["calls"]), rec["secs"],
                      (rec["final"] or "").replace("\n", " ")[:80], flush=True)
