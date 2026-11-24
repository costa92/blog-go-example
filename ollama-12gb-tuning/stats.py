"""Print median tables from logs/*.jsonl."""
import glob
import json
import statistics
from collections import defaultdict

med = statistics.median


def rows(pattern):
    for f in sorted(glob.glob(pattern)):
        for line in open(f):
            yield json.loads(line)


print("## ctx x KV (median of runs; first short run included)")
print("config | num_ctx | ps | GPU layers | KV | load s | VRAM delta MiB | short prompt/gen tok/s | long prompt/gen tok/s")
for r in rows("logs/ctx_kv-*.jsonl"):
    out = []
    for kind in ("short", "long"):
        rs = [x for x in r["runs"] if x["kind"] == kind]
        if rs:
            out.append(f"{med(x['prompt_tps'] for x in rs):.0f} / {med(x['gen_tps'] for x in rs):.1f} (n={len(rs)}, {rs[0]['prompt_tokens']} tok)")
        else:
            out.append("-")
    ps = r["ps"]
    print(f"{r['config']} | {r['num_ctx']} | {ps['size_gb']} GB {ps['gpu_pct']}% GPU | {r.get('offloaded')} | "
          f"{r.get('kv_size')} {r.get('kv_types')} FA={r.get('flash_attn_enabled')} | {r['load_s']} | "
          f"{r['vram_delta_mib']} (base {r['vram_base_mib']}) | {out[0]} | {out[1]}")

print("\n## quality")
for r in rows("logs/quality-*.jsonl"):
    if r["exp"] == "quality_summary":
        print(r)
wrong = defaultdict(list)
for r in rows("logs/quality-*.jsonl"):
    if r["exp"] == "quality" and not r["correct"]:
        wrong[(r["config"], r["num_ctx"])].append((r["record"], r["expected"], r["response"]))
for k, v in wrong.items():
    print("wrong", k, v)

print("\n## parallel (median over rounds)")
g = defaultdict(list)
for r in rows("logs/parallel-*.jsonl"):
    g[(r.get("kv", "f16"), r["num_parallel"], r["clients"])].append(r)
    if r.get("load"):
        L = r["load"]
        print("load", r.get("kv", "f16"), "np", r["num_parallel"], L["ps"], L.get("n_ctx_slot"), L.get("kv_size"), L["vram_delta_mib"])
for (kv, np_, nc), rs in sorted(g.items()):
    print(f"kv={kv} np={np_} clients={nc} n={len(rs)} throughput={med(x['throughput_tps'] for x in rs)} "
          f"lat_med={med(x['latency_median_s'] for x in rs)} lat_max={med(x['latency_max_s'] for x in rs)} "
          f"per_req_gen={med(x['per_req_gen_tps_median'] for x in rs)} vram={max(x['vram_mib'] for x in rs)} "
          f"tokens={[x['total_gen_tokens'] for x in rs]}")
