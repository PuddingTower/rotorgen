"""Airfoil geometry: CST generator, NACA generators, I/O, resampling, blunt-TE handling.

Conventions
-----------
- Airfoil stored as one closed loop of nodes ordered: TE_upper -> upper -> LE -> lower -> TE_lower,
  (clockwise when viewed with x right / y up, interior on the right of travel).
- Unit chord, LE at x=0, TE at x=1. Blunt trailing edges keep two distinct TE nodes;
  the base segment (TE_upper - TE_lower) is part of the solid outline.
- ``te_gap`` = physical TE thickness (per unit chord), i.e. distance between TE_upper and TE_lower.
"""
from __future__ import annotations
import numpy as np
from dataclasses import dataclass, field

# ----------------------------------------------------------------------------- utilities

def _cosine(n: int) -> np.ndarray:
    """Cosine-spaced points in (0,1), endpoints excluded-included via half offsets."""
    return 0.5 * (1.0 - np.cos(np.linspace(0.0, np.pi, n)))


def bernstein_basis(x: np.ndarray, i: int, n: int) -> np.ndarray:
    from math import comb
    return comb(n, i) * x**i * (1.0 - x) ** (n - i)


def shape_function(x: np.ndarray, coeffs: np.ndarray) -> np.ndarray:
    """Sum of Bernstein polynomials (coeffs length N+1, order N)."""
    N = len(coeffs) - 1
    out = np.zeros_like(x)
    for i, a in enumerate(coeffs):
        out += a * bernstein_basis(x, i, N)
    return out


def class_function(x: np.ndarray, N1: float = 0.5, N2: float = 1.0) -> np.ndarray:
    return x**N1 * (1.0 - x) ** N2


# ----------------------------------------------------------------------------- Airfoil class

