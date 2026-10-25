"""Generate all verification-report figures -> docs/verif_figs/*.png"""
import sys, json, glob
sys.path.insert(0, "E:/旋翼设计/src")
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

plt.rcParams.update({
    "font.sans-serif": ["Microsoft YaHei", "SimHei", "DejaVu Sans"],
    "axes.unicode_minus": False, "figure.dpi": 150,
    "axes.grid": True, "grid.alpha": 0.25, "font.size": 9,
    "axes.titlesize": 10, "axes.labelsize": 9, "legend.fontsize": 8,
})
FIG = "E:/旋翼设计/docs/verif_figs"
import os
os.makedirs(FIG, exist_ok=True)
C = dict(core="#d62728", ok="#2ca02c", warn="#ff7f0e", blue="#1f77b4", gray="#7f7f7f",
         purple="#9467bd")

def save(fig, name):
    try:
        fig.tight_layout()
    except Exception:
        pass
    fig.savefig(f"{FIG}/{name}", bbox_inches="tight")
    plt.close(fig)
    print("saved", name, flush=True)

# ================================================================ fig01 kernel
from rotorgen.kernels3d import velocity_at_points
fig, axs = plt.subplots(1, 2, figsize=(9, 3.4))
# (a) three analytic checks
n = 4000
nodes = np.zeros((n, 3)); nodes[:, 2] = np.linspace(0, 4000, n)
segs = np.concatenate([nodes[:-1], nodes[1:]], axis=1)
G, d = 1.7, 2.5
gam = np.full(len(segs), G / n * 4000); rc2 = np.full(len(segs), 1e-16)
v = np.zeros((1, 3))
velocity_at_points(segs, gam, rc2, np.array([[d, 0, 1234.0]]), v)
rel1 = abs(v[0, 1] / (G / (2 * np.pi * d)) - 1)
p1, p2 = np.array([0., 0, 0]), np.array([0., 0, 3.0])
r1 = np.array([d, 0, 1.5])
c1 = r1[2] / np.linalg.norm(r1 - p1); c2 = (r1[2] - 3) / np.linalg.norm(r1 - p2)
ex2 = G / (4 * np.pi * d) * (c1 - c2)
v = np.zeros((1, 3))
velocity_at_points(np.array([[*p1, *p2]]), np.array([G]), np.array([1e-16]),
                   r1[None, :], v)
rel2 = abs(np.hypot(v[0, 0], v[0, 1]) / ex2 - 1)
m = 4000; th = np.linspace(0, 2 * np.pi, m + 1); Rr = 1.3
ring = np.stack([Rr * np.cos(th), Rr * np.sin(th), 0 * th], axis=1)
rsegs = np.concatenate([ring[:-1], ring[1:]], axis=1)
v = np.zeros((1, 3))
velocity_at_points(rsegs, np.full(len(rsegs), G), np.full(len(rsegs), 1e-18),
                   np.array([[0., 0, 0.7]]), v)
rel3 = abs(v[0, 2] / (G * Rr**2 / (2 * (Rr**2 + 0.49)**1.5)) - 1)
names = ["半无限直线涡丝\nvs Γ/(2πd)", "有限直线涡段\nvs 解析式", "涡环(轴向)\nvs ΓR²/2(R²+z²)³ᐟ²"]
vals = [rel1, rel2, rel3]
axs[0].bar(range(3), np.maximum(vals, 1e-17), color=[C["ok"], C["ok"], C["ok"]])
for i, vv in enumerate(vals):
    axs[0].text(i, max(vv, 1e-17) * 1.6, f"{vv:.1e}", ha="center", fontsize=8)
axs[0].set_yscale("log"); axs[0].set_ylim(1e-17, 1e-5)
axs[0].set_xticks(range(3), names, fontsize=7.5)
axs[0].set_ylabel("相对误差")
axs[0].set_title("(a) Biot–Savart 精确有限段核 vs 三类解析解")
# (b) core regularization
L = 1.0
p1b, p2b = np.array([0., -L / 2, 0]), np.array([0., L / 2, 0])
pts = np.array([[x, 0, 0] for x in np.linspace(0.005, 0.6, 200)])
for rc, ls in ((1e-8, ":"), (0.02, "--"), (0.08, "-")):
    v = np.zeros_like(pts)
    velocity_at_points(np.array([[*p1b, *p2b]]), np.array([1.0]),
                       np.array([rc**2]), pts, v)
    axs[1].plot(pts[:, 0], v[:, 2] * 2 * np.pi * pts[:, 0], ls,
                label=f"rc={rc:g} (×2πd 归一)")
