"""Benchmark matrix runner: blind predictions vs experimental truth.

Cases (2-blade focus + one 4-blade stretch):
  05 Caradonna-Tung: 7 hover points (collective x RPM)
  03 Martin-Tung 10in: NACA0012 rectangular, low Re
  07 Harrington 25ft Rotor 1 (rect NACA0012) + Rotor 2 (tapered)
  01 DJI 9443: real geometry (chord/twist tables), low-Re sections approximated
"""
import sys, time, json
sys.path.insert(0, "E:/旋翼设计/src")
import numpy as np

from rotorgen.rotor3d import BladeDef, RotorSolver
from rotorgen.airfoil import naca0012, naca4
from rotorgen.foil2d import Foil2D

ALPHA_TAB = np.arange(-8, 24.01, 0.5)
_foil_cache = {}


def naca_sections(rr, R, Omega, chord_R, mach_tip, digits="0012", re_ref=None):
    """Section tables per station (Re from local speed)."""
    key = digits
    if key not in _foil_cache:
        _foil_cache[key] = Foil2D(naca4(digits, n_per_side=70), n_per_side=70)
    f = _foil_cache[key]
    secs = []
    for i in range(len(rr) - 1):
        r_mid = 0.5 * (rr[i] + rr[i + 1]) * R
        c = 0.5 * (chord_R[i] + chord_R[i + 1]) * R
        U = Omega * r_mid
        Re = max(U * c / 1.8e-5, 3e4)
        M = min(mach_tip * r_mid / R, 0.6)
        rs = f.polar(ALPHA_TAB, Re=Re, M=M)
        cl = np.array([r.cl for r in rs])
        cd = np.array([r.cd for r in rs])
        secs.append((ALPHA_TAB, cl, cd))
    return secs


class SecTab:
    def __init__(self, tab):
        self.a, self.cl, self.cd = tab

    def cl_of(self, a):
        return float(np.interp(a, self.a, self.cl))

    def cd_of(self, a):
        return float(np.interp(a, self.a, self.cd))


def run_case(name, blade, Omega, sections, ct_guess, ct_exp, cq_exp, fm_exp,
             rho=1.225, n_outer=30):
    sol = RotorSolver(blade, Omega, rho=rho, dpsi_deg=10.0, n_rev=5.0, rc0_frac=0.10)
    sol.freeze_rev = 4.0
    sol.n_far_rev = 8.0
    sol.relax_it = 1.3
    sol.gamma_relax = 0.35
    sol.inflow_scale = 1.3
    sol.sections = [SecTab(t) for t in sections]
    t0 = time.time()
    res = sol.solve(n_outer=n_outer, n_sweeps=4, ct_guess=ct_guess)
    dt = time.time() - t0
    h = np.array(res.history)
    ct = float(h[-8:, 0].mean())
    cq = float(h[-8:, 1].mean())
    fm = ct ** 1.5 / (np.sqrt(2) * cq) if cq > 0 else 0.0
    ct_err = 100 * (ct / ct_exp - 1) if ct_exp > 1e-9 else float('nan')
    cq_err = 100 * (cq / cq_exp - 1) if cq_exp > 1e-9 else float('nan')
    row = dict(case=name, CT=ct, CT_exp=ct_exp, CT_err=ct_err,
               CQ=cq, CQ_exp=cq_exp, CQ_err=cq_err,
               FM=fm, FM_exp=fm_exp, t_s=round(dt, 1))
    print(f"{name:28s} CT={ct:.5f} ({ct_err:+6.1f}%)  "
          f"CQ={cq:.6f} ({cq_err:+6.1f}%)  FM={fm:.3f}/{fm_exp:.3f}  [{dt:.0f}s]")
    return row


def main():
    results = []

    # ---------------- Case 05: Caradonna-Tung ----------------
    R, Rhub = 1.143, 0.1143
    Ns = 24
    rr = np.linspace(Rhub / R, 1.0, Ns + 1)
    chord = np.full(Ns + 1, 0.1905 / R)
    ct_data = [(5.0, 1250, 0.0021, 0.00018, 0.38),
               (5.0, 2050, 0.0028, 0.00025, 0.42), (8.0, 1250, 0.00459, 0.00036, 0.611),
               (8.0, 2050, 0.00461, 0.00039, 0.567), (12.0, 1250, 0.0079, 0.00078, 0.635),
               (12.0, 2050, 0.0067, 0.00085, 0.457)]
    for th, rpm, cte, cqe, fme in ct_data:
        Omega = rpm * 2 * np.pi / 60
        mach_tip = Omega * R / 340.0
        blade = BladeDef(R=R, Rhub=Rhub, B=2, r=rr, chord=chord,
                         twist=np.full(Ns + 1, th))
        secs = naca_sections(rr, R, Omega, chord, mach_tip)
        results.append(run_case(f"CT th{th:.0f} @{rpm}", blade, Omega, secs,
                                cte, cte, cqe, fme))

    # ---------------- Case 03: Martin-Tung 10in ----------------
    R, Rhub = 0.127, 0.0254
    rr = np.linspace(Rhub / R, 1.0, Ns + 1)
    chord = np.full(Ns + 1, 0.0381 / R)
    mt_data = [(6.0, 2500, 0.00318, 0.00049, 0.368), (6.0, 3500, 0.00319, 0.00049, 0.37),
               (8.0, 2500, 0.00464, 0.00073, 0.443), (8.0, 3500, 0.00465, 0.00074, 0.441),
               (10.0, 2500, 0.00605, 0.00102, 0.468), (12.0, 2500, 0.0073, 0.00137, 0.457)]
    for th, rpm, cte, cqe, fme in mt_data:
        Omega = rpm * 2 * np.pi / 60
        mach_tip = Omega * R / 340.0
        blade = BladeDef(R=R, Rhub=Rhub, B=2, r=rr, chord=chord,
                         twist=np.full(Ns + 1, th))
        secs = naca_sections(rr, R, Omega, chord, mach_tip)
        results.append(run_case(f"MartinTung th{th:.0f}@{rpm}", blade, Omega, secs,
                                cte, cte, cqe, fme))

    # ---------------- Case 07: Harrington Rotor 1 ----------------
    R = 3.81
    rr = np.linspace(0.15, 1.0, Ns + 1)
    chord = np.full(Ns + 1, 0.457 / R)
    har_data = [(4.0, 240, 0.00192, 0.00017, 0.352), (6.0, 240, 0.00329, 0.00028, 0.474),
                (8.0, 240, 0.00478, 0.00041, 0.569), (10.0, 240, 0.00632, 0.00057, 0.622),
                (12.0, 240, 0.00781, 0.00078, 0.624)]
    for th, rpm, cte, cqe, fme in har_data:
        Omega = rpm * 2 * np.pi / 60
        mach_tip = Omega * R / 340.0
        blade = BladeDef(R=R, Rhub=0.45, B=2, r=rr, chord=chord,
                         twist=np.full(Ns + 1, th))
        secs = naca_sections(rr, R, Omega, chord, mach_tip)
        results.append(run_case(f"Harrington1 th{th:.0f}", blade, Omega, secs,
                                cte, cte, cqe, fme))

    with open("E:/旋翼设计/results/bench/matrix_results.json", "w") as f:
        json.dump(results, f, indent=1)
    print("\nsaved results/bench/matrix_results.json")


if __name__ == "__main__":
    main()
