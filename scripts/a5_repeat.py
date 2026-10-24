"""A5: run-protocol reproducibility check (docs/FM075_PLAN.md A5).

Same configuration (delivered blade, hi-fi tier, frozen protocol) trimmed and
evaluated TWICE in fresh solver instances; acceptance: FM repeat spread < 0.005.
"""
import sys, json
sys.path.insert(0, "E:/旋翼设计/src")
sys.path.insert(0, "E:/旋翼设计/scripts")
import numpy as np

from diag_fm075 import report

CFG = (7.5, 6.0, 5.0, 12.0)
runs = [report(f"repeat-{k+1}", CFG) for k in range(2)]
fms = [r["FM_v2"] for r in runs]
ps = [r["pitch"] for r in runs]
spread = abs(fms[0] - fms[1])
print(f"\nA5 REPEAT: FM = {fms[0]:.4f} vs {fms[1]:.4f}  |dFM| = {spread:.4f} "
      f"({'PASS' if spread < 0.005 else 'FAIL'}, target <0.005)", flush=True)
print(f"          pitch = {ps[0]:.3f} vs {ps[1]:.3f}", flush=True)
json.dump(dict(cfg=list(CFG), runs=runs, dFM=spread,
               passed=bool(spread < 0.005)),
          open("E:/旋翼设计/results/a5_repeat.json", "w"), indent=1, default=float)
print("saved results/a5_repeat.json", flush=True)