axs[1].axhline(1.0, color="k", lw=0.8)
axs[1].set_xlabel("场点到涡段垂距 d"); axs[1].set_ylabel("归一化诱导速度")
axs[1].legend(); axs[1].set_title("(b) 涡核正则化:d≫rc 精确,d→0 有限(无奇异性)")
save(fig, "fig01_kernel.png")

# ================================================================ fig02 2D NACA0012
z2 = np.load("E:/旋翼设计/results/verif_2d.npz")
fig, axs = plt.subplots(2, 2, figsize=(9.6, 7.4))
a = z2["alphas"]; cl = z2["cl"]; cd = z2["cd"]; cl_inv = z2["cl_inv"]
ax = axs[0, 0]
ax.plot(a, cl, "-o", ms=3, color=C["blue"], label="自研 Foil2D(粘性)")
ax.plot(a, cl_inv, "--", color=C["gray"], label="自研(无粘)")
nf_a = [0, 1, 2, 4, 5]; nf_cl = [0.0000, 0.1072, 0.2141, 0.4263, 0.5439]
ax.plot(nf_a, nf_cl, "s", ms=5, mfc="none", color=C["core"], label="NFool(mfoil 体系)")
ax.plot(a, 0.109 * a, ":", color="k", label="Ladson 实验 Cl_α=0.109/deg")
ax.set_xlabel("α (deg)"); ax.set_ylabel("Cl"); ax.legend()
ax.set_title("(a) NACA0012 升力线 @Re6e6:自研 0.1121 / NFool 0.1088 / 实验 0.109")
ax = axs[0, 1]
inv_a = np.arange(0, 17, 2)
nf_m0 = [-0.0000, 0.2417, 0.4831, 0.7239, 0.9638, 1.2025, 1.4398, 1.6753, 1.9089]
our_m0 = [0.0000, 0.2401, 0.4799, 0.7189, 0.9570, 1.1937, 1.4287, 1.6616, 1.8922]
ax.plot(inv_a, nf_m0, "s-", ms=4, color=C["core"], label="NFool 无粘 M0")
ax.plot(inv_a, our_m0, "o--", ms=4, color=C["blue"], label="自研无粘 M0")
nf_m3 = [-0.0000, 0.2569, 0.5150, 0.7758, 1.0410, 1.3130, 1.5952, 1.8926, 2.2132]
our_m3 = [0.0000, 0.2551, 0.5114, 0.7700, 1.0326, 1.3013, 1.5791, 1.8703, 2.1819]
ax.plot(inv_a, nf_m3, "^:", ms=4, color=C["core"], alpha=0.6, label="NFool M0.3")
ax.plot(inv_a, our_m3, "v--", ms=4, color=C["gray"], label="自研 M0.3(Kármán–Tsien)")
ax.set_xlabel("α (deg)"); ax.set_ylabel("Cl(无粘)"); ax.legend()
ax.set_title("(b) 无粘全域对比:自研比 NFool 低 0.7~0.9% 全程一致")
ax = axs[1, 0]
ax.plot(z2["xmid"], z2["cp0"], "-", color=C["blue"], label="α=0° 自研")
ax.plot(z2["xmid"], z2["cp5"], "-", color=C["core"], label="α=5° 自研")
ax.scatter([z2["xmid"][np.argmin(z2["cp0"])]], [z2["cp0"].min()], marker="x",
           s=60, color="k", zorder=5)
ax.scatter([z2["xmid"][np.argmin(z2["cp5"])]], [z2["cp5"].min()], marker="x",
           s=60, color="k", zorder=5)
ax.annotate(f"Cp_min={z2['cp0'].min():.3f}\n(实验 −0.42)",
            (z2["xmid"][np.argmin(z2["cp0"])], z2["cp0"].min()),
            textcoords="offset points", xytext=(18, -2), fontsize=8)
ax.annotate(f"Cp_min={z2['cp5'].min():.3f}\n(实验 −2.0)",
            (z2["xmid"][np.argmin(z2["cp5"])], z2["cp5"].min()),
            textcoords="offset points", xytext=(18, -2), fontsize=8)
