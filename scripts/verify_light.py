"""Verification light checks (independent recomputation). Writes JSON + prints."""
import sys, json
sys.path.insert(0, "E:/旋翼设计/src")
sys.path.insert(0, "E:/旋翼设计/scripts")
import numpy as np

out = {}

# ---------------------------------------------------------------- 1. kernels
from rotorgen.kernels3d import velocity_at_points

def vel(segs, gam, rc2, pts):
    v = np.zeros_like(pts)
    velocity_at_points(np.ascontiguousarray(segs), np.ascontiguousarray(gam),
                       np.ascontiguousarray(rc2), np.ascontiguousarray(pts), v)
    return v

# (a) semi-infinite filament along +z, evaluate at distance d
n = 4000
nodes = np.zeros((n, 3)); nodes[:, 2] = np.linspace(0, 4000, n)
segs = np.concatenate([nodes[:-1], nodes[1:]], axis=1)
G = 1.7
gam = np.full(len(segs), G / n * 4000)  # uniform density -> total circulation G
rc2 = np.full(len(segs), 1e-16)
d = 2.5
p = np.array([[d, 0.0, 1234.0]])
v = vel(segs, gam, rc2, p)[0]
out['filament'] = dict(num=float(np.hypot(*v[:2])), exact=G / (2 * np.pi * d))

# (b) finite segment, no core: analytic v = G/(4 pi d) (cos t1 - cos t2)
p1, p2 = np.array([0.0, 0, 0]), np.array([0.0, 0, 3.0])
segs2 = np.array([[*p1, *p2]])
gam2 = np.array([G]); rc2b = np.array([1e-16])
pt = np.array([[d, 0.0, 1.5]])
vb = vel(segs2, gam2, rc2b, pt)[0]
r1 = np.linalg.norm(pt[0] - p1); r2 = np.linalg.norm(pt[0] - p2)
c1 = (pt[0, 2] - p1[2]) / r1; c2 = (pt[0, 2] - p2[2]) / r2
exact_b = G / (4 * np.pi * d) * (c1 - c2)
out['segment'] = dict(num=float(np.hypot(*vb[:2])), exact=float(exact_b))

# (c) vortex ring on-axis (rc->0 limit): v = G R^2 / (2 (R^2+z^2)^1.5)
m = 2000
th = np.linspace(0, 2 * np.pi * 30, m + 1)
Rr = 1.3
ring = np.stack([Rr * np.cos(th), Rr * np.sin(th), np.zeros_like(th)], axis=1)
segs3 = np.concatenate([ring[:-1], ring[1:]], axis=1)
gam3 = np.full(len(segs3), G / m * 30 * 30 / 30 * (30 / (m / m)) if False else G * 30 / m)
rc2c = np.full(len(segs3), 1e-16)
pt3 = np.array([[0.0, 0.0, 0.7]])
vc = vel(segs3, gam3, rc2c, pt3)[0]
exact_c = G * Rr**2 / (2 * (Rr**2 + 0.7**2)**1.5)
out['ring'] = dict(num=float(vc[2]), exact=float(exact_c))

# ---------------------------------------------------------------- 2. FM / CQ identity
rng = np.random.default_rng(0)
ids = []
for _ in range(5):
    R = rng.uniform(0.1, 4.0); Om = rng.uniform(20, 300); rho = 1.225
    T = rng.uniform(50, 5e4); P = rng.uniform(1e3, 2e5)
    q_ct = rho * (Om * R) ** 2 * np.pi * R ** 2
    CT = T / q_ct; CQ = P / Om / (q_ct * R)
    fm_coef = CT ** 1.5 / (np.sqrt(2) * CQ)
    fm_dir = T ** 1.5 / np.sqrt(2 * rho * np.pi * R ** 2) / P
    ids.append(abs(fm_coef / fm_dir - 1))
out['fm_identity_maxrel'] = float(max(ids))

# UIUC -> solver conversion identities
ct0, cp0 = 0.104, 0.040
D = 0.240; Rr = D / 2; n_ = 100.0; Om = 2 * np.pi * n_
T_ = ct0 * 1.225 * n_ ** 2 * D ** 4
P_ = cp0 * 1.225 * n_ ** 3 * D ** 5
CTs = T_ / (1.225 * Om ** 2 * np.pi * Rr ** 4)
CQs = (P_ / Om) / (1.225 * Om ** 2 * np.pi * Rr ** 5)
out['uiuc'] = dict(CT_ratio=float(CTs / (ct0 * 4 / np.pi**3)),
                   CQ_ratio=float(CQs / (cp0 * 4 / np.pi**4)),
                   FM_direct=float(T_**1.5/np.sqrt(2*1.225*np.pi*Rr**2)/P_),
                   FM_formula=float(2*ct0**1.5/np.sqrt(2*np.pi)/cp0))

# ---------------------------------------------------------------- 3. 2D NACA0012
from rotorgen.airfoil import naca0012
from rotorgen.foil2d import Foil2D

