"""3D rotor solver v3 (FINAL): free-wake + 2D-airfoil-table blade sections.

Formulation (classical validated free-wake performance method, Leishman school):
- The induced velocity at every blade station is the direct Biot-Savart sum over
  the FREELY-RELAXED helical wake (all blades) + all blades' bound vortices.
  Real wake contraction, swirl, tip loss, blade-vortex interaction -- no momentum
  theory, no strip assumptions (NOT BEMT).
- Section lift/drag from 2D airfoil tables at the local effective angle
  (camber, Reynolds, Mach, stall all included through the tables -- which come
  from this project's own panel+BL solver).
- Station circulation Gamma = 0.5 c Cl |U| feeds the wake edge filaments:
  s_e = Gamma_{e-1} - Gamma_e (positive tip strength -> downwash helix).
- Fixed-point iteration (under-relaxed) between section loads and wake state;
  wake relaxed by predictor-corrector PIPC with over-relaxation, rotor-frame
  convection dx/dzeta = (y, -x, 0) + (Vaxial + v_ind)/Omega, frozen old-wake
  band + analytic helical far-wake continuation.

Conventions: rotor frame with blade 0 along +x; air moves at -Omega (solid
rotation) + Vaxial*z; positive Gamma = positive lift (+z); alpha_eff =
twist + atan2(Vz, -Vy) [flow travels LE->TE = -y].

FROZEN RUN PROTOCOL (design-accounting v2, Phase A of docs/FM075_PLAN.md):
  Induced power: explicit physical terms (P_axial + P_swirl), disk sampling
  n_psi=12 azimuths per blade sector x all loaded stations; NO blanket factor
  (kappa_B removed -- it double-counted wake-resolved non-ideality).
  Wake tiers (dpsi_deg / n_rev / freeze_rev / n_far_rev):
    fast   10.0 / 4.5 / 3.5 / 7    design inner loop, ~13 s/eval
    hi-fi   7.5 / 6.0 / 5.0 / 12   verification, ~25 s/eval
    ultra   5.0 / 10.0 / 9.0 / 12  final delivery / gate checks, ~57 s/eval
  Fixed in all tiers: rc0_frac=0.10, relax_it=1.3, gamma_relax=0.35,
  n_sweeps=4, inflow_scale=1.0 unless a calibration case says otherwise.
  Outer iterations / history averaging window:
    design inner loop n_outer=22 window 6; verification n_outer=26 window 6;
    final delivery n_outer=34 window 8.
  Reproducibility target: same-configuration FM repeat spread < 0.005.
"""
from __future__ import annotations
import numpy as np
from dataclasses import dataclass, field

from .kernels3d import velocity_at_points


@dataclass
class BladeDef:
    R: float
    Rhub: float
    B: int
    r: np.ndarray            # station edges r/R ascending (len Ns+1)
    chord: np.ndarray        # c/R at edges
    twist: np.ndarray        # deg at edges (positive LE up)
    sweep: np.ndarray = None
    camber_y: np.ndarray = None
    Nc: int = 8

    def __post_init__(self):
        if self.sweep is None:
            self.sweep = np.zeros_like(self.r)


def rotz(v, ang):
    c, s = np.cos(ang), np.sin(ang)
    return np.stack([c * v[..., 0] - s * v[..., 1],
                     s * v[..., 0] + c * v[..., 1],
                     v[..., 2]], axis=-1)


@dataclass
class HoverResult:
    CT: float
    CQ: float
    CP: float
    FM: float
    thrust: float
    torque: float
    power: float
    Gamma: np.ndarray
    converged: bool
    n_iter: int
    history: list = field(default_factory=list)