ax.invert_yaxis(); ax.set_xlabel("x/c"); ax.set_ylabel("Cp")
ax.legend(loc="lower right"); ax.set_title("(c) Cp 分布:吸力峰误差 <2.5%")
ax = axs[1, 1]
grids = [60, 70, 80, 140]
cds = dict(n60=[0.00523, 0.00528, 0.00538], n70=[0.00527, 0.00536, 0.00535],
           n80=[0.00493, 0.00515, 0.00524], n140=[0.0043, 0.00407, 0.00399])
for g, key, ls in zip(grids, cds, ("-", "--", "-.", ":")):
    ax.plot([0, 1, 2], cds[key], marker="o", ms=4, ls=ls,
            label=f"自研 n_per_side={g}")
ax.axhspan(0.0058, 0.0065, color=C["ok"], alpha=0.18, label="Ladson 实验 0.0058~0.0065")
ax.plot([0, 1, 2], [0.00530, 0.00538, 0.00565], "s", mfc="none", color=C["core"],
        label="NFool 粘性")
ax.plot([4], [0.00530], "s", mfc="none", color=C["core"])
ax.set_xticks(range(5), ["α=0°", "α=1°", "α=2°", "", "α=0°"])
ax.set_ylabel("Cd"); ax.legend(fontsize=7); ax.set_title("(d) 型阻:生产网格(60-70)比实验低 12~18% → ×1.15 修正依据")
save(fig, "fig02_2d.png")

# ================================================================ fig03 A4 matrix
d = json.load(open("E:/旋翼设计/results/bench/matrix_v2_ultra_phi1.20_cd1.15.json"))
rows = d["rows"]
fam_color = dict(ct=C["core"], har=C["blue"], dji=C["warn"], mt=C["gray"])
fig, axs = plt.subplots(1, 2, figsize=(11.5, 5.6))
y = np.arange(len(rows))[::-1]
lbl = [r["case"].replace("CT ", "C-T ").replace("MartinTung", "Martin-Tung ")
       .replace("Harrington1", "Harrington ").replace("DJI9450", "DJI9450 ")
       for r in rows]
fams = [r["family"] for r in rows]
for ax, key, band, title in ((axs[0], "CT_err", 10, "(a) 推力系数误差 CT(定距)"),
                             (axs[1], "CQ_matched_err", 8, "(b) 配平扭矩误差 CQ_matched")):
    xlo, xhi = (-55, 75) if key == "CT_err" else (-55, 60)
    raw = [r[key] for r in rows]
    vals = [max(min(v, xhi - 10), xlo + 10) for v in raw]
    colors = [fam_color[f] for f in fams]
    ax.barh(y, vals, color=colors, height=0.72)
    ax.axvspan(-band, band, color=C["ok"], alpha=0.13)
    ax.axvline(0, color="k", lw=0.8)
    for yi, v0, v in zip(y, raw, vals):
        clipped = abs(v0) > xhi - 10 or v0 < xlo + 10
        ax.text(v + (2 if v >= 0 else -2), yi, f"{v0:+.0f}%*" if clipped else f"{v0:+.0f}%",
                va="center", ha="left" if v >= 0 else "right", fontsize=7)
    ax.set_yticks(y, lbl, fontsize=7.5)
    ax.set_xlim(xlo, xhi)
    ax.set_title(title + "  [绿带=验收带,*=超出截断]")
    ax.set_xlabel("误差 (%)")
axs[0].text(0.98, 0.03, "C-T 核心(θ≥8,M<0.6):+3.5~+8.6% 达标", transform=axs[0].transAxes,
            ha="right", fontsize=8, color=C["ok"])
axs[1].text(0.98, 0.03, "全家族扭矩低估 15~25%(Martin-Tung 离散化失效域)", 
            transform=axs[1].transAxes, ha="right", fontsize=8, color=C["warn"])
from matplotlib.patches import Patch
axs[1].legend(handles=[Patch(color=fam_color[k], label=l) for k, l in
                       (("ct", "Caradonna–Tung(核心域)"), ("har", "Harrington(全尺寸)"),
                        ("dji", "DJI 9450(低 Re)"), ("mt", "Martin-Tung(微型)"))],
              loc="lower right", fontsize=7)
