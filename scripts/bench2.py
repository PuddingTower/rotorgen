"""Shared library for Phase-A benchmarking under the v2 explicit accounting.

Benchmarks: Caradonna-Tung (core), Martin-Tung 10in, Harrington R1, DJI 9443.
Primary acceptance metric (docs/FM075_PLAN.md A4): matched-thrust CQ error
  CQ_matched = CQ_solver * (CT_exp / CT_solver)^1.5
which is the only meaningful error measure for a trimmed design point.
"""
import sys, time, json
sys.path.insert(0, "E:/旋翼设计/src")
sys.path.insert(0, "E:/旋翼设计/scripts")
import numpy as np

from rotorgen.rotor3d import BladeDef, RotorSolver

# frozen wake tiers (rotor3d.py docstring, A5)
TIERS = {
    "fast":   dict(dpsi=10.0, n_rev=4.5, freeze=3.5, far=7.0),
    "hifi":   dict(dpsi=7.5, n_rev=6.0, freeze=5.0, far=12.0),
    "ultra":  dict(dpsi=5.0, n_rev=10.0, freeze=9.0, far=12.0),
}

ALPHA_TAB = np.arange(-8, 24.01, 0.5)
_foil_cache = {}


def naca_sections(rr, R, Omega, chord_R, mach_tip, digits="0012"):
    from rotorgen.airfoil import naca4
    from rotorgen.foil2d import Foil2D
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
    __slots__ = ("a", "cl", "cd")

    def __init__(self, tab):
        self.a, self.cl, self.cd = tab

    def cl_of(self, a):
        return float(np.interp(a, self.a, self.cl))

    def cd_of(self, a):
        return float(np.interp(a, self.a, self.cd))


def run_case(name, blade, Omega, sections, ct_exp, cq_exp, fm_exp,
             tier="ultra", phi=1.0, rho=1.225, n_outer=30, window=8,
             ct_guess=None, cd_factor=1.0):
    """One blind 3D case under the v2 accounting. Returns row dict.

    cd_factor: multiplies the 2D table Cd (design-accounting v2 uses 1.15 --
    our panel/BL chain reads 12-18% low vs experiment; benchmarks can run
    raw tables with cd_factor=1.0 to isolate the contribution)."""
    t = TIERS[tier]
    sol = RotorSolver(blade, Omega, rho=rho, dpsi_deg=t["dpsi"], n_rev=t["n_rev"],
                      rc0_frac=0.10)
    sol.freeze_rev = t["freeze"]
    sol.n_far_rev = t["far"]
    sol.relax_it = 1.3
    sol.gamma_relax = 0.35
    sol.inflow_scale = phi
    if cd_factor != 1.0:
        sections = [(a, cl, cd * cd_factor) for (a, cl, cd) in sections]
    sol.sections = [SecTab(s) for s in sections]
    if ct_guess is None:
        ct_guess = max(ct_exp, 1e-4)
    t0 = time.time()
    res = sol.solve(n_outer=n_outer, n_sweeps=4, ct_guess=ct_guess)
    dt = time.time() - t0
    h = np.array(res.history)
    w = min(window, len(h))
    ct = float(h[-w:, 0].mean())
    cq = float(h[-w:, 1].mean())
    fm = ct ** 1.5 / (np.sqrt(2) * cq) if cq > 0 else 0.0
    ld = sol._last_loads
    ct_err = 100 * (ct / ct_exp - 1) if ct_exp > 1e-9 else float('nan')
    cq_err = 100 * (cq / cq_exp - 1) if cq_exp > 1e-9 else float('nan')
    # matched-thrust torque error (trimmed design point metric)
    cq_m = cq * (ct_exp / ct) ** 1.5 if ct > 0 else float('nan')
    cqm_err = 100 * (cq_m / cq_exp - 1) if cq_exp > 1e-9 else float('nan')
    row = dict(case=name, tier=tier, phi=phi,
               CT=ct, CT_exp=ct_exp, CT_err=ct_err,
               CQ=cq, CQ_exp=cq_exp, CQ_err=cq_err,
               CQ_matched=cq_m, CQ_matched_err=cqm_err,
               FM=fm, FM_exp=fm_exp, t_s=round(dt, 1),
               P_swirl_frac=100 * ld["P_swirl"] / ld["power"] if ld["power"] else 0.0,
               P_ind_frac=ld["P_ind"] / ld["power"] if ld["power"] else 0.0)
    print(f"{name:26s} CT={ct:.5f} ({ct_err:+6.1f}%)  CQm={cqm_err:+6.1f}%  "
          f"CQ={cq:.6f} ({cq_err:+6.1f}%)  FM={fm:.3f}"
          f"/{'n/a' if fm_exp is None else format(fm_exp, '.3f')}  [{dt:.0f}s]",
          flush=True)
    return row


