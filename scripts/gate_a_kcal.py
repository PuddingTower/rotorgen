"""Gate A: kappa_cal calibration on the fixed-convention A4 matrix.

CQm_err(kappa) = (kappa*P_ind_matched + P_prof_matched)/P_exp - 1, affine in
kappa (P_ind_matched = P_ind_frac*CQ_matched*q5*Omega etc.). Uses each row's
recorded P_ind_frac to convert exactly. Optimal kappa minimizes max |err|
over the chosen case set; FM ladder for the delivered blade reported at
kappa = 1.0 / 1.1 / 1.15 / 1.18.
"""
import sys, json
sys.path.insert(0, "E:/旋翼设计/src")
sys.path.insert(0, "E:/旋翼设计/scripts")
import numpy as np

path = sys.argv[1] if len(sys.argv) > 1 else \
    "E:/旋翼设计/results/bench/matrix_v2_ultra_phi1.20_cd1.15.json"
d = json.load(open(path))
rows = d["rows"]

core = [r for r in rows if r["family"] == "ct"
        and (r["case"].startswith("CT th8") or r["case"].startswith("CT th12"))
        and "2050" not in r["case"]]
print("core set (fixed conventions):")
for r in core:
    print(f"  {r['case']:16s} CT_err={r['CT_err']:+6.1f}%  CQm={r['CQ_matched_err']:+6.1f}%"
          f"  P_ind_frac={r['P_ind_frac']:.3f}")

# CQm_err(kappa) = (kappa - kappa0) * P_ind_frac/(1) ... derive: at kappa=1 the
# matched error is e1 = CQ_matched_err/100. Power share of induced at the
# matched point ~ P_ind_frac. d(err)/d(kappa) = P_ind_frac (as fraction).
print("\nkappa scan (core max|CQm_err|):")
best = None
for k in np.arange(1.0, 1.30, 0.005):
    errs = [(k - 1.0) * 100.0 * r["P_ind_frac"] * (1.0 + r["CQ_matched_err"] / 100.0)
            + r["CQ_matched_err"] for r in core]
    mx = max(abs(e) for e in errs)
    if best is None or mx < best[1]:
        best = (float(k), float(mx))
    if abs(k * 100 - round(k * 100)) < 1e-6 and round(k * 100) % 5 == 0:
        print(f"  kappa={k:.2f}  errs={['%+.1f' % e for e in errs]}  max={mx:.1f}%")
print(f"\nOPTIMAL kappa_cal = {best[0]:.3f}  (max |CQm_err| = {best[1]:.1f}%)")

# FM ladder for the delivered blade under the design accounting
# (from results/diag_fm075_v2_phi1.20_cd1.15.json: T=1976 N, hi-fi tier)
try:
    dg = json.load(open("E:/旋翼设计/results/diag_fm075_v2_phi1.20_cd1.15.json"))[0]
    P_ax, P_sw, P_pr = dg["P_axial"], dg["P_swirl"], dg["P_prof"]
    P_ideal = dg["P_ideal"]
    print("\nDelivered-blade FM ladder (design accounting, hi-fi):")
    for k in (1.0, 1.05, 1.1, 1.15, 1.18, 1.2):
        P = (P_ax + P_sw) * k + P_pr
        print(f"  kappa={k:.2f}: FM = {P_ideal / P:.4f}")
except Exception as e:
    print("FM ladder skipped:", e)
