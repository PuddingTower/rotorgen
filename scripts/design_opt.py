"""End-to-end design optimization: D=2.08m, B=2, T=200 kgf hover, 2mm TE, max FM.

Design vector x (7 vars):
  [Vt (tip speed m/s), twist_drop (deg, linear twist rate), taper,
   chord_scale, camber, tc_root, tc_tip]

Inner loop: collective trim (uniform pitch offset) -> thrust == T_target.
Outer loop: Nelder-Mead on shaft power at trimmed thrust (max FM equivalent).
3D evaluation: this project's free-wake solver (validated on C-T to CT+-6%/CQ+-9%).
Sections: this project's CST family (exact 2 mm TE) + panel/BL tables.
"""
import sys, time, json, os
sys.path.insert(0, "E:/旋翼设计/src")
import numpy as np

from rotorgen.rotor3d import BladeDef, RotorSolver
from rotorgen.famgen import AirfoilFamily
from rotorgen.foil2d import Foil2D
from rotorgen.airfoil import naca4

R = 1.04
B = 2
T_TARGET = 200 * 9.80665
RHO = 1.225
NS = 18
RR = np.linspace(0.16, 1.0, NS + 1)
ALPHA_TAB = np.arange(-6, 20.01, 0.5)

_foil_cache = {}


def get_foil(tc, camber, te_gap):
    key = (round(tc, 4), round(camber, 4), round(te_gap, 4))
    if key not in _foil_cache:
        if len(_foil_cache) > 60:
            _foil_cache.clear()
        from rotorgen.famgen import family_airfoil
        _foil_cache[key] = Foil2D(family_airfoil(tc, camber, te_gap, n_side=60),
                                  n_per_side=60)
    return _foil_cache[key]


class SecTab:
    __slots__ = ("a", "cl", "cd")

    def __init__(self, a, cl, cd):
        self.a, self.cl, self.cd = a, cl, cd

    def cl_of(self, x):
        return float(np.interp(x, self.a, self.cl))

    def cd_of(self, x):
        return float(np.interp(x, self.a, self.cd))


def build_design(x, trim_pitch):
    Vt, tw_drop, taper, cscale, camber, tc_r, tc_t = x
    Omega = Vt / R
    # chord: rounded-taper planform (rounded via sin law), scaled
    rbar = RR
    shape = 0.62 + 0.38 * np.sin(np.pi * np.clip((rbar - 0.10) / 0.90, 0, 1) ** 0.75)
    shape = shape / shape.max()
    shape = (1 - taper) * shape + taper * np.ones_like(shape)
    chord_R = cscale * shape / R          # c/R (meters/R)
    twist = trim_pitch + tw_drop * (0.75 - rbar) / 0.75
    return Omega, chord_R, twist, camber, tc_r, tc_t


def make_solver(x, trim_pitch, fast=True):
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
                               np.array([r.cd for r in rs])))
    blade = BladeDef(R=R, Rhub=0.1664, B=B, r=RR, chord=chord_R, twist=twist)
    sol = RotorSolver(blade, Omega, rho=RHO,
                      dpsi_deg=10.0 if fast else 7.5,
                      n_rev=4.5 if fast else 6.0, rc0_frac=0.10)
    sol.freeze_rev = 3.5 if fast else 5.0
    sol.n_far_rev = 7.0
    sol.relax_it = 1.3
    sol.gamma_relax = 0.35
    sol.inflow_scale = 1.3
    sol.sections = sections
    return sol


