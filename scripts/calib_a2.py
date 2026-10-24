"""A2: 2D 表 Cl 交叉标定(NFool)+ inflow_scale(phi)处置.

Part 1 (2D): 自研 Foil2D NACA0012 vs NFool(mfoil 体系权威).
  - 粘性: NFool 可靠域 alpha<=5(本机 fork 在 alpha>=6 Newton 不收敛,
    conv=False 可检测),验证爬升线斜率 Cl_alpha;
  - 无粘: 全 alpha 域对比(面板 + Karman-Tsien),隔离粘性建模差异。
  CT 高估(+22~48% @ theta>=8)的归因:若 2D 表 Cl 偏差小,则主要来自
  叶站位入流欠估 -> phi 重标;若 2D Cl 偏强,先修表再扫 phi。

Part 2 (3D): C-T 核心工况(theta>=8)超深档 x phi in {1.0,1.1,1.2,1.3},
  以 CT 误差 <= +-10% 且 CQ_matched 合理为准则给出 phi 建议。
"""
import sys, json
sys.path.insert(0, "E:/旋翼设计/src")
sys.path.insert(0, "E:/旋翼设计/scripts")
sys.path.insert(0, "E:/旋翼设计/docs/NFoil")
import numpy as np

from rotorgen.airfoil import naca4
from rotorgen.foil2d import Foil2D
from bench2 import ct_cases, run_case


def part1_2d():
    print("=== Part 1: 2D cross-check, NACA0012 ===", flush=True)
    ours = Foil2D(naca4("0012", n_per_side=70), n_per_side=70)
    from nfoil import nfoil
    Re = 1.2e6
    out = {"viscous": [], "inviscid": []}
    # viscous climb line (NFool reliable envelope alpha<=5)
    m = nfoil(naca="0012", npanel=199)
    m.param.verb = 0
    m.setoper(alpha=0.0, Re=Re, Ma=0.0, visc=True)
    try:
        m.solve()
    except ZeroDivisionError:
        pass
    for a in np.arange(0, 5.01, 1.0):
        try:
            m.setoper(alpha=float(a), Re=Re, visc=True)
            m.solve()
            conv = bool(getattr(m.glob, "conv", False))
            cl_nf, cd_nf = float(m.post.cl), float(m.post.cd)
        except Exception:
            conv, cl_nf, cd_nf = False, float("nan"), float("nan")
        r_ours = ours.analyze(float(a), Re, 0.0)
        out["viscous"].append(dict(alpha=float(a), conv=conv,
                                   cl_nfoil=cl_nf, cd_nfoil=cd_nf,
                                   cl_ours=float(r_ours.cl),
                                   cd_ours=float(r_ours.cd)))
        print(f"  visc a={a:.0f} conv={conv}  cl: nfoil={cl_nf:.4f} "
              f"ours={r_ours.cl:.4f} ({100*(r_ours.cl/max(cl_nf,1e-9)-1):+.1f}%)  "
              f"cd: nfoil={cd_nf:.5f} ours={r_ours.cd:.5f}", flush=True)
    # inviscid full range (panel + Karman-Tsien both sides)
    for a in np.arange(0, 17.01, 2.0):
        def nfi_cl(ma):
            mm = nfoil(naca="0012", npanel=199)
            mm.param.verb = 0
            mm.setoper(alpha=float(a), Ma=ma, visc=False)
            try:
                mm.solve()
                return float(mm.post.cl)
            except Exception:
                return float("nan")
        cl_nfi = nfi_cl(0.0)
        cl_nfi3 = nfi_cl(0.3)
        r0 = ours.analyze(float(a), Re, 0.0)
        r3 = ours.analyze(float(a), Re, 0.3)
        out["inviscid"].append(dict(alpha=float(a), cl_nfoil_M0=cl_nfi,
                                    cl_nfoil_M03=cl_nfi3,
                                    cl_inv_ours_M0=float(r0.cl_inv),
                                    cl_inv_ours_M03=float(r3.cl_inv),
                                    cl_visc_ours_M03=float(r3.cl)))
        print(f"  inv  a={a:.0f}  M0: nfoil={cl_nfi:.4f} ours_inv={r0.cl_inv:.4f} "
              f"({100*(r0.cl_inv/max(cl_nfi,1e-9)-1):+.1f}%)  "
              f"M0.3: nfoil={cl_nfi3:.4f} ours_inv={r3.cl_inv:.4f} "
              f"ours_visc={r3.cl:.4f}", flush=True)
    # climb-line slopes
    va = out["viscous"]
    slope_n = (va[-1]["cl_nfoil"] - va[0]["cl_nfoil"]) / (va[-1]["alpha"] - va[0]["alpha"])
    slope_o = (va[-1]["cl_ours"] - va[0]["cl_ours"]) / (va[-1]["alpha"] - va[0]["alpha"])
    out["cl_alpha_per_deg"] = dict(nfoil=slope_n, ours=slope_o,
                                   ladson_exp=0.109)
    print(f"  Cl_alpha: nfoil={slope_n:.4f}/deg ours={slope_o:.4f}/deg "
          f"(Ladson exp 0.109)", flush=True)
    return out


def part2_phi():
    print("\n=== Part 2: C-T core cases x phi sweep (ultra tier) ===", flush=True)
    cases = {name: (blade, Omega, secs, exp)
             for name, blade, Omega, secs, exp in ct_cases()
             if name in ("CT th8 @1250", "CT th12 @1250", "CT th8 @2050")}
    out = []
    for phi in (1.0, 1.1, 1.2, 1.3):
        print(f"\n--- phi = {phi} ---", flush=True)
        for name, (blade, Omega, secs, exp) in cases.items():
            row = run_case(name, blade, Omega, secs, exp["ct_exp"],
                           exp["cq_exp"], exp["fm_exp"], tier="ultra", phi=phi)
            out.append(row)
    return out


if __name__ == "__main__":
    res = {}
    if "--part2-only" not in sys.argv:
        res["twodim"] = part1_2d()
    if "--part1-only" not in sys.argv:
        res["phi_sweep"] = part2_phi()
    json.dump(res, open("E:/旋翼设计/results/calib_a2.json", "w"),
              indent=1, default=float)
    print("\nsaved results/calib_a2.json", flush=True)
