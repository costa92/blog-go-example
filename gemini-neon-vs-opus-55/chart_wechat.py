"""公众号版配图：竖排、大字号的 chart-mobile.png（手机正文约 375pt 宽），和 900x383 的封面 cover.png。"""
import matplotlib.pyplot as plt

from chart import SERIES, SUITES, accuracy, cost, latency

BG, FG, DIM = "#14161b", "#f0f2f5", "#8a90a0"


def mobile():
    fig, axes = plt.subplots(3, 1, figsize=(7.2, 12.8), facecolor=BG)
    panels = [("准确率（%）", accuracy, "{:.0f}"), ("延迟中位数（秒）", latency, "{:.0f}"),
              ("每次调用成本（美元）", cost, "{:.2f}")]
    w = 0.27
    for ax, (title, fn, fmt) in zip(axes, panels):
        ax.set_facecolor(BG)
        for k, (m, label, color) in enumerate(SERIES):
            for i, _ in enumerate(SUITES):
                v = fn(SUITES[i][0], m)
                if v is None:
                    continue
                x = i + (k - 1) * w
                ax.bar(x, v, w * 0.92, color=color, label=label if i == 0 else None)
                ax.text(x, v, fmt.format(v), ha="center", va="bottom", color=FG, fontsize=15)
        ax.set_xticks(range(len(SUITES)), [n for _, n in SUITES], color=FG, fontsize=17)
        ax.set_yticks([])
        ax.margins(y=0.18)
        for sp in ax.spines.values():
            sp.set_visible(False)
        ax.set_title(title, color=FG, fontsize=20, pad=10, loc="left")
    axes[0].set_ylim(0, 118)
    h, l = axes[0].get_legend_handles_labels()
    fig.legend(h, l, loc="upper center", ncol=1, frameon=False, fontsize=16, labelcolor=FG, bbox_to_anchor=(0.5, 0.995))
    fig.text(0.5, 0.012, "长上下文只测了 Neon high 与 Opus", ha="center", color=DIM, fontsize=13)
    fig.subplots_adjust(left=0.04, right=0.96, top=0.86, bottom=0.075, hspace=0.42)
    fig.savefig("chart-mobile.png", dpi=150, facecolor=BG)


def cover():
    # 2.35:1 头图；分享卡片从中间裁 1:1（383x383），主要文字放在中间
    fig = plt.figure(figsize=(9, 3.83), dpi=100, facecolor=BG)
    fig.text(0.5, 0.70, "Neon vs Opus 5.5", ha="center", color="#9ec2ff", fontsize=22, weight="bold")
    fig.text(0.5, 0.45, "答对率打平", ha="center", color=FG, fontsize=40, weight="bold")
    fig.text(0.5, 0.20, "Neon 写代码慢 8 倍", ha="center", color="#e08a4f", fontsize=25, weight="bold")
    fig.savefig("cover.png", facecolor=BG)


if __name__ == "__main__":
    mobile()
    cover()
