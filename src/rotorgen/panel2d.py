"""2D linear-vorticity panel solver — stream-function (Dirichlet) formulation.

My implementation of the classic XFOIL/mfoil inviscid formulation (Drela 1989;
Fidkowski mfoil notes), adapted to this project's conventions:

- Nodes ordered CLOCKWISE: node 0 = TE_lower -> lower -> LE -> upper -> node N-1 = TE_upper.
- Unknowns: vortex sheet strength gamma_i at N nodes + surface streamfunction psi_s.
- Equations: psi(node_i) = psi_s for i=0..N-1  (surface is a streamline),
  + Kutta: gamma[0] + gamma[N-1] = 0 (equal TE upper/lower velocities).
- Blunt TE: extra constant-source + constant-vortex panel across the TE gap whose
  strength is tied to the jump (gamma[N-1] - gamma[0]) via the bisector geometry
  (tcp = |t x p|, tdp = t.p, t = TE bisector, p = unit TE connector lower->upper).
  This regularizes the TE corner (removes the inviscid corner singularity mode).
- Sharp TE: the (N-1)-th psi row is replaced by a gamma-curvature extrapolation row
  [1,-2,1,-1,2,-1] (finite sheet curvature at TE).
- The system matrix depends only on geometry: it is built once and factored once;
  solutions for the two unit freestreams (alpha=0, 90deg) give gam0, gam90, from
  which gamma(alpha) = gam0*cos(alpha) + gam90*sin(alpha)  -> O(N) per angle.

Kernels (panel frame: t along panel 1->2, n = (-ty, tx), evaluation at (x,z),
panel spans [0,d], r1 = |(x,z)|, r2 = |(x-d,z)|, th1 = atan2(z,x), th2 = atan2(z,x-d)):

  stream function (a*g1 + b*g2):
    P1 = (1/2pi) [ z(th2-th1) - d + x ln r1 - (x-d) ln r2 ]
    P2 = x P1 + (1/2pi) [ 0.5 r2^2 ln r2 - 0.5 r1^2 ln r1 - r2^2/4 + r1^2/4 ]
    a = P1 - P2/d,   b = P2/d
  velocity (u,g1 + w,g2 vectors in panel frame), general point:
    T1 = (th2-th1)/(2pi);   T2 = [ 2z(ln r1 - ln r2) - 2x(th2-th1) ] / (4 pi d)
    ug1 = T1 + T2,   ug2 = -T2
    T3 = (ln r2 - ln r1)/(2pi);  T4 = [ x(ln r1 - ln r2) - d + z(th2-th1) ] / (2 pi d)
    wg1 = T3 + T4,   wg2 = -T4
  velocity at panel's own midpoint (special case):
    ug1 = ug2 = 1/4;   wg1 = -1/(2pi), wg2 = +1/(2pi)
  constant-source panel velocity:  u = (1/2pi) ln(r1/r2),  w = (1/2pi)(th2 - th1)
"""
from __future__ import annotations
import numpy as np
from dataclasses import dataclass

from .airfoil import Airfoil

TWOPI = 2.0 * np.pi


def _te_info(X: np.ndarray):
    """TE geometry: t = gap bisector (wake direction), p = unit connector lower->upper."""
    t1 = X[:, 0] - X[:, 1]; t1 = t1 / np.linalg.norm(t1)     # lower-TE tangent
    t2 = X[:, -1] - X[:, -2]; t2 = t2 / np.linalg.norm(t2)   # upper-TE tangent
    t = 0.5 * (t1 + t2); t = t / np.linalg.norm(t)
    s = X[:, -1] - X[:, 0]
    hTE = -s[0] * t[1] + s[1] * t[0]
    snorm = np.linalg.norm(s)
    if snorm < 1e-15:
        p = np.array([-t[1], t[0]])
        tcp, tdp = 0.0, 1.0
    else:
        p = s / snorm
        tcp = abs(t[0] * p[1] - t[1] * p[0])
        tdp = float(t @ p)
    return t, hTE, tcp, tdp


