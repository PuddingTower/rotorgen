# -*- coding: utf-8 -*-
"""Generate plain-language flowchart PNGs for docs/PIPELINE_GUIDE.pdf.

Outputs docs/flow_figs/fig_flow_main.png (end-to-end pipeline) and
fig_flow_wake.png (free-wake inner loop). Low-saturation fills, embedded at
~460pt width in the PDF so effective font sizes stay >= 8-10pt.
"""
import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei"]
plt.rcParams["axes.unicode_minus"] = False

ACCENT = "#368aa6"
TEXT = "#1c1c1a"
MUTED = "#78766f"
FILL = "#eef5f8"      # pale accent fill
FILL_OK = "#eaf3ed"   # pale green
FILL_WARN = "#f6efe2" # pale amber
FILL_ERR = "#f5e9e7"  # pale red
EDGE_OK = "#46875c"
EDGE_WARN = "#a18347"
EDGE_ERR = "#92453e"
ARROW_D = "#23657d"

OUT = os.path.join(os.path.dirname(__file__), "..", "docs", "flow_figs")
os.makedirs(OUT, exist_ok=True)


def box(ax, cx, cy, w, h, title, desc="", fill=FILL, edge=ACCENT, tfs=13, dfs=10.5):
    ax.add_patch(FancyBboxPatch((cx - w / 2, cy - h / 2), w, h,
                                boxstyle="round,pad=0.6,rounding_size=2.2",
                                linewidth=1.6, edgecolor=edge, facecolor=fill))
    if desc:
        ax.text(cx, cy + h * 0.22, title, ha="center", va="center",
                fontsize=tfs, fontweight="bold", color=TEXT, linespacing=1.25)
        ax.text(cx, cy - h * 0.22, desc, ha="center", va="center",
                fontsize=dfs, color=MUTED, linespacing=1.35)
    else:
        ax.text(cx, cy, title, ha="center", va="center",
                fontsize=tfs, fontweight="bold", color=TEXT, linespacing=1.3)


def arrow(ax, p1, p2, label="", rad=0.0, color=ACCENT, lfs=10.5,
          lx=None, ly=None, style="-|>"):
    ax.add_patch(FancyArrowPatch(p1, p2, arrowstyle=style, mutation_scale=16,
                                 linewidth=1.6, color=color,
                                 connectionstyle=f"arc3,rad={rad}"))
    if label:
        mx = lx if lx is not None else (p1[0] + p2[0]) / 2
        my = ly if ly is not None else (p1[1] + p2[1]) / 2
        ax.text(mx, my, label, ha="center", va="center", fontsize=lfs,
                color=color if color != ACCENT else ARROW_D,
                bbox=dict(boxstyle="round,pad=0.25", fc="white", ec="none"))


