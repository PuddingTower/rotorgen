"""Isolate the vortex lattice: rectangular wing AR=6, alpha=5deg vs lifting-line."""
import sys
sys.path.insert(0, "E:/旋翼设计/src")
import numpy as np
from rotorgen.rotor3d import ring_segments, ring_influence_matrix

Ns, Nc = 40, 6          # spanwise cells, chordwise cells
span, chord = 6.0, 1.0  # AR=6

xs = np.linspace(-span / 2, span / 2, Ns + 1)
ys = np.linspace(0, chord, Nc + 1)
full = np.zeros((Ns + 1, Nc + 1, 3))
full[:, :, 0] = xs[:, None]
full[:, :, 1] = ys[None, :]

mid = 0.25 * (full[:-1, :-1] + full[1:, :-1] + full[1:, 1:] + full[:-1, 1:])   # (Ns, Nc, 3) cell centers
n_hat = np.zeros_like(mid); n_hat[:, :, 2] = 1.0

segs, ring_of, NsF, NcF = ring_segments(full)
n_ring = NsF * NcF
print(f"NsF={NsF} NcF={NcF} n_ring={n_ring} coll={mid.reshape(-1,3).shape}")

rc2 = np.full(len(segs), (0.02 * chord) ** 2)
A = np.zeros((n_ring, n_ring))
ring_influence_matrix(np.ascontiguousarray(segs), np.ascontiguousarray(ring_of),
                       np.ascontiguousarray(rc2),
                       np.ascontiguousarray(mid.reshape(-1, 3)),
                       np.ascontiguousarray(n_hat.reshape(-1, 3)), 1, n_ring, A)
alpha = np.deg2rad(5.0)
Uinf = np.array([0.0, np.cos(alpha), np.sin(alpha)])
rhs = -(Uinf @ n_hat.reshape(-1, 3).T)
G = np.linalg.solve(A, rhs)
g_col = G.reshape(NsF, NcF).sum(axis=1)
dr = np.diff(xs)
S_ref = span * chord
CL = 2.0 * np.sum(np.abs(g_col) * dr) / S_ref
AR = 6.0
CL_ll = 2 * np.pi * AR * np.sin(alpha) / (AR + 2)
print(f"wing AR=6 a=5deg: CL_lattice={CL:.4f}  CL_lifting_line={CL_ll:.4f}  ratio={CL/CL_ll:.3f}")
# local section Cl at centerline
ic = Ns // 2
cl_local = 2 * abs(g_col[ic]) / (chord)
print(f"center section Cl (2D-ish, expect ~0.55): {cl_local:.3f}")
print("g_col few:", np.round(g_col[Ns//2-3:Ns//2+4], 3))