def eval_thrust(x, trim_pitch):
    sol = make_solver(x, trim_pitch)
    res = sol.solve(n_outer=22 if trim_pitch > 2 else 14, n_sweeps=4,
                    ct_guess=max(T_TARGET / (RHO * np.pi * R ** 2 * (x[0]) ** 2), 1e-4))
    h = np.array(res.history)
    ct = float(h[-6:, 0].mean())
    T = ct * RHO * np.pi * R ** 2 * x[0] ** 2
    q = RHO * (x[0]) ** 2 * np.pi * R ** 2
    cq = float(h[-6:, 1].mean())
    # P = CQ * rho * Vt^3 * pi * R^2 = CQ * q * Vt  (fixed 2026-10-25; a leftover
    # "/R" from the pre-fix CQ convention understated power by 4.3%)
    P = cq * q * x[0]
    return T, P, sol


def trim_and_power(x, tol=0.03, iters=6):
    """Coarse pitch scan then bisect: thrust == target. Returns power."""
    # coarse scan for bracket (4 points)
    pts = []
    for p in (8.0, 12.0, 15.0, 18.0):
        T, P, _ = eval_thrust(x, p)
        pts.append((p, T, P))
        if T >= T_TARGET:
            break
    if len(pts) == 1 or pts[0][1] >= T_TARGET:
        return None
    if pts[-1][1] < T_TARGET:
        return None
    lo = pts[-2]
    hi = pts[-1]
    T, P = lo[1], lo[2]
    for _ in range(iters):
        mid = 0.5 * (lo[0] + hi[0])
        T, P, _ = eval_thrust(x, mid)
        if abs(T - T_TARGET) < tol * T_TARGET:
            return P
        if T < T_TARGET:
            lo = (mid, T, P)
        else:
            hi = (mid, T, P)
    # accept nearest
    cands = [c for c in (lo, hi) if abs(c[1] - T_TARGET) < 0.10 * T_TARGET]
    if not cands:
        return None
    return min(cands, key=lambda c: abs(c[1] - T_TARGET))[2]


_best = {"P": 1e12, "x": None, "n": 0}


def objective(x):
    x = np.asarray(x, dtype=float)
    Vt, tw_drop, taper, cscale, camber, tc_r, tc_t = x
    # bounds penalties
    pen = 0.0
    if not (95 <= Vt <= 158):
        return 1e6
    if not (0 <= tw_drop <= 22):
        return 1e6
    if not (0.0 <= taper <= 1.0):
        return 1e6
    if not (0.13 <= cscale <= 0.345):
        return 1e6
    if not (0.010 <= camber <= 0.045):
        return 1e6
    if not (0.10 <= tc_r <= 0.18) or not (0.08 <= tc_t <= 0.13):
        return 1e6
    if tc_t > tc_r:
        return 1e6
    t0 = time.time()
    P = trim_and_power(x)
    _best["n"] += 1
    if P is None:
        print(f"[{_best['n']:3d}] x={np.round(x,3)} INFEASIBLE", flush=True)
        return 1e6
    if P < _best["P"]:
        _best["P"] = P
        _best["x"] = x.copy()
        print(f"[{_best['n']:3d}] P={P:.0f} W  FM={T_TARGET**1.5/np.sqrt(2*RHO*np.pi*R**2)/P:.3f}  x={np.round(x,3)}  [{time.time()-t0:.0f}s]", flush=True)
    else:
        print(f"[{_best['n']:3d}] P={P:.0f} W  x={np.round(x,3)}  [{time.time()-t0:.0f}s]", flush=True)
    return P


def main():
    from scipy.optimize import minimize
    x0 = np.array([156.0, 13.0, 0.25, 0.32, 0.030, 0.15, 0.10])
    res = minimize(objective, x0, method="Nelder-Mead",
                   options=dict(maxiter=140, xatol=0.02, fatol=50.0, adaptive=True))
    print("OPT DONE", res.x, res.fun)
    with open("E:/旋翼设计/results/final/opt_result.json", "w") as f:
        json.dump(dict(x=list(map(float, res.x)), P=float(res.fun),
                       best_x=list(map(float, _best["x"])), best_P=float(_best["P"]),
                       n_evals=_best["n"]), f, indent=1)


if __name__ == "__main__":
    main()