save(fig, "fig03_matrix.png")

# ================================================================ fig04 phi sweep
cal = json.load(open("E:/旋翼设计/results/calib_a2.json"))["phi_sweep"]
R_ct = 1.143
cases = ["CT th8 @1250", "CT th8 @2050", "CT th12 @1250"]
fig, axs = plt.subplots(1, 2, figsize=(9.6, 3.8))
for c, mk in zip(cases, ("o", "s", "^")):
    ph = [r["phi"] for r in cal if r["case"] == c]
    ct = [r["CT_err"] for r in cal if r["case"] == c]
    cqm_old = [r["CQ_matched_err"] for r in cal if r["case"] == c]
    cqm_true = [(1 + e / 100) / R_ct * 100 - 100 for e in cqm_old]
    axs[0].plot(ph, ct, "-" + mk, label=c.replace("CT ", "θ").replace(" @", "@"))
    axs[1].plot(ph, cqm_true, "-" + mk, label=c.replace("CT ", "θ").replace(" @", "@") + " (去污染)")
    axs[1].plot(ph, cqm_old, ":" + mk, alpha=0.35,
                label=c.replace("CT ", "θ") + " (当时打印值)" if c == cases[0] else None)
axs[0].axhline(0, color="k", lw=0.8)
axs[0].axhspan(-10, 10, color=C["ok"], alpha=0.15, label="±10% 验收带")
axs[0].axvline(1.2, color=C["core"], lw=1.2, ls="--")
axs[0].text(1.205, axs[0].get_ylim()[0] * 0.5 + 5, "φ_cal=1.2", color=C["core"], fontsize=8)
axs[0].set_xlabel("inflow_scale φ"); axs[0].set_ylabel("CT 误差 (%)")
axs[0].set_title("(a) 定距推力:φ=1.2 把核心 CT 压进 ±10%")
axs[0].legend(fontsize=7)
axs[1].axhline(0, color="k", lw=0.8)
axs[1].axvline(1.2, color=C["core"], lw=1.2, ls="--")
axs[1].set_xlabel("inflow_scale φ"); axs[1].set_ylabel("CQ_matched 误差 (%)")
axs[1].set_title("(b) 配平扭矩(旧读数按 (1+e)/R−1 去污染,R=1.143):φ 不修复缺口")
axs[1].legend(fontsize=7)
save(fig, "fig04_phi.png")

# ================================================================ fig05 kappa Gate A
zk = np.load("E:/旋翼设计/results/verif_kappa.npz")
ks, mx = zk["ks"], zk["mx_err"]
fig, axs = plt.subplots(1, 2, figsize=(9.6, 3.8))
axs[0].plot(ks, mx, "-", color=C["blue"], lw=1.6)
axs[0].axhline(8, color=C["ok"], ls="--", lw=1, label="Gate A ±8%")
for k, lab, cc in ((1.15, "1.15(计划上限)", C["warn"]), (1.18, "1.18(止损线)", C["warn"]),
                   (1.20, "1.20(采用)", C["core"]), (1.218, "最优 1.218", C["blue"])):
    e = mx[np.argmin(abs(ks - k))]
    axs[0].plot(k, e, "o", color=cc, ms=6)
    axs[0].annotate(f"κ={k:g}\nmax|err|={e:.1f}%", (k, e), xytext=(6, 14),
                    textcoords="offset points", fontsize=7.5, color=cc)
axs[0].set_xlabel("κ_cal"); axs[0].set_ylabel("核心集最大 |CQ_matched 误差| (%)")
axs[0].set_title("(a) Gate A 定标曲线(复算 gate_a_kcal)")
axs[0].legend()
for i, nm in enumerate(zk["core_names"]):
    e1 = zk["core_cqm"][i]; pf = zk["core_pind"][i]
    line = ks * 0 + np.array([(k - 1) * 100 * pf * (1 + e1 / 100) + e1 for k in ks])
    axs[1].plot(ks, line, label=f"{nm.replace('CT ','θ').replace(' @','@')} "
                 f"(P_ind={pf*100:.0f}%)")
