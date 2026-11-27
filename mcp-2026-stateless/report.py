"""只读 logs/，打印文章里的全部数字，并画 chart.png：python3 report.py [--chart]"""
import collections
import json
import sys

rows = [json.loads(l) for l in open("logs/scenarios.jsonl")]
wire = [json.loads(l) for l in open("logs/wire.jsonl")]
claude = [json.loads(l) for l in open("logs/claude-wire.jsonl")]

OPS = ["connect", "whoami", "cart_add (3 items per cart)", "delete_branch (confirm)"]
LABELS = {"connect": "建连", "whoami": "普通调用", "cart_add (3 items per cart)": "句柄串状态", "delete_branch (confirm)": "MRTR 确认"}


def rate(name, op):
    r = next((r for r in rows if r["name"] == name and r["op"] == op), None)
    if r is None:
        return None
    return r["ok"], r["ok"] + r["failed"], r.get("first_err", "")


scen = list(dict.fromkeys(r["name"] for r in rows))
print("## 成功数 / 总数")
for s in scen:
    cells = []
    for op in OPS:
        v = rate(s, op)
        cells.append("-" if v is None else f"{v[0]}/{v[1]}")
    print(f"{s:32}", "  ".join(f"{c:>6}" for c in cells))
print("\n## 首个错误")
for r in rows:
    if r.get("first_err"):
        print(f"{r['name']:32} {r['op']:28} {r['first_err']}")

print("\n## 线上请求")
for s in scen:
    rs = [w for w in wire if w["scenario"] == s]
    before = []
    for w in rs:
        if w.get("rpc_method") == "tools/call" or w.get("rpc_method") == "tools/list":
            break
        before.append(f"{w['http_method']} {w.get('rpc_method', '-')}→{w['status']}")
    lists = sum(w.get("rpc_method") == "tools/list" for w in rs)
    who = [w for w in rs if w.get("tool") == "whoami"]
    dels = [w for w in rs if w.get("tool") == "delete_branch"]
    replies = sum(w["http_method"] == "POST" and not w.get("rpc_method") for w in rs)
    print(f"{s:32} 握手阶段: {before}")
    print(f"{'':32} tools/list 实际发出 {lists}/3 次；whoami 平均请求体 "
          f"{sum(w['req_bytes'] for w in who) / max(len(who), 1):.0f} 字节，落在副本 {dict(collections.Counter(w['backend'] for w in who))}")
    print(f"{'':32} delete_branch 的 tools/call {len(dels)} 次，另有客户端回包 POST {replies} 次；带 Mcp-Session-Id 的请求 "
          f"{sum(w['hdr_session_id'] for w in rs)}/{len(rs)}")

print("\n## Claude Code 实际发出的请求")
for w in claude:
    print(w["seq"], w["http_method"], w.get("rpc_method"), w.get("tool", ""), w["status"], w.get("hdr_protocol_version"),
          w.get("hdr_mcp_method", ""), w.get("hdr_mcp_name", ""), w.get("input_actions", ""), w.get("user_agent", ""))
caps = {w["client_caps"] for w in claude if w.get("client_caps")}
print("声明的能力:", *caps, sep="\n  ")

if "--chart" in sys.argv:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import font_manager

    CJK = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"
    font_manager.fontManager.addfont(CJK)
    plt.rcParams["font.family"] = [font_manager.FontProperties(fname=CJK).get_name(), "sans-serif"]
    NAMES = {
        "legacy-roundrobin": "2025-11-25 有会话 · 轮询",
        "legacy-sticky": "2025-11-25 有会话 · 会话保持",
        "stateless-roundrobin": "2026-07-28 无状态 · 轮询",
        "stateless-mrtr-local-pending": "同上，待确认状态存副本内存",
        "stateless-handle-local-store": "同上，句柄背后是副本内存",
        "stateless-list-ttl": "同上，tools/list 带 ttlMs",
        "legacy-client-stateless-server": "旧客户端 → 无状态服务端",
    }
    BG, FG, DIM = "#14161b", "#f0f2f5", "#8a90a0"
    fig, ax = plt.subplots(figsize=(16, 6.8), facecolor=BG)
    ax.set_facecolor(BG)
    for i, s in enumerate(scen):
        for j, op in enumerate(OPS):
            v = rate(s, op)
            if v is None or v[1] == 0:
                color, txt = "#2a2e37", "未执行"
            else:
                ok = v[0] / v[1]
                color = "#3f9d6b" if ok == 1 else ("#c0533f" if ok == 0 else "#d1a23f")
                txt = f"{v[0]}/{v[1]}"
            ax.add_patch(plt.Rectangle((j, i), 0.96, 0.9, color=color))
            ax.text(j + 0.48, i + 0.45, txt, ha="center", va="center", color=FG, fontsize=15)
    ax.set_xlim(0, len(OPS))
    ax.set_ylim(len(scen), -0.1)
    ax.set_xticks([j + 0.48 for j in range(len(OPS))], [LABELS[o] for o in OPS], color=FG, fontsize=14)
    ax.xaxis.tick_top()
    ax.set_yticks([i + 0.45 for i in range(len(scen))], [NAMES[s] for s in scen], color=FG, fontsize=13)
    ax.tick_params(length=0)
    for sp in ax.spines.values():
        sp.set_visible(False)
    fig.suptitle("3 个 MCP 副本 + 反向代理：哪些组合能跑通（成功次数 / 总次数）", color=FG, fontsize=18, y=0.98)
    fig.text(0.5, 0.03, "Go SDK v1.8.0；建连失败的场景后续调用未执行；句柄串状态每轮连加 3 件，按轮计", ha="center", color=DIM, fontsize=11)
    fig.subplots_adjust(left=0.24, right=0.98, top=0.83, bottom=0.08)
    fig.savefig("chart.png", dpi=100, facecolor=BG)
    print("\nwrote chart.png")
