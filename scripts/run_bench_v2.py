"""A4: full benchmark matrix under the v2 explicit accounting (design-accounting v2).

Acceptance (docs/FM075_PLAN.md Gate A): core-case matched-thrust CQ error
within +-8%; if residual is larger, a single global factor kappa_cal in
[1.0, 1.15] may be introduced with documented provenance.

Usage: python run_bench_v2.py [--phi 1.15] [--tier ultra] [--families ct,mt,har,dji]
"""
import sys, json, time
sys.path.insert(0, "E:/旋翼设计/src")
sys.path.insert(0, "E:/旋翼设计/scripts")
import numpy as np

import bench2
from bench2 import run_case, ct_cases, mt_cases, har_cases, dji_cases


def main():
    phi = 1.2
    tier = "ultra"
    fams = "ct,mt,har,dji"
    cdf = 1.15
    args = sys.argv[1:]
    if "--phi" in args:
        phi = float(args[args.index("--phi") + 1])
    if "--tier" in args:
        tier = args[args.index("--tier") + 1]
    if "--families" in args:
        fams = args[args.index("--families") + 1]
    if "--cd-factor" in args:
        cdf = float(args[args.index("--cd-factor") + 1])
    fams = fams.split(",")
    builders = dict(ct=ct_cases, mt=mt_cases, har=har_cases, dji=dji_cases)

    all_rows = []
    t_start = time.time()
    for fam in fams:
        print(f"\n===== family {fam} (tier={tier}, phi={phi}, cd_factor={cdf}) =====",
              flush=True)
        for name, blade, Omega, secs, exp in builders[fam]():
            row = run_case(name, blade, Omega, secs, exp["ct_exp"],
                           exp["cq_exp"], exp["fm_exp"], tier=tier, phi=phi,
                           cd_factor=cdf)
            row["family"] = fam
            all_rows.append(row)
    # summary
    print("\n===== summary =====", flush=True)
    core = [r for r in all_rows if r["family"] == "ct"
            and (r["case"].startswith("CT th8") or r["case"].startswith("CT th12"))
            and "2050" not in r["case"]]
    print("core C-T (theta>=8, M_tip<0.6):", flush=True)
    for r in core:
        print(f"  {r['case']:18s} CT_err={r['CT_err']:+6.1f}%  "
              f"CQ_matched_err={r['CQ_matched_err']:+6.1f}%", flush=True)
    if core:
        mx = max(abs(r["CQ_matched_err"]) for r in core)
        mxc = max(abs(r["CT_err"]) for r in core)
        print(f"  max |CQ_matched_err| = {mx:.1f}%  (Gate A: <=8%)", flush=True)
        print(f"  max |CT_err|         = {mxc:.1f}%  (A2 target: <=10%)", flush=True)
    out = dict(phi=phi, tier=tier, cd_factor=cdf, rows=all_rows,
               wall_s=round(time.time()-t_start, 1))
    json.dump(out, open(f"E:/旋翼设计/results/bench/matrix_v2_{tier}_phi{phi:.2f}_cd{cdf:.2f}.json",
                        "w"), indent=1, default=float)
    print(f"\nsaved results/bench/matrix_v2_{tier}_phi{phi:.2f}_cd{cdf:.2f}.json",
          flush=True)


if __name__ == "__main__":
    main()
