"""Closed centripetal Catmull-Rom spline with arc-length parameterisation.

Everything downstream (terrain ribbon, obstacles, map, decals, props, gates) is
derived from this one centreline, so its parameterisation has to be stable:
centripetal Catmull-Rom avoids the loops and cusps that uniform Catmull-Rom
produces when control points are unevenly spaced.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


def _catmull_rom_closed(points: np.ndarray, alpha: float = 0.5) -> np.ndarray:
    pts = np.asarray(points, dtype=float)
    n = len(pts)
    chunks = []
    for i in range(n):
        p0, p1, p2, p3 = (pts[(i + k) % n] for k in (-1, 0, 1, 2))

        def knot(t_prev: float, a: np.ndarray, b: np.ndarray) -> float:
            distance = float(np.linalg.norm(b - a))
            return t_prev + max(distance, 1e-6) ** alpha

        t0 = 0.0
        t1 = knot(t0, p0, p1)
        t2 = knot(t1, p1, p2)
        t3 = knot(t2, p2, p3)

        # Sample by chord length so long straight segments are not under-sampled.
        count = max(16, int(np.linalg.norm(p2 - p1) / 1.0) + 8)
        t = np.linspace(t1, t2, count, endpoint=False)[:, None]

        a1 = (t1 - t) / (t1 - t0) * p0 + (t - t0) / (t1 - t0) * p1
        a2 = (t2 - t) / (t2 - t1) * p1 + (t - t1) / (t2 - t1) * p2
        a3 = (t3 - t) / (t3 - t2) * p2 + (t - t2) / (t3 - t2) * p3

        b1 = (t2 - t) / (t2 - t0) * a1 + (t - t0) / (t2 - t0) * a2
        b2 = (t3 - t) / (t3 - t1) * a2 + (t - t1) / (t3 - t1) * a3
        chunks.append((t2 - t) / (t2 - t1) * b1 + (t - t1) / (t2 - t1) * b2)
    return np.vstack(chunks)


@dataclass
class Samples:
    """Arc-length resampled centreline."""

    x: np.ndarray
    z: np.ndarray
    tx: np.ndarray
    tz: np.ndarray
    nx: np.ndarray
    nz: np.ndarray
    k: np.ndarray
    s: np.ndarray
    length: float
    ds: float

    def point(self, s: float) -> tuple[float, float]:
        s = s % self.length
        return float(np.interp(s, self.s_ext, self.x_ext)), float(
            np.interp(s, self.s_ext, self.z_ext)
        )

    def tangent(self, s: float) -> tuple[float, float]:
        s = s % self.length
        return float(np.interp(s, self.s_ext, self.tx_ext)), float(
            np.interp(s, self.s_ext, self.tz_ext)
        )

    def normal(self, s: float) -> tuple[float, float]:
        tx, tz = self.tangent(s)
        return -tz, tx

    def curvature(self, s: float) -> float:
        s = s % self.length
        return float(np.interp(s, self.s_ext, self.k_ext))

    def offset(self, s: float, lateral: float) -> tuple[float, float]:
        x, z = self.point(s)
        nx, nz = self.normal(s)
        return x + nx * lateral, z + nz * lateral


class ClosedSpline:
    def __init__(self, points: list[list[float]] | np.ndarray, alpha: float = 0.5):
        pts = np.asarray(points, dtype=float)
        if pts.ndim != 2 or pts.shape[1] != 2:
            raise ValueError("control_points must be a list of [x, z] pairs")
        if len(pts) < 3:
            raise ValueError("a closed track needs at least 3 control points")
        if np.allclose(pts[0], pts[-1]):
            pts = pts[:-1]
        self.points = pts
        self.dense = _catmull_rom_closed(pts, alpha=alpha)
        self._samples: Samples | None = None

    def resample(self, step: float) -> Samples:
        step = max(0.25, float(step))
        dense = np.vstack([self.dense, self.dense[:1]])
        seg = np.linalg.norm(np.diff(dense, axis=0), axis=1)
        cumulative = np.concatenate([[0.0], np.cumsum(seg)])
        length = float(cumulative[-1])

        count = max(8, int(np.ceil(length / step)))
        ds = length / count
        targets = np.arange(count) * ds

        x = np.interp(targets, cumulative, dense[:, 0])
        z = np.interp(targets, cumulative, dense[:, 1])

        # Central differences on the closed loop, no dependency on sample index 0.
        dx = np.roll(x, -1) - np.roll(x, 1)
        dz = np.roll(z, -1) - np.roll(z, 1)
        norm = np.hypot(dx, dz)
        norm[norm < 1e-9] = 1.0
        tx, tz = dx / norm, dz / norm

        angle = np.unwrap(np.arctan2(tz, tx))
        k = np.gradient(angle, ds)

        samples = Samples(
            x=x,
            z=z,
            tx=tx,
            tz=tz,
            nx=-tz,
            nz=tx,
            k=k,
            s=targets,
            length=length,
            ds=ds,
        )
        # Extended arrays make periodic interpolation a single np.interp call.
        samples.s_ext = np.concatenate([samples.s, [length]])
        samples.x_ext = np.concatenate([samples.x, samples.x[:1]])
        samples.z_ext = np.concatenate([samples.z, samples.z[:1]])
        samples.tx_ext = np.concatenate([samples.tx, samples.tx[:1]])
        samples.tz_ext = np.concatenate([samples.tz, samples.tz[:1]])
        samples.k_ext = np.concatenate([samples.k, samples.k[:1]])
        self._samples = samples
        return samples

    @property
    def samples(self) -> Samples:
        if self._samples is None:
            self._samples = self.resample(1.0)
        return self._samples

    @property
    def length(self) -> float:
        return self.samples.length