class PanelSolver:
    """Build+factor the geometry system once; sweep angles at O(N) each."""

    def __init__(self, af: Airfoil):
        self.af = af
        loop = np.column_stack([af.x, af.y])            # CCW TEu->u->LE->l->TEl
        X = np.ascontiguousarray(loop[::-1].T)          # CW: X[:,0]=TEl ... X[:,-1]=TEu
        self.X = X
        N = X.shape[1]
        self.N = N
        P = X[:, 1:] - X[:, :-1]
        d = np.linalg.norm(P, axis=0)
        self.panel_t = P / d                            # (2, N-1)
        self.panel_n = np.vstack([-self.panel_t[1], self.panel_t[0]])
        self.panel_d = d
        self.panel_mid = 0.5 * (X[:, :-1] + X[:, 1:])
        self.t_te, self.hTE, self.tcp, self.tdp = _te_info(X)
        self.anchor = X.mean(axis=1)
        self._build_system()
        self._solve_unit()
        self._build_velocity_matrices()
        self._build_source_matrices()

    # ------------------------------------------------------------------ viscous (transpiration)
    def _build_source_matrices(self):
        """Matrices for transpiration coupling: constant source sheet sigma=2*vw per panel.
        Msrc[i, j]: psi difference (node_i - anchor) from unit source on panel j.
        Vsrc[:, i, j]: velocity at midpoint i from unit source on panel j."""
        N = self.N
        Np = N - 1
        Msrc = np.zeros((N, Np))
        Vsrc = np.zeros((2, Np, Np))
        for j in range(Np):
            Xj = np.array([[self.X[0, j], self.X[0, j + 1]],
                           [self.X[1, j], self.X[1, j + 1]]])
            for i in range(N):
                xi = self.X[:, i:i + 1]
                Msrc[i, j] = (self._constsource_stream_te(Xj, xi)
                              - self._constsource_stream_te(Xj, self.anchor[:, None]))
            # velocity at all midpoints (unit source)
            v = self._constsource_velocity(j, self.panel_mid)
            Vsrc[:, :, j] = v
        self._Msrc = Msrc
        self._Vsrc = Vsrc

    def solve_with_transpiration(self, alpha_deg: float, vw: np.ndarray):
        """Solve gamma with panel-normal transpiration vw (Np,). Returns gamma nodes."""
        N = self.N
        al = np.deg2rad(alpha_deg)
        rhs = np.zeros(N + 1)
        psi_inf_n = np.cos(al) * self.X[1] - np.sin(al) * self.X[0]
        psi_inf_a = np.cos(al) * self.anchor[1] - np.sin(al) * self.anchor[0]
        rhs[:N] = -(psi_inf_n - psi_inf_a)
        rhs[:N] -= self._Msrc @ (2.0 * vw)
        return _lu_solve(self._lu, rhs)[:N]

    def ue_from_gamma(self, gamma_nodes: np.ndarray, alpha_deg: float) -> np.ndarray:
        """Edge velocities at midpoints from given node gammas (no source terms)."""
        ca, sa = np.cos(np.deg2rad(alpha_deg)), np.sin(np.deg2rad(alpha_deg))
        v = (np.einsum('cmk,k->cm', self._Amid, gamma_nodes)
             + _applyB(self._Bmid, gamma_nodes)
             + np.array([[ca], [sa]]))
        return np.einsum('cm,cm->m', v, self.panel_t)

    def ue_source_contrib(self, vw: np.ndarray) -> np.ndarray:
        """Tangential midpoint velocity from transpiration source sheets."""
        vt = np.einsum('cmk,k->m', self._Vsrc, 2.0 * vw)
        return vt

    # ------------------------------------------------------------------ system build
    def _panel_frame(self, j: int, pts: np.ndarray):
        """Transform points (2, M) into panel-j frame: x, z, r1, r2, th1, th2."""
        xz = pts - self.X[:, j:j + 1]
        x = self.panel_t[:, j] @ xz
        z = self.panel_n[:, j] @ xz
        r1 = np.hypot(x, z)
        r2 = np.hypot(x - self.panel_d[j], z)
        th1 = np.arctan2(z, x)
        th2 = np.arctan2(z, x - self.panel_d[j])
        return x, z, r1, r2, th1, th2

    def _linvortex_stream(self, j: int, pts: np.ndarray):
        x, z, r1, r2, th1, th2 = self._panel_frame(j, pts)
        dj = self.panel_d[j]
        eps = 1e-9
        lr1 = np.where(r1 < eps, 0.0, np.log(np.maximum(r1, eps)))
        lr2 = np.where(r2 < eps, 0.0, np.log(np.maximum(r2, eps)))
        P1 = (0.5 / np.pi) * (z * (th2 - th1) - dj + x * lr1 - (x - dj) * lr2)
        P2 = x * P1 + (0.5 / np.pi) * (0.5 * r2**2 * lr2 - 0.5 * r1**2 * lr1
                                       - 0.25 * r2**2 + 0.25 * r1**2)
        return P1 - P2 / dj, P2 / dj

    def _linvortex_velocity(self, j: int, pts: np.ndarray, onmid_mask=None):
        """Velocity influence vectors (2,M) for unit (g1, g2), global components."""
        x, z, r1, r2, th1, th2 = self._panel_frame(j, pts)
        dj = self.panel_d[j]
        eps = 1e-9
        lr1 = np.where(r1 < eps, 0.0, np.log(np.maximum(r1, eps)))
        lr2 = np.where(r2 < eps, 0.0, np.log(np.maximum(r2, eps)))
        t1e = np.where(r1 < eps, np.pi, th1)
        t2e = np.where(r2 < eps, 0.0, th2)
        T1 = (t2e - t1e) / TWOPI
        T2 = (2 * z * (lr1 - lr2) - 2 * x * (t2e - t1e)) / (4 * np.pi * dj)
        ug1, ug2 = T1 + T2, -T2
        T3 = (lr2 - lr1) / TWOPI
        T4 = (x * (lr1 - lr2) - dj + z * (t2e - t1e)) / (TWOPI * dj)
        wg1, wg2 = T3 + T4, -T4
        if onmid_mask is not None:
            # midpoint self-evaluation special case
            ug1 = np.where(onmid_mask, 0.25, ug1)
            ug2 = np.where(onmid_mask, 0.25, ug2)
            wg1 = np.where(onmid_mask, -1.0 / TWOPI, wg1)
            wg2 = np.where(onmid_mask, 1.0 / TWOPI, wg2)
        tj, nj = self.panel_t[:, j], self.panel_n[:, j]
        a = ug1[None, :] * tj[:, None] + wg1[None, :] * nj[:, None]
        b = ug2[None, :] * tj[:, None] + wg2[None, :] * nj[:, None]
        return a, b

    def _constsource_velocity(self, j: int, pts: np.ndarray):
        x, z, r1, r2, th1, th2 = self._panel_frame(j, pts)
        eps = 1e-9
        lr1 = np.where(r1 < eps, 0.0, np.log(np.maximum(r1, eps)))
        lr2 = np.where(r2 < eps, 0.0, np.log(np.maximum(r2, eps)))
        t1e = np.where(r1 < eps, np.pi, th1)
        t2e = np.where(r2 < eps, 0.0, th2)
        u = (0.5 / np.pi) * (lr1 - lr2)
        w = (0.5 / np.pi) * (t2e - t1e)
        tj, nj = self.panel_t[:, j], self.panel_n[:, j]
        return u[None, :] * tj[:, None] + w[None, :] * nj[:, None]

    def _build_system(self):
        N = self.N
        X = self.X
        A = np.zeros((N + 1, N + 1))
        rhs = np.zeros((N + 1, 2))
        nodes = X                                       # collocation AT nodes
        for i in range(N):
            xi = X[:, i:i + 1]
            for j in range(N - 1):
                aij, bij = self._linvortex_stream(j, xi)
                A[i, j] += aij[0]
                A[i, j + 1] += bij[0]
            A[i, N] = -1.0
            rhs[i, 0] = -X[1, i]
            rhs[i, 1] = X[0, i]
            # TE gap panels (from node N-1 (TEu) to node 0 (TEl))
            Xte = np.array([[X[0, N-1], X[0, 0]], [X[1, N-1], X[1, 0]]])
            jte = self.N - 1  # use last-panel index space: handled explicitly
            # source panel strength sigma = 0.5*tcp*(g[N-1] - g[0])
            a_src = self._constsource_stream_te(Xte, xi)
            A[i, 0] += -a_src * (0.5 * self.tcp)
            A[i, N - 1] += a_src * (0.5 * self.tcp)
            # vortex panel strength = -0.5*tdp*(g[N-1] - g[0])
            a_te, b_te = self._linvortex_stream_te(Xte, xi)
            A[i, 0] += -(a_te + b_te) * (-0.5 * self.tdp)
            A[i, N - 1] += (a_te + b_te) * (-0.5 * self.tdp)
        nogap = abs(self.hTE) < 1e-10
        if nogap:
            A[N - 1, :] = 0.0
            A[N - 1, [0, 1, 2, N - 3, N - 2, N - 1]] = [1, -2, 1, -1, 2, -1]
        A[N, 0] = 1.0
        A[N, N - 1] = 1.0
        self._A = A
        self._rhs = rhs
        self._lu = _lu_factor(A)
        self.nogap = nogap

    # TE-gap helper kernels (panels defined by two arbitrary endpoint coords)
    def _constsource_stream_te(self, Xte, xi):
        """Streamfunction of unit constant-source panel (NFoil panel_constsource_stream)."""
        t = Xte[:, 1] - Xte[:, 0]; d = np.linalg.norm(t)
        if d < 1e-15:
            return 0.0
        t = t / d; n = np.array([-t[1], t[0]])
        xz = xi - Xte[:, :1]
        x = t @ xz; z = n @ xz
        r1 = np.hypot(x, z); r2 = np.hypot(x - d, z)
        th1 = np.arctan2(z, x); th2 = np.arctan2(z, x - d)
        lr1 = 0.0 if r1 < 1e-9 else np.log(r1)
        lr2 = 0.0 if r2 < 1e-9 else np.log(r2)
        t1e = np.pi if r1 < 1e-9 else th1
        t2e = 0.0 if r2 < 1e-9 else th2
        P = (x * (t1e - t2e) + d * t2e + z * (lr1 - lr2)) / TWOPI
        P = (P - 0.25 * d) if ((t1e + t2e) > np.pi) else (P + 0.75 * d)
        return P[0] if np.ndim(P) else P

    def _linvortex_stream_te(self, Xte, xi):
        t = Xte[:, 1] - Xte[:, 0]; d = np.linalg.norm(t)
        if d < 1e-15:
            return 0.0, 0.0
        t = t / d; n = np.array([-t[1], t[0]])
        xz = xi - Xte[:, :1]
        x = t @ xz; z = n @ xz
        r1 = np.hypot(x, z); r2 = np.hypot(x - d, z)
        th1 = np.arctan2(z, x); th2 = np.arctan2(z, x - d)
        lr1 = 0.0 if r1 < 1e-9 else np.log(r1)
        lr2 = 0.0 if r2 < 1e-9 else np.log(r2)
        P1 = (0.5 / np.pi) * (z * (th2 - th1) - d + x * lr1 - (x - d) * lr2)
        P2 = x * P1 + (0.5 / np.pi) * (0.5 * r2**2 * lr2 - 0.5 * r1**2 * lr1
                                       - 0.25 * r2**2 + 0.25 * r1**2)
        p1 = (P1 - P2 / d); p2 = P2 / d
        return (p1[0] if np.ndim(p1) else p1), (p2[0] if np.ndim(p2) else p2)

    def _solve_unit(self):
        N = self.N
        g = _lu_solve(self._lu, self._rhs)
        self.gam0 = g[:N, 0].copy()   # unit stream at alpha = 0
        self.gam90 = g[:N, 1].copy()  # unit stream at alpha = 90
        self.psi_s0, self.psi_s90 = g[N, 0], g[N, 1]

    # ------------------------------------------------------------------ velocities
    def _build_velocity_matrices(self):
        """ue influence: velocities at panel midpoints from all panels + TE panels."""
        N = self.N
        Np = N - 1
        mids = self.panel_mid
        # contribution to midpoint velocity: A_mid[:, k] g_k + B_mid[:, k] g_{k+1}
        A_mid = np.zeros((2, Np, N))   # [component, midpoint, node]
        B_mid = np.zeros((2, Np, N))
        for j in range(Np):
            a, b = self._linvortex_velocity(j, mids, onmid_mask=None)
            # a[:, m] multiplies g_j ; b[:, m] multiplies g_{j+1}
            A_mid[:, :, j] += a
            B_mid[:, :, j] += b
            # correct the diagonal (self) midpoints with the special case
            A_mid[:, j, j] = 0.0; B_mid[:, j, j] = 0.0
            tj, nj = self.panel_t[:, j], self.panel_n[:, j]
            A_mid[0, j, j] = 0.25 * tj[0] + (-1.0 / TWOPI) * nj[0]
            A_mid[1, j, j] = 0.25 * tj[1] + (-1.0 / TWOPI) * nj[1]
            B_mid[0, j, j] = 0.25 * tj[0] + (1.0 / TWOPI) * nj[0]
            B_mid[1, j, j] = 0.25 * tj[1] + (1.0 / TWOPI) * nj[1]
        # TE gap panel contributions (strengths tied to g_0, g_{N-1})
        Xte = np.array([[self.X[0, N-1], self.X[0, 0]], [self.X[1, N-1], self.X[1, 0]]])
        d_te = np.linalg.norm(Xte[:, 1] - Xte[:, 0])
        if d_te > 1e-12:
            t = (Xte[:, 1] - Xte[:, 0]) / d_te
            nvec = np.array([-t[1], t[0]])
            xz = mids - Xte[:, :1]
            x = t @ xz; z = nvec @ xz
            r1 = np.hypot(x, z); r2 = np.hypot(x - d_te, z)
            th1 = np.arctan2(z, x); th2 = np.arctan2(z, x - d_te)
            lr1 = np.where(r1 < 1e-9, 0.0, np.log(np.maximum(r1, 1e-9)))
            lr2 = np.where(r2 < 1e-9, 0.0, np.log(np.maximum(r2, 1e-9)))
            t1e = np.where(r1 < 1e-9, np.pi, th1)
            t2e = np.where(r2 < 1e-9, 0.0, th2)
            # const source: u = (1/2pi) ln(r1/r2); w = (1/2pi)(th2-th1); sigma=0.5 tcp (g_{N-1}-g_0)
            us = (0.5 / np.pi) * (lr1 - lr2)
            ws = (0.5 / np.pi) * (t2e - t1e)
            vs = us[None, :] * t[:, None] + ws[None, :] * nvec[:, None]
            A_mid[:, :, 0] += -vs * (0.5 * self.tcp)
            A_mid[:, :, N - 1] += vs * (0.5 * self.tcp)
            # const vortex: u = -(th2-th1)/2pi ; w = (1/2pi) ln(r1/r2); gamma = -0.5 tdp (g_{N-1}-g_0)
            uv = -(t2e - t1e)[None, :] / TWOPI * t[:, None] + (lr1 - lr2)[None, :] / TWOPI * nvec[:, None]
            A_mid[:, :, 0] += -uv * (-0.5 * self.tdp)
            A_mid[:, :, N - 1] += uv * (-0.5 * self.tdp)
        self._Amid = A_mid
        self._Bmid = B_mid
        self._Cmid0 = np.einsum('cmk,k->cm', A_mid, self.gam0) + _applyB(B_mid, self.gam0)
        self._Cmid90 = np.einsum('cmk,k->cm', A_mid, self.gam90) + _applyB(B_mid, self.gam90)

    def surface_velocity(self, alpha_deg: float) -> np.ndarray:
        """Inviscid edge speed (along panel travel direction) at panel midpoints."""
        al = np.deg2rad(alpha_deg)
        ca, sa = np.cos(al), np.sin(al)
        vel_vec = ca * self._Cmid0 + sa * self._Cmid90
        vel_vec = vel_vec + np.array([[ca], [sa]])
        return np.einsum('cm,cm->m', vel_vec, self.panel_t)

    def velocity(self, alpha_deg: float, pts: np.ndarray) -> np.ndarray:
        """Velocity at arbitrary points (2, M) from solved gammas + freestream."""
        al = np.deg2rad(alpha_deg)
        g = np.cos(al) * self.gam0 + np.sin(al) * self.gam90
        V = np.zeros_like(pts)
        N = self.N
        for j in range(N - 1):
            a, b = self._linvortex_velocity(j, pts)
            V += a * g[j] + b * g[j + 1]
        # TE panels
        Xte = np.array([[self.X[0, N-1], self.X[0, 0]], [self.X[1, N-1], self.X[1, 0]]])
        d_te = np.linalg.norm(Xte[:, 1] - Xte[:, 0])
        if d_te > 1e-12:
            t = (Xte[:, 1] - Xte[:, 0]) / d_te
            nvec = np.array([-t[1], t[0]])
            xz = pts - Xte[:, :1]
            x = t @ xz; z = nvec @ xz
            r1 = np.hypot(x, z); r2 = np.hypot(x - d_te, z)
            th1 = np.arctan2(z, x); th2 = np.arctan2(z, x - d_te)
            lr1 = np.where(r1 < 1e-9, 0.0, np.log(np.maximum(r1, 1e-9)))
            lr2 = np.where(r2 < 1e-9, 0.0, np.log(np.maximum(r2, 1e-9)))
            t1e = np.where(r1 < 1e-9, np.pi, th1)
            t2e = np.where(r2 < 1e-9, 0.0, th2)
            us = (0.5 / np.pi) * (lr1 - lr2); ws = (0.5 / np.pi) * (t2e - t1e)
            vs = us[None, :] * t[:, None] + ws[None, :] * nvec[:, None]
            V += vs * (0.5 * self.tcp * (g[N - 1] - g[0]))
            uv = -(t2e - t1e)[None, :] / TWOPI * t[:, None] + (lr1 - lr2)[None, :] / TWOPI * nvec[:, None]
            V += uv * (-0.5 * self.tdp * (g[N - 1] - g[0]))
        return V + np.array([[np.cos(al)], [np.sin(al)]])

    def gamma(self, alpha_deg: float) -> np.ndarray:
        al = np.deg2rad(alpha_deg)
        return np.cos(al) * self.gam0 + np.sin(al) * self.gam90

    def cp_distribution(self, alpha_deg: float, M: float = 0.0) -> np.ndarray:
        v = self.surface_velocity(alpha_deg)
        cp = 1.0 - v * v
        if M > 1e-6:
            beta = np.sqrt(1.0 - M * M)
            cp = cp / (beta + (M * M / (1.0 + beta)) * 0.5 * cp)
        return cp

    def loads(self, alpha_deg: float, M: float = 0.0) -> dict:
        cp = self.cp_distribution(alpha_deg, M)
        pf = -cp[None, :] * self.panel_d[None, :] * self.panel_n
        al = np.deg2rad(alpha_deg)
        ca, sa = np.cos(al), np.sin(al)
        fx, fy = pf[0].sum(), pf[1].sum()
        cl = fy * ca - fx * sa
        cd_p = fx * ca + fy * sa
        lever = self.panel_mid - np.array([[0.25], [0.0]])
        cm = (lever[0] * pf[1] - lever[1] * pf[0]).sum()
        return dict(cl=cl, cd_press=cd_p, cm=cm, cp=cp, ue=self.surface_velocity(alpha_deg))


def _applyB(B_mid, g):
    """B_mid[:, m, k] multiplies g_{k+1}: shift node index."""
    return np.einsum('cmk,k->cm', B_mid[:, :, :-1], g[1:])


def _lu_factor(A):
    from scipy.linalg import lu_factor
    return lu_factor(A)


def _lu_solve(lu_piv, b):
    from scipy.linalg import lu_solve
    return lu_solve(lu_piv, b)
