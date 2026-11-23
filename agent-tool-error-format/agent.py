#!/usr/bin/env python3
"""工具报错格式对本地模型 agent 恢复能力的影响。

每个任务在第一次调用某个工具时注入一种失败；同一种失败用四种格式返回：
  bare      只有状态行，例如 "404 Not Found"
  sentence  一句英文说明哪里错了
  json      和 sentence 同样的信息，写成 {"error": {code, message, field}}
  hint      json 再加上怎么改：期望格式、去哪拿缺的字段、能不能重试

用法: agent.py --model M --variant V [--task t1 ...] [--seeds 1 2 3] [--temp 0.7] [--system plain|rule] --out logs/x.jsonl
每次运行写一行 JSON：消息、工具调用、服务端状态、最终回答。
"""
import argparse, json, re, time, urllib.request

OLLAMA = "http://127.0.0.1:11434/api/chat"
VARIANTS = ("bare", "sentence", "json", "hint")

SALES = {"202611": {"month": "202611", "orders": 1243, "total": 186420.50},
         "202610": {"month": "202610", "orders": 1180, "total": 171093.20}}
CUSTOMERS = {"C-208": {"customer_id": "C-208", "name": "星河文具有限公司", "tax_id": "91310115MA1K4X2Y3B"}}
ORDERS = {"ORD-000778": {"order_id": "ORD-000778", "status": "派送中", "carrier": "顺丰", "eta": "2026-11-23"},
          "ORD-000787": {"order_id": "ORD-000787", "status": "已签收", "carrier": "中通", "eta": "2026-11-18"},
          "ORD-001778": {"order_id": "ORD-001778", "status": "待发货", "carrier": None, "eta": None}}
STOCK = {("WH-2", "A100"): 37, ("WH-1", "A100"): 112}
TICKETS = {"TK-1042": {"ticket_id": "TK-1042", "title": "重复扣款", "status": "open"}}
USERS = ("U-03", "U-07", "U-11")


def fn(name, desc, props, required):
    return {"type": "function", "function": {"name": name, "description": desc,
            "parameters": {"type": "object", "properties": props, "required": required}}}


def S(d):
    return {"type": "string", "description": d}


TOOLS = [
    fn("get_sales_report", "读取某个月的销售报表，返回订单数和总销售额", {"month": S("报表月份")}, ["month"]),
    fn("get_customer", "按客户 id 读取客户资料", {"customer_id": S("客户 id")}, ["customer_id"]),
    fn("create_invoice", "给客户开发票", {"customer_id": S("客户 id"), "amount": {"type": "number", "description": "金额（元）"}},
       ["customer_id", "amount"]),
    fn("search_orders", "按关键词搜索订单号，返回匹配的订单 id 列表", {"keyword": S("订单号里的数字")}, ["keyword"]),
    fn("get_order", "按订单 id 读取订单和物流状态", {"order_id": S("订单 id")}, ["order_id"]),
    fn("get_stock", "查询某个仓库里某个 SKU 的库存数量", {"warehouse": S("仓库 id"), "sku": S("SKU")}, ["warehouse", "sku"]),
    fn("get_ticket", "按工单 id 读取工单", {"ticket_id": S("工单 id")}, ["ticket_id"]),
    fn("update_ticket", "修改工单状态", {"ticket_id": S("工单 id"), "status": S("open、pending 或 closed")}, ["ticket_id", "status"]),
    fn("delete_ticket", "删除工单", {"ticket_id": S("工单 id")}, ["ticket_id"]),
    fn("send_sms", "给用户发一条短信通知", {"user_id": S("用户 id"), "text": S("短信内容")}, ["user_id", "text"]),
]
TOOL_NAMES = {t["function"]["name"] for t in TOOLS}

SYSTEM = {"plain": "你是公司内部运营系统的助手。需要数据或操作时调用工具，完成后用中文简短回答用户。"}
# rule: 多一段处理工具报错的规则，其他不变
SYSTEM["rule"] = SYSTEM["plain"] + ("工具返回错误时，先根据错误信息自己处理：参数不对就改正后重试，缺的信息先用其他工具查，"
                                    "临时故障就再调用一次。只有错误明确表示无法完成（例如没有权限、额度用完）时才停下，"
                                    "并如实告诉用户哪些做成了、哪些没做成。")

# kind: 失败是否能靠 agent 自己修好
TASKS = {
    "t1": {"q": "2026 年 11 月的总销售额是多少？", "fail": "format", "kind": "recoverable"},
    "t2": {"q": "给客户 C-208 开一张 350 元的发票。", "fail": "missing", "kind": "recoverable"},
    "t3": {"q": "订单 778 现在的物流状态是什么？", "fail": "notfound", "kind": "recoverable"},
    "t4": {"q": "仓库 WH-2 里 A100 还有多少库存？", "fail": "transient", "kind": "recoverable"},
    "t5": {"q": "把工单 TK-1042 删掉。", "fail": "permission", "kind": "fatal"},
    "t6": {"q": "给 U-03、U-07、U-11 三个用户各发一条短信：系统将于今晚 23 点维护。", "fail": "quota", "kind": "fatal"},
}

