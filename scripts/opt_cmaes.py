"""Phase C: CMA-ES optimization on the expanded 17-dim design space.

Multi-fidelity schedule (docs/FM075_PLAN.md Phase C):
  - objective: fast tier (dpsi10/4.5rev, n_outer=22, window 6), warm-started
    collective trim (secant, 2-3 solves) -> ~30-45 s/objective;
  - every 8 generations the current best is re-verified at hifi tier
    (dpsi7.5/6rev, n_outer=26) to track the fidelity drift;
  - final delivery: ultra tier (Phase D).
Cd x1.15 hard correction is baked into the tables (design_opt2.station_polar).

Persistence: every evaluation appended to results/logs/cmaes_evals.jsonl;
best-so-far in results/cmaes_best.json; --resume continues from the jsonl.
"""
import sys, json, time, argparse
sys.path.insert(0, "E:/旋翼设计/src")
sys.path.insert(0, "E:/旋翼设计/scripts")
import numpy as np
import cma

from design_opt2 import (X0, BOUNDS_LO, BOUNDS_HI, trim_and_power,
                         check_constraints, _cache_stats)
from rotorgen.rotor3d import RotorSolver  # noqa: F401 (import check)

EVALS_JSONL = "E:/旋翼设计/results/logs/cmaes_evals.jsonl"
BEST_JSON = "E:/旋翼设计/results/cmaes_best.json"

_trim_mem = {"pitch": 15.5}          # warm-start collective (seed trim point)


def trim_fast(x, tol=0.02):
    """Warm-started secant trim at the fast tier: ~2-4 solves."""
    p0 = _trim_mem["pitch"]
    def T_of(p):
        T, P, sol = None, None, None
        from design_opt2 import eval_thrust
        T, P, sol = eval_thrust(x, p, "fast")
        return T, P, sol
    T0, P0, sol0 = T_of(p0)
    if abs(T0 - 1961.33) < 0.01 * 1961.33:
        return P0, sol0, p0
    # secant needs a second point
    p1 = p0 + (2.0 if T0 < 1961.33 else -2.0)
    T1, P1, sol1 = T_of(p1)
    lo, hi = (p0, p1) if T0 < T1 else (p1, p0)
    Tlo, Thi = (T0, T1) if T0 < T1 else (T1, T0)
    Plo, Phi = (P0, P1) if T0 < T1 else (P1, P0)
    if Tlo > 1961.33 or Thi < 1961.33:      # bracket lost -> widen once
        for dp in (3.0, -3.0, 5.0, -5.0):
            Tn, Pn, sn = T_of(p0 + dp)
            if Tn < 1961.33:
                lo, Tlo, Plo = p0 + dp, Tn, Pn
            else:
                hi, Thi, Phi = p0 + dp, Tn, Pn
            if Tlo < 1961.33 < Thi:
                break
        else:
            return None, None, None
    best = (abs(T0 - 1961.33), P0, sol0, p0)
    for _ in range(4):
        pm = hi - (Thi - 1961.33) * (hi - lo) / max(Thi - Tlo, 1e-9)
        Tm, Pm, sm = T_of(pm)
        if abs(Tm - 1961.33) < best[0]:
            best = (abs(Tm - 1961.33), Pm, sm, pm)
        if abs(Tm - 1961.33) < tol * 1961.33:
            break
        if Tm < 1961.33:
            lo, Tlo, Plo = pm, Tm, Pm
        else:
            hi, Thi, Phi = pm, Tm, Pm
    _trim_mem["pitch"] = best[3]
    return best[1], best[2], best[3]


def fast_objective(x, gen=-1, idx=-1):
    x = np.asarray(x, dtype=float)
    t0 = time.time()
    if np.any(x < BOUNDS_LO - 1e-9) or np.any(x > BOUNDS_HI + 1e-9):
        row = dict(gen=gen, idx=idx, P=1e6, feasible=False, why="bounds",
                   t_s=round(time.time() - t0, 1))
        append_row(row, x)
        return 1e6
    P, sol, pitch = trim_fast(x)
    if P is None:
        row = dict(gen=gen, idx=idx, P=1e6, feasible=False, why="no-trim",
                   t_s=round(time.time() - t0, 1))
        append_row(row, x)
        return 1e6
    bad = check_constraints(x, sol)
    if bad:
        row = dict(gen=gen, idx=idx, P=1e6, feasible=False, why="+".join(bad),
                   t_s=round(time.time() - t0, 1))
        append_row(row, x)
        return 1e6
    fm = 1961.33 ** 1.5 / np.sqrt(2 * 1.225 * np.pi * 1.04 ** 2) / P
    row = dict(gen=gen, idx=idx, P=float(P), FM=round(fm, 4),
               pitch=round(pitch, 3), feasible=True,
               x=[float(v) for v in np.round(x, 4)],
               t_s=round(time.time() - t0, 1))
    append_row(row, x)
    return float(P)


