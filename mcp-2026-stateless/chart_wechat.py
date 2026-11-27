"""公众号版配图：竖排 3 面板的 chart-mobile.png（1080x1920），和 900x383 的封面 cover.png。数字只从 logs/scenarios.jsonl 读。"""
import json

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager

CJK = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"
font_manager.fontManager.addfont(CJK)
plt.rcParams["font.family"] = [font_manager.FontProperties(fname=CJK).get_name(), "sans-serif"]

BG, FG, DIM = "#14161b", "#f0f2f5", "#8a90a0"
OPS = [("connect", "建连"), ("whoami", "普通调用"), ("cart_add (3 items per cart)", "句柄"), ("delete_branch (confirm)", "确认")]
PANELS = [
    ("旧协议 2025-11-25（有会话）", [("legacy-roundrobin", "轮询"), ("legacy-sticky", "会话保持")]),
    ("新协议 2026-07-28（无状态，轮询）", [("stateless-roundrobin", "状态签名\n存共享库"),
                                    ("stateless-mrtr-local-pending", "确认状态\n存内存"),
                                    ("stateless-handle-local-store", "句柄数据\n存内存")]),
    ("新旧混跑", [("legacy-client-stateless-server", "旧客户端\n连新服务端")]),
]
rows = {(r["name"], r["op"]): r for r in map(json.loads, open("logs/scenarios.jsonl"))}


def cell(name, op):
    r = rows.get((name, op))
    if r is None or r["ok"] + r["failed"] == 0:
        return "#2a2e37", "未执行"
    ok, n = r["ok"], r["ok"] + r["failed"]
    return ("#3f9d6b" if ok == n else "#c0533f" if ok == 0 else "#d1a23f"), f"{ok}/{n}"


def mobile():
    fig, axes = plt.subplots(3, 1, figsize=(7.2, 12.8), facecolor=BG, gridspec_kw={"height_ratios": [2, 3, 1]})
    for ax, (title, scen) in zip(axes, PANELS):
        ax.set_facecolor(BG)
        for i, (name, _) in enumerate(scen):
            for j, (op, _) in enumerate(OPS):
                color, txt = cell(name, op)
                ax.add_patch(plt.Rectangle((j, i), 0.94, 0.88, color=color))
                ax.text(j + 0.47, i + 0.44, txt, ha="center", va="center", color=FG, fontsize=17)
        ax.set_xlim(0, len(OPS))
        ax.set_ylim(len(scen), -0.05)
        ax.set_xticks([j + 0.47 for j in range(len(OPS))], [l for _, l in OPS], color=FG, fontsize=17)
        ax.xaxis.tick_top()
        ax.set_yticks([i + 0.44 for i in range(len(scen))], [l for _, l in scen], color=FG, fontsize=16)
        ax.tick_params(length=0)
        for sp in ax.spines.values():
            sp.set_visible(False)
        ax.set_title(title, color=FG, fontsize=20, pad=34, loc="left")
    fig.text(0.5, 0.965, "3 个副本 + 轮询代理：成功次数 / 总次数", ha="center", color=FG, fontsize=20, weight="bold")
    fig.text(0.5, 0.012, "Go SDK v1.8.0；建连失败的场景后续调用未执行", ha="center", color=DIM, fontsize=13)
    fig.subplots_adjust(left=0.25, right=0.97, top=0.87, bottom=0.05, hspace=0.62)
    fig.savefig("chart-mobile.png", dpi=150, facecolor=BG)


def cover():
    # 2.35:1 头图；分享卡片从中间裁 1:1（383x383），文字都放在中间
    fig = plt.figure(figsize=(9, 3.83), dpi=100, facecolor=BG)
    fig.text(0.5, 0.70, "MCP 2026-07-28", ha="center", color="#9ec2ff", fontsize=22, weight="bold")
    fig.text(0.5, 0.45, "会话没了", ha="center", color=FG, fontsize=40, weight="bold")
    fig.text(0.5, 0.20, "状态放内存 0/30", ha="center", color="#e08a4f", fontsize=25, weight="bold")
    fig.savefig("cover.png", facecolor=BG)


if __name__ == "__main__":
    mobile()
    cover()