@dataclass
class Airfoil:
    x: np.ndarray          # (M,) node coordinates, loop TEu->u->LE->l->TEl
    y: np.ndarray
    name: str = "airfoil"
    _cache: dict = field(default_factory=dict, repr=False)

    # ---- basic geometry properties
    @property
    def te_gap(self) -> float:
        """TE thickness (Euclidean distance TE_upper to TE_lower)."""
        return float(np.hypot(self.x[0] - self.x[-1], self.y[0] - self.y[-1]))

    @property
    def thickness(self) -> float:
        """Max thickness / chord."""
        t, _ = self.thickness_distribution()
        return float(t.max())

    @property
    def camber_max(self) -> float:
        cm, _ = self.camber_distribution()
        return float(np.max(np.abs(cm)))

    def thickness_distribution(self, n: int = 160):
        xs = np.linspace(0.0, 1.0, n)
        yu = np.interp(xs, self.x_upper[::-1], self.y_upper[::-1])
        yl = np.interp(xs, self.x_lower, self.y_lower)
        return (yu - yl), xs

    def camber_distribution(self, n: int = 160):
        xs = np.linspace(0.0, 1.0, n)
        yu = np.interp(xs, self.x_upper[::-1], self.y_upper[::-1])
        yl = np.interp(xs, self.x_lower, self.y_lower)
        return 0.5 * (yu + yl), xs

    @property
    def n(self) -> int:
        return len(self.x)

    # upper runs from index 0 (TE) to LE; lower from LE to TE (index n-1)
    @property
    def x_upper(self):
        return self.x[: self._ile + 1]

    @property
    def y_upper(self):
        return self.y[: self._ile + 1]

    @property
    def x_lower(self):
        return self.x[self._ile :]

    @property
    def y_lower(self):
        return self.y[self._ile :]

    @property
    def _ile(self) -> int:
        if "_ile_v" not in self._cache:
            self._cache["_ile_v"] = int(np.argmin(self.x))
        return self._cache["_ile_v"]

    def le_radius(self) -> float:
        """Leading-edge radius by circle fit through LE and two near points."""
        i = self._ile
        idx = [i - 2, i - 1, i, i + 1, i + 2]
        pts = np.array([self.x[j % self.n] for j in idx]), np.array([self.y[j % self.n] for j in idx])
        x0, y0 = pts[0] - pts[0][2], pts[1] - pts[1][2]
        # fit circle x^2+y^2 = 2 R (cx, cy)·(x,y)  -> linear least squares
        A = np.column_stack([x0, y0])
        b = 0.5 * (x0**2 + y0**2)
        cx, cy = np.linalg.lstsq(A, b, rcond=None)[0]
        return float(np.hypot(cx, cy))

    # ---- transforms
    def scaled(self, scale: float) -> "Airfoil":
        return Airfoil(self.x * scale, self.y * scale, self.name)

    def close_te(self, frac: float = 0.0) -> "Airfoil":
        """Squeeze TE gap to frac of current (frac=0 -> sharp)."""
        g = self.te_gap
        if g < 1e-12:
            return self
        # linearly taper the gap over the whole surface
        xs = self.x.copy()
        dx_u = xs[0]
        dx_l = 1.0 - xs[-1]
        y = self.y.copy()
        # move TEu down, TEl up proportionally, weighted by proximity to TE
        wu = np.zeros_like(xs); wu[: self._ile + 1] = 1.0 - xs[: self._ile + 1] / max(dx_u, 1e-9)
        wl = np.zeros_like(xs); wl[self._ile :] = 1.0 - (1.0 - xs[self._ile :]) / max(dx_l, 1e-9)
        y[: self._ile + 1] -= 0.5 * g * (1.0 - frac) * wu
        y[self._ile :] += 0.5 * g * (1.0 - frac) * wl
        return Airfoil(xs, y, self.name + "_cte")

    def resample(self, n_per_side: int = 100, te_gap_abs: float | None = None) -> "Airfoil":
        """Resample with cosine spacing. If te_gap_abs given (absolute gap in chord units),
        enforce exactly that TE thickness by moving TE nodes vertically."""
        s = _cosine(n_per_side)                 # 0 at LE -> 1 at TE, clustered both ends
        xu = s.copy()                           # LE -> TE
        xl = s.copy()
        yu = np.interp(xu, self.x_upper[::-1], self.y_upper[::-1])
        yl = np.interp(xl, self.x_lower, self.y_lower)
        if te_gap_abs is not None:
            yu[-1] = yl[-1] + te_gap_abs
        x = np.concatenate([xu[::-1], xl[1:]])   # TE -> upper -> LE -> lower -> TE
        y = np.concatenate([yu[::-1], yl[1:]])
        af = Airfoil(x, y, self.name)
        return af

    def rotated(self, deg: float) -> "Airfoil":
        t = np.deg2rad(deg)
        R = np.array([[np.cos(t), -np.sin(t)], [np.sin(t), np.cos(t)]])
        xy = R @ np.vstack([self.x, self.y])
        return Airfoil(xy[0], xy[1], self.name)

    def translated(self, dx=0.0, dy=0.0) -> "Airfoil":
        return Airfoil(self.x + dx, self.y + dy, self.name)

    # ---- IO
    @staticmethod
    def from_dat(path: str, name: str | None = None) -> "Airfoil":
        pts = []
        with open(path, "r", errors="ignore") as f:
            lines = f.readlines()
        start = 0
        # skip header line if it is not numeric
        while start < len(lines):
            parts = lines[start].split()
            if len(parts) >= 2:
                try:
                    float(parts[0]); float(parts[1]); break
                except ValueError:
                    start += 1
            else:
                start += 1
        for ln in lines[start:]:
            parts = ln.split()
            if len(parts) < 2:
                continue
            try:
                a, b = float(parts[0]), float(parts[1])
            except ValueError:
                continue
            pts.append((a, b))
        if len(pts) < 20:
            raise ValueError(f"bad dat file: {path}")
        P = np.array(pts)
        # normalize: unit chord, LE at origin
        xmin, xmax = P[:, 0].min(), P[:, 0].max()
        c = xmax - xmin
        P = (P - [xmin, P[:, 1].min() + (P[:, 1].max() - P[:, 1].min()) / 2])  # rough center
        P[:, 0] /= c; P[:, 1] /= c
        # order loop TE->upper->LE->lower->TE (Selig format: TE->upper->LE->lower->TE already)
        ile = int(np.argmin(P[:, 0]))
        up = P[: ile + 1]
        lo = P[ile:]
        if up[0, 0] < lo[-1, 0]:  # starts from lower side? reorder
            P = np.roll(P, -1, axis=0)  # try simple fix
        return Airfoil(P[:, 0], P[:, 1], name or path.split("/")[-1])

    def to_dat(self, path: str) -> None:
        with open(path, "w") as f:
            f.write(self.name + "\n")
            for xi, yi in zip(self.x, self.y):
                f.write(f"{xi: .6f} {yi: .6f}\n")

    def summary(self) -> str:
        t, xt = self.thickness_distribution()
        return (f"{self.name}: t/c={self.thickness:.4f} (x/c={xt[np.argmax(t)]:.3f}), "
                f"camber={self.camber_max:.4f}, te_gap={self.te_gap:.5f}, n={self.n}")


# ----------------------------------------------------------------------------- generators

