#!/usr/bin/env python3
"""同一段长会话，用七种历史策略喂给模型，在会话末尾跑 6 个探针。

策略：
  full8k   整段历史原样发出，num_ctx=8192，放不下时由 Ollama 自己从最早的消息开始丢
  window   客户端滑动窗口：system 加上最近几轮，估算不超过 BUDGET token，按整轮裁剪
  pin      window 的基础上固定保留前 4 轮（用户交代事实和约束的那几轮）
  sysrules 把前 4 轮里用户的原话抄进 system 提示词，其余同 window
  summary  回放时历史超过 BUDGET 就把最早的若干轮交给同一个模型写成摘要，摘要放在 system 后面
  notes    每一轮之后让同一个模型更新一份固定格式的状态笔记，笔记放在 system 后面，再接滑动窗口
  full32k  整段历史，num_ctx=32768，不发生截断，作为上限参照

用法: agent.py --model M --strategy S [--seeds 1 2 3] [--probe email ...] --out logs/x.jsonl
摘要和笔记按 (模型, seed) 缓存在 logs/compact.jsonl，同一个 seed 的 6 个探针共用一份。
"""
import argparse, json, os, re, time, urllib.request

import session as s

OLLAMA = "http://127.0.0.1:11434/api/chat"
BUDGET = 6000          # 估算 token；num_ctx=8192 里再留出工具定义（约 800）、system 和输出的空间
KEEP_AFTER_SUMMARY = 3000
PIN = 4
TEMP = 0.7
CACHE = "logs/compact.jsonl"
# 摘要和笔记的生成上限。第一轮用的 1024 对 gemma4 不够：思考也算在 eval_count 里，摘要被截在半句话
COMPACT_PREDICT = 4096

SUMMARY_PROMPT = ("下面是你和用户之前的一段对话。请把它压缩成一份摘要，供你之后继续工作时参考。"
                  "保留用户交代的事实、约束、决定和还没完成的事，省略工具输出里的原始数据。只输出摘要。")
NOTES_PROMPT = ("你在维护一份会话状态笔记，之后的对话里旧消息会被删掉，只剩这份笔记。"
                "根据「新的一轮对话」更新笔记：保留原有条目，除非用户明确推翻；加入新的事实、约束、决定和关键数据。"
                "严格按下面的格式输出，总长度不超过 400 字，只输出笔记本身：\n"
                "## 事实\n- ...\n## 约束（必须遵守）\n- ...\n## 已做决定\n- ...\n## 关键数据\n- ...\n## 待办\n- ...")


