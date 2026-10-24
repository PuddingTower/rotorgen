"""C-T 基准复跑:超深尾迹 + 原始记账(无 kappa_B、无 inflow_scale 标定).

目的:现行验证(浅尾迹 dpsi=10/5圈 + kappa_B=1.2 + phi=1.3)CQ 达标 ±9%;
若深尾迹原始口径的 CQ 误差仍在 ±10% 内,则 1.2/1.3 属双重计入,应在设计
口径中移除;若系统性低估 >10%,则真实标定介于原始与 1.2 之间,需单点重标。
"""
import sys, json, time
sys.path.insert(0, "E:/旋翼设计/src")
sys.path.insert(0, "E:/旋翼设计/scripts")
import numpy as np

from rotorgen.rotor3d import BladeDef, RotorSolver
from run_bench import naca_sections, SecTab


def run_cfg(blade, Omega, sections, ct_guess,
            dpsi, n_rev, freeze, far, kappa_b, phi, n_outer=30):
    sol = RotorSolver(blade, Omega, rho=1.225, dpsi_deg=dpsi, n_rev=n_rev,
                      rc0_frac=0.10)
    sol.freeze_rev = freeze
    sol.n_far_rev = far
    sol.relax_it = 1.3
    sol.gamma_relax = 0.35
    sol.inflow_scale = phi
    sol.kappa_B = kappa_b
    sol.sections = [SecTab(t) for t in sections]
    t0 = time.time()
    res = sol.solve(n_outer=n_outer, n_sweeps=4, ct_guess=ct_guess)
    h = np.array(res.history)
    ct = float(h[-8:, 0].mean())
    cq = float(h[-8:, 1].mean())
    fm = ct ** 1.5 / (np.sqrt(2) * cq)
    return ct, cq, fm, time.time() - t0


def main():
    R, Rhub = 1.143, 0.1143
    Ns = 24
    rr = np.linspace(Rhub / R, 1.0, Ns + 1)
    chord = np.full(Ns + 1, 0.1905 / R)
    ct_data = [(5.0, 1250, 0.0021, 0.00018, 0.38),
               (5.0, 2050, 0.0028, 0.00025, 0.42),
               (8.0, 1250, 0.00459, 0.00036, 0.611),
               (8.0, 2050, 0.00461, 0.00039, 0.567),
               (12.0, 1250, 0.0079, 0.00078, 0.635),
               (12.0, 2050, 0.0067, 0.00085, 0.457)]
    # (dpsi, n_rev, freeze, far, kappa_B, phi)
    cfgs = [
        ("raw-deep  kb1.0 phi1.0", (5.0, 10.0, 9.0, 12.0, 1.0, 1.0)),
        ("deep+kb  kb1.2 phi1.3", (5.0, 10.0, 9.0, 12.0, 1.2, 1.3)),
    ]
    out = []
    for cfg_name, cfg in cfgs:
        print(f"\n=== C-T {cfg_name} ===", flush=True)
        for th, rpm, cte, cqe, fme in ct_data:
            Omega = rpm * 2 * np.pi / 60
            mach_tip = Omega * R / 340.0
            blade = BladeDef(R=R, Rhub=Rhub, B=2, r=rr, chord=chord,
                             twist=np.full(Ns + 1, th))
            secs = naca_sections(rr, R, Omega, chord, mach_tip)
            ct, cq, fm, dt = run_cfg(blade, Omega, secs, cte, *cfg)
            row = dict(cfg=cfg_name, case=f"th{th:.0f}@{rpm}", CT=ct, CQ=cq,
                       CT_err=100*(ct/cte-1), CQ_err=100*(cq/cqe-1),
                       FM=fm, FM_exp=fme, t_s=round(dt, 1))
            out.append(row)
            print(f"  th{th:4.1f}@{rpm}  CT={ct:.5f} ({row['CT_err']:+6.1f}%)  "
                  f"CQ={cq:.6f} ({row['CQ_err']:+6.1f}%)  "
                  f"FM={fm:.3f}/{fme:.3f}  [{dt:.0f}s]", flush=True)
    json.dump(out, open("E:/旋翼设计/results/diag_ct_raw.json", "w"),
              indent=1, default=float)
    print("\nsaved results/diag_ct_raw.json", flush=True)


if __name__ == "__main__":
    main()
