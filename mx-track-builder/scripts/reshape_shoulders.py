#!/usr/bin/env python3
"""Recontour the off-track shoulder without moving the riding surface.

The normal wide-falloff stamp is expensive because every track station covers
its full falloff footprint.  This pass keeps the existing track surface, finds
the distance from that surface to each outside pixel, and blends the edge
height back to the base terrain over the configured ``edge_falloff``.

Usage:
    py scripts/reshape_shoulders.py <track_dir> <description> --out <dir>
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
from scipy.ndimage import distance_transform_edt, gaussian_filter

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mxtrack.description import load_description
from mxtrack.files import decode_png16_gray, terrain_hf, write_png16_gray, write_text
from mxtrack.obstacles import build_profile, half_widths, smootherstep
from mxtrack.spline import ClosedSpline
from mxtrack.terrain import (
    _smooth_heightfield,
    build_base,
    sample_grid_many,
    stamp_ribbon,
)


def read_heightfield(track_dir: Path) -> tuple[np.ndarray, float, float]:
    raw = (track_dir / "terrain.hf").read_text().split()
    low, high = float(raw[2]), float(raw[3])
    encoded = decode_png16_gray(track_dir / "terrain.png")
    grid = low + encoded.astype(np.float64) / 65535.0 * (high - low)
    return grid, low, high


def reshape(args: argparse.Namespace) -> None:
    source = Path(args.track_dir)
    out = Path(args.out)
    desc, _ = load_description(args.description)
    grid, _, _ = read_heightfield(source)

    terrain_cfg = desc.get("terrain") or {}
    res = float(terrain_cfg["resolution"])
    dimension = int(terrain_cfg["dimension"])
    n = 2 ** (dimension + 1) + 1
    world = (n - 1) * res
    smooth_iterations = int(terrain_cfg.get("smooth_iterations", 0))

    samples = ClosedSpline(desc["track"]["control_points"]).resample(
        min(1.0, max(0.5, res))
    )
    hw = half_widths(samples, desc["track"], desc["gates"])
    falloff = float(args.falloff or desc["track"].get("edge_falloff", 18.0))
    if falloff <= 0:
        raise SystemExit("edge falloff must be positive")

    base = build_base(desc, n, res)
    base_along = sample_grid_many(base, res, samples.x, samples.z)
    profile, _, _, _ = build_profile(
        samples, base_along, desc["track"], desc["obstacles"]
    )

    # A narrow stamp is enough to identify the running surface.  It is not
    # used for its falloff height; it is a fast mask for the distance field.
    _, weight = stamp_ribbon(
        (n, n),
        res,
        samples.x,
        samples.z,
        samples.nx,
        samples.nz,
        hw,
        4.0,
        sample_value=profile,
        sample_spacing=samples.ds,
        interpolate_sample_value=True,
    )
    surface = weight >= 0.999
    if not surface.any():
        raise SystemExit("no running surface found")

    distance_px, nearest = distance_transform_edt(~surface, return_indices=True)
    distance_ft = distance_px.astype(np.float64) * res
    edge_height = grid[nearest[0], nearest[1]]

    # Folded lanes can be closer to each other than the shoulder width.  The
    # nearest-edge field then changes abruptly along the lane midline.  Smooth
    # that edge-height field, not the finished shoulder: blurring the target
    # would pull the first off-track pixel down and create a cliff at the edge.
    smooth_ft = float(args.smooth)
    if smooth_ft > 0.0:
        edge_height = gaussian_filter(
            edge_height, sigma=smooth_ft / res, mode="nearest"
        )

    # The old terrain's far field is the base terrain after the normal light
    # heightfield smoothing.  Match that so the new shoulder meets the
    # surrounding ground without a seam.
    far = _smooth_heightfield(base, smooth_iterations)
    blend = smootherstep(np.clip(1.0 - distance_ft / falloff, 0.0, 1.0))
    target = far + blend * (edge_height - far)

    # Keep the known-good first few feet of shoulder, then ease into the broad
    # target.  This protects the lip where a raster mask is only one pixel
    # wide, without preserving the old steep falloff farther out.
    edge_blend_ft = float(args.edge_blend)
    if edge_blend_ft > 0.0:
        edge_feather = smootherstep(
            np.clip(distance_ft / edge_blend_ft, 0.0, 1.0)
        )
        target = grid * (1.0 - edge_feather) + target * edge_feather
    reshaped = np.where(surface, grid, target)

    margin = float(terrain_cfg.get("margin", 1.0))
    low = float(np.floor(reshaped.min() - margin))
    high = float(np.ceil(reshaped.max() + margin))
    if high - low < 2.0:
        high = low + 2.0
    encoded = np.clip(
        (reshaped - low) / (high - low) * 65535.0, 0, 65535
    ).astype(np.uint16)

    out.mkdir(parents=True, exist_ok=True)
    write_text(out / "terrain.hf", terrain_hf(dimension, res, low, high))
    write_png16_gray(out / "terrain.png", encoded)

    changed = ~surface
    shift = np.abs(target - grid)
    print("EDGE_FALLOFF", falloff, "SHOULDER_SMOOTH_FT", smooth_ft,
          "EDGE_BLEND_FT", edge_blend_ft)
    print("SURFACE_PIXELS", int(surface.sum()), "OUTSIDE_PIXELS", int(changed.sum()))
    print("MAX_SHOULDER_SHIFT", round(float(shift[changed].max()), 3))
    print("LOW", low, "HIGH", high, "WORLD", world)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("track_dir", help="installed track directory to reshape")
    parser.add_argument("description", help="track YAML")
    parser.add_argument("--out", required=True, help="output stage directory")
    parser.add_argument(
        "--falloff",
        type=float,
        default=None,
        help="shoulder width in feet; defaults to track.edge_falloff",
    )
    parser.add_argument(
        "--smooth",
        type=float,
        default=25.0,
        help="Gaussian radius in feet for the reshaped shoulder",
    )
    parser.add_argument(
        "--edge-blend",
        type=float,
        default=30.0,
        help="feet outside the ribbon that ease from the old shoulder",
    )
    reshape(parser.parse_args())


if __name__ == "__main__":
    main()