f = Foil2D(naca0012(n_per_side=140), n_per_side=140)
Re = 6e6
alphas = np.arange(-4, 16.01, 1.0)
res = [f.analyze(float(a), Re, 0.0) for a in alphas]
cl = np.array([r.cl for r in res]); cd = np.array([r.cd for r in res])
cl_inv = np.array([r.cl_inv for r in res])
slope = np.polyfit(alphas[(alphas >= 0) & (alphas <= 5)], cl[(alphas >= 0) & (alphas <= 5)], 1)[0]
out['naca0012'] = dict(
    cl_alpha=float(slope), cl_alpha_exp=0.109,
    cl0=float(cl[alphas == 0][0]),
    cd_min=float(cd.min()), cd_at0=float(cd[alphas == 0][0]),
    cd_exp_range=[0.0058, 0.0065],
    cp_min_0=float((1 - f.ps.surface_velocity(0.0) ** 2).min()),
    cp_min_5=float((1 - f.ps.surface_velocity(5.0) ** 2).min()),
    cp_min_exp=[-0.42, -2.0],
    cl_16=float(cl[-1]),
)
# store curves for figures
np.savez("E:/旋翼设计/results/verif_2d.npz", alphas=alphas, cl=cl, cd=cd, cl_inv=cl_inv,
         xmid=f.x_mid, cp0=1 - f.ps.surface_velocity(0.0) ** 2,
         cp5=1 - f.ps.surface_velocity(5.0) ** 2)

# ---------------------------------------------------------------- 4. bench exp values vs CSV
import csv
rows = list(csv.DictReader(open(
    "E:/旋翼设计/benchmarks/rotor-propeller-benchmarks/05_经典悬停模型旋翼_Caradonna_Tung/experiment/caradonna_tung_hover_performance.csv")))
ct_csv = {(float(r["collective_deg"]), float(r["RPM"])):
          (float(r["CT_rotor"]), float(r["CQ_rotor"]), float(r["Figure_of_Merit"])) for r in rows}
bench2_ct = [(5.0,1250,0.0021,0.00018,0.38),(5.0,2050,0.0028,0.00025,0.42),
             (8.0,1250,0.00459,0.00036,0.611),(8.0,2050,0.00461,0.00039,0.567),
             (12.0,1250,0.0079,0.00078,0.635),(12.0,2050,0.0067,0.00085,0.457)]
mx = 0.0
for th, rpm, cte, cqe, fme in bench2_ct:
    c2 = ct_csv[(th, rpm)]
    mx = max(mx, abs(cte - c2[0]), abs(cqe - c2[1]), abs(fme - c2[2]))
out['ct_csv_match_maxabs'] = float(mx)

# Martin-Tung CSV vs bench2 hardcoded
try:
    rows = list(csv.DictReader(open(
        "E:/旋翼设计/benchmarks/rotor-propeller-benchmarks/03_微型孤立旋翼_MartinTung_10in/experiment/martin_tung_10in_hover_exp.csv")))
    out['mt_csv_sample'] = rows[:3]
except Exception as e:
    out['mt_csv_sample'] = str(e)

# ---------------------------------------------------------------- 5. kappa scan + FM ladder
d = json.load(open("E:/旋翼设计/results/bench/matrix_v2_ultra_phi1.20_cd1.15.json"))
core = [r for r in d["rows"] if r["family"] == "ct"
        and (r["case"].startswith("CT th8") or r["case"].startswith("CT th12"))
        and "2050" not in r["case"]]
ks = np.arange(1.0, 1.30, 0.001)
mx_err = []
for k in ks:
    errs = [(k - 1.0) * 100.0 * r["P_ind_frac"] * (1.0 + r["CQ_matched_err"] / 100.0)
            + r["CQ_matched_err"] for r in core]
    mx_err.append(max(abs(e) for e in errs))
mx_err = np.array(mx_err)
i = int(np.argmin(mx_err))
out['kappa_scan'] = dict(k_opt=float(ks[i]), maxerr_opt=float(mx_err[i]),
                         err118=float(mx_err[np.argmin(abs(ks - 1.18))]),
                         err115=float(mx_err[np.argmin(abs(ks - 1.15))]),
                         err120=float(mx_err[np.argmin(abs(ks - 1.20))]),
                         err122=float(mx_err[np.argmin(abs(ks - 1.22))]))
np.savez("E:/旋翼设计/results/verif_kappa.npz", ks=ks, mx_err=mx_err,
         core_names=[r["case"] for r in core],
         core_cqm=np.array([r["CQ_matched_err"] for r in core]),
         core_ct=np.array([r["CT_err"] for r in core]),
         core_pind=np.array([r["P_ind_frac"] for r in core]))

dg = json.load(open("E:/旋翼设计/results/diag_fm075_v2_phi1.20_cd1.15.json"))[0]
kgrid = np.arange(1.0, 1.26, 0.005)
ladder = [dg["P_ideal"] / ((dg["P_axial"] + dg["P_swirl"]) * k + dg["P_prof"]) for k in kgrid]
out['fm_ladder'] = {f"{k:.2f}": dg["P_ideal"] / ((dg["P_axial"] + dg["P_swirl"]) * k + dg["P_prof"])
                    for k in (1.0, 1.1, 1.15, 1.18, 1.2, 1.22)}
out['diag_consistency'] = dict(
    P_coeff_route=dg["P"],
    P_ledger=dg["P_axial"] + dg["P_swirl"] + dg["P_prof"],
    ratio=(dg["P_axial"] + dg["P_swirl"] + dg["P_prof"]) / dg["P"])

# ---------------------------------------------------------------- 6. CMA-ES log
rows = []
for line in open("E:/旋翼设计/results/logs/cmaes_evals.jsonl"):
    rows.append(json.loads(line))
out['cmaes'] = dict(n=len(rows), feasible=sum(1 for r in rows if r.get("feasible")),
                    best_fm=max((r.get("FM", 0) for r in rows if r.get("feasible")), default=None))
json.dump(rows, open("E:/旋翼设计/results/verif_cmaes.json", "w"))

print(json.dumps(out, indent=1, default=str))
