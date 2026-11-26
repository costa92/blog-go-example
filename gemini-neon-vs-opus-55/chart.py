"""从 logs/ 画文章用的汇总图 chart.png：准确率、延迟中位数、每次调用成本。"""
import json

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager

from grade import extract, median, parse_json, rows, same

CJK = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"  # Debian/Ubuntu 的 fonts-noto-cjk
font_manager.fontManager.addfont(CJK)
plt.rcParams["font.family"] = [font_manager.FontProperties(fname=CJK).get_name(), "sans-serif"]

SERIES = [("gemini", "Gemini 4 Neon（high）", "#4f8df7"),
          ("gemini-low", "Gemini 4 Neon（low）", "#9ec2ff"),
          ("claude", "Claude Opus 5.5（high）", "#e08a4f")]
SUITES = [("coding", "编程 10 题"), ("reasoning", "推理 30 题"), ("longctx", "长上下文")]


def accuracy(suite, m):
    if suite == "coding":
        res = [r for r in map(json.loads, open("logs/coding-tests.jsonl")) if r["model"] == m]
        return 100 * sum(r["passed"] == r["tests"] for r in res) / len(res) if res else None
    rs = [r for r in rows(suite) if r["model"] == m]
    if not rs:
        return None
    if suite == "reasoning":
        want = {t["id"]: t["answer"] for t in map(json.loads, open("reasoning.jsonl"))}
        return 100 * sum(same(extract(r["text"]), want[r["id"]]) for r in rs) / len(rs)
    want = {i: json.load(open(f"longctx/{i}.json"))["answer"] for i in ("100k", "300k", "600k")}
    return 100 * sum((parse_json(r["text"]) or {}).get("total") == want[r["id"]]["total"] for r in rs) / len(rs)


def latency(suite, m):
    rs = [r for r in rows(suite) if r["model"] == m and (suite != "longctx" or r["run"] == 0)]
    return median([r["latency_s"] for r in rs]) if rs else None


def cost(suite, m):
    rs = [r for r in rows(suite) if r["model"] == m]
    return sum(r["cost_usd"] for r in rs) / len(rs) if rs else None


def draw():
    fig, axes = plt.subplots(1, 3, figsize=(16, 6.8), facecolor="#14161b")
    panels = [("准确率（%）", accuracy, "{:.0f}"), ("延迟中位数（秒）", latency, "{:.0f}"), ("每次调用成本（美元）", cost, "{:.2f}")]
    w = 0.26
    for ax, (title, fn, fmt) in zip(axes, panels):
        ax.set_facecolor("#14161b")
        for k, (m, label, color) in enumerate(SERIES):
            for i, (s, _) in enumerate(SUITES):
                v = fn(s, m)
                if v is None:
                    continue
                x = i + (k - 1) * w
                ax.bar(x, v, w * 0.92, color=color, label=label if i == 0 else None)
                ax.text(x, v, fmt.format(v), ha="center", va="bottom", color="#d8dbe2", fontsize=11)
        ax.set_xticks(range(len(SUITES)), [n for _, n in SUITES], color="#d8dbe2", fontsize=12)
        ax.tick_params(axis="y", colors="#8a90a0")
        for sp in ax.spines.values():
            sp.set_visible(False)
        ax.set_title(title, color="#f0f2f5", fontsize=15, pad=12)
        ax.grid(axis="y", color="#2a2e37", lw=0.8)
        ax.set_axisbelow(True)
    axes[0].set_ylim(0, 112)
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=3, frameon=False, fontsize=13, labelcolor="#d8dbe2")
    fig.suptitle("Gemini 4 Neon 与 Claude Opus 5.5 实测：答对率接近，Neon 默认思考慢 3 到 8 倍", color="#f0f2f5", fontsize=18, y=0.97)
    fig.text(0.5, 0.075, "编程=三遍隐藏测试全过；长上下文=只测 Neon high 与 Opus；延迟为冷启动中位数；成本按官方标价、输入不计缓存",
             ha="center", color="#8a90a0", fontsize=10.5)
    fig.subplots_adjust(left=0.04, right=0.99, top=0.84, bottom=0.2, wspace=0.18)
    fig.savefig("chart.png", dpi=100, facecolor=fig.get_facecolor())


if __name__ == "__main__":
    draw()
