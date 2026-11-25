"""Summarise logs/tasks.jsonl: pass rate per config x model x task, failure modes, median wall time."""
import collections, json, statistics, sys

path = sys.argv[1] if len(sys.argv) > 1 else "logs/tasks.jsonl"
rows = [json.loads(l) for l in open(path)]
tasks = list(dict.fromkeys(r["task"] for r in rows))
by = collections.defaultdict(list)
for r in rows:
    by[(r["config"], r["model"])].append(r)

def mode(r):
    t = r.get("reply") or ""
    if r["pass"]: return "pass"
    if r["rc"] == "timeout": return "timeout"
    if r["tool_calls"]: return "called_tools_wrong_result"
    if '"name"' in t and ('"arguments"' in t or '"parameters"' in t): return "tool_call_as_json_text"
    if "```" in t: return "printed_command_or_code"
    return "answered_without_tools"

print("config | model | " + " | ".join(tasks) + " | total | median s | median prompt tokens/run")
for (cfg, model), rs in sorted(by.items()):
    cells = []
    for t in tasks:
        tr = [r for r in rs if r["task"] == t]
        cells.append(f"{sum(r['pass'] for r in tr)}/{len(tr)}")
    print(f"{cfg} | {model} | " + " | ".join(cells) +
          f" | {sum(r['pass'] for r in rs)}/{len(rs)} | {statistics.median(r['wall_s'] for r in rs)}"
          f" | {statistics.median(r['prompt_eval_total'] for r in rs)}")
print()
for (cfg, model), rs in sorted(by.items()):
    print(cfg, model, dict(collections.Counter(mode(r) for r in rs)),
          "tool names:", dict(collections.Counter(c for r in rs for c in r["tool_calls"])))
