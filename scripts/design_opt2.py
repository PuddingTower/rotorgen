"""Phase B: expanded parameterization for the 0.75-FM redesign (docs/FM075_PLAN.md).

Design vector x (17 vars):
  x[0]      tip speed Vt [m/s], box [95, 176] (M_tip <= 0.52)
  x[1]      twist root angle rel. 0.75R (deg), box [-2, 20]
  x[2:7]    five monotone twist drops (deg), box [0, 8] each ->
            control angles rel. 0.75R at r=[0.16,0.32,0.50,0.68,0.85,1.00] (non-increasing)
  x[7:12]   chord control points (c/R), box [0.06, 0.34], at
            r=[0.16,0.35,0.55,0.78,1.00] (PCHIP interpolation)
  x[12:15]  camber at r=[0.16,0.55,1.00], box [0.0, 0.05], linear interp
  x[15]     t/c root, box [0.12, 0.18]
  x[16]     t/c tip,  box [0.08, 0.13], <= t/c root
Trim: uniform collective pitch offset added to the twist spline (as before).
Hard constraints unchanged: 2 mm TE, stall Cl <= 0.85 Cl_max (penalty),
M_tip <= 0.52. Polar results cached per (section, Re, M) -- Phase C target
cache hit rate > 80%.
"""
import sys, time, json, hashlib
sys.path.insert(0, "E:/旋翼设计/src")
sys.path.insert(0, "E:/旋翼设计/scripts")
import numpy as np
from scipy.interpolate import PchipInterpolator

from rotorgen.rotor3d import BladeDef, RotorSolver
from rotorgen.famgen import AirfoilFamily
from rotorgen.foil2d import Foil2D

R = 1.04
B = 2
T_TARGET = 200 * 9.80665
RHO = 1.225
NS = 18
RR = np.linspace(0.16, 1.0, NS + 1)
ALPHA_TAB = np.arange(-6, 20.01, 0.5)

R_TW = np.array([0.16, 0.32, 0.50, 0.68, 0.85, 1.00])
R_CH = np.array([0.16, 0.35, 0.55, 0.78, 1.00])
R_CB = np.array([0.16, 0.55, 1.00])

CD_FACTOR = 1.15          # Phase C hard correction: our chain Cd reads 12-18% low

_foil_cache = {}
_polar_cache = {}
_cache_stats = {"hits": 0, "miss": 0}


def get_foil(tc, camber, te_gap):
    key = (round(tc, 4), round(camber, 4), round(te_gap, 4))
    if key not in _foil_cache:
        if len(_foil_cache) > 80:
            _foil_cache.clear()
        from rotorgen.famgen import family_airfoil
        _foil_cache[key] = Foil2D(family_airfoil(tc, camber, te_gap, n_side=60),
                                  n_per_side=60)
    return _foil_cache[key]


def station_polar(tc, camber, te_gap, Re, M):
    """Cached Cl/Cd table for one (section, Re, M). Re 3 sig digits, M 2 dec."""
    re_k = float(f"{Re:.3g}")
    key = (round(tc, 3), round(camber, 4), round(te_gap, 4), re_k, round(M, 2))
    if key in _polar_cache:
        _cache_stats["hits"] += 1
        return _polar_cache[key]
    _cache_stats["miss"] += 1
    if len(_polar_cache) > 4000:
        _polar_cache.clear()
    f = get_foil(tc, camber, te_gap)
    rs = f.polar(ALPHA_TAB, Re=max(Re, 6e4), M=M)
    tab = (np.array([r.cl for r in rs]) * 1.0,
           np.array([r.cd for r in rs]) * CD_FACTOR,
           float(np.max([r.cl for r in rs])))
    _polar_cache[key] = tab
    return tab


class SecTab:
    __slots__ = ("a", "cl", "cd", "cl_max")

    def __init__(self, a, cl, cd, cl_max):
        self.a, self.cl, self.cd, self.cl_max = a, cl, cd, cl_max

    def cl_of(self, x):
        return float(np.interp(x, self.a, self.cl))

    def cd_of(self, x):
        return float(np.interp(x, self.a, self.cd))