def chat(model, messages, seed, num_ctx, tools=True, num_predict=1024):
    body = {"model": model, "messages": messages, "stream": False, "keep_alive": "10m",
            "options": {"temperature": TEMP, "seed": seed, "num_ctx": num_ctx, "num_predict": num_predict}}
    if tools:
        body["tools"] = s.TOOLS
    req = urllib.request.Request(OLLAMA, json.dumps(body).encode(), {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=900) as r:
        return json.load(r)


def render(rounds):
    out = []
    for r in rounds:
        for m in r:
            if m["role"] == "user":
                out.append("用户：" + m["content"])
            elif m["role"] == "tool":
                out.append(f"工具 {m['tool_name']} 返回：\n" + m["content"])
            elif m.get("tool_calls"):
                f = m["tool_calls"][0]["function"]
                out.append(f"助手调用 {f['name']}({json.dumps(f['arguments'], ensure_ascii=False)})")
            else:
                out.append("助手：" + m["content"])
    return "\n".join(out)


def flat(rounds):
    return [m for r in rounds for m in r]


def tail_within(rounds, budget):
    kept, used = [], 0
    for r in reversed(rounds):
        t = s.est_tokens(r)
        if used + t > budget:
            break
        kept.insert(0, r)
        used += t
    return kept


def load_cache():
    c = {}
    if os.path.exists(CACHE):
        for line in open(CACHE):
            r = json.loads(line)
            if r.get("num_predict") == COMPACT_PREDICT:
                c[(r["model"], r["strategy"], r["seed"])] = r
    return c


def compact(model, strategy, seed):
    """回放整段会话，返回 (摘要或笔记文本, 保留的轮次下标, 生成记录)。"""
    cache = load_cache()
    if (model, strategy, seed) in cache:
        return cache[(model, strategy, seed)]
    events, text, kept = [], "", []
    for i, r in enumerate(s.ROUNDS):
        if strategy == "summary":
            kept.append(i)
            if s.est_tokens(flat(s.ROUNDS[j] for j in kept) + [{"content": text}]) > BUDGET:
                recent = tail_within([s.ROUNDS[j] for j in kept], KEEP_AFTER_SUMMARY)
                old = kept[:len(kept) - len(recent)]
                prompt = (f"已有摘要：\n{text}\n\n" if text else "") + "对话：\n" + render(s.ROUNDS[j] for j in old)
                t0 = time.time()
                resp = chat(model, [{"role": "system", "content": SUMMARY_PROMPT}, {"role": "user", "content": prompt}],
                            seed, 16384, tools=False, num_predict=COMPACT_PREDICT)
                text = resp["message"]["content"].strip()
                events.append({"after_round": i + 1, "folded": [j + 1 for j in old], "secs": round(time.time() - t0, 2),
                               "prompt_tokens": resp.get("prompt_eval_count"), "out_tokens": resp.get("eval_count"),
                               "text": text})
                kept = kept[len(old):]
        else:  # notes
            prompt = f"当前笔记：\n{text or '（空）'}\n\n新的一轮对话：\n" + render([r])
            t0 = time.time()
            resp = chat(model, [{"role": "system", "content": NOTES_PROMPT}, {"role": "user", "content": prompt}],
                        seed, 16384, tools=False, num_predict=COMPACT_PREDICT)
            text = resp["message"]["content"].strip()
            events.append({"after_round": i + 1, "secs": round(time.time() - t0, 2),
                           "prompt_tokens": resp.get("prompt_eval_count"), "out_tokens": resp.get("eval_count"),
                           "text": text})
    rec = {"model": model, "strategy": strategy, "seed": seed, "num_predict": COMPACT_PREDICT, "text": text, "kept": kept, "events": events}
    with open(CACHE, "a") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec


def history(model, strategy, seed):
    """返回 (发给模型的历史消息, num_ctx, 压缩记录或 None)。"""
    sysmsg = {"role": "system", "content": s.SYSTEM}
    if strategy == "full8k":
        return [sysmsg] + flat(s.ROUNDS), 8192, None
    if strategy == "full32k":
        return [sysmsg] + flat(s.ROUNDS), 32768, None
    if strategy == "window":
        return [sysmsg] + flat(tail_within(s.ROUNDS, BUDGET)), 8192, None
    if strategy == "pin":
        head = s.ROUNDS[:PIN]
        tail = tail_within(s.ROUNDS[PIN:], BUDGET - s.est_tokens(flat(head)))
        return [sysmsg] + flat(head + tail), 8192, None
    if strategy == "sysrules":
        rules = "\n".join("- " + m["content"] for r in s.ROUNDS[:PIN] for m in r if m["role"] == "user")
        sysmsg = {"role": "system", "content": s.SYSTEM + "\n\n用户在会话开头交代过的事实和规则，一直有效：\n" + rules}
        return [sysmsg] + flat(tail_within(s.ROUNDS, BUDGET - s.est_tokens([sysmsg]))), 8192, None
    rec = compact(model, strategy, seed)
    if strategy == "summary":
        extra = {"role": "system", "content": "之前对话的摘要：\n" + rec["text"]}
        return [sysmsg, extra] + flat(s.ROUNDS[j] for j in rec["kept"]), 8192, rec
    extra = {"role": "system", "content": "会话状态笔记（旧消息已删除，以这份笔记为准）：\n" + rec["text"]}
    tail = tail_within(s.ROUNDS, BUDGET - s.est_tokens([extra]))
    return [sysmsg, extra] + flat(tail), 8192, rec


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
        if not isinstance(o, dict) or o.get("name") not in {x['function']['name'] for x in s.TOOLS}:
            return []
        out.append({"function": {"name": o["name"], "arguments": o.get("arguments", o.get("parameters", {}))}})
    return out


PAYMENT_YAML = "# config/payment.yaml\nprovider: mockpay\ncallback_timeout: 10s\nretry: 3\nsign_type: RSA2"


def probe_tool(name, args):
    if name == "read_file":
        p = str(args.get("path", ""))
        return PAYMENT_YAML if "payment" in p else f"# {p}\n（内容省略）"
    if name in ("edit_file", "set_ad_budget", "create_shipment", "send_email"):
        return json.dumps({"ok": True, **{k: v for k, v in args.items() if k != "body"}}, ensure_ascii=False)
    return json.dumps({"ok": True, "note": "（探针阶段不返回数据）"}, ensure_ascii=False)


ACTION = ("email", "budget", "payment", "ship")
NUDGE = "继续。"


def run_probe(model, strategy, seed, pid, max_steps=5):
    msgs, num_ctx, rec = history(model, strategy, seed)
    q = dict((p[0], p[1]) for p in s.PROBES)[pid]
    msgs = msgs + [{"role": "user", "content": q}]
    sent_est = s.est_tokens(msgs)
    calls, steps, texts, text_calls, nudged, t0 = [], [], [], 0, False, time.time()
    for step in range(max_steps):
        r = chat(model, msgs, seed, num_ctx)
        m = r["message"]
        steps.append({"prompt_tokens": r.get("prompt_eval_count"), "out_tokens": r.get("eval_count"),
                      "prompt_ms": round(r.get("prompt_eval_duration", 0) / 1e6), "total_ms": round(r.get("total_duration", 0) / 1e6),
                      "done_reason": r.get("done_reason")})
        msgs.append({k: v for k, v in m.items() if k in ("role", "content", "tool_calls")})
        tcs = m.get("tool_calls") or []
        if not tcs:
            tcs = parse_text_calls(m.get("content", ""))
            if tcs:
                text_calls += len(tcs)
                msgs[-1] = {"role": "assistant", "content": "", "tool_calls": tcs}
        if m.get("content"):
            texts.append(m["content"])
        if not tcs:
            # 动作类探针第一次只回了一句话（常见是「好的，请稍等。」）时，像真实用户一样回一句「继续。」，只追问一次
            if pid in ACTION and not calls and not nudged:
                nudged = True
                msgs.append({"role": "user", "content": NUDGE})
                continue
            break
        for tc in tcs:
            f = tc.get("function", {})
            out = probe_tool(f.get("name"), f.get("arguments") or {})
            calls.append({"step": step, "name": f.get("name"), "args": f.get("arguments")})
            msgs.append({"role": "tool", "tool_name": f.get("name"), "content": out})
    return {"model": model, "strategy": strategy, "seed": seed, "probe": pid, "num_ctx": num_ctx,
            "compact_predict": COMPACT_PREDICT if rec else None,
            "history_msgs": len(msgs), "sent_est_tokens": sent_est, "calls": calls, "text_calls": text_calls, "nudged": nudged, "texts": texts, "final": "\n".join(texts),
            "steps": steps, "secs": round(time.time() - t0, 2)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--strategy", required=True, choices=["full8k", "window", "pin", "sysrules", "summary", "notes", "full32k"])
    ap.add_argument("--seeds", type=int, nargs="+", default=[1, 2, 3, 4, 5])
    ap.add_argument("--probe", nargs="+", default=[p[0] for p in s.PROBES])
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    os.makedirs("logs", exist_ok=True)
    for seed in a.seeds:
        for pid in a.probe:
            r = run_probe(a.model, a.strategy, seed, pid)
            with open(a.out, "a") as f:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
            print(a.model, a.strategy, seed, pid, r["steps"][0]["prompt_tokens"], [c["name"] for c in r["calls"]],
                  (r["final"] or "")[:60].replace("\n", " "), flush=True)


if __name__ == "__main__":
    main()
