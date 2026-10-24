"""FM=0.75 可行性诊断:对已交付最终设计做功率账本拆分与尾迹深度敏感性.

问题:performance.json 的 P_total=46.7 kW 中,诱导功率按
  P_ind = kappa_B(=1.2) * T * vi_disk(自由尾迹盘均值)
计算,kappa_B 是教材式旋涡/非均匀修正,叠加在自由尾迹自身已解析的
非理想诱导之上。本脚本量化:
  1) P_ind / P_prof 实际占比
  2) kappa_raw = vi_disk / vi_ideal(尾迹自身的非理想度)
  3) 尾迹加深(dpsi / n_rev / far_rev)后 kappa_raw 的收敛方向
     —— 判断 1.2/1.3 标定中有多少其实是尾迹截断亏空
  4) 不同记账口径下的 FM(kappa_B=1.2 交付口径 vs kappa_B=1.0 纯尾迹口径)
"""
import sys, json, time
sys.path.insert(0, "E:/旋翼设计/src")
sys.path.insert(0, "E:/旋翼设计/scripts")
import numpy as np

from design_opt import (R, B, T_TARGET, RHO, NS, RR, ALPHA_TAB,
                        get_foil, build_design, SecTab)
from rotorgen.rotor3d import BladeDef, RotorSolver
from rotorgen.famgen import AirfoilFamily

XF = json.load(open("E:/旋翼设计/results/final/performance.json"))
X = np.array(XF["design_vector"])
PITCH0 = XF["trim_pitch_deg"]


def make_solver_cfg(x, trim_pitch, dpsi, n_rev, freeze, n_far,
                    phi=1.3, cdf=1.0):
    Omega, chord_R, twist, camber, tc_r, tc_t = build_design(x, trim_pitch)
    fam = AirfoilFamily(R=R, tc_root=tc_r, tc_tip=tc_t, camber=camber, t_te_phys=0.002)
    sections = []
    mach_tip = min(Omega * R / 340.0, 0.58)
    for i in range(NS):
        r_mid = 0.5 * (RR[i] + RR[i + 1])
        c_m = 0.5 * (chord_R[i] + chord_R[i + 1]) * R
        tc = fam.tc_at(r_mid)
        te_gap = fam.te_gap_at(c_m)
        foil = get_foil(tc, camber, te_gap)
        U = Omega * r_mid * R
        Re = max(RHO * U * c_m / 1.8e-5, 6e4)
        M = min(mach_tip * r_mid, 0.55)
        rs = foil.polar(ALPHA_TAB, Re=Re, M=M)
        sections.append(SecTab(ALPHA_TAB, np.array([r.cl for r in rs]),
                               np.array([r.cd for r in rs]) * cdf))
    blade = BladeDef(R=R, Rhub=0.1664, B=B, r=RR, chord=chord_R, twist=twist)
    sol = RotorSolver(blade, Omega, rho=RHO, dpsi_deg=dpsi, n_rev=n_rev,
                      rc0_frac=0.10)
    sol.freeze_rev = freeze
    sol.n_far_rev = n_far
    sol.relax_it = 1.3
    sol.gamma_relax = 0.35
    sol.inflow_scale = phi
    sol.sections = sections
    return sol


def run_pitch(x, pitch, cfg, phi=1.3, cdf=1.0):
    sol = make_solver_cfg(x, pitch, *cfg, phi=phi, cdf=cdf)
    t0 = time.time()
    res = sol.solve(n_outer=26, n_sweeps=4,
                    ct_guess=max(T_TARGET / (RHO * np.pi * R ** 2 * x[0] ** 2), 1e-4))
    h = np.array(res.history)
    T = float(h[-6:, 0].mean()) * RHO * np.pi * R ** 2 * x[0] ** 2
    P = float(h[-6:, 1].mean()) * RHO * x[0] ** 2 * np.pi * R ** 2 * x[0] / R
    ld = sol._last_loads
    print(f"    pitch={pitch:6.2f}  T={T:7.1f} N  P={P/1000:6.2f} kW  "
          f"P_ind={ld['P_ind']/1e3:5.2f} P_prof={ld['P_prof']/1e3:5.2f} "
          f"vi_disk={ld['vi_disk']:5.2f} m/s  [{time.time()-t0:.0f}s]", flush=True)
    return T, P, ld