def decode(x):
    """Map raw design vector to physical parameters."""
    x = np.asarray(x, dtype=float)
    Vt = x[0]
    tw_root = x[1]
    drops = np.clip(x[2:7], 0.0, None)
    tw_ctrl = tw_root - np.concatenate([[0.0], np.cumsum(drops)])
    ch_ctrl = x[7:12]
    cb_ctrl = x[12:15]
    tc_r, tc_t = x[15], x[16]
    return Vt, tw_ctrl, ch_ctrl, cb_ctrl, tc_r, tc_t


def build_design(x, trim_pitch):
    """Twist spline is relative to 0.75R (there trim_pitch acts as the pure
    collective, same semantics as v1); root/tip absolute angles are then
    trim_pitch + spline value."""
    Vt, tw_ctrl, ch_ctrl, cb_ctrl, tc_r, tc_t = decode(x)
    Omega = Vt / R
    twist_spl = PchipInterpolator(R_TW, tw_ctrl)
    chord_spl = PchipInterpolator(R_CH, ch_ctrl)
    camber_spl = PchipInterpolator(R_CB, cb_ctrl)
    twist = trim_pitch + twist_spl(RR) - float(twist_spl(0.75))
    chord_R = np.clip(chord_spl(RR), 0.02, None)
    camber = lambda r: float(np.clip(camber_spl(r), 0.0, 0.06))  # noqa: E731
    return Omega, chord_R, twist, camber, tc_r, tc_t


def make_sections(Omega, chord_R, camber, tc_r, tc_t):
    fam = AirfoilFamily(R=R, tc_root=tc_r, tc_tip=tc_t, camber=camber(0.5),
                        t_te_phys=0.002)
    sections = []
    mach_tip = min(Omega * R / 340.0, 0.58)
    for i in range(NS):
        r_mid = 0.5 * (RR[i] + RR[i + 1])
        c_m = 0.5 * (chord_R[i] + chord_R[i + 1]) * R
        tc = fam.tc_at(r_mid)
        te_gap = fam.te_gap_at(c_m)
        U = Omega * r_mid * R
        Re = max(RHO * U * c_m / 1.8e-5, 6e4)
        M = min(mach_tip * r_mid, 0.55)
        cl, cd, cl_max = station_polar(tc, camber(r_mid), te_gap, Re, M)
        sections.append(SecTab(ALPHA_TAB, cl, cd, cl_max))
    return sections


def make_solver(x, trim_pitch, tier="fast"):
    from bench2 import TIERS
    Omega, chord_R, twist, camber, tc_r, tc_t = build_design(x, trim_pitch)
    sections = make_sections(Omega, chord_R, camber, tc_r, tc_t)
    t = TIERS[tier]
    blade = BladeDef(R=R, Rhub=0.1664, B=B, r=RR, chord=chord_R, twist=twist)
    sol = RotorSolver(blade, Omega, rho=RHO, dpsi_deg=t["dpsi"], n_rev=t["n_rev"],
                      rc0_frac=0.10)
    sol.freeze_rev = t["freeze"]
    sol.n_far_rev = t["far"]
    sol.relax_it = 1.3
    sol.gamma_relax = 0.35
    sol.inflow_scale = 1.2     # A2-calibrated station-inflow factor (phi_cal)
    sol.kappa_cal = 1.20       # Gate A calibration (core-optimal 1.22, stop-loss
                               # boundary 1.18; max core residual 6.0% at 1.20)
    sol.sections = sections
    return sol


def eval_thrust(x, trim_pitch, tier="fast"):
    sol = make_solver(x, trim_pitch, tier)
    res = sol.solve(n_outer=22 if tier == "fast" else 26, n_sweeps=4,
                    ct_guess=max(T_TARGET / (RHO * np.pi * R ** 2 * x[0] ** 2), 1e-4))
    h = np.array(res.history)
    w = min(6, len(h))
    ct = float(h[-w:, 0].mean())
    T = ct * RHO * np.pi * R ** 2 * x[0] ** 2
    q = RHO * x[0] ** 2 * np.pi * R ** 2
    cq = float(h[-w:, 1].mean())
    # P = CQ * rho * Vt^3 * pi * R^2 = CQ * q * Vt  (fixed 2026-10-25; a leftover
    # "/R" from the pre-fix CQ convention understated power by 4.3%)
    P = cq * q * x[0]
    return T, P, sol


