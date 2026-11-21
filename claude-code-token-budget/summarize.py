#!/usr/bin/env python3
"""Re-print run summaries from saved runs/<name>.jsonl (same format as run.py, duration from result.duration_ms)."""
import json, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
def n(v):
    return v["count"] if isinstance(v, dict) else len(v or [])
for name in sys.argv[1:]:
    msgs = [json.loads(l) for l in open(HERE / "runs" / f"{name}.jsonl")]
    init = next((m for m in msgs if m.get("subtype") == "init"), {})
    res = next((m for m in msgs if m.get("type") == "result"), {})
    print(f"== {name}  duration_ms={res.get('duration_ms')}")
    print(f"init: tools={len(init.get('tools', []))} mcp_servers={len(init.get('mcp_servers', []))} "
          f"slash_commands={n(init.get('slash_commands'))} skills={n(init.get('skills'))} "
          f"agents={n(init.get('agents'))} plugins={n(init.get('plugins'))} model={init.get('model')}")
    seen = set(); i = 0
    for m in msgs:
        if m.get("type") == "assistant" and m["message"]["id"] not in seen:
            seen.add(m["message"]["id"]); u = m["message"]["usage"]; i += 1
            cc = u.get("cache_creation") or {}
            tot = u["input_tokens"] + u["cache_creation_input_tokens"] + u["cache_read_input_tokens"]
            print(f"req{i}: input={u['input_tokens']} cache_create={u['cache_creation_input_tokens']} "
                  f"(5m={cc.get('ephemeral_5m_input_tokens')},1h={cc.get('ephemeral_1h_input_tokens')}) "
                  f"cache_read={u['cache_read_input_tokens']} output={u['output_tokens']} context={tot}")
    print(f"result: turns={res.get('num_turns')} cost=${res.get('total_cost_usd')} is_error={res.get('is_error')} "
          f"text={str(res.get('result'))[:120]!r}")
    for k, v in (res.get("modelUsage") or {}).items():
        print(f"  modelUsage {k}: in={v.get('inputTokens')} out={v.get('outputTokens')} cr={v.get('cacheReadInputTokens')} cc={v.get('cacheCreationInputTokens')} cost={v.get('costUSD')}")