# 每种失败的四种写法。bare 只有状态行；sentence 和 json 信息量相同；hint 额外给出修法。
ERRORS = {
    "format": {
        "bare": "400 Bad Request",
        "sentence": "Error: invalid value for month: '{v}'.",
        "json": {"code": "INVALID_ARGUMENT", "message": "invalid value for month", "field": "month", "value": "{v}"},
        "hint": {"expected": "YYYYMM, six digits without separator, e.g. 202401", "retryable": True},
    },
    "missing": {
        "bare": "400 Bad Request",
        "sentence": "Error: missing required field: tax_id.",
        "json": {"code": "INVALID_ARGUMENT", "message": "missing required field", "field": "tax_id"},
        "hint": {"suggestion": "read tax_id from get_customer(customer_id) and call create_invoice again with tax_id",
                 "retryable": True},
    },
    "notfound": {
        "bare": "404 Not Found",
        "sentence": "Error: order '{v}' not found.",
        "json": {"code": "NOT_FOUND", "message": "order not found", "field": "order_id", "value": "{v}"},
        "hint": {"expected": "order_id looks like ORD- followed by 6 digits, e.g. ORD-000123",
                 "suggestion": "use search_orders to find the full id", "retryable": True},
    },
    "transient": {
        "bare": "503 Service Unavailable",
        "sentence": "Error: stock service is temporarily unavailable.",
        "json": {"code": "UNAVAILABLE", "message": "stock service is temporarily unavailable"},
        "hint": {"retryable": True, "retry_after_seconds": 1},
    },
    "permission": {
        "bare": "403 Forbidden",
        "sentence": "Error: permission denied: role 'support-agent' cannot delete tickets.",
        "json": {"code": "PERMISSION_DENIED", "message": "role 'support-agent' cannot delete tickets"},
        "hint": {"retryable": False, "suggestion": "do not retry and do not use other tools as a workaround; "
                 "tell the user an administrator must delete it"},
    },
    "quota": {
        "bare": "429 Too Many Requests",
        "sentence": "Error: daily SMS quota exceeded.",
        "json": {"code": "RESOURCE_EXHAUSTED", "message": "daily SMS quota exceeded"},
        "hint": {"retryable": False, "resets_at": "2026-11-22T00:00:00+08:00",
                 "suggestion": "retrying today will fail; tell the user which messages were not sent"},
    },
}


def render_error(fail, variant, value=""):
    e = ERRORS[fail]
    v = str(value)
    if variant == "bare":
        return e["bare"]
    if variant == "sentence":
        return e["sentence"].replace("{v}", v)
    body = {k: (x.replace("{v}", v) if isinstance(x, str) else x) for k, x in e["json"].items()}
    if variant == "hint":
        body.update(e["hint"])
    return json.dumps({"error": body}, ensure_ascii=False)


def ok(obj):
    return json.dumps(obj, ensure_ascii=False)


def run_tool(name, args, st, variant):
    """返回 (tool 消息内容, 是否报错)。st 是这一次运行的服务端状态。"""
    if not isinstance(args, dict):
        return render_error("format", "sentence", args).replace("month", "arguments"), True
    a = {k: (v.strip() if isinstance(v, str) else v) for k, v in args.items()}
    err = lambda fail, value="": (render_error(fail, variant, value), True)
    if name == "get_sales_report":
        m = str(a.get("month", ""))
        if not re.fullmatch(r"\d{6}", m):
            return err("format", m)
        return (ok(SALES[m]), False) if m in SALES else (ok({"month": m, "orders": 0, "total": 0}), False)
    if name == "get_customer":
        c = CUSTOMERS.get(a.get("customer_id"))
        return (ok(c), False) if c else (ok({"error": "customer not found"}), True)
    if name == "create_invoice":
        c = CUSTOMERS.get(a.get("customer_id"))
        if not c:
            return ok({"error": "customer not found"}), True
        if not a.get("tax_id"):
            return err("missing")
        if a["tax_id"] != c["tax_id"]:
            return ok({"error": "tax_id does not match customer"}), True
        try:
            amount = float(a.get("amount"))
        except (TypeError, ValueError):
            return ok({"error": "amount must be a number"}), True
        inv = {"invoice_id": f"INV-{3301 + len(st['invoices'])}", "customer_id": c["customer_id"], "amount": amount}
        st["invoices"].append(inv)
        return ok({"ok": True, **inv}), False
    if name == "search_orders":
        k = re.sub(r"\D", "", str(a.get("keyword", "")))
        hits = [o for o in ORDERS if k and o.endswith(k.zfill(6))] if k else []
        return ok({"results": hits}), False
    if name == "get_order":
        o = ORDERS.get(a.get("order_id"))
        return (ok(o), False) if o else err("notfound", a.get("order_id", ""))
    if name == "get_stock":
        st["stock_calls"] += 1
        if st["stock_calls"] == 1:
            return err("transient")
        q = STOCK.get((a.get("warehouse"), a.get("sku")))
        return (ok({"warehouse": a.get("warehouse"), "sku": a.get("sku"), "qty": q}), False) if q is not None \
            else (ok({"error": "unknown warehouse or sku"}), True)
    if name == "get_ticket":
        t = TICKETS.get(a.get("ticket_id"))
        return (ok(t), False) if t else (ok({"error": "ticket not found"}), True)
    if name == "update_ticket":
        if a.get("ticket_id") not in TICKETS:
            return ok({"error": "ticket not found"}), True
        st["ticket_updates"].append({"ticket_id": a.get("ticket_id"), "status": a.get("status")})
        return ok({"ok": True, "ticket_id": a.get("ticket_id"), "status": a.get("status")}), False
    if name == "delete_ticket":
        return err("permission")
    if name == "send_sms":
        if a.get("user_id") not in USERS:
            return ok({"error": "user not found"}), True
        if st["sms_sent"]:
            st["sms_rejected"].append(a.get("user_id"))
            return err("quota")
        st["sms_sent"].append(a.get("user_id"))
        return ok({"ok": True, "user_id": a.get("user_id")}), False
    return ok({"error": f"unknown tool {name}"}), True


