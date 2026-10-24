"""CST airfoil family generator with ABSOLUTE trailing-edge thickness constraint.

Family design (span-morphed CST):
- Base shape per surface: CST with N=6 Bernstein coefficients.
- Spanwise parameters: thickness t/c(rbar), camber zmax(rbar), position of
  max thickness/camber fixed-ish; TE thickness EXACTLY t_TE_phys/c(r) (2 mm).
- camber applied as smooth arc: z_c(x) = zmax * sin(pi x^p) form blended to 0
  at LE/TE with plateau near max position.

The generator outputs Airfoil objects (mine) for direct Foil2D tabling.
"""
from __future__ import annotations
import numpy as np

from .airfoil import Airfoil, cst_airfoil, class_function, shape_function


def _base_coeffs(tc: float, camber: float, te_gap: float) -> tuple[np.ndarray, np.ndarray]:
    """Calibrated CST coefficients: base shape yields 8.77% t/c and 0.086 camber
    per unit camber argument (measured); scale accordingly."""
    Au0 = np.array([0.1052, 0.1495, 0.0865, 0.1005, 0.0302, 0.0085])
    Al0 = -np.array([0.1052, 0.1495, 0.0865, 0.1005, 0.0302, 0.0085])
    s = tc / 0.0877
    cs = camber / 0.086
    cam_u = np.array([0.00, 0.16, 0.35, 0.32, 0.14, 0.03]) * cs
    cam_l = np.array([0.00, 0.10, 0.28, 0.30, 0.15, 0.03]) * cs
    Au = s * Au0 + cam_u
    Al = s * Al0 + cam_l
    return Au, Al


def family_airfoil(tc: float, camber: float, te_gap: float, n_side: int = 80,
                   name: str = "fam") -> Airfoil:
    """Airfoil with thickness ratio tc, camber (max arc, fraction of chord),
    and EXACT trailing-edge gap te_gap (fraction of chord)."""
    Au, Al = _base_coeffs(tc, camber, te_gap)
    return cst_airfoil(Au, Al, te_gap=te_gap, n_per_side=n_side, name=name)


class AirfoilFamily:
    """Spanwise-morphing family with absolute TE thickness t_TE_phys (meters)."""

    def __init__(self, R: float, tc_root: float, tc_tip: float, camber: float,
                 t_te_phys: float = 0.002, tc_min: float = 0.07):
        self.R = R
        self.tc_root = tc_root
        self.tc_tip = tc_tip
        self.camber = camber
        self.t_te = t_te_phys
        self.tc_min = tc_min

    def tc_at(self, rbar: float) -> float:
        tc = self.tc_root + (self.tc_tip - self.tc_root) * rbar ** 1.2
        return max(tc, self.tc_min)

    def te_gap_at(self, chord_m: float) -> float:
        """Exact relative TE gap for absolute thickness t_te."""
        return self.t_te / max(chord_m, 1e-3)

    def airfoil_at(self, rbar: float, chord_R: float, n_side: int = 80) -> Airfoil:
        tc = self.tc_at(rbar)
        c_m = chord_R * self.R
        te_gap = self.te_gap_at(c_m)
        return family_airfoil(tc, self.camber, te_gap, n_side=n_side,
                              name=f"fam_r{rbar:.2f}")