def trim_cfg(x, cfg, pitch0=PITCH0, tol=0.01, phi=1.3, cdf=1.0):
    """3 点割线法(对 T,不是 P)配平到 T_TARGET ±tol,返回拆分账本."""
    lo = (pitch0 - 1.5, *run_pitch(x, pitch0 - 1.5, cfg, phi, cdf))
    hi = (pitch0 + 1.5, *run_pitch(x, pitch0 + 1.5, cfg, phi, cdf))
    best = None
    for _ in range(4):
        p = hi[0] - (hi[1] - T_TARGET) * (hi[0] - lo[0]) / (hi[1] - lo[1])
        r = (p, *run_pitch(x, p, cfg, phi, cdf))
        best = min([c for c in (lo, hi, r)], key=lambda c: abs(c[1] - T_TARGET))
        if abs(r[1] - T_TARGET) < tol * T_TARGET:
            best = r
            break
        if r[1] < T_TARGET:
            lo = r
        else:
            hi = r
    return best  # (pitch, T, P, ld)


def report(name, cfg, phi=1.3, cdf=1.0):
    print(f"\n=== {name}  dpsi={cfg[0]} n_rev={cfg[1]} freeze={cfg[2]} far={cfg[3]} "
          f"phi={phi} cdf={cdf} ===",
          flush=True)
    pitch, T, P, ld = trim_cfg(X, cfg, phi=phi, cdf=cdf)
    A = np.pi * R ** 2
    P_ideal = T ** 1.5 / np.sqrt(2 * RHO * A)
    vi_ideal = np.sqrt(T / (2 * RHO * A))
    k_raw = ld["vi_disk"] / vi_ideal
    k_eff = ld["P_ind"] / P_ideal
    fm_v2 = P_ideal / P
    P_ax = ld["P_axial"]
    print(f"  trim_pitch={pitch:.2f}  T={T:.0f} N")
    print(f"  P_total={P/1e3:.2f} kW | P_ideal={P_ideal/1e3:.2f} | "
          f"P_axial={P_ax/1e3:.2f} ({100*P_ax/P:.1f}%) | "
          f"P_swirl={ld['P_swirl']/1e3:.2f} ({100*ld['P_swirl']/P:.1f}%) | "
          f"P_nonuni={ld['P_nonuniform']/1e3:.2f} ({100*ld['P_nonuniform']/P:.1f}%) | "
          f"P_prof={ld['P_prof']/1e3:.2f} ({100*ld['P_prof']/P:.1f}%)")
    print(f"  vi_disk={ld['vi_disk']:.2f} m/s vs vi_ideal={vi_ideal:.2f} -> "
          f"kappa_raw={k_raw:.3f}, kappa_eff={k_eff:.3f}")
    print(f"  FM (v2 显式口径, 无 kappa_B): {fm_v2:.3f}")
    return dict(name=name, cfg=list(cfg), pitch=pitch, T=T, P=P,
                P_ideal=P_ideal, **{k: ld[k] for k in
                ("P_ind", "P_axial", "P_swirl", "P_nonuniform", "P_prof",
                 "vi_disk", "v_area")},
                kappa_raw=k_raw, kappa_eff=k_eff,
                FM_v2=fm_v2)


if __name__ == "__main__":
    phi = 1.3
    cdf = 1.0
    if "--phi" in sys.argv:
        phi = float(sys.argv[sys.argv.index("--phi") + 1])
    if "--cdf" in sys.argv:
        cdf = float(sys.argv[sys.argv.index("--cdf") + 1])
    out = []
    out.append(report("delivered-hifi", (7.5, 6.0, 5.0, 12.0), phi=phi, cdf=cdf))
    if "--deep" in sys.argv:
        out.append(report("deep-wake", (7.5, 9.0, 8.0, 12.0), phi=phi, cdf=cdf))
    if "--ultra" in sys.argv:
        out.append(report("ultra", (5.0, 10.0, 9.0, 12.0), phi=phi, cdf=cdf))
    suffix = f"_phi{phi:.2f}_cd{cdf:.2f}"
    json.dump(out, open(f"E:/旋翼设计/results/diag_fm075_v2{suffix}.json", "w"),
              indent=1, default=float)
    print(f"\nsaved results/diag_fm075_v2{suffix}.json", flush=True)
