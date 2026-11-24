import json, sys
res = None
tools = {}
results = []
for line in open(sys.argv[1]):
    try: e = json.loads(line)
    except Exception: continue
    if e.get("type") == "assistant":
        for c in e["message"].get("content", []):
            if c.get("type") == "tool_use":
                n = c["name"]
                if n == "Skill": n = "Skill:" + c["input"].get("skill", "")
                if n in ("Agent", "Task"): n = "Agent:" + str(c["input"].get("subagent_type"))
                tools[n] = tools.get(n, 0) + 1
    if e.get("type") == "result":
        res = e; results.append(e)
out = {"wall_s": int(sys.argv[2]) if len(sys.argv) > 2 else None, "tools": tools}
if res:
    U = lambda k: sum((r.get("usage") or {}).get(k) or 0 for r in results)
    u = {k: U(k) for k in ("input_tokens","output_tokens","cache_read_input_tokens","cache_creation_input_tokens")}
    out.update(result_events=len(results), subtype=res.get("subtype"), num_turns=sum(r.get("num_turns") or 0 for r in results), cost_usd=res.get("total_cost_usd"),
               duration_api_ms=res.get("duration_api_ms"), model_cost={m: round(v.get("costUSD",0),4) for m,v in (res.get("modelUsage") or {}).items()}, input_tokens=u.get("input_tokens"), output_tokens=u.get("output_tokens"),
               cache_read=u.get("cache_read_input_tokens"), cache_create=u.get("cache_creation_input_tokens"),
               models=list((res.get("modelUsage") or {}).keys()))
print(json.dumps(out, ensure_ascii=False))
