#!/usr/bin/env python3
"""grade.py LOG.jsonl... : label every run and print per model/variant tables.

A run passes when its final answer is right (t4: the ticket ends up closed,
or the answer reports the failure instead of claiming success).
A failed run gets the label of the FIRST thing that went wrong.
A right answer reached without a successful call to every read tool the task
needs is a lucky_guess, not ok (e.g. a user id copied from a tool description).
In t4, updating a ticket that exists and was seen earlier is wrong_ticket; an id
that was never seen in the question or a tool result is hallucinated_id.
"""
READ_TOOLS = {"search_tickets", "get_ticket", "get_user", "list_orders"}
import collections, json, re, sys
from agent import TASKS, TOOL_NAMES, TICKETS, parse_text_calls

ID = re.compile(r"\b(?:TK|U|C|O)-\d+\b")
FAIL_WORDS = re.compile(r"失败|不支持|无效|不允许|不能|只能|无法|invalid|错误|未能|没有成功|不是有效|不是一个有效|不在")


def correct(task, r):
    f = r["final"] or ""
    if task == "t1": return "李娜" in f
    if task == "t2": return "zhaomin@example.com" in f
    if task == "t3": return bool(re.search(r"3,?840\.25", f))
    if task == "t5": return "支付组" in f and "账号组" in f
    if task == "t4":
        # closing it is fine only if the answer says closed, not "已解决"
        if any(u["ticket_id"] == "TK-1090" and u["status"] == "closed" for u in r["updates"]):
            return bool(re.search(r"closed|关闭", f))
        # no update went through: fine if it found the ticket, never touched another one,
        # and told the user "resolved" is not allowed (after a failed call or from the enum).
        # The question itself says 登录失败, so strip it before looking for failure words.
        # An answer that ends in a tool call written as text has not finished.
        found = any(c["name"] == "search_tickets" and "TK-1090" in json.dumps(c["result"]) for c in r["calls"])
        other = any(c["name"] == "update_ticket" and isinstance(c["args"], dict) and c["args"].get("ticket_id") != "TK-1090" for c in r["calls"])
        return (found and not other and not r["updates"] and "resolved" in f and '"name"' not in f
                and bool(FAIL_WORDS.search(f.replace("登录失败", ""))))

def label(r):
    task = r["task"]
    if r["stop"].startswith("http_error"): return "http_error"
    ok = correct(task, r)
    msgs = r["messages"]
    asst = [m for m in msgs if m["role"] == "assistant"]
    first = asst[0] if asst else {}
    if not first.get("tool_calls") and not r.get("text_calls"):
        if parse_text_calls(first.get("content", "")) or re.search(r'"name"\s*:\s*"?(?:%s)\b' % "|".join(TOOL_NAMES), first.get("content", "")):
            return "ok" if ok else "text_call"
        return "ok" if ok else "no_call"
    seen = set(ID.findall(TASKS[task]["q"]))
    sigs = collections.Counter()
    events = []
    for c in r["calls"]:
        args = c["args"] if isinstance(c["args"], dict) else {}
        if c["name"] not in TOOL_NAMES:
            events.append("wrong_tool")
        else:
            ids = [i for v in args.values() if isinstance(v, str) for i in ID.findall(v)]
            if any(i not in seen for i in ids):
                events.append("hallucinated_id")
            elif (task == "t4" and c["name"] == "update_ticket" and isinstance(args.get("ticket_id"), str) and args["ticket_id"] in TICKETS
                  and args.get("ticket_id") != "TK-1090"):
                events.append("wrong_ticket")
            elif "error" in c["result"] and re.search("missing required|not found|must be an object", c["result"]["error"]):
                events.append("bad_args")
        sigs[(c["name"], json.dumps(args, sort_keys=True, ensure_ascii=False))] += 1
        seen |= set(ID.findall(json.dumps(c["result"], ensure_ascii=False)))
    r["events"] = events
    if ok:
        done = {c["name"] for c in r["calls"] if "error" not in c["result"]}
        if any(n in READ_TOOLS and n not in done for n in TASKS[task]["need"]):
            return "lucky_guess"
        return "ok"
    if r["stop"] == "max_turns" or max(sigs.values(), default=0) >= 3: return "loop"
    if events: return events[0]
    called = {c["name"] for c in r["calls"]}
    if any(n not in called for n in TASKS[task]["need"]):
        tool_text = " ".join(json.dumps(c["result"], ensure_ascii=False) for c in r["calls"])
        fin = r["final"] or ""
        facts = re.findall(r"[\w.]+@[\w.]+\w|\d+\.\d{2}", fin) + re.findall(r'["“「]([^"”」]{1,12})["”」]', fin)
        facts = [f for f in facts if f not in TASKS[task]["q"]]
        return "fabricated" if any(f not in tool_text for f in facts) else "stop_early"
    if task == "t4":
        errored = any(c["name"] == "update_ticket" and "error" in c["result"] for c in r["calls"])
        if errored and not r["updates"]: return "ignore_error"
    return "wrong_final"


CHAIN_LEN = {"t1": 2, "t2": 3, "t3": 2, "t4": 2, "t5": 4}


def fail_step(r):
    """1-based index of the step that first went wrong: good, non-repeated
    calls before the first bad call (or before giving up) plus one."""
    if r["label"] == "ok":
        return None
    if r["label"] in ("text_call", "no_call"):
        return 1
    seen = set(ID.findall(TASKS[r["task"]]["q"]))
    good = set()
    for c in r["calls"]:
        args = c["args"] if isinstance(c["args"], dict) else {}
        ids = [i for v in args.values() if isinstance(v, str) for i in ID.findall(v)]
        bad = c["name"] not in TOOL_NAMES or any(i not in seen for i in ids) or (
            "error" in c["result"] and not c["result"]["error"].startswith("invalid status"))
        if bad:
            break
        good.add((c["name"], json.dumps(args, sort_keys=True, ensure_ascii=False)))
        seen |= set(ID.findall(json.dumps(c["result"], ensure_ascii=False)))
    return min(len(good), CHAIN_LEN[r["task"]]) + 1


if __name__ == "__main__":
    runs = [json.loads(l) for p in sys.argv[1:] for l in open(p)]
    by = collections.defaultdict(list)
    for r in runs:
        r["label"] = label(r)
        key = (r["model"], r["variant"] + (("+parse" + (r.get("parser") or "v1")) if r.get("textparse") else "") + ("" if r.get("think") is None else f"+think={r['think']}"))
        by[key].append(r)
    for (m, v), rs in by.items():
        n = len(rs); ok = sum(r["label"] == "ok" for r in rs)
        per_task = collections.defaultdict(lambda: [0, 0])
        for r in rs:
            per_task[r["task"]][1] += 1; per_task[r["task"]][0] += r["label"] == "ok"
        labs = collections.Counter(r["label"] for r in rs if r["label"] != "ok")
        tc = sum(r.get("text_calls", 0) > 0 for r in rs)
        secs = sorted(r["secs"] for r in rs)
        steps = collections.Counter(fail_step(r) for r in rs if r["label"] != "ok")
        print(f"{m:18} {v:22} {ok:3}/{n:<3} {100*ok/n:5.1f}%  " +
              " ".join(f"{t}={a}/{b}" for t, (a, b) in sorted(per_task.items())) +
              f"  median_s={secs[len(secs)//2]:.1f}  text_parsed_runs={tc}  fails={dict(labs)}  fail_step={dict(sorted(steps.items()))}")