def append_row(row, x):
    row["x"] = [float(v) for v in np.round(x, 4)]
    with open(EVALS_JSONL, "a") as f:
        f.write(json.dumps(row, default=float) + "\n")
    fm = row.get("FM")
    if row.get("feasible") and fm is not None:
        try:
            best = json.load(open(BEST_JSON))
        except Exception:
            best = {"FM": -1}
        if fm > best.get("FM", -1):
            json.dump(dict(gen=row["gen"], FM=fm, P=row["P"],
                           pitch=row["pitch"], x=row["x"]),
                      open(BEST_JSON, "w"), indent=1)


def hifi_check(x, tag):
    """Re-verify a design at the hifi tier (fidelity-drift tracking)."""
    from design_opt2 import eval_thrust
    x = np.asarray(x, dtype=float)
    t0 = time.time()
    # fresh trim at hifi
    lo_p, hi_p = 10.0, 22.0
    best = None
    for _ in range(6):
        mid = 0.5 * (lo_p + hi_p)
        T, P, sol = eval_thrust(x, mid, "hifi")
        if best is None or abs(T - 1961.33) < best[0]:
            best = (abs(T - 1961.33), mid, P, sol)
        if T < 1961.33:
            lo_p = mid
        else:
            hi_p = mid
    _, pitch, P, sol = best
    fm = 1961.33 ** 1.5 / np.sqrt(2 * 1.225 * np.pi * 1.04 ** 2) / P
    bad = check_constraints(x, sol)
    row = dict(gen=tag, idx="hifi", P=float(P), FM=round(fm, 4),
               pitch=round(pitch, 3), feasible=not bad, why="+".join(bad),
               x=[float(v) for v in np.round(x, 4)],
               t_s=round(time.time() - t0, 1))
    append_row(row, x)
    print(f"[hifi check @{tag}] P={P:.0f} FM={fm:.4f} pitch={pitch:.2f} "
          f"{'OK' if not bad else bad}", flush=True)
    return row


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gens", type=int, default=40)
    ap.add_argument("--sigma0", type=float, default=0.22)
    ap.add_argument("--popsize", type=int, default=14)
    ap.add_argument("--hifi-every", type=int, default=8)
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()

    scale = (BOUNDS_HI - BOUNDS_LO)
    x0 = np.clip(X0, BOUNDS_LO + 0.02 * scale, BOUNDS_HI - 0.02 * scale)
    es = cma.CMAEvolutionStrategy(x0, args.sigma0 * 1.0,
                                  dict(bounds=[list(BOUNDS_LO), list(BOUNDS_HI)],
                                       popsize=args.popsize, seed=args.seed,
                                       verbose=-9))
    print(f"CMA-ES start: dim={len(x0)} popsize={args.popsize} "
          f"sigma0={args.sigma0} gens={args.gens}", flush=True)
    gen = 0
    while not es.stop() and gen < args.gens:
        solutions = es.ask()
        vals = [fast_objective(x, gen=gen, idx=i) for i, x in enumerate(solutions)]
        es.tell(solutions, vals)
        gen += 1
        best_gen = min(vals)
        print(f"[gen {gen:3d}] best={best_gen:.0f} W  "
              f"FM~{1961.33**1.5/np.sqrt(2*1.225*np.pi*1.04**2)/best_gen:.4f}  "
              f"sigma={es.sigma:.3f}  evals={gen*args.popsize}", flush=True)
        if gen % args.hifi_every == 0:
            try:
                b = json.load(open(BEST_JSON))
                hifi_check(np.array(b["x"]), tag=gen)
            except Exception as e:
                print("hifi check failed:", e, flush=True)
        json.dump(dict(gen=gen, sigma=float(es.sigma),
                       xbest=list(map(float, es.best.x[-1])) if es.best.x else None),
                  open("E:/旋翼设计/results/cmaes_state.json", "w"), default=float)
    print("CMA-ES done:", es.stop(), flush=True)
    b = json.load(open(BEST_JSON))
    print("BEST:", json.dumps(b, indent=1), flush=True)


if __name__ == "__main__":
    main()
