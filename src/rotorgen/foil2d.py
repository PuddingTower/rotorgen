"""Coupled 2D airfoil analysis: panel (inviscid) + integral BL -> Cl, Cd, Cm.

Pipeline per (alpha, Re, M):
 1. PanelSolver.solve (geometry-factored, O(N) per alpha) -> ue at panel midpoints.
 2. Split upper/lower at stagnation point; march BL each side (Thwaites->Michel->Head).
 3. Drag = Squire-Young(TE theta, H) + Grasso blunt-TE base drag.
 4. Lift: inviscid Cl corrected by viscous decambering near separation
    (progressive reduction once upper-surface separation starts).
 5. Compressibility: Karman-Tsien Cp (panel) + turbulent Cf Mach correction.

Post-stall (for rotor tables): linear-attached core blended to a flat-plate-type
curve beyond stall angle detected from the BL separation sweep.
"""
from __future__ import annotations
import numpy as np
from dataclasses import dataclass

from .airfoil import Airfoil
from .panel2d import PanelSolver
from . import bl2d


@dataclass
class FoilResult:
    alpha: float
    cl: float
    cd: float
    cm: float
    cl_inv: float
    sep_x_up: float
    tr_x_up: float
    tr_x_lo: float
    stalled: bool


class Foil2D:
    """Reusable solver per airfoil geometry (panel system factored once)."""

    def __init__(self, af: Airfoil, n_per_side: int = 80):
        self.af = af.resample(n_per_side) if af.n < 2 * n_per_side else af
        self.ps = PanelSolver(self.af)
        mids = self.ps.panel_mid
        self.x_mid = mids[0]
        self.y_mid = mids[1]
        # panel indices: nodes 0=TEl -> lower -> LE -> upper -> TEu (clockwise)
        n_pan = len(self.x_mid)
        self.i_le = int(np.argmin(self.x_mid))
        self.i_up = np.arange(self.i_le, n_pan)        # upper: LE -> TEu
        self.i_lo = np.arange(0, self.i_le + 1)[::-1]  # lower: LE -> TEl (reversed)

    def analyze(self, alpha_deg: float, Re: float, M: float = 0.0,
                ncrit: float = 9.0, n_coupled: int = 1) -> FoilResult:
        ps = self.ps
        Np = len(self.x_mid)
        gamma = ps.gamma(alpha_deg)
        ue = ps.surface_velocity(alpha_deg)
        side_u = self._march(self.x_mid[self.i_up], ue[self.i_up], Re, ncrit)
        side_l = self._march(self.x_mid[self.i_lo], -ue[self.i_lo], Re, ncrit)
        # one-shot (or few-shot) displacement correction
        for it in range(n_coupled):
            vw = np.zeros(Np)
            for idxs, sd in ((self.i_up, side_u), (self.i_lo, side_l)):
                xs = sd.x
                dstar = sd.theta * sd.H
                usd = sd.ue * dstar
                ok = np.where((usd > 0) & (np.isfinite(usd)) & (xs > 0.03) & (xs < 0.98))[0]
                if len(ok) < 5:
                    continue
                ok = ok[np.argsort(xs[ok])]
                # smooth d(ue*delta*)/dx on uniform grid then sample at panel mids
                xg = np.linspace(xs[ok][0], xs[ok][-1], 60)
                ug = np.interp(xg, xs[ok], usd[ok])
                dudx = np.gradient(ug, xg)
                x_pan = self.x_mid[idxs]
                sel = (x_pan > xg[0]) & (x_pan < xg[-1])
                gi = np.where(sel)[0]
                vw_idx = idxs[gi]
                vw[vw_idx] = np.interp(x_pan[gi], xg, dudx)
            vw = np.clip(vw, -0.03, 0.03)
            gamma = ps.solve_with_transpiration(alpha_deg, vw)
            ue = ps.ue_from_gamma(gamma, alpha_deg) + ps.ue_source_contrib(vw)
            side_u = self._march(self.x_mid[self.i_up], ue[self.i_up], Re, ncrit)
            side_l = self._march(self.x_mid[self.i_lo], -ue[self.i_lo], Re, ncrit)
        # viscous lift from circulation (Kutta-Joukowski)
        circ = float(np.sum(0.5 * (gamma[:-1] + gamma[1:]) * ps.panel_d))
        ld = ps.loads(alpha_deg, M)
        cl = -2.0 * circ if abs(-2 * circ - ld["cl"]) < abs(2 * circ - ld["cl"]) else 2.0 * circ
        cd_fric = bl2d.squire_young_cd(side_u, side_l)
        cd_base = bl2d.base_drag_hoerner(self.af.te_gap, max(cd_fric, 1e-4))
        cd = (cd_fric + cd_base) * (1.0 + 0.13 * M * M)
        stalled = False
        if side_u.sep_x < 0.97:
            ext = np.clip(0.95 - side_u.sep_x, 0.0, 0.6)
            cl *= max(1.0 - 1.2 * ext, 0.30)
            stalled = ext > 0.08
        return FoilResult(alpha_deg, cl, cd, ld["cm"], ld["cl"],
                          side_u.sep_x, side_u.tr_x, side_l.tr_x, stalled)

    @staticmethod
    def _march(x, ue, Re, ncrit):
        # drop leading points with ue <= 0.05 (stagnation region), start march after
        good = np.where(ue > 0.05)[0]
        if len(good) < 8:
            return bl2d.BLSide(x=x, ue=np.abs(ue) + 1e-3,
                               theta=np.full_like(x, 1e-3), H=np.full_like(x, 2.6),
                               cf=np.zeros_like(x), s=x, tr_x=0.1, sep_x=np.inf)
        i0 = good[0]
        # enforce monotonic x
        xx = x[i0:]
        uue = np.abs(ue[i0:])
        keep = np.concatenate([[True], np.diff(xx) > 1e-9])
        xx = xx[keep]; uue = uue[keep]
        return bl2d.march_side(xx, uue, Re, xx[0])

    # ------------------------------------------------------------------ polar
    def polar(self, alphas_deg, Re: float, M: float = 0.0, ncrit: float = 9.0):
        res = [self.analyze(a, Re, M, ncrit) for a in alphas_deg]
        return res


def make_table(af: Airfoil, Re_list, M_list, alpha_deg=np.arange(-8, 20.01, 0.5),
               n_per_side: int = 80, ncrit: float = 9.0):
    """Build Cl/Cd/Cm tables over (alpha, Re, M) for rotor section lookups."""
    f = Foil2D(af, n_per_side)
    out = {}
    for M in M_list:
        for Re in Re_list:
            rs = f.polar(alpha_deg, Re, M, ncrit)
            out[(float(Re), float(M))] = dict(
                alpha=alpha_deg.copy(),
                cl=np.array([r.cl for r in rs]),
                cd=np.array([r.cd for r in rs]),
                cm=np.array([r.cm for r in rs]),
                sep=np.array([r.sep_x_up for r in rs]),
            )
    return out