def save(fig, name):
    path = os.path.join(OUT, name)
    fig.savefig(path, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print("saved", path)


# ================================================================ fig 1: main pipeline
W, H = 100, 158
fig, ax = plt.subplots(figsize=(8.0, 12.6), dpi=200)
ax.set_xlim(0, W); ax.set_ylim(0, H); ax.axis("off")

mx, bw = 37, 50     # main column center / width
rx, rw = 83, 28     # right column center / width
bh = 11.5

rows = [
    ("输入 4 个数", "直径 2.08 m · 拉力 200 kgf\n2 叶 · 尾缘 2 mm", 142),
    ("设计向量 x（17 个数）", "一把桨的全部\u201c基因\u201d：桨尖速度、扭角、\n弦长、弯度、厚度", 128),
    ("翻译成形状", "样条插值长出扭角/弦长曲线，\n18 个展向站位", 114),
    ("翼型族生成 famgen", "每个站位一个翼型；尾缘厚度\n逐站位精确 = 2 mm", 100),
    ("2D 气动表 foil2d", "面板法+边界层 → 每个翼型的\n升力/阻力表（~3 ms/迎角）", 86),
    ("3D 自由尾迹求解 rotor3d", "桨叶环量与螺旋尾迹互相迭代\n到收敛（~13-57 s/次）", 72),
    ("配平：拧总距", "二分/割线搜索，让拉力\n正好 = 200 kgf", 58),
    ("约束检查", "桨尖不超音速？不失速？\n根部够厚？", 44),
]
for t, d, y in rows:
    box(ax, mx, y, bw, bh, t, d)

for (t, d, y), (t2, d2, y2) in zip(rows[:-1], rows[1:]):
    arrow(ax, (mx, y - bh / 2), (mx, y2 + bh / 2 + 0.8))

# branch: constraint violated -> out (no long arrow; text says where it goes)
box(ax, rx, 44, rw, 11, "罚 100 万", "此路不通，\n直接试下一个候选",
    fill=FILL_ERR, edge=EDGE_ERR, tfs=12.5, dfs=10)
arrow(ax, (mx + bw / 2, 44), (rx - rw / 2 - 1, 44), label="违反", lx=65.5, ly=47.4,
      color=EDGE_ERR)

# objective + loop
box(ax, mx, 29, bw, bh, "目标：轴功率 P 最小", "等价于悬停效率 FM 最大：\nFM = 理想功率 ÷ 实际功率")
arrow(ax, (mx, 44 - bh / 2), (mx, 29 + bh / 2 + 0.8), label="通过", lx=mx + 9, ly=36.2,
      color=EDGE_OK)

box(ax, rx, 29, rw, 11, "每 8 代抽查", "拉去 hi-fi 档重考，\n防\u201c假最优\u201d蒙混过关",
    fill=FILL_WARN, edge=EDGE_WARN, tfs=12.5, dfs=10)
arrow(ax, (mx + bw / 2, 29), (rx - rw / 2 - 1, 29), label="例行", lx=65.5, ly=32.4,
      color=EDGE_WARN)

box(ax, mx, 14, bw, bh, "CMA-ES 优化器", "总结这一代经验，生成下一代 14 个候选")
arrow(ax, (mx, 29 - bh / 2), (mx, 14 + bh / 2 + 0.8))

# loop back to design vector
ax.add_patch(FancyArrowPatch((mx - bw / 2, 14), (5, 14), arrowstyle="-",
                             linewidth=1.6, color=ACCENT))
ax.add_patch(FancyArrowPatch((5, 14), (5, 128), arrowstyle="-",
                             linewidth=1.6, color=ACCENT))
ax.add_patch(FancyArrowPatch((5, 128), (mx - bw / 2 - 1, 128),
                             arrowstyle="-|>", mutation_scale=16,
                             linewidth=1.6, color=ACCENT))
ax.text(2.2, 71, "下一代", ha="center", va="center", fontsize=10.5,
        color=ARROW_D, rotation=90)

# hi-fi check outcomes
box(ax, rx, 14, rw, 11, "终验 + 交付", "超深档算总账\n→ 图纸导出",
    fill=FILL_OK, edge=EDGE_OK, tfs=12.5, dfs=10)
arrow(ax, (rx, 29 - 5.5), (rx, 14 + 5.5 + 0.8), label="通过", lx=rx + 0.5, ly=21.8,
      color=EDGE_OK)
arrow(ax, (rx - rw / 2, 25.5), (mx + bw / 2 - 2, 17.5), rad=0.15, color=EDGE_WARN)

save(fig, "fig_flow_main.png")

# ================================================================ fig 2: wake inner loop
W2, H2 = 100, 116
fig, ax = plt.subplots(figsize=(8.0, 9.3), dpi=200)
ax.set_xlim(0, W2); ax.set_ylim(0, H2); ax.axis("off")

box(ax, 50, 108, 62, 9, "输入桨叶几何 + 转速", tfs=13)
box(ax, 50, 93, 62, 10.5, "猜初始环量 Γ(r)，铺初始螺旋尾迹",
    "只是给个起点；收敛态 100% 由方程自己解出", tfs=13)

lx, rx2, lw2 = 27, 73, 38
box(ax, rx2, 67, lw2, 12.5, "算诱导风", "尾迹每段涡用 Biot–Savart 公式，\n算出它在桨叶处吹出的风")
box(ax, rx2, 42, lw2, 12.5, "查 2D 表得升阻", "桨叶真实来风 = 旋转风 + 诱导风\n→ 迎角 → 查升力/阻力表")
box(ax, lx, 42, lw2, 12.5, "反推新环量 Γ_new", "升力 = ρ·V·Γ，由升力反解\n每段桨叶的环量")
box(ax, lx, 67, lw2, 12.5, "环量收敛了？", "新旧环量最大变化\n< 0.03% 即收敛",
    fill=FILL_WARN, edge=EDGE_WARN)

box(ax, 50, 53, 24, 6.5, "松弛 + 尾迹漂移", "（PIPC 一步）", tfs=11, dfs=9.5)
box(ax, 50, 16, 54, 10.5, "出成绩单", "推力 / 功率 / 功率账本（电都花哪了）/ FM",
    fill=FILL_OK, edge=EDGE_OK)

arrow(ax, (50, 103.5), (50, 98.5))
arrow(ax, (60, 87.5), (rx2 - 4, 73.8), rad=0.12)
arrow(ax, (rx2, 60.5), (rx2, 48.5))
arrow(ax, (rx2 - lw2 / 2, 42), (lx + lw2 / 2 + 1, 42))
arrow(ax, (lx, 48.5), (lx, 60.5))
arrow(ax, (lx + lw2 / 2, 67), (rx2 - lw2 / 2, 67), label="否", lx=50, ly=70)
arrow(ax, (50, 66.5), (50, 56.6))
arrow(ax, (62, 54), (69, 60.4), rad=-0.1)
arrow(ax, (lx - lw2 / 2, 67), (4, 67), style="-")
arrow(ax, (4, 67), (4, 16), style="-")
arrow(ax, (4, 16), (50 - 27 - 1, 16), label="是", lx=4, ly=24, color=EDGE_OK)

save(fig, "fig_flow_wake.png")
print("done")
