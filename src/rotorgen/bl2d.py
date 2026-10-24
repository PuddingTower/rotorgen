"""Integral boundary layer: Thwaites (laminar) + Michel (transition) + Head (turbulent).

Formulas cross-verified against literature (see RESEARCH_AND_BENCHMARK_LOG 1.3):
- Thwaites:  d(theta^2)/dx = 0.45 nu/ue - 6 theta^2/ue due/dx   (equivalent integrated form)
  lambda = theta^2/nu * due/dx ;  l(lambda) ~ 0.45 + lambda/18.57 approx via Curle
  cf = 2 l(lambda) nu/(ue theta)
  H(lambda):  lambda>=0: 2.215 - 0.025*lam + 0.5*lam^2 ; lambda<0: 2.088 + 0.0731/(lam+0.14)
  laminar separation: lambda < -0.09
- Michel:    Re_theta,tr = 1.174 (1 + 22400/Re_x) Re_x^0.4631
- Head:      dtheta/dx = cf/2 - (H+2) theta/ue due/dx
             d(H1 theta)/dx = ue * Ce ,   Ce = 0.0306 (H1-3.0)^-0.6169
             H1(H):  H<1.6: 3.15 + 1.72/(H-0.6773) ; else 3.3 + 0.8234 (H-1.1)^-1.287
- Ludwieg-Tillmann:  cf = 0.246 10^(-0.678 H) Re_theta^-0.268
- Drag: Squire-Young at TE:  Cd = 2 theta_TE/c * (ue_TE/Uinf)^{(H_TE+5)/2}

Marching in surface coordinates s from stagnation point; ue from panel solver
(positive by construction). Separation flagged when H > 3.5 (turbulent) — loads
post-processing handles stall.
"""
from __future__ import annotations
import numpy as np
from dataclasses import dataclass


@dataclass
class BLSide:
    x: np.ndarray       # chordwise x of stations
    ue: np.ndarray      # edge velocity (positive, scaled by Uinf)
    theta: np.ndarray
    H: np.ndarray
    cf: np.ndarray
    s: np.ndarray       # arc length from stagnation
    tr_x: float         # transition x/c
    sep_x: float        # separation x/c (np.inf if attached)


def _thwaites_march(x, ue, nu):
    """Laminar march on one side; returns theta, H, cf arrays and separation index."""
    n = len(x)
    theta = np.zeros(n)
    H = np.zeros(n)
    cf = np.zeros(n)
    theta[0] = np.sqrt(0.075 * nu / (ue[0] / (x[1] - x[0]))) if n > 1 else 1e-5
    theta[0] = np.sqrt(nu * 1e-4)
    sep = n
    for i in range(n - 1):
        dx = x[i + 1] - x[i]
        ue_i, ue_j = ue[i], ue[i + 1]
        duedx = (ue_j - ue_i) / dx
        # march theta^2
        th2 = theta[i] ** 2
        th2_j = th2 + dx * (0.45 * nu / ue_i - 6.0 * th2 / ue_i * duedx)
        th2_j = max(th2_j, 1e-14)
        theta[i + 1] = np.sqrt(th2_j)
        # local lambda at i (midpoint)
        ue_m = 0.5 * (ue_i + ue_j)
        th_m = 0.5 * (theta[i] + theta[i + 1])
        lam = th_m ** 2 / nu * duedx
        lam = max(min(lam, 0.25), -0.15)
        if lam >= 0:
            H[i] = 2.215 - 0.025 * lam + 0.5 * lam ** 2
        else:
            H[i] = 2.088 + 0.0731 / (lam + 0.14)
        l = 0.45 + lam / 18.57  # approximate shear correlation
        cf[i] = max(2 * l * nu / (ue_m * th_m), 0.0)
        if lam < -0.09 and sep == n:
            sep = i
    H[n - 1] = H[n - 2] if n > 1 else 2.5
    return theta, H, cf, sep


def _michel_transition(x, theta, ue, nu, x0):
    """First station where Michel criterion is exceeded."""
    Rex = np.maximum(x - x0, 1e-6) * ue / nu
    Reth = theta * ue / nu
    with np.errstate(divide="ignore", invalid="ignore"):
        crit = 1.174 * (1 + 22400 / Rex) * Rex ** 0.4631
    idx = np.where((Reth > crit) & (Rex > 1e3))[0]
    return int(idx[0]) if len(idx) else len(x)


def _H1_of_H(H):
    H = np.clip(H, 0.9, 4.5)
    return np.where(H < 1.6, 3.15 + 1.72 / np.maximum(H - 0.6773, 1e-3),
                    3.3 + 0.8234 * np.maximum(H - 1.1, 1e-3) ** -1.287)


def _H_of_H1(H1):
    H1 = np.clip(H1, 3.0, 40.0)
    H = np.where(H1 < 3.3,
                 0.6773 + 1.72 / np.maximum(H1 - 3.15, 1e-3),
                 1.1 + 0.8234 ** (1 / 1.287) * np.maximum(H1 - 3.3, 1e-6) ** (-1 / 1.287))
    return np.clip(H, 1.05, 4.8)