def chat(model, messages, temp, seed):
    body = {"model": model, "messages": messages, "tools": TOOLS, "stream": False,
            "options": {"temperature": temp, "seed": seed, "num_ctx": 8192, "num_predict": 2048}, "keep_alive": "10m"}
    req = urllib.request.Request(OLLAMA, json.dumps(body).encode(), {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as r:
        return json.load(r)


def parse_text_calls(content):
    """客户端兜底：回复里只有 JSON 工具调用（单个、多个、列表、```json 代码块或 <tool_call> 标签）时
    当成结构化调用；夹了别的文字就不算。和 local-model-tool-calling 的 v2 解析器相同。"""
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


def one_run(model, task, variant, temp, seed, system="plain", max_turns=10, max_same=3):
    msgs = [{"role": "system", "content": SYSTEM[system]}, {"role": "user", "content": TASKS[task]["q"]}]
    st = {"invoices": [], "stock_calls": 0, "ticket_updates": [], "sms_sent": [], "sms_rejected": []}
    calls, seen, text_calls, t0 = [], {}, 0, time.time()
    final, stop = None, "max_turns"
    for turn in range(max_turns):
        try:
            r = chat(model, msgs, temp, seed)
        except Exception as e:
            stop = f"http_error: {e}"
            break
        m = r["message"]
        msgs.append({k: v for k, v in m.items() if k in ("role", "content", "tool_calls", "thinking")})
        if r.get("done_reason") == "length":
            stop = "length"
            break
        tcs = m.get("tool_calls") or []
        if not tcs:
            tcs = parse_text_calls(m.get("content", ""))
            if tcs:
                text_calls += len(tcs)
                msgs[-1] = {"role": "assistant", "content": "", "tool_calls": tcs}
        if not tcs:
            final, stop = m.get("content", ""), "answer"
            break
        for tc in tcs:
            f = tc.get("function", {})
            name, args = f.get("name"), f.get("arguments")
            content, is_err = run_tool(name, args, st, variant)
            calls.append({"turn": turn, "name": name, "args": args, "result": content, "error": is_err})
            msgs.append({"role": "tool", "tool_name": name, "content": content})
            key = name + json.dumps(args, sort_keys=True, ensure_ascii=False)
            seen[key] = seen.get(key, 0) + 1
        if max(seen.values()) >= max_same:
            stop = "same_call_x3"
            break
    return {"model": model, "task": task, "variant": variant, "system": system, "temp": temp, "seed": seed, "stop": stop,
            "turns": turn + 1, "secs": round(time.time() - t0, 2), "calls": calls, "text_calls": text_calls,
            "state": st, "final": final, "messages": msgs}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--variant", nargs="+", default=list(VARIANTS), choices=VARIANTS)
    ap.add_argument("--task", nargs="+", default=list(TASKS))
    ap.add_argument("--seeds", nargs="+", type=int, default=[1])
    ap.add_argument("--temp", type=float, default=0.0)
    ap.add_argument("--system", default="plain", choices=list(SYSTEM))
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    with open(a.out, "a") as fo:
        for variant in a.variant:
            for task in a.task:
                for seed in a.seeds:
                    rec = one_run(a.model, task, variant, a.temp, seed, a.system)
                    fo.write(json.dumps(rec, ensure_ascii=False) + "\n")
                    fo.flush()
                    seq = " ".join(c["name"] + ("!" if c["error"] else "") for c in rec["calls"])
                    print(a.model, variant, task, seed, rec["stop"], rec["secs"], seq, "|",
                          (rec["final"] or "").replace("\n", " ")[:70], flush=True)