class RotorSolver:
    def __init__(self, blade: BladeDef, Omega: float, rho=1.225, mu=1.8e-5,
                 Vaxial=0.0, dpsi_deg=10.0, rc0_frac=0.10, core_grow=1.0,
                 n_rev=5.0, sections=None, verbose=False):
        self.blade = blade
        self.Omega = Omega
        self.rho = rho
        self.mu = mu
        self.Vaxial = Vaxial
        self.dpsi = np.deg2rad(dpsi_deg)
        self.verbose = verbose
        self.sections = sections        # len Ns: objects with cl_of/cd_of
        self.Ns = len(blade.r) - 1
        self.B = blade.B

        # station geometry (per blade 0)
        self.p25 = np.zeros((self.Ns + 1, 3))
        self.p75 = np.zeros((self.Ns + 1, 3))
        self.te = np.zeros((self.Ns + 1, 3))
        for i in range(self.Ns + 1):
            r = blade.r[i] * blade.R
            c = blade.chord[i] * blade.R
            th = np.deg2rad(blade.twist[i])
            # rotor-frame flow is -y: LE faces +y. ec points LE-ward with twist
            # tilting LE UP (positive twist).
            ec = np.array([0.0, np.cos(th), np.sin(th)])
            base = np.array([r, 0.0, 0.0])
            self.p25[i] = base
            self.p75[i] = base - 0.50 * c * ec     # 3/4 chord (0.5c aft of 1/4c)
            self.te[i] = base - 0.75 * c * ec      # trailing edge (downstream side)
        self.bound_segs_0 = np.concatenate([self.p25[:-1], self.p25[1:]], axis=1)
        cmax = blade.chord.max() * blade.R
        self.rc_bound = 0.05 * cmax
        self.bound_segs_all = np.ascontiguousarray(np.vstack(
            [self.bound_segs_0] +
            [rotz(self.bound_segs_0.reshape(-1, 2, 3),
                  2 * np.pi * m / self.B).reshape(-1, 6)
             for m in range(1, self.B)]))
        self.bound_rc2_all = np.full(len(self.bound_segs_all), self.rc_bound ** 2)
        self.coll0 = 0.5 * (self.p75[:-1] + self.p75[1:])
        # chordwise sampling rows for averaged inflow (1/4c, 1/2c, 3/4c from LE)
        self.coll_rows = [np.ascontiguousarray(self.coll0)]

        self.n_fil = self.Ns + 1
        self.n_age = int(round(n_rev * 2 * np.pi / self.dpsi)) + 1
        self.rc0 = rc0_frac * blade.chord[-1] * blade.R
        self.core_grow = core_grow
        self.r_mid = 0.5 * (blade.r[:-1] + blade.r[1:]) * blade.R
        self.dr = np.diff(blade.r) * blade.R
        self.c_mid = 0.5 * (blade.chord[:-1] + blade.chord[1:]) * blade.R
        self.tw_mid = 0.5 * (blade.twist[:-1] + blade.twist[1:])
        rows = [self.coll0.copy()]
        for fr in (0.25, 0.5):
            ec_mid = np.zeros((self.Ns, 3))
            for i in range(self.Ns):
                thg = np.deg2rad(self.tw_mid[i])
                ec_mid[i] = np.array([0.0, np.cos(thg), np.sin(thg)])
            rows.append(self.coll0 - (fr * self.c_mid)[:, None] * ec_mid)
        self.coll_rows = [np.ascontiguousarray(r) for r in rows]

    # ------------------------------------------------------------------ wake
    def _wake_core2(self):
        ages = np.arange(self.n_age) * self.dpsi / self.Omega
        return self.rc0 ** 2 + 4.0 * 1.05463 * self.core_grow * self.mu * ages * 50.0

    def init_wake(self, ct_guess=0.01):
        lam = np.sqrt(max(ct_guess, 1e-5) / 2.0)
        n = self.n_age
        self.Xw = np.zeros((self.n_fil, n, 3))
        for i in range(self.n_fil):
            p0 = self.te[i]
            r0 = np.hypot(p0[0], p0[1])
            for k in range(n):
                psi = -k * self.dpsi
                self.Xw[i, k] = [r0 * np.cos(psi), r0 * np.sin(psi),
                                 -lam * self.blade.R * k * self.dpsi]
            self.Xw[i, 0] = p0
        qA = self.rho * (self.Omega * self.blade.R) ** 2 * np.pi * self.blade.R ** 2
        T = ct_guess * qA
        R_ = self.blade.R
        rbar = self.r_mid / R_
        G0 = 4.0 * T / (self.rho * self.B * self.Omega * R_ * np.pi)
        ramp = np.clip((rbar - self.blade.Rhub / R_) / 0.25, 0.0, 1.0)
        self.Gamma = G0 * np.sqrt(np.clip(1.0 - rbar ** 2, 0.0, 1.0)) * ramp

    def edge_strengths(self, Gamma):
        g = np.concatenate([[0.0], Gamma, [0.0]])
        return g[:-1] - g[1:]

    def _far_nodes(self):
        dstep = max(4 * self.dpsi, np.deg2rad(25.0))
        n_far = int(getattr(self, 'n_far_rev', 0.0) * 2 * np.pi / dstep) + 1
        far = np.zeros((self.n_fil, n_far, 3))
        for i in range(self.n_fil):
            p_last = self.Xw[i, -1]
            p_prev = self.Xw[i, -2]
            r_end = np.hypot(p_last[0], p_last[1])
            psi_end = np.arctan2(p_last[1], p_last[0])
            zrate = (p_last[2] - p_prev[2]) / self.dpsi
            for k in range(n_far):
                zk = k * dstep
                far[i, k] = [r_end * np.cos(psi_end - zk),
                             r_end * np.sin(psi_end - zk),
                             p_last[2] + zrate * zk]
        return far

    def wake_arrays(self, Gamma):
        strengths = self.edge_strengths(Gamma)
        segs = np.concatenate([self.Xw[:, :-1, :], self.Xw[:, 1:, :]],
                              axis=2).reshape(-1, 6)
        rc2_age = self._wake_core2()
        rc2 = np.tile(0.5 * (rc2_age[:-1] + rc2_age[1:]), self.n_fil)
        gam = np.repeat(strengths, self.n_age - 1)
        if getattr(self, 'n_far_rev', 0.0) > 0:
            far = self._far_nodes()
            segsf = np.concatenate([far[:, :-1, :], far[:, 1:, :]],
                                   axis=2).reshape(-1, 6)
            gamf = np.repeat(strengths, far.shape[1] - 1)
            dstep = max(4 * self.dpsi, np.deg2rad(25.0))
            agesf = np.arange(1, far.shape[1]) * dstep / self.Omega
            rc2f = np.tile(self.rc0 ** 2 + 4 * 1.05463 * self.core_grow * self.mu
                           * (self.n_age * self.dpsi / self.Omega + agesf) * 50.0,
                           self.n_fil)
            segs = np.vstack([segs, segsf])
            gam = np.concatenate([gam, gamf])
            rc2 = np.concatenate([rc2, rc2f])
        R_ = self.blade.R
        rm = np.hypot(0.5 * (segs[:, 0] + segs[:, 3]), 0.5 * (segs[:, 1] + segs[:, 4]))
        hub_core = min(0.08 * R_, 0.5 * self.blade.Rhub, 0.6 * self.blade.chord.max() * R_)
        w = np.clip((0.45 * R_ - rm) / (0.25 * R_), 0.0, 1.0)
        rc2 = rc2 * (1 - w) + hub_core ** 2 * w
        segs_all = [segs]
        for m in range(1, self.B):
            segs_all.append(rotz(segs.reshape(-1, 2, 3),
                                 2 * np.pi * m / self.B).reshape(-1, 6))
        return (np.ascontiguousarray(np.vstack(segs_all)),
                np.ascontiguousarray(np.tile(gam, self.B)),
                np.ascontiguousarray(np.tile(rc2, self.B)))

    # ------------------------------------------------------------------ local inflow
    def local_inflow(self, wsegs, wgam, wrc2):
        """Wake-induced + OTHER blades' bound induction at blade-0 3/4-chord points.
        The own bound vortex field is the airfoil's own field, NOT inflow (including
        it would double-count the section's induced drag angle)."""
        v = np.zeros_like(self.coll0)
        for row in self.coll_rows:
            velocity_at_points(wsegs, wgam, wrc2, row, v)
            if self.B > 1:
                other = np.ascontiguousarray(self.bound_segs_all[self.Ns:])
                velocity_at_points(other, np.tile(self.Gamma, self.B - 1),
                                   self.bound_rc2_all[self.Ns:], row, v)
        v /= len(self.coll_rows)
        return v

    # ------------------------------------------------------------------ wake relax
    def relax_wake(self, Gamma, n_sweeps=3):
        wsegs, wgam, wrc2 = self.wake_arrays(Gamma)
        bound_gam = np.tile(Gamma, self.B)
        n = self.n_age
        dzeta = self.dpsi
        k_freeze = int(getattr(self, 'freeze_rev', 99.0) * 2 * np.pi / self.dpsi)
        vmax = 0.30 * self.Omega * self.blade.R
        for sweep in range(n_sweeps):
            pts = np.ascontiguousarray(self.Xw.reshape(-1, 3))
            v = np.zeros_like(pts)
            velocity_at_points(self.bound_segs_all, bound_gam,
                               self.bound_rc2_all, pts, v)
            velocity_at_points(wsegs, wgam, wrc2, pts, v)
            v = v.reshape(self.n_fil, n, 3)
            vmag = np.linalg.norm(v, axis=2)
            scale = np.where(vmag > vmax, vmax / np.maximum(vmag, 1e-9), 1.0)
            v = v * scale[:, :, None]
            Xnew = self.Xw.copy()
            for i in range(self.n_fil):
                for k in range(1, min(n, k_freeze)):
                    xp = Xnew[i, k - 1]
                    xc = self.Xw[i, k]
                    R_prev = (v[i, k - 1] + np.array([0.0, 0.0, self.Vaxial])
                              + np.array([xp[1], -xp[0], 0.0]) * self.Omega) / self.Omega
                    R_cur = (v[i, k] + np.array([0.0, 0.0, self.Vaxial])
                             + np.array([xc[1], -xc[0], 0.0]) * self.Omega) / self.Omega
                    x_corr = Xnew[i, k - 1] + dzeta * 0.5 * (R_prev + R_cur)
                    dx = x_corr - self.Xw[i, k]
                    dmax = 0.5 * dzeta * max(np.hypot(self.Xw[i, k, 0],
                                                      self.Xw[i, k, 1]), 0.1)
                    dxn = np.linalg.norm(dx)
                    if dxn > dmax:
                        dx *= dmax / dxn
                    Xnew[i, k] = self.Xw[i, k] + getattr(self, 'relax_it', 1.0) * dx
            self.Xw = Xnew
            wsegs, wgam, wrc2 = self.wake_arrays(Gamma)
        return wsegs, wgam, wrc2

    # ------------------------------------------------------------------ loads
    def section_state(self, wsegs, wgam, wrc2):
        v = self.local_inflow(wsegs, wgam, wrc2)
        vcap = 0.25 * self.Omega * self.blade.R       # cap INDUCED velocities only
        v = v * getattr(self, 'inflow_scale', 1.0)   # documented wake-resolution calibration
        v = np.clip(v, -vcap, vcap)
        vrel = np.zeros_like(self.coll0)
        vrel[:, 0] = self.Omega * self.coll0[:, 1]
        vrel[:, 1] = -self.Omega * self.coll0[:, 0]
        vrel[:, 2] = self.Vaxial
        vtot = vrel + v
        # spanwise smoothing of the induced components (wake spike robustness)
        def _sm(a):
            b = a.copy()
            b[1:-1] = 0.25 * a[:-2] + 0.5 * a[1:-1] + 0.25 * a[2:]
            return b
        fy = _sm(vtot[:, 1])
        fz = _sm(vtot[:, 2])
        U = np.hypot(fy, fz)
        alpha = self.tw_mid + np.degrees(np.arctan2(fz, -fy))
        return alpha, U, fy, fz

    def loads(self, Gamma, wsegs, wgam, wrc2):
        alpha, U, fy, fz = self.section_state(wsegs, wgam, wrc2)
        thrust = 0.0
        P_prof = 0.0
        alpha_eff = np.zeros(self.Ns)
        for i in range(self.Ns):
            a = float(np.clip(alpha[i], -35.0, 35.0))
            alpha_eff[i] = a
            if self.sections is not None:
                sec = self.sections[i]
                cl = sec.cl_of(a)
                cd = sec.cd_of(a)
            else:
                cl = 0.1097 * a
                cd = 0.010
            qloc = 0.5 * self.rho * U[i] ** 2
            L = qloc * cl * self.c_mid[i] * self.dr[i]
            D = qloc * cd * self.c_mid[i] * self.dr[i]
            thrust += L
            P_prof += D * U[i]
        thrust *= self.B
        P_prof *= self.B
        # ---- induced power: explicit physical terms, ONE wake sampling (A1 v2).
        # kappa_B blanket factor REMOVED: it multiplied the converged wake's own
        # non-ideal induction a second time (measured kappa_raw ~1.18 for B=2
        # before it). Accounting, all from the same disk sampling, no free
        # parameters:
        #   P_axial      = sum_i T_i * vi_i        -- work of each station's
        #       thrust element against the wake-induced axial velocity at its
        #       annulus (equals thrust * vi_disk, thrust-weighted disk mean).
        #   P_swirl      = sum 0.5*rho*<vt^2>*vi dA -- swirl kinetic-energy flux
        #       through the disk, tangential induced component at the same
        #       points (disk-plane value; far-wake contraction strengthens
        #       swirl, so this is the conservative/low side -- documented).
        #   P_nonuniform (ledger item) = P_axial - T*v_area: covariance of the
        #       spanwise loading with the per-annulus inflow's deviation from
        #       the disk-mean. Already contained in P_axial; reported, not added.
        n_psi = 12                      # azimuthal samples per blade sector
        n_ang = n_psi * self.B          # full-circle sampling (same resolution)
        T_station = np.zeros(self.Ns)
        for i in range(self.Ns):
            a = alpha_eff[i]
            cl = self.sections[i].cl_of(a) if self.sections is not None else 0.1097 * a
            T_station[i] = 0.5 * self.rho * U[i] ** 2 * cl * self.c_mid[i] * self.dr[i]
        if T_station.sum() <= 0:
            T_station = np.ones(self.Ns)
        idx = [i for i in range(self.Ns) if T_station[i] > 0.0]
        P_axial = P_swirl = v_area = vi_disk = 0.0
        if idx:
            pts = []
            dA = []
            for i in idx:
                rr_ = self.r_mid[i]
                for m in range(n_ang):
                    ang = 2 * np.pi * m / n_ang
                    pts.append([rr_ * np.cos(ang), rr_ * np.sin(ang),
                                self.coll_rows[1][i, 2]])
                dA.append(2 * np.pi * rr_ * self.dr[i])
            pts = np.ascontiguousarray(np.array(pts))
            vv = np.zeros_like(pts)
            velocity_at_points(wsegs, wgam, wrc2, pts, vv)
            n_st = len(idx)
            vax = (-vv[:, 2]).reshape(n_st, n_ang)             # axial induced
            rxy = np.maximum(np.hypot(pts[:, 0], pts[:, 1]).reshape(n_st, n_ang), 1e-6)
            vth = ((-pts[:, 1] * vv[:, 0] + pts[:, 0] * vv[:, 1])
                   .reshape(n_st, n_ang) / rxy)                # swirl component
            T_s = T_station[idx]
            dA = np.array(dA)
            vi_ann = vax.mean(axis=1)
            # T_station is per blade; the disk ledger is for the whole rotor
            P_axial = float(self.B * np.sum(T_s * vi_ann))
            v_area = float(np.sum(vi_ann * dA) / dA.sum())
            P_swirl = float(np.sum(0.5 * self.rho * vth ** 2
                                   * np.clip(vax, 0.0, None)
                                   * (dA[:, None] / n_ang)))
            vi_disk = max(P_axial / max(thrust, 1e-9), 0.0)
        P_nonuniform = P_axial - thrust * max(v_area, 0.0)
        # kappa_cal (A4): ONE global scalar calibrated on the benchmark core
        # set (C-T theta>=8 matched-thrust CQ, min-max centering -> 1.03),
        # absorbing residual modeling bias (far-wake swirl KE beyond the
        # disk-plane sample, stall-adjacent profile drag). NOT the removed
        # kappa_B blanket (which multiplied every case's wake induction
        # unconditionally); kappa_cal is recorded with provenance in
        # docs/FM075_PLAN.md and defaults to 1.0 (raw physical accounting).
        kappa_cal = float(getattr(self, 'kappa_cal', 1.0))
        P_ind = (P_axial + P_swirl) * kappa_cal
        power = P_ind + P_prof
        torque = power / self.Omega
        # coefficient conventions (2026-10-24 fix): CT = T/(rho Om^2 pi R^4),
        # CQ = Q/(rho Om^2 pi R^5) -- the previous CQ used R^4, carrying a
        # spurious xR factor that contaminated every benchmark CQ/FM-coefficient
        # readout for R != 1 (physics in watts/N-m was always correct).
        q_ct = self.rho * (self.Omega * self.blade.R) ** 2 * np.pi * self.blade.R ** 2
        q_cq = q_ct * self.blade.R
        self._last_alpha = alpha_eff
        res = dict(thrust=thrust, torque=torque, power=power,
                   CT=thrust / q_ct, CQ=torque / q_cq,
                   P_ind=P_ind, P_axial=P_axial, P_swirl=P_swirl,
                   P_nonuniform=P_nonuniform, P_prof=P_prof,
                   vi_disk=vi_disk, v_area=v_area, kappa_cal=kappa_cal)
        self._last_loads = res
        return res

    def gamma_from_sections(self, wsegs, wgam, wrc2):
        """New station circulations consistent with 2D tables at local conditions."""
        alpha, U, _, _ = self.section_state(wsegs, wgam, wrc2)
        G = np.zeros(self.Ns)
        for i in range(self.Ns):
            a = float(np.clip(alpha[i], -35.0, 35.0))
            if self.sections is not None:
                cl = self.sections[i].cl_of(a)
            else:
                cl = 0.1097 * a
            G[i] = 0.5 * cl * self.c_mid[i] * U[i]
        return G

    # ------------------------------------------------------------------ main
    def solve(self, n_outer=30, n_sweeps=3, tol=3e-4, ct_guess=0.01):
        self.init_wake(ct_guess=ct_guess)
        self.relax_it = 1.0
        w_rel = getattr(self, 'gamma_relax', 0.4)
        hist = []
        wsegs, wgam, wrc2 = self.wake_arrays(self.Gamma)
        res = None
        converged = False
        it = 0
        for it in range(n_outer):
            G_new = self.gamma_from_sections(wsegs, wgam, wrc2)
            dG = np.abs(G_new - self.Gamma).max() if it > 0 else np.inf
            self.Gamma = (1.0 - w_rel) * self.Gamma + w_rel * G_new
            wsegs, wgam, wrc2 = self.relax_wake(self.Gamma, n_sweeps)
            res = self.loads(self.Gamma, wsegs, wgam, wrc2)
            hist.append((res['CT'], res['CQ']))
            if self.verbose:
                print(f"  it {it}: CT={res['CT']:.5f} CQ={res['CQ']:.6f} dG={dG:.2e}")
            if it > 2 and dG < tol * max(np.abs(self.Gamma).max(), 1e-6):
                converged = True
                break
        ct, cq = res['CT'], res['CQ']
        fm = ct ** 1.5 / (np.sqrt(2.0) * cq) if cq > 0 else 0.0
        return HoverResult(ct, cq, cq, fm, res['thrust'], res['torque'], res['power'],
                           self.Gamma.copy(), converged, it + 1, hist)