def check_constraints(x, sol):
    """Return list of violated constraint strings (empty = feasible)."""
    Vt, _, _, _, tc_r, tc_t = decode(x)
    bad = []
    if Vt / 340.0 > 0.52 + 1e-9:
        bad.append("M_tip>0.52")
    if tc_r < 0.12 - 1e-9:
        bad.append("tc_root<12%")
    # stall margin: any station running above 0.85*Cl_max
    if sol is not None and getattr(sol, "_last_alpha", None) is not None:
        for i, sec in enumerate(sol.sections):
            a = sol._last_alpha[i]
            if sec.cl_of(a) > 0.85 * sec.cl_max + 1e-9:
                bad.append(f"stall@st{i}")
                break
    return bad


def trim_and_power(x, tier="fast", tol=0.03, iters=6):
    """Coarse pitch scan then bisect: thrust == target. Returns (P, sol, pitch)."""
    pts = []
    for p in (8.0, 12.0, 15.0, 18.0):
        T, P, sol = eval_thrust(x, p, tier)
        pts.append((p, T, P, sol))
        if T >= T_TARGET:
            break
    if len(pts) == 1 or pts[0][1] >= T_TARGET:
        return None, None, None
    if pts[-1][1] < T_TARGET:
        return None, None, None
    lo, hi = pts[-2], pts[-1]
    best = (abs(lo[1] - T_TARGET), lo)
    for _ in range(iters):
        mid = 0.5 * (lo[0] + hi[0])
        T, P, sol = eval_thrust(x, mid, tier)
        cur = (mid, T, P, sol)
        if abs(T - T_TARGET) < best[0]:
            best = (abs(T - T_TARGET), cur)
        if abs(T - T_TARGET) < tol * T_TARGET:
            return P, sol, mid
        if T < T_TARGET:
            lo = cur
        else:
            hi = cur
    return best[1][2], best[1][3], best[1][0]


BOUNDS_LO = np.array([95, -2, 0, 0, 0, 0, 0, 0.06, 0.06, 0.06, 0.06, 0.06,
                      0.0, 0.0, 0.0, 0.12, 0.08])
BOUNDS_HI = np.array([176, 20, 8, 8, 8, 8, 8, 0.34, 0.34, 0.34, 0.34, 0.34,
                      0.05, 0.05, 0.05, 0.18, 0.13])
# seed ≈ delivered v1 design (linear twist 14.7 deg drop, sin-shaped chord),
# expressed in the v2 relative-to-0.75R parameterization
X0 = np.array([156.0,
               11.56, 3.13, 3.53, 3.53, 3.07, 3.20,    # +11.6@root -> -4.9@tip
               0.22, 0.30, 0.29, 0.26, 0.21,           # chord c/R controls
               0.030, 0.030, 0.030,                    # camber uniform
               0.15, 0.10])


def objective(x, tier="fast", verbose=True):
    x = np.asarray(x, dtype=float)
    if np.any(x < BOUNDS_LO - 1e-9) or np.any(x > BOUNDS_HI + 1e-9):
        return 1e6
    t0 = time.time()
    P, sol, pitch = trim_and_power(x, tier)
    if P is None:
        if verbose:
            print(f"  INFEASIBLE (no trim bracket) x={np.round(x, 3)}", flush=True)
        return 1e6
    bad = check_constraints(x, sol)
    if bad:
        if verbose:
            print(f"  INFEASIBLE {bad} x={np.round(x, 3)}", flush=True)
        return 1e6
    fm = T_TARGET ** 1.5 / np.sqrt(2 * RHO * np.pi * R ** 2) / P
    if verbose:
        print(f"  P={P:.0f} W FM={fm:.4f} pitch={pitch:.2f} "
              f"[{time.time()-t0:.0f}s] x={np.round(x, 3)}", flush=True)
    return P


if __name__ == "__main__":
    # smoke test: evaluate the seed vector end-to-end
    _cache_stats.update(hits=0, miss=0)
    t0 = time.time()
    P, sol, pitch = trim_and_power(X0, "fast")
    fm = T_TARGET ** 1.5 / np.sqrt(2 * RHO * np.pi * R ** 2) / P
    print(f"SEED: P={P:.0f} W FM={fm:.4f} pitch={pitch:.2f} "
          f"wall={time.time()-t0:.0f}s")
    print(f"polar cache: hits={_cache_stats['hits']} miss={_cache_stats['miss']} "
          f"rate={_cache_stats['hits']/max(1,_cache_stats['hits']+_cache_stats['miss']):.0%}")
    print("constraints:", check_constraints(X0, sol))
