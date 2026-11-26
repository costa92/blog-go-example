"""两个模型的统一调用：返回文本、耗时、token 和按官方标价算出的美元成本。

Gemini 走 REST（GEMINI_API_KEY）；Claude 走 `claude -p`（订阅登录），
替换系统提示、关闭工具和 MCP、不读任何 settings，在空目录里运行，
除提示词外只多约 600 个缓存前缀 token。
"""
import json
import os
import subprocess
import tempfile
import time
import urllib.error
import urllib.request

# 每百万 token 的美元标价（2026-11-26 核对官方价目页）
PRICE = {
    "gemini": {"in": 3.0, "out": 15.0, "cache_read": 0.15},
    "claude": {"in": 4.0, "out": 20.0, "cache_read": 0.20, "cache_write": 5.0, "cache_write_1h": 8.0},
}
MODEL_ID = {"gemini": "gemini-4-neon", "claude": "claude-opus-5-5"}
SYSTEM = "You are a helpful assistant."
EMPTY_DIR = tempfile.mkdtemp(prefix="bench-empty-")


def call_gemini(prompt, timeout=1800, level="high"):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_ID['gemini']}:generateContent"
    body = {
        "systemInstruction": {"parts": [{"text": SYSTEM}]},
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"thinkingConfig": {"thinkingLevel": level}},
    }
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={
        "content-type": "application/json", "x-goog-api-key": os.environ["GEMINI_API_KEY"]})
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            d = json.load(r)
    except urllib.error.HTTPError as e:
        return {"error": f"HTTP {e.code}: {e.read()[:500].decode(errors='replace')}", "latency_s": time.time() - t0}
    lat = time.time() - t0
    cand = d["candidates"][0]
    text = "".join(p.get("text", "") for p in cand.get("content", {}).get("parts", []) if not p.get("thought"))
    u = d["usageMetadata"]
    cached = u.get("cachedContentTokenCount", 0)
    inp = u["promptTokenCount"]
    out = u.get("candidatesTokenCount", 0)
    think = u.get("thoughtsTokenCount", 0)
    p = PRICE["gemini"]
    billed = ((inp - cached) * p["in"] + cached * p["cache_read"] + (out + think) * p["out"]) / 1e6
    cost = (inp * p["in"] + (out + think) * p["out"]) / 1e6
    return {"text": text, "latency_s": lat, "input_tokens": inp, "cached_tokens": cached,
            "output_tokens": out + think, "thinking_tokens": think,
            "finish": cand.get("finishReason"), "model_version": d.get("modelVersion"), "cost_usd": cost,
            "billed_usd": billed}


def call_claude(prompt, timeout=1800):
    cmd = ["claude", "-p", "--model", MODEL_ID["claude"], "--effort", "high",
           "--system-prompt", SYSTEM, "--tools", "", "--strict-mcp-config",
           "--setting-sources", "", "--no-session-persistence", "--output-format", "json"]
    t0 = time.time()
    r = subprocess.run(cmd, input=prompt, capture_output=True, text=True, cwd=EMPTY_DIR, timeout=timeout)
    lat = time.time() - t0
    try:
        d = json.loads(r.stdout)
    except json.JSONDecodeError:
        return {"error": f"exit {r.returncode}: {(r.stdout + r.stderr)[-500:]}", "latency_s": lat}
    if d.get("is_error"):
        return {"error": str(d.get("result"))[:500], "latency_s": lat}
    u = d["usage"]
    p = PRICE["claude"]
    inp = u["input_tokens"] + u["cache_creation_input_tokens"] + u["cache_read_input_tokens"]
    cc = u.get("cache_creation", {})
    billed = (u["input_tokens"] * p["in"] + cc.get("ephemeral_5m_input_tokens", 0) * p["cache_write"]
              + cc.get("ephemeral_1h_input_tokens", 0) * p["cache_write_1h"]
              + u["cache_read_input_tokens"] * p["cache_read"] + u["output_tokens"] * p["out"]) / 1e6
    # 对比用：输入全按基础价，不计 CLI 自动加的缓存读写
    cost = (inp * p["in"] + u["output_tokens"] * p["out"]) / 1e6
    return {"text": d["result"], "latency_s": d["duration_api_ms"] / 1000, "wall_s": lat,
            "input_tokens": inp, "cached_tokens": u["cache_read_input_tokens"],
            "output_tokens": u["output_tokens"],
            "thinking_tokens": u.get("output_tokens_details", {}).get("thinking_tokens", 0),
            "finish": d.get("stop_reason"), "model_version": next(iter(d["modelUsage"])), "cost_usd": cost,
            "billed_usd": billed}


CALL = {"gemini": call_gemini, "claude": call_claude,
        "gemini-low": lambda p: call_gemini(p, level="low")}  # 对照：思考强度降到 low
