"""Flat-plate debug: analytic Cl = 2*pi*alpha, loading gamma(x) = 2*U*alpha*sqrt((1-x)/x)."""
import sys
sys.path.insert(0, "E:/旋翼设计/src")
import numpy as np
from rotorgen.airfoil import Airfoil
from rotorgen.panel2d import PanelSolver

# thin camber plate: flat sheet of zero thickness, 60 panels upper = lower (sharp TE)
n = 60
x = 0.5*(1-np.cos(np.linspace(0, np.pi, n)))[::-1]  # TE->LE clustered
plate = Airfoil(x, np.zeros_like(x), "plate")
ps = PanelSolver(plate)
print("N panels:", ps.N, " (last panel is degenerate closure: length", ps.L[-1], ")")

sol = ps.solve(5.0)
g = sol.gamma
print("gamma at nodes (first 5, last 5):", g[:5], g[-5:])
vm = sol.surface_velocity()
ld = sol.loads()
print(f"Cl={ld['cl']:.4f} (expect {2*np.pi*np.deg2rad(5):.4f}), vmax={np.abs(vm).max():.3f}")
mid = ps.mid[:,0]
gam_mid = 0.5*(g[:-1]+g[1:])
for xr in [0.05, 0.2, 0.5, 0.8]:
    i = np.argmin(np.abs(mid - xr))
    exact = 2*np.sin(np.deg2rad(5))*np.sqrt((1-mid[i])/mid[i])
    print(f"x={mid[i]:.3f}  gamma_num={gam_mid[i]:+.4f}  gamma_exact={exact:+.4f}")
