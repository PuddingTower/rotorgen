"""Heavy reproduction runs: A4 matrix spot-check + delivered blade + unit-route test."""
import sys, json, time
sys.path.insert(0, "E:/旋翼设计/src")
sys.path.insert(0, "E:/旋翼设计/scripts")
import numpy as np

OUT = {}

# ================================================================ B2: C-T th8@1250 ultra
import bench2
from bench2 import run_case, ct_cases

t0 = time.time()
name, blade, Omega, secs, exp = next(
    c for c in ct_cases() if c[0] == "CT th8 @1250")
# run with capture: need solver internals -> replicate run_case manually
t = bench2.TIERS["ultra"]
from rotorgen.rotor3d import RotorSolver
from bench2 import SecTab
sol = RotorSolver(blade, Omega, rho=1.225, dpsi_deg=t["dpsi"], n_rev=t["n_rev"],
                  rc0_frac=0.10)
sol.freeze_rev = t["freeze"]; sol.n_far_rev = t["far"]
sol.relax_it = 1.3; sol.gamma_relax = 0.35; sol.inflow_scale = 1.2
secs15 = [(a, cl, cd * 1.15) for (a, cl, cd) in secs]
sol.sections = [SecTab(s) for s in secs15]
res = sol.solve(n_outer=30, n_sweeps=4, ct_guess=exp["ct_exp"])
h = np.array(res.history)
w = min(8, len(h))
ct = float(h[-w:, 0].mean()); cq = float(h[-w:, 1].mean())
ld = sol._last_loads
OUT["ct8_case"] = dict(
    CT=ct, CQ=cq, CT_ref=0.004754, CQ_ref=0.000377,   # matrix json values
    CT_err=100 * (ct / exp["ct_exp"] - 1),
    CQm_err=100 * ((cq * (exp["ct_exp"] / ct) ** 1.5) / exp["cq_exp"] - 1),
    P_watts=ld["power"], t_s=round(time.time() - t0, 1),
    P_ind_frac=ld["P_ind"] / ld["power"])
print("CT th8@1250 rerun:", OUT["ct8_case"], flush=True)

# wake capture: filament radius vs age, tip filament; blade loading
Xw = sol.Xw.copy()
R_ = blade.R
tip_r = np.hypot(Xw[-1, :, 0], Xw[-1, :, 1]) / R_
tip_z = Xw[-1, :, 2] / R_
ages_deg = np.arange(Xw.shape[1]) * np.rad2deg(sol.dpsi)
# bound circulation distribution
gam = sol.Gamma.copy()
r_mid = 0.5 * (blade.r[:-1] + blade.r[1:])
alpha_span = sol._last_alpha.copy()
np.savez("E:/旋翼设计/results/verif_ct8.npz",
         hist=h, tip_r=tip_r, tip_z=tip_z, ages=ages_deg, gam=gam,
         r_mid=r_mid, alpha=alpha_span,
         wake_xyz=Xw[[len(Xw)//4, -1]],           # mid + tip filaments
         vortex_age180_r=0.905, vortex_age180_z=0.09)

# ================================================================ B1: delivered blade
from diag_fm075 import make_solver_cfg, T_TARGET, RHO, R
from design_opt import NS, RR
X = np.array(json.load(open("E:/旋翼设计/results/final/performance.json"))["design_vector"])
dg = json.load(open("E:/旋翼设计/results/diag_fm075_v2_phi1.20_cd1.15.json"))[0]

t0 = time.time()
sol2 = make_solver_cfg(X, 16.926001022107584, 7.5, 6.0, 5.0, 12.0, phi=1.2, cdf=1.15)
res2 = sol2.solve(n_outer=26, n_sweeps=4,
                  ct_guess=max(T_TARGET / (RHO * np.pi * R ** 2 * X[0] ** 2), 1e-4))
h2 = np.array(res2.history)
ct2 = float(h2[-6:, 0].mean()); cq2 = float(h2[-6:, 1].mean())
ld2 = sol2._last_loads
Vt = X[0]
q = RHO * Vt ** 2 * np.pi * R ** 2
P_correct = cq2 * q * Vt          # correct unit route = what eval_thrust uses
P_logstyle = cq2 * q * Vt / R     # OLD /R route: pre-2026-10-25 log FM readouts
                                  # were 1.04x too high (P understated) -- kept so
                                  # historical logs can be de-contaminated
OUT["delivered"] = dict(
    T=ct2 * q, T_ref=dg["T"],
    P_watts=ld2["power"], P_watts_ref=dg["P_axial"] + dg["P_swirl"] + dg["P_prof"],
    P_coeff_correct=P_correct, P_coeff_script=P_logstyle,
    ratio_watts_over_correct=ld2["power"] / P_correct,
    ratio_watts_over_logstyle=ld2["power"] / P_logstyle,
    P_axial=ld2["P_axial"], P_axial_ref=dg["P_axial"],
    P_swirl=ld2["P_swirl"], P_prof=ld2["P_prof"], P_prof_ref=dg["P_prof"],
    vi_disk=ld2["vi_disk"], vi_disk_ref=dg["vi_disk"],
    t_s=round(time.time() - t0, 1))
print("delivered rerun:", OUT["delivered"], flush=True)
np.savez("E:/旋翼设计/results/verif_deliv.npz", hist=h2,
         gam=sol2.Gamma.copy(),
         r_mid=0.5 * (RR[:-1] + RR[1:]),
         alpha=sol2._last_alpha.copy(),
         wake_tip=sol2.Xw[-1].copy())

json.dump(OUT, open("E:/旋翼设计/results/verif_heavy.json", "w"), indent=1, default=float)
print("saved results/verif_heavy.json", flush=True)