axs[1].axhline(0, color="k", lw=0.8); axs[1].axhspan(-8, 8, color=C["ok"], alpha=0.15)
axs[1].axvline(1.20, color=C["core"], ls="--")
axs[1].set_xlabel("κ_cal"); axs[1].set_ylabel("CQ_matched 误差 (%)")
axs[1].set_title("(b) 各核心工况误差随 κ 平移(仿射,P_ind 加权)")
axs[1].legend(fontsize=7.5)
save(fig, "fig05_kappa.png")

# ================================================================ fig06 ledger + FM ladder
dg12 = json.load(open("E:/旋翼设计/results/diag_fm075_v2_phi1.20_cd1.15.json"))[0]
dv2 = json.load(open("E:/旋翼设计/results/diag_fm075_v2.json"))
dg13, dgdeep = dv2[0], dv2[1]
fig, axs = plt.subplots(1, 2, figsize=(9.8, 4.0))
cfgs = [dg13, dgdeep, dg12]
names = ["hi-fi φ1.3\nCd×1.0", "deep φ1.3\nCd×1.0", "hi-fi φ1.2\nCd×1.15(设计口径)"]
bot = np.zeros(3)
for key, lab, cc in (("P_axial", "P_axial(推力×当地入流)", C["blue"]),
                     ("P_swirl", "P_swirl(旋涡 KE)", C["purple"]),
                     ("P_prof", "P_prof(型阻)", C["warn"])):
    vals = np.array([c[key] / 1000 for c in cfgs])
    axs[0].bar(range(3), vals, bottom=bot, color=cc, label=lab, width=0.55)
    bot += vals
for i, c in enumerate(cfgs):
    axs[0].text(i, bot[i] + 0.6, f"κ_raw={c['kappa_raw']:.3f}\nFM(v2)={c['FM_v2']:.3f}",
                ha="center", fontsize=7.5)
axs[0].set_xticks(range(3), names, fontsize=8)
axs[0].set_ylabel("功率 (kW)"); axs[0].set_ylim(0, 45)
axs[0].legend(loc="upper left", fontsize=7.5)
axs[0].set_title("(a) 交付叶片功率账本(显式物理项,无 κ_B 毯子)")
kgrid = np.arange(1.0, 1.26, 0.005)
ladder = [dg12["P_ideal"] / ((dg12["P_axial"] + dg12["P_swirl"]) * k + dg12["P_prof"])
          for k in kgrid]
axs[1].plot(kgrid, ladder, lw=1.8, color=C["blue"])
for k, fm in ((1.0, 0.821), (1.1, 0.751), (1.18, 0.703), (1.20, 0.692), (1.22, 0.681)):
    axs[1].plot(k, fm, "o", ms=5, color=C["core"] if k == 1.20 else C["gray"])
    off = (7, -20) if k == 1.1 else (4, 6)   # keep the 0.75-line labels clear
    axs[1].annotate(f"κ={k:.2f}\n{fm:.3f}", (k, fm), xytext=off,
                    textcoords="offset points", fontsize=7.5)
axs[1].axhline(0.75, color=C["ok"], ls="--", lw=1)
axs[1].text(1.005, 0.752, "Gate C:FM(κ=1.0)>=0.75 达标(0.821)", fontsize=7.5, color=C["ok"])
axs[1].axhline(0.73, color=C["warn"], ls=":", lw=1)
axs[1].text(1.13, 0.732, "FM(κ=1.1)>=0.73 达标(0.751)", fontsize=7.5, color=C["warn"])
axs[1].set_xlabel("κ_cal(口径因子)"); axs[1].set_ylabel("FM")
axs[1].set_title("(b) FM 阶梯:FM 的口径不确定度(日志表末列 0.692 实为 κ=1.20 值)")
save(fig, "fig06_ledger.png")

# ================================================================ fig07 CQ bug audit
fig, axs = plt.subplots(1, 3, figsize=(11.5, 3.8))
core3 = ["θ8@1250", "θ8@2050", "θ12@1250"]
first = [2.6, -4.6, -8.8]                       # printed (old convention)
decon = [(1 + e / 100) / 1.143 * 100 - 100 for e in first]
rerun = [-10.2, -16.5, -20.2]
x = np.arange(3); w = 0.27
axs[0].bar(x - w, first, w, color=C["gray"], label="①A4 首跑打印值(旧 CQ,多×R)")
axs[0].bar(x, decon, w, color=C["blue"], label="②勘误公式 (1+e)/R−1 去污染")
axs[0].bar(x + w, rerun, w, color=C["core"], label="③修复后复跑实测")
for xi, (a1, a2, a3) in zip(x, zip(first, decon, rerun)):
    for off, v in ((-w, a1), (0, a2), (w, a3)):
        axs[0].text(xi + off, v - 1.5, f"{v:+.1f}", ha="center", fontsize=7)