def naca4(digits: str = "0012", n_per_side: int = 120, te_gap: float | None = None,
          close_te: bool = False) -> Airfoil:
    """NACA 4-digit series (exact analytic thickness + camber), cosine spacing.
    te_gap overrides final TE thickness (per chord)."""
    m = int(digits[0]) / 100.0        # max camber
    p = int(digits[1]) / 10.0         # camber position
    tt = int(digits[2:]) / 100.0      # max thickness
    a4 = -0.1036 if close_te else -0.1015
    beta = np.linspace(0.0, np.pi, n_per_side)
    x = 0.5 * (1.0 - np.cos(beta))    # clustered at both ends
    yt = 5.0 * tt * (0.2969 * np.sqrt(x) - 0.1260 * x - 0.3516 * x**2
                     + 0.2843 * x**3 + a4 * x**4)
    if te_gap is not None:
        yt = yt + 0.5 * (te_gap - 2 * yt[-1]) * x**2  # taper correction keeping LE fixed
    if m > 0:
        yc = np.where(x < p, m / p**2 * (2 * p * x - x**2),
                      m / (1 - p) ** 2 * ((1 - 2 * p) + 2 * p * x - x**2))
        dyc = np.where(x < p, 2 * m / p**2 * (p - x), 2 * m / (1 - p) ** 2 * (p - x))
    else:
        yc = np.zeros_like(x); dyc = np.zeros_like(x)
    th = np.arctan(dyc)
    xu, yu = x - yt * np.sin(th), yc + yt * np.cos(th)
    xl, yl = x + yt * np.sin(th), yc - yt * np.cos(th)
    X = np.concatenate([xu[::-1], xl[1:]])
    Y = np.concatenate([yu[::-1], yl[1:]])
    return Airfoil(X, Y, f"NACA{digits}")


def naca0012(n_per_side: int = 120, **kw) -> Airfoil:
    return naca4("0012", n_per_side, **kw)


def cst_airfoil(coeffs_u: np.ndarray, coeffs_l: np.ndarray,
                te_gap: float = 0.0, n_per_side: int = 100,
                yte_u: float | None = None, yte_l: float | None = None,
                name: str = "CST") -> Airfoil:
    """CST airfoil with exact TE thickness.

    y_u(x) = C(x) S_u(x) + x * yTE_u
    y_l(x) = C(x) S_l(x) + x * yTE_l
    te_gap = yTE_u - yTE_l  (vertical TE opening; for small gaps ~ Euclidean thickness)

    If yte_u/l not given, symmetric split of te_gap.
    """
    x = _cosine(n_per_side)
    C = class_function(x)
    su = shape_function(x, np.asarray(coeffs_u))
    sl = shape_function(x, np.asarray(coeffs_l))
    if yte_u is None:
        yte_u, yte_l = 0.5 * te_gap, -0.5 * te_gap
    yu = C * su + x * yte_u
    yl = C * sl + x * yte_l
    X = np.concatenate([x[::-1], x[1:]])
    Y = np.concatenate([yu[::-1], yl[1:]])
    return Airfoil(X, Y, name)


def fit_cst(af: Airfoil, n_coeff: int = 7, te_gap: float | None = None) -> tuple[np.ndarray, np.ndarray]:
    """Least-squares CST fit of an existing airfoil (upper/lower). Returns (Au, Al)."""
    if te_gap is None:
        te_gap = af.te_gap
    yte_u, yte_l = 0.5 * te_gap, -0.5 * te_gap
    B = np.column_stack([bernstein_basis(af.x_upper[::-1], i, n_coeff - 1)
                         for i in range(n_coeff)])
    C = class_function(af.x_upper[::-1])
    rhs = af.y_upper[::-1] - af.x_upper[::-1] * yte_u
    Au = np.linalg.lstsq(B * C[:, None], rhs, rcond=None)[0]
    B = np.column_stack([bernstein_basis(af.x_lower, i, n_coeff - 1) for i in range(n_coeff)])
    C = class_function(af.x_lower)
    rhs = af.y_lower - af.x_lower * yte_l
    Al = np.linalg.lstsq(B * C[:, None], rhs, rcond=None)[0]
    return Au, Al


# ----------------------------------------------------------------------------- self-test

if __name__ == "__main__":
    af = naca0012()
    print(af.summary())
    af2 = cst_airfoil(np.array([0.2, 0.3, 0.2, 0.1, 0.05]), -np.array([0.2, 0.3, 0.2, 0.1, 0.05]),
                      te_gap=0.01)
    print(af2.summary())
    Au, Al = fit_cst(af, 7)
    fit = cst_airfoil(Au, Al, te_gap=af.te_gap)
    err_u = np.abs(np.interp(af.x_upper, fit.x_upper[::-1], fit.y_upper[::-1]) - af.y_upper).max()
    err_l = np.abs(np.interp(af.x_lower, fit.x_lower, fit.y_lower) - af.y_lower).max()
    print(f"CST fit of NACA0012: max |dy| upper={err_u:.2e} lower={err_l:.2e}")
