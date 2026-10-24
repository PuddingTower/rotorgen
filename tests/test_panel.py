"""Validate stream-function panel solver on NACA0012 (Ladson TM-4044 targets:
Cl_alpha ~ 0.108-0.11/deg inviscid-ish, Cd_min ~ 0.0058-0.0065 at Re 6e6)."""
import sys, time
sys.path.insert(0, "E:/旋翼设计/src")
import numpy as np
from rotorgen.airfoil import naca0012
from rotorgen.panel2d import PanelSolver

af = naca0012(n_per_side=80)
t0 = time.time(); ps = PanelSolver(af); t1 = time.time()
print(f"build {t1-t0:.2f}s, N={ps.N}, hTE={ps.hTE:.5f}, tcp={ps.tcp:.5f}, tdp={ps.tdp:.5f}")
for alpha in [0.0, 2.0, 5.0, 8.0, 12.0]:
    ld = ps.loads(alpha)
    ue = ps.surface_velocity(alpha)
    print(f"a={alpha:5.1f} Cl={ld['cl']:+.4f} slope={ld['cl']/alpha if alpha else 0:.5f}/deg"
          f"  Cd_p={ld['cd_press']:+.2e}  umax={ue.max():.3f}  umin={ue.min():+.3f}")