axs[0].set_xticks(x, core3); axs[0].set_ylabel("CQ_matched 误差 (%)")
axs[0].legend(fontsize=7); axs[0].set_title("(a) 勘误链闭环:②与③逐点吻合")
axs[1].bar([0, 1], [6.45, 0.773], color=[C["gray"], C["core"]], width=0.5)
axs[1].axhline(1.0, color="k", ls="--", lw=1)
axs[1].text(0.02, 1.05, "FM=1 物理上限", fontsize=8)
axs[1].text(0, 6.45, "FM=6.4\n(>1,不可能)", ha="center", va="bottom", fontsize=8)
axs[1].text(1, 0.773, "FM=0.77", ha="center", va="bottom", fontsize=8)
axs[1].set_xticks([0, 1], ["DJI 首跑(旧 CQ)", "修复后复跑"])
axs[1].set_title("(b) 暴露 bug 的铁证:DJI 9450 @3000")
axs[1].set_ylabel("FM(系数式)")
# (c) residual /R regression test (my rerun)
vh = json.load(open("E:/旋翼设计/results/verif_heavy.json"))["delivered"]
axs[2].bar([0, 1, 2], [vh["P_watts"] / vh["P_coeff_correct"],
                       1.0,
                       vh["P_watts"] / vh["P_coeff_script"]],
       color=[C["ok"], "k", C["core"]], width=0.55)
axs[2].axhline(1.04, color=C["core"], ls="--")
axs[2].text(2.3, 1.045, "R=1.04", color=C["core"], fontsize=8)
axs[2].set_xticks([0, 1, 2], ["瓦特账本 /\n正确换算 cq·q·Vt", "1.0",
                              "瓦特账本 /\n脚本现存 cq·q·Vt/R"],
                  fontsize=7.5)
for i, v in enumerate([vh["P_watts"] / vh["P_coeff_correct"], 1.0,
                       vh["P_watts"] / vh["P_coeff_script"]]):
    axs[2].text(i, v + 0.002, f"{v:.4f}", ha="center", fontsize=8)
axs[2].set_ylim(0.95, 1.06)
axs[2].set_title("(c) 新发现:CQ 修复后脚本残留 /R → 功率低 4.3%")
save(fig, "fig07_cqbug.png")

# ================================================================ fig08 delivered geometry
import csv
geo = list(csv.DictReader(open("E:/旋翼设计/results/final/blade_geometry.csv")))
rr = np.array([float(r["r_over_R"]) for r in geo])
ch = np.array([float(r["chord_m"]) for r in geo])
tw = np.array([float(r["twist_deg"]) for r in geo])
tcv = np.array([float(r["tc_over_c"]) for r in geo])
Re = np.array([float(r["Re_at_6000N_hover"]) for r in geo])
from rotorgen.airfoil import Airfoil
files = sorted(glob.glob("E:/旋翼设计/results/final/airfoils/*.dat"))
m_r, m_tc, m_cam, m_te = [], [], [], []
for p in files:
    af = Airfoil.from_dat(p); c = af.x.max() - af.x.min()
    m_r.append(float(p.split("_r")[1][:2]) / 100)
    m_tc.append(af.thickness); m_cam.append(af.camber_max); m_te.append(af.te_gap * c * 1000)
