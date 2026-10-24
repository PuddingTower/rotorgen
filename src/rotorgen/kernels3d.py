"""Numba-parallel EXACT finite-segment Biot-Savart kernels.

For a straight vortex segment from x1 to x2 with circulation G and core rc:
    a = xp - x1, b = xp - x2
    denom = sqrt((|a|^2+rc^2)(|b|^2+rc^2)) + a.b
    v = G/(4 pi) * (a x b) * ( 1/sqrt(|a|^2+rc^2) + 1/sqrt(|b|^2+rc^2) ) / denom
(core-regularized form of the classic vortex-segment formula; exact for rc->0,
never singular, and correct at distances comparable to the segment length --
unlike the midpoint-lumped approximation which overestimates near fields).
"""
from __future__ import annotations
import numpy as np
from numba import njit, prange


@njit(parallel=True, cache=True, fastmath=True)
def velocity_at_points(segs, gam, rcs2, pts, out):
    n_seg = segs.shape[0]
    n_pts = pts.shape[0]
    for i in prange(n_pts):
        px = pts[i, 0]; py = pts[i, 1]; pz = pts[i, 2]
        sx = 0.0; sy = 0.0; sz = 0.0
        for j in range(n_seg):
            g = gam[j]
            if g == 0.0:
                continue
            ax = px - segs[j, 0]; ay = py - segs[j, 1]; az = pz - segs[j, 2]
            bx = px - segs[j, 3]; by = py - segs[j, 4]; bz = pz - segs[j, 5]
            a2 = ax * ax + ay * ay + az * az + rcs2[j]
            b2 = bx * bx + by * by + bz * bz + rcs2[j]
            adotb = ax * bx + ay * by + az * bz
            denom = np.sqrt(a2 * b2) + adotb
            if denom < 1e-12:
                continue
            ra = np.sqrt(a2); rb = np.sqrt(b2)
            coef = g * 0.25 / np.pi * (1.0 / ra + 1.0 / rb) / denom
            cx = ay * bz - az * by
            cy = az * bx - ax * bz
            cz = ax * by - ay * bx
            sx += cx * coef; sy += cy * coef; sz += cz * coef
        out[i, 0] += sx; out[i, 1] += sy; out[i, 2] += sz


@njit(parallel=True, cache=True, fastmath=True)
def velocity_at_points_zero(segs, gam, rcs2, pts, out):
    n_pts = pts.shape[0]
    for i in prange(n_pts):
        out[i, 0] = 0.0; out[i, 1] = 0.0; out[i, 2] = 0.0
    velocity_at_points(segs, gam, rcs2, pts, out)


def segments_from_filament(nodes, gam_per_node_age, rc2_per_age):
    p1 = nodes[:-1]
    p2 = nodes[1:]
    segs = np.concatenate([p1, p2], axis=1)
    gam = 0.5 * (gam_per_node_age[:-1] + gam_per_node_age[1:])
    rcs2 = 0.5 * (rc2_per_age[:-1] + rc2_per_age[1:])
    return segs, gam, rcs2


if __name__ == "__main__":
    import time
    nodes = np.zeros((200, 3)); nodes[:, 2] = np.linspace(0, 100, 200)
    segs = np.concatenate([nodes[:-1], nodes[1:]], axis=1)
    gam = np.full(len(segs), 1e-2)
    rc2 = np.full(len(segs), 1e-6)
    pts = np.array([[1.0, 0.0, 50.0]])
    out = np.zeros((1, 3))
    velocity_at_points_zero(segs, gam, rc2, pts, out)
    print("semi-infinite filament v_y (expect 0.01/(2 pi) ~ 0.00159):", out[0, 1])
    n_seg = 20000; n_pts = 5000
    segs = np.random.randn(n_seg, 6); gam = np.random.randn(n_seg)
    rc2 = np.full(n_seg, 1e-4); pts = np.random.randn(n_pts, 3)
    out = np.zeros((n_pts, 3))
    t0 = time.time(); velocity_at_points_zero(segs, gam, rc2, pts, out); t1 = time.time()
    print(f"perf: {n_seg*n_pts/(t1-t0)/1e6:.0f}M pairs/s")
