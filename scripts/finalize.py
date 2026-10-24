"""Final delivery: high-fidelity verification + geometry export of the design.

Reads results/final/opt_result.json, rebuilds the trimmed design, runs the
high-fidelity (dpsi=7.5, 6 rev) free-wake verification, and exports:
  - spanwise geometry table (CSV)
  - airfoil coordinates at 12 stations (Selig .dat)
  - 3D blade surface point cloud (offset surface at t/c/2 upper/lower)
  - performance summary (JSON) + sectional loadings (CSV)
"""
import sys, json, os
sys.path.insert(0, "E:/旋翼设计/src")
sys.path.insert(0, "E:/旋翼设计/scripts")
import numpy as np

from design_opt import build_design, make_solver, eval_thrust, T_TARGET, R, B, RHO
from rotorgen.famgen import AirfoilFamily

OUT = "E:/旋翼设计/results/final"


def export(x_opt, pitch_trim):
    os.makedirs(OUT, exist_ok=True)
    Vt, tw_drop, taper, cscale, camber, tc_r, tc_t = x_opt
    Omega = Vt / R
    # high-fidelity solve
    sol = make_solver(x_opt, pitch_trim, fast=False)
    res = sol.solve(n_outer=34, n_sweeps=4,
                    ct_guess=T_TARGET / (RHO * np.pi * R ** 2 * Vt ** 2))
    h = np.array(res.history)
    ct = float(h[-8:, 0].mean())
    cq = float(h[-8:, 1].mean())
    T = ct * RHO * np.pi * R ** 2 * Vt ** 2
    P = cq * RHO * np.pi * R ** 2 * Vt ** 3
    Q = P / Omega
    fm = T ** 1.5 / np.sqrt(2 * RHO * np.pi * R ** 2) / P

    # geometry tables
    rbar = np.linspace(0.16, 1.0, 41)
    _, chord_R, twist, _, _, _ = build_design(x_opt, pitch_trim)
    rrb = np.linspace(0.16, 1.0, 41)
    shape = 0.62 + 0.38 * np.sin(np.pi * np.clip((rrb - 0.10) / 0.90, 0, 1) ** 0.75)
    shape = shape / shape.max()
    shape = (1 - taper) * shape + taper
    chord_m = cscale * shape
    tw = pitch_trim + tw_drop * (0.75 - rrb) / 0.75
    fam = AirfoilFamily(R=R, tc_root=tc_r, tc_tip=tc_t, camber=camber, t_te_phys=0.002)
    tc = np.array([fam.tc_at(r) for r in rrb])

    with open(f"{OUT}/blade_geometry.csv", "w") as f:
        f.write("r_over_R,r_m,chord_m,twist_deg,tc_over_c,TE_thickness_m,"
                "Re_at_6000N_hover\n")
        for i, r in enumerate(rrb):
            Re = RHO * Omega * r * R * chord_m[i] / 1.8e-5
            f.write(f"{r:.4f},{r*R:.4f},{chord_m[i]:.4f},{tw[i]:.3f},{tc[i]:.4f},"
                    f"0.002,{Re:.3e}\n")

    # airfoil files at 12 stations (chord-scaled, absolute 2mm TE)
    os.makedirs(f"{OUT}/airfoils", exist_ok=True)
    for r in np.linspace(0.20, 0.98, 12):
        ci = np.interp(r, rrb, chord_m)
        af = fam.airfoil_at(r, ci / R, n_side=90).resample(90)
        afm = af.scaled(ci)
        afm.name = f"rotor2D08_r{int(r*100):02d}_c{ci*1000:.0f}mm_te2mm"
        afm.to_dat(f"{OUT}/airfoils/{afm.name}.dat")

    # 3D surface point cloud (upper/lower offset surfaces, pitch-axis stacked)
    pts = []
    for r in rrb[::2]:
        ci = np.interp(r, rrb, chord_m)
        af = fam.airfoil_at(r, ci / R, n_side=60).resample(60)
        th = np.deg2rad(np.interp(r, rrb, tw))
        # section frame: LE toward +y (rotor-frame flow -y), LE up with twist
        a = np.array([0.0, np.cos(th), np.sin(th)])
        xle = -0.25 * ci
        for j in range(af.n):
            xr = af.x[j] - 0.25
            yr = af.y[j]
            p = np.array([r * R, 0, 0]) + xr * ci * (-a) + yr * ci * np.array([0, -a[2], a[1]]) * 0
            # build proper: chordwise along -a, perpendicular in (y,z)
            e_c = -a
            e_n = np.array([0.0, a[2], -a[1]])
            p = np.array([r * R, 0, 0]) + xr * ci * e_c + yr * ci * e_n
            pts.append(list(p) + [r])
    pts = np.array(pts)
    np.savetxt(f"{OUT}/blade_surface_xyz.txt", pts, fmt="%.5f",
               header="x_m y_m z_m r_over_R (rotor frame, blade0 along +x, z up; "
                      "upper/lower lofted surface, TE absolute thickness 2 mm)")

    # performance
    alpha = sol._last_alpha
    perf = dict(
        diameter_m=2.08, blades=B, thrust_target_N=T_TARGET,
        tip_speed_ms=Vt, RPM=Omega * 60 / (2 * np.pi), tip_mach=Vt / 340.0,
        solidity=float(2 * chord_m.mean() / (np.pi * R)),
        thrust_N=T, power_W=P, torque_Nm=Q, FM=fm,
        CT=ct, CQ=cq, PC_W_per_kgf=P / (T / 9.80665),
        disk_loading_kgf_m2=T / 9.80665 / (np.pi * R ** 2),
        mean_chord_m=float(chord_m.mean()),
        design_vector=[float(v) for v in x_opt],
        trim_pitch_deg=float(pitch_trim),
        alpha_eff_span=alpha.round(2).tolist(),
        solver="free-wake + 2D panel/BL tables (this project)",
    )
    with open(f"{OUT}/performance.json", "w") as f:
        json.dump(perf, f, indent=1, ensure_ascii=False)
    print(json.dumps({k: perf[k] for k in
                      ["thrust_N", "power_W", "FM", "RPM", "tip_mach", "solidity",
                       "PC_W_per_kgf"]}, indent=1))
    return perf


def main():
    with open(f"{OUT}/opt_result.json") as f:
        opt = json.load(f)
    x = np.array(opt["best_x"])
    # re-trim precisely at high fidelity
    lo, hi = 12.0, 20.0
    best = None
    for _ in range(6):
        mid = 0.5 * (lo + hi)
        T, P, _ = eval_thrust(x, mid)
        print(f"trim mid={mid:.2f}: T={T:.0f}", flush=True)
        if best is None or abs(T - T_TARGET) < best[0]:
            best = (abs(T - T_TARGET), mid, P)
        if T < T_TARGET:
            lo = mid
        else:
            hi = mid
    print("final pitch:", best[1], "T-err:", 100*best[0]/T_TARGET, "%")
    export(x, best[1])


if __name__ == "__main__":
    main()