def _cf_turb(H, Reth):
    """Ludwieg-Tillmann (clipped)."""
    lt = 0.246 * 10.0 ** (-0.678 * np.clip(H, 1.0, 4.5)) * np.maximum(Reth, 1e2) ** -0.268
    return np.maximum(lt, 1e-5)


def _head_march(x, ue, theta0, H0, nu):
    """Head turbulent march in conservative form: d(ue*E)/dx = ue*Ce, E = theta*H1,
    with explicit theta march. Robust right after transition (tiny theta)."""
    n = len(x)
    theta = np.zeros(n); theta[0] = max(theta0, 1e-8)
    H = np.zeros(n); H[0] = H0
    E = np.zeros(n); E[0] = theta[0] * float(_H1_of_H(H0))
    cf = np.zeros(n)
    Ce = lambda h1: 0.0306 * np.maximum(h1 - 3.0, 0.05) ** -0.6169
    for i in range(n - 1):
        dx = x[i + 1] - x[i]
        ue_i, ue_j = ue[i], ue[i + 1]
        ue_m = 0.5 * (ue_i + ue_j)
        duedx = (ue_j - ue_i) / dx
        th = theta[i]; H_ = float(np.clip(H[i], 1.1, 4.0))
        Reth = th * ue_m / nu
        cf_ = float(_cf_turb(H_, Reth))
        # theta explicit (midpoint)
        dth = cf_ / 2 - (H_ + 2) * th / ue_m * duedx
        th_new = max(th + dx * dth, 1e-9)
        # E conservative
        H1_i = E[i] / th
        E_new = (ue_i * E[i] + dx * ue_m * Ce(H1_i)) / max(ue_j, 1e-6)
        theta[i + 1] = th_new
        E[i + 1] = E_new
        H1_new = E_new / th_new
        H[i + 1] = float(_H_of_H1(H1_new))
        cf[i] = cf_
    cf[0] = cf[1] if n > 1 else 0.0
    cf[n - 1] = cf[n - 2] if n > 1 else 0.0
    return theta, H, cf


def march_side(x: np.ndarray, ue: np.ndarray, Re: float, x_stag: float,
               turb_trigger: str = "michel") -> BLSide:
    """March one side from stagnation to TE. x strictly increasing from stagnation."""
    nu = 1.0 / Re  # chord-normalized
    ue = np.abs(ue)
    # laminar march
    theta, H, cf, sep_lam = _thwaites_march(x, ue, nu)
    i_tr = _michel_transition(x, theta, ue, nu, x_stag)
    i_tr = max(i_tr, 1)
    # if laminar separation occurs before natural transition -> transition there (bubble)
    if sep_lam < i_tr:
        i_tr = min(sep_lam + 1, len(x) - 1)
    # turbulent march from transition (theta continuous)
    # natural transition (Michel first): H1 continuity; bubble (laminar sep first):
    # reattachment turbulent state, H ~ 2.4
    if sep_lam < i_tr:
        i_tr = min(sep_lam + 1, len(x) - 1)
        H_turb0 = 2.4
    else:
        H_lam_tr = H[max(i_tr - 1, 0)] if i_tr > 0 else 2.6
        H_turb0 = float(_H_of_H1(_H1_of_H(H_lam_tr)))
    x_t = x[i_tr:]
    ue_t = ue[i_tr:]
    if len(x_t) > 2:
        th_t, H_t, cf_t = _head_march(x_t, ue_t, theta[i_tr], H_turb0, nu)
        theta[i_tr:] = th_t
        H[i_tr:] = H_t
        cf[i_tr:] = cf_t
    # turbulent TE separation: H > 3.5 sustained beyond x>0.10 (ignore LE bubble zone)
    sep_x = np.inf
    for i in range(len(x)):
        if x[i] < 0.10:
            continue
        if H[i] > 3.5 and i + 1 < len(x) and H[i + 1] > 3.5:
            sep_x = x[i]
            break
    i_tr = min(i_tr, len(x) - 1)
    return BLSide(x=x, ue=ue, theta=theta, H=H, cf=cf, s=x, tr_x=x[i_tr], sep_x=sep_x)


def squire_young_cd(side_u: BLSide, side_l: BLSide) -> float:
    """Profile drag (both sides) via Squire-Young at TE."""
    cd = 0.0
    for sd in (side_u, side_l):
        if len(sd.x) < 2:
            continue
        th = sd.theta[-1]
        uev = sd.ue[-1]
        Hv = sd.H[-1]
        cd += 2 * th * uev ** ((Hv + 5.0) / 2.0)
    return cd


def base_drag_hoerner(te_gap: float, cd_fric: float) -> float:
    """Grasso/Hoerner blunt-TE base drag: Cd_b = 0.135 h^(4/3) / Cd^(1/3)."""
    if te_gap <= 0 or cd_fric <= 1e-6:
        return 0.0
    return 0.135 * te_gap ** (4.0 / 3.0) / cd_fric ** (1.0 / 3.0)