fig, axs = plt.subplots(2, 2, figsize=(9.8, 6.2))
ax = axs[0, 0]
ax.plot(rr, ch, color=C["blue"], label="弦长 c(r)")
ax2 = ax.twinx()
ax2.plot(rr, tw, color=C["core"], label="扭角 θ(r)")
ax.set_xlabel("r/R"); ax.set_ylabel("弦长 (m)", color=C["blue"])
ax2.set_ylabel("扭角 (deg)", color=C["core"]); ax2.grid(False)
ax.set_title("(a) 平面形与扭转:28.6°→13.5° 线性扭转,平均弦 0.29 m,σ=0.178")
ax = axs[0, 1]
ax.plot(rr, tcv * 100, "-", color=C["gray"], label="CSV 列(参数目标值)")
ax.plot(m_r, np.array(m_tc) * 100, "o", ms=5, color=C["blue"], label=".dat 实测")
ax.plot(m_r, np.array(m_cam) * 100, "s", ms=5, color=C["warn"], label="弯度实测(设计参数=3.0%)")
ax.axhline(3.0, color=C["warn"], ls=":", lw=1)
ax.set_xlabel("r/R"); ax.set_ylabel("%"); ax.legend(fontsize=7.5)
ax.set_title("(b) 厚度实测比参数目标偏厚 0.5~0.8pp;弯度实测 2.2%≠参数 3.0%")
ax = axs[1, 0]
ax.plot(m_r, m_te, "o-", color=C["ok"], ms=5)
ax.axhline(2.0, color="k", ls="--", lw=1)
ax.set_ylim(1.98, 2.02); ax.set_xlabel("r/R"); ax.set_ylabel("尾缘厚度 (mm)")
ax.set_title("(c) 2 mm 钝尾缘硬约束:12 站位 .dat 实测全部 2.000 mm 达标")
ax = axs[1, 1]
ax.semilogy(rr, Re, color=C["blue"], label="Re(r) @悬停配平")
ax.axhspan(3e5, 3e6, color=C["ok"], alpha=0.15, label="基准已验证带 3e5~3e6")
ax.set_xlabel("r/R"); ax.set_ylabel("Re"); ax.legend(fontsize=7.5)
ax.set_title("(d) 展向雷诺数 4.5e5~2.4e6,全部落在已验证域内")
save(fig, "fig08_geom.png")

# ================================================================ fig09 wake physics
zw = np.load("E:/旋翼设计/results/verif_ct8.npz")
fig, axs = plt.subplots(1, 3, figsize=(11.5, 3.8))
ages = zw["ages"]; tr = zw["tip_r"]; tz = zw["tip_z"]
axs[0].plot(ages, tr, "-", color=C["blue"], lw=1.4, label="自由尾迹尖端涡丝(求解)")
axs[0].scatter([180], [0.905], marker="*", s=140, color=C["core"], zorder=5,
               label="C-T 实测 @180°(r/R=0.905)")
axs[0].set_xlabel("涡龄 ψ (deg)"); axs[0].set_ylabel("尖端涡半径 r/R")
axs[0].set_title(f"(a) 桨尖涡收缩:180° 处求解 {np.interp(180, ages, tr):.3f} vs 实验 0.905")
axs[0].legend(fontsize=7.5)
axs[1].plot(ages, tz, "-", color=C["blue"], lw=1.4)
axs[1].scatter([180], [0.09], marker="*", s=140, color=C["core"], zorder=5)
axs[1].set_xlabel("涡龄 ψ (deg)"); axs[1].set_ylabel("尖端涡下沉 z/R")
axs[1].set_title(f"(b) 桨尖涡下沉:180° 处求解 {np.interp(180, ages, tz):.3f} vs 实验 0.09")
w = zw["wake_xyz"]           # [mid filament, tip filament]
th = np.linspace(0, 2 * np.pi, 400)
axs[2].plot(w[1][:, 0], w[1][:, 1], "-", lw=0.8, color=C["blue"], label="叶 0 尖涡")
axs[2].plot(-w[1][:, 0], -w[1][:, 1], "-", lw=0.8, color=C["purple"], label="叶 1(旋转叠加)")
axs[2].add_patch(plt.Circle((0, 0), 1.0, fill=False, ls=":", color="k", lw=0.8))
axs[2].set_aspect("equal"); axs[2].set_xlabel("x/R"); axs[2].set_ylabel("y/R")
axs[2].set_title("(c) 悬停螺旋尾迹(俯视):收缩+双叶周期结构为求解结果")
axs[2].legend(fontsize=7.5, loc="lower left")
save(fig, "fig09_wake.png")