def ct_cases():
    """Caradonna-Tung hover matrix (R=1.143 m, NACA0012, sigma=0.106)."""
    R, Rhub = 1.143, 0.1143
    Ns = 24
    rr = np.linspace(Rhub / R, 1.0, Ns + 1)
    chord = np.full(Ns + 1, 0.1905 / R)
    data = [(5.0, 1250, 0.0021, 0.00018, 0.38),
            (5.0, 2050, 0.0028, 0.00025, 0.42),
            (8.0, 1250, 0.00459, 0.00036, 0.611),
            (8.0, 2050, 0.00461, 0.00039, 0.567),
            (12.0, 1250, 0.0079, 0.00078, 0.635),
            (12.0, 2050, 0.0067, 0.00085, 0.457)]
    out = []
    for th, rpm, cte, cqe, fme in data:
        Omega = rpm * 2 * np.pi / 60
        mach_tip = Omega * R / 340.0
        blade = BladeDef(R=R, Rhub=Rhub, B=2, r=rr, chord=chord,
                         twist=np.full(Ns + 1, th))
        out.append((f"CT th{th:.0f} @{rpm}", blade, Omega,
                    naca_sections(rr, R, Omega, chord, mach_tip),
                    dict(ct_exp=cte, cq_exp=cqe, fm_exp=fme)))
    return out


def mt_cases():
    """Martin-Tung 10in (R=0.127 m, NACA0012, sigma=0.191, low Re)."""
    R, Rhub = 0.127, 0.0254
    Ns = 24
    rr = np.linspace(Rhub / R, 1.0, Ns + 1)
    chord = np.full(Ns + 1, 0.0381 / R)
    data = [(6.0, 2500, 0.00318, 0.00049, 0.368),
            (6.0, 3500, 0.00319, 0.00049, 0.37),
            (8.0, 2500, 0.00464, 0.00073, 0.443),
            (8.0, 3500, 0.00465, 0.00074, 0.441),
            (10.0, 2500, 0.00605, 0.00102, 0.468),
            (12.0, 2500, 0.0073, 0.00137, 0.457)]
    out = []
    for th, rpm, cte, cqe, fme in data:
        Omega = rpm * 2 * np.pi / 60
        mach_tip = Omega * R / 340.0
        blade = BladeDef(R=R, Rhub=Rhub, B=2, r=rr, chord=chord,
                         twist=np.full(Ns + 1, th))
        out.append((f"MartinTung th{th:.0f}@{rpm}", blade, Omega,
                    naca_sections(rr, R, Omega, chord, mach_tip),
                    dict(ct_exp=cte, cq_exp=cqe, fm_exp=fme)))
    return out


def har_cases():
    """Harrington Rotor 1 (R=3.81 m, NACA0012, sigma=0.076, full scale)."""
    R = 3.81
    Ns = 24
    rr = np.linspace(0.15, 1.0, Ns + 1)
    chord = np.full(Ns + 1, 0.457 / R)
    data = [(4.0, 240, 0.00192, 0.00017, 0.352),
            (6.0, 240, 0.00329, 0.00028, 0.474),
            (8.0, 240, 0.00478, 0.00041, 0.569),
            (10.0, 240, 0.00632, 0.00057, 0.622),
            (12.0, 240, 0.00781, 0.00078, 0.624)]
    out = []
    for th, rpm, cte, cqe, fme in data:
        Omega = rpm * 2 * np.pi / 60
        mach_tip = Omega * R / 340.0
        blade = BladeDef(R=R, Rhub=0.45, B=2, r=rr, chord=chord,
                         twist=np.full(Ns + 1, th))
        out.append((f"Harrington1 th{th:.0f}", blade, Omega,
                    naca_sections(rr, R, Omega, chord, mach_tip),
                    dict(ct_exp=cte, cq_exp=cqe, fm_exp=fme)))
    return out