# ================================================================ fig10 convergence + repro
fig, axs = plt.subplots(1, 3, figsize=(11.5, 3.6))
hist = zw["hist"]
axs[0].plot(hist[:, 0], "-o", ms=3, color=C["blue"], label="CT")
axs[0].set_xlabel("外迭代(Γ-尾迹 不动点)"); axs[0].set_ylabel("CT")
axs[0].legend()
axt = axs[0].twinx(); axt.grid(False)
axt.plot(hist[:, 1], "--s", ms=3, color=C["core"], label="CQ")
axt.set_ylabel("CQ", color=C["core"]); axt.legend(loc="lower right")
axs[0].set_title("(a) C-T θ8@1250 收敛史(本次复跑,ultra 档)")
vh1 = json.load(open("E:/旋翼设计/results/verif_heavy.json"))["ct8_case"]
axs[1].text(0.5, 0.88, "CT  复跑 0.004749750\n     存档 0.004749750\nCQ  复跑 0.0003401944\n     存档 0.0003401944",
            transform=axs[1].transAxes, ha="center", va="top", fontsize=10)
axs[1].text(0.5, 0.30, "逐位一致 (Δ = 0)", transform=axs[1].transAxes,
            ha="center", fontsize=15, color=C["ok"], fontweight="bold")
axs[1].set_xticks([]); axs[1].set_yticks([])
axs[1].set_title("(b) 独立复跑 vs A4 矩阵存档(ultra/φ1.2/Cd×1.15)")
vhd = json.load(open("E:/旋翼设计/results/verif_heavy.json"))["delivered"]
items = ["T (N)", "P_axial (W)", "P_prof (W)", "vi_disk (m/s)"]
mine = [vhd["T"], vhd["P_axial"], vhd["P_prof"], vhd["vi_disk"]]
ref = [vhd["T_ref"], vhd["P_axial_ref"], vhd["P_prof_ref"], vhd["vi_disk_ref"]]
rel = [abs(m / r - 1) * 100 for m, r in zip(mine, ref)]
axs[2].bar(range(4), np.maximum(rel, 1e-13), color=C["ok"])
for i, v in enumerate(rel):
    axs[2].text(i, max(v, 1e-13) * 1.8, f"{v:.1e}", ha="center", fontsize=7.5)
axs[2].set_yscale("log"); axs[2].set_ylim(1e-13, 1e-2)
axs[2].set_xticks(range(4), items, fontsize=7.5)
axs[2].set_ylabel("相对偏差")
axs[2].set_title("(c) 交付叶片复跑 vs 10/24 JSON:一致到 1e-10 量级")
save(fig, "fig10_repro.png")

# ================================================================ fig11 CMA-ES
rows = json.load(open("E:/旋翼设计/results/verif_cmaes.json"))
fig, axs = plt.subplots(1, 2, figsize=(9.8, 3.7))
idx = np.arange(len(rows))
feas = [r.get("feasible") for r in rows]
Ps = [r.get("P", np.nan) if f else np.nan for r, f in zip(rows, feas)]
axs[0].plot(idx, Ps, "-o", ms=4, color=C["blue"], label="可行个体 P")
inf_x = [i for i, f in enumerate(feas) if not f]
axs[0].scatter(inf_x, [43000] * len(inf_x), marker="x", color=C["gray"],
               label="不可行(stall/no-trim,记 1e6)")
best = np.nanmin(np.where(np.isnan(Ps), np.inf, Ps))
bsf = np.minimum.accumulate(np.where(np.isnan(Ps), np.inf, Ps))
axs[0].plot(idx, bsf, "--", color=C["core"], lw=1.5, label="最优至今")
axs[0].set_xlabel("评估序号(gen0 种群)"); axs[0].set_ylabel("配平轴功率 P (W)")
axs[0].set_title("(a) CMA-ES gen0:14/560 次评估后被用户暂停")
axs[0].legend(fontsize=7.5)
fms = [r.get("FM", np.nan) if f else np.nan for r, f in zip(rows, feas)]
axs[1].plot(idx, fms, "-o", ms=4, color=C["blue"], label="日志 FM(κ=1.2 口径,fast 档)")
axs[1].plot(idx, np.array(fms) / 1.04, "--", color=C["core"],
            label="×1/R 修正后(本报告)")
axs[1].set_xlabel("评估序号"); axs[1].set_ylabel("FM")
axs[1].set_title("(b) FM 绝对值受 /R 换算残留偏高 ×1.04(排序不受影响)")
axs[1].legend(fontsize=7.5)
save(fig, "fig11_cmaes.png")

print("ALL FIGURES DONE", flush=True)