def dji_cases():
    """DJI Phantom 3 9450 plastic propeller -- UIUC static bench (A3 anchor).

    Replaces the plan's original 'DJI 9443' idea: the 9443-specific public data
    (Zawodny et al. / PoF 2020) is thrust-only, while Deters-Kleinke-Selig
    AIAA 2017-3743 gives the 9450 plastic (same DJI 9-inch class, 9443
    successor) with SELF-CONSISTENT laser-scanned geometry AND thrust+torque.
    Plan erratum: claimed 9443 'CT~0.02-0.03, same regime as design' matches
    neither CT convention (measured: 0.0134 PoF-style / 0.104 UIUC-style);
    the case anchors the low-Re cambered-blade regime instead.

    Geometry digitized from Fig. 7 (PropellerScanner; twist known to be
    underestimated by ~10-15%), true diameter 0.240 m, 2 blades.
    Static data digitized from Fig. 31 (CT0 = T/(rho n^2 D^4), n in rev/s;
    CP0 = P/(rho n^3 D^5)); CQ_exp = CP0/(2*pi).
    Section approximated as NACA 4412 (real sections unavailable; cambered
    plate class), t/c ~10-12%.
    """
    from rotorgen.airfoil import naca4
    from rotorgen.foil2d import Foil2D
    R, Rhub = 0.12, 0.012
    Ns = 20
    rr = np.linspace(Rhub / R, 1.0, Ns + 1)
    # chord c/R: digitized Fig. 7
    r_d = np.array([0.10, 0.15, 0.20, 0.25, 0.30, 0.40, 0.50, 0.60, 0.70,
                    0.80, 0.90, 0.95, 1.00])
    c_d = np.array([0.170, 0.220, 0.250, 0.260, 0.260, 0.230, 0.200, 0.165,
                    0.135, 0.115, 0.100, 0.080, 0.050])
    b_d = np.array([15.0, 17.0, 19.0, 19.0, 18.0, 16.0, 13.5, 12.0, 10.0,
                    9.0, 8.0, 7.5, 7.0])
    chord = np.interp(rr, r_d, c_d)
    twist = np.interp(rr, r_d, b_d)
    key = "4412"
    if key not in _foil_cache:
        _foil_cache[key] = Foil2D(naca4("4412", n_per_side=70), n_per_side=70)
    f = _foil_cache[key]
    # (rpm, CT0, CP0) digitized from Fig. 31 (UIUC definitions, n in rev/s:
    # CT0 = T/(rho n^2 D^4), CP0 = P/(rho n^3 D^5)). Converted to the solver
    # conventions (Omega-based): CT = T/(rho Om^2 pi R^4) = CT0*4/pi^3,
    # CQ = Q/(rho Om^2 pi R^5) = CP0*4/pi^4, FM = 2*CT0^1.5/(sqrt(2*pi)*CP0).
    u2s_ct = 4.0 / np.pi ** 3
    u2s_cq = 4.0 / np.pi ** 4
    data = [(2000, 0.089, 0.0425), (3000, 0.096, 0.0425), (4000, 0.099, 0.0422),
            (5000, 0.102, 0.0418), (6000, 0.1035, 0.0410), (7500, 0.102, 0.0395)]
    out = []
    for rpm, ct0, cp0 in data:
        n = rpm / 60.0
        Omega = 2 * np.pi * n
        cte = ct0 * u2s_ct
        cqe = cp0 * u2s_cq
        fme = 2.0 * ct0 ** 1.5 / np.sqrt(2 * np.pi) / cp0
        mach_tip = Omega * R / 340.0
        blade = BladeDef(R=R, Rhub=Rhub, B=2, r=rr, chord=chord, twist=twist)
        secs = []
        for i in range(len(rr) - 1):
            r_mid = 0.5 * (rr[i] + rr[i + 1]) * R
            c = 0.5 * (chord[i] + chord[i + 1]) * R
            U = Omega * r_mid
            Re = max(U * c / 1.8e-5, 3e4)
            M = min(mach_tip * r_mid / R, 0.5)
            rs = f.polar(ALPHA_TAB, Re=Re, M=M)
            secs.append((ALPHA_TAB, np.array([r.cl for r in rs]),
                         np.array([r.cd for r in rs])))
        out.append((f"DJI9450 @{rpm}", blade, Omega, secs,
                    dict(ct_exp=cte, cq_exp=cqe, fm_exp=fme)))
    return out
