"""Terrain heightfield generation.

The base terrain is layered value noise; the track ribbon is stamped along the
spline with a flat running surface, edge falloff and per-sample banking.
"""

from __future__ import annotations

import numpy as np
from PIL import Image

from .obstacles import bank_cross_section, half_widths, rut_cross_section, smootherstep

DEFAULTS = {
    "dimension": 9,
    "resolution": 2.0,
    "base_height": 55.0,
    "relief": 16.0,
    "roughness": 0.35,
    "margin": 1.0,
    "hills": [],
    "smooth_iterations": 0,
    "shoulder_smooth": 0.0,
}


def _value_noise(rng: np.random.Generator, size: int, cells: int) -> np.ndarray:
    grid = rng.random((cells + 1, cells + 1))
    image = Image.fromarray((grid * 255.0).astype(np.uint8), mode="L")
    image = image.resize((size, size), Image.BICUBIC)
    return np.asarray(image, dtype=np.float64) / 255.0


def build_base(desc: dict, n: int, res: float) -> np.ndarray:
    cfg = dict(DEFAULTS)
    cfg.update(desc.get("terrain") or {})
    rng = np.random.default_rng(int(desc.get("seed", 1)))

    relief = float(cfg["relief"])
    roughness = float(np.clip(float(cfg["roughness"]), 0.0, 1.0))

    # Three octaves: landform, rolling hills, surface roughness.
    coarse = _value_noise(rng, n, 3) - 0.5
    medium = _value_noise(rng, n, 9) - 0.5
    fine = _value_noise(rng, n, 33) - 0.5

    grid = (
        float(cfg["base_height"])
        + coarse * relief
        + medium * relief * 0.35
        + fine * relief * 0.18 * (0.4 + roughness)
    )

    for hill in cfg.get("hills") or []:
        x = float(hill["x"])
        z = float(hill["z"])
        radius = max(1.0, float(hill.get("radius", 300.0)))
        height = float(hill.get("height", 20.0))
        cols = np.arange(n) * res
        dx = cols[None, :] - x
        dz = cols[:, None] - z
        grid += height * np.exp(-(dx * dx + dz * dz) / (2.0 * (radius * 0.5) ** 2))

    return grid


def sample_grid(grid: np.ndarray, res: float, x: float, z: float) -> float:
    return float(sample_grid_many(grid, res, np.array([x]), np.array([z]))[0])


def sample_grid_many(grid: np.ndarray, res: float, x: np.ndarray, z: np.ndarray) -> np.ndarray:
    n = grid.shape[0]
    px = np.clip(np.asarray(x, dtype=float) / res, 0, n - 1.001)
    pz = np.clip(np.asarray(z, dtype=float) / res, 0, n - 1.001)
    x0 = np.floor(px).astype(int)
    z0 = np.floor(pz).astype(int)
    fx = px - x0
    fz = pz - z0
    g00 = grid[z0, x0]
    g10 = grid[z0, x0 + 1]
    g01 = grid[z0 + 1, x0]
    g11 = grid[z0 + 1, x0 + 1]
    top = g00 * (1 - fx) + g10 * fx
    bottom = g01 * (1 - fx) + g11 * fx
    return top * (1 - fz) + bottom * fz


def stamp_ribbon(
    shape: tuple[int, int],
    res: float,
    x: np.ndarray,
    z: np.ndarray,
    nx: np.ndarray,
    nz: np.ndarray,
    half_width: np.ndarray,
    edge_falloff: float,
    sample_value: np.ndarray,
    bank: np.ndarray | None = None,
    rut: np.ndarray | None = None,
    crown: float = 0.0,
    sample_spacing: float | None = None,
    interpolate_sample_value: bool = False,
) -> tuple[np.ndarray, np.ndarray]:
    """Rasterise the ribbon, keeping the nearest station per pixel.

    Returns ``(value, weight)`` arrays; weight is 1 on the running surface and
    fades to 0 across the edge falloff.  Using the nearest sample (max weight)
    instead of averaging avoids soft, washed-out jump lips.

    Each sample paints a broad strip, but a pixel is taken from the sample
    whose station is nearest along the track, not the first one to claim it.
    The along-track gate is essential on a folded layout: without it, a station
    on another part of a hook can be laterally close to the infield while being
    hundreds of feet away along the track, and it would stamp a phantom shelf.
    When ``interpolate_sample_value`` is set, the value and bank are taken from
    the continuous position between that station and its neighbour instead of
    being held constant for a whole 1 ft station.  That removes the stair-step
    terraces on steep jump faces without blurring the whole ribbon.
    """
    rows, cols = shape
    best_along = np.full(shape, np.inf, dtype=np.float32)
    best_w = np.zeros(shape, dtype=np.float32)
    value = np.zeros(shape, dtype=np.float32)
    falloff = max(0.0, float(edge_falloff))
    sample_count = len(sample_value)

    for i in range(len(x)):
        hw = float(half_width[i])
        if hw <= 0:
            continue
        reach = hw + falloff + res
        px = x[i] / res
        pz = z[i] / res
        i0 = max(0, int(np.floor(px - reach / res)))
        i1 = min(cols - 1, int(np.ceil(px + reach / res)))
        j0 = max(0, int(np.floor(pz - reach / res)))
        j1 = min(rows - 1, int(np.ceil(pz + reach / res)))
        if i0 > i1 or j0 > j1:
            continue

        dx = np.arange(i0, i1 + 1) * res - x[i]
        dz = np.arange(j0, j1 + 1) * res - z[i]
        lateral = dx[None, :] * nx[i] + dz[:, None] * nz[i]
        # The normal is (-tz, tx), so the forward tangent is (nz, -nx).
        # Measuring along the opposite sign makes the interpolated profile
        # run backward through each station and turns ramps into a sawtooth.
        along = dx[None, :] * nz[i] - dz[:, None] * nx[i]
        key = np.abs(along)

        ratio = np.clip(lateral / hw, -1.0, 1.0)
        eval_lateral = lateral
        eval_half_width = hw
        value_i = np.full_like(ratio, float(sample_value[i]))
        bank_i = None if bank is None else np.full_like(ratio, float(bank[i]))
        rut_i = None if rut is None else np.asarray(rut[i], dtype=float)

        if interpolate_sample_value and sample_spacing:
            frac = np.clip(along / sample_spacing, -0.5, 0.5)
            forward = frac >= 0.0
            a = np.where(forward, i, (i - 1) % sample_count)
            b = np.where(forward, (i + 1) % sample_count, i)
            t = np.where(forward, frac, 1.0 + frac)
            value_i = sample_value[a] * (1.0 - t) + sample_value[b] * t
            if bank is not None:
                bank_i = bank[a] * (1.0 - t) + bank[b] * t
            if rut is not None:
                rut_i = np.moveaxis(
                    rut[a] * (1.0 - t)[..., None] + rut[b] * t[..., None],
                    -1,
                    0,
                )

            # A station's normal and width rotate as the track curves.  If a
            # pixel switches to the next station, using that station's local
            # lateral coordinate makes the bank jump by a small step even
            # though the height profile is interpolated.  Evaluate the lateral
            # coordinate against the same interpolated centreline and normal
            # on both sides of the switch so the whole cross-section stays C0.
            centre_x = x[a] + t * (x[b] - x[a])
            centre_z = z[a] + t * (z[b] - z[a])
            normal_x = nx[a] + t * (nx[b] - nx[a])
            normal_z = nz[a] + t * (nz[b] - nz[a])
            normal_len = np.hypot(normal_x, normal_z)
            normal_x = np.divide(normal_x, normal_len, out=np.zeros_like(normal_x), where=normal_len > 1e-9)
            normal_z = np.divide(normal_z, normal_len, out=np.zeros_like(normal_z), where=normal_len > 1e-9)
            eval_half_width = half_width[a] + t * (half_width[b] - half_width[a])
            offset_x = x[i] + dx[None, :] - centre_x
            offset_z = z[i] + dz[:, None] - centre_z
            eval_lateral = offset_x * normal_x + offset_z * normal_z
            ratio = np.clip(eval_lateral / eval_half_width, -1.0, 1.0)

        absolute = np.abs(eval_lateral)
        if falloff > 0.0:
            weight = np.where(
                absolute <= eval_half_width,
                1.0,
                np.where(
                    absolute >= eval_half_width + falloff,
                    0.0,
                    smootherstep(1.0 - (absolute - eval_half_width) / falloff),
                ),
            )
        else:
            weight = (absolute <= eval_half_width).astype(np.float64)

        if sample_spacing:
            # A station owns only the thin longitudinal slice of ribbon around
            # its own centreline point.  Three station spacings leave enough
            # overlap for curves and coarse maps without letting a nearby
            # parallel lane paint across the gap between hooks.
            along_limit = max(3.0 * float(sample_spacing), 2.0 * res)
            weight = np.where(np.abs(along) <= along_limit, weight, 0.0)

        # Coverage is the max weight: a max of smooth falloffs is continuous and
        # leaves no seams where station cells meet.  A station may only supply
        # the height where it actually covers the pixel.  Comparing along-track
        # distance alone lets a distant lane with zero coverage overwrite the
        # surface the pixel is standing on, producing multi-foot spikes along
        # the track edge.  Prefer the strongest coverage, then the nearest
        # station along the track so jump lips stay sharp.
        window_weight = best_w[j0 : j1 + 1, i0 : i1 + 1]
        window_key = best_along[j0 : j1 + 1, i0 : i1 + 1]
        stronger = weight > window_weight + 1e-6
        tied = weight >= window_weight - 1e-6
        update = (weight > 0.0) & (stronger | (tied & (key < window_key)))
        coverage = weight > window_weight
        if coverage.any():
            window_weight[coverage] = weight[coverage]
        if not update.any():
            continue

        profile = value_i + float(crown) * (1.0 - ratio * ratio)
        if bank_i is not None:
            profile = profile + bank_cross_section(bank_i, ratio)
        if rut_i is not None:
            profile = profile + rut_cross_section(rut_i, eval_lateral)

        window_key[update] = key[update]
        value[j0 : j1 + 1, i0 : i1 + 1][update] = np.broadcast_to(
            profile, window_key.shape
        )[update]

    return value, best_w


def _smooth_heightfield(grid: np.ndarray, iterations: int) -> np.ndarray:
    """A light 3x3 blur for high-resolution heightfields.

    Each pass removes one-pixel station steps left on steep faces while the
    4/1/1/1/1 kernel keeps the centre dominant, so jump lips and berm crests
    stay defined.  On the 0.625 ft Cactus grid eight passes clean up the surface
    without needing a coarse, lip-rounding blur.
    """
    for _ in range(max(0, int(iterations))):
        padded = np.pad(grid, 1, mode="edge")
        grid = (
            4.0 * padded[1:-1, 1:-1]
            + padded[:-2, 1:-1]
            + padded[2:, 1:-1]
            + padded[1:-1, :-2]
            + padded[1:-1, 2:]
        ) / 8.0
    return grid


def _box_blur_axis(grid: np.ndarray, radius: int, axis: int) -> np.ndarray:
    """Box blur one axis with a sliding-window sum.

    The shoulder pass needs a spatial radius measured in feet, not a handful
    of 3x3 iterations: a 3x3 pass only reaches one pixel, which is too small
    to relax the broad crease where two falloffs meet.
    """
    if radius < 1:
        return grid
    pads = [(0, 0), (0, 0)]
    pads[axis] = (radius, radius)
    padded = np.pad(grid, pads, mode="edge")
    cumulative = np.cumsum(padded, axis=axis, dtype=np.float64)
    window = 2 * radius + 1
    if axis == 0:
        cumulative = np.concatenate(
            (np.zeros((1, grid.shape[1]), dtype=np.float64), cumulative), axis=0
        )
        return (cumulative[window:] - cumulative[:-window]) / window
    cumulative = np.concatenate(
        (np.zeros((grid.shape[0], 1), dtype=np.float64), cumulative), axis=1
    )
    return (cumulative[:, window:] - cumulative[:, :-window]) / window


def _smooth_shoulders(
    grid: np.ndarray, weight: np.ndarray, radius_ft: float, resolution: float
) -> np.ndarray:
    """Blur the off-track shoulder without moving the running surface.

    ``weight`` is exactly 1 on the ribbon and fades to 0 across the falloff.
    The mask therefore preserves the riding surface and jump faces, while the
    two 2D box passes relax the overlapping falloff seams that a 3x3 global
    blur cannot reach.  The blur fades in over the first part of the falloff
    instead of switching on at 99% coverage; a near-binary mask left its own
    crease along the track edge.  This is deliberately shoulder-local rather
    than a larger ``smooth_iterations`` value, which would round off the
    track itself.
    """
    radius = int(round(max(0.0, float(radius_ft)) / float(resolution)))
    if radius < 1:
        return grid
    mask = np.clip((1.0 - weight.astype(np.float64)) / 0.10, 0.0, 1.0)
    mask = mask * mask * (3.0 - 2.0 * mask)
    blurred = grid
    for _ in range(2):
        blurred = _box_blur_axis(blurred, radius, 0)
        blurred = _box_blur_axis(blurred, radius, 1)
    return grid * (1.0 - mask) + blurred * mask


def build_heightmap(
    desc: dict,
    samples,
    profile: np.ndarray,
    bank: np.ndarray,
    gates_cfg: dict,
    base: np.ndarray | None = None,
    rut: np.ndarray | None = None,
) -> dict:
    terrain_cfg = dict(DEFAULTS)
    terrain_cfg.update(desc.get("terrain") or {})
    dimension = int(terrain_cfg["dimension"])
    res = float(terrain_cfg["resolution"])
    # Dimension 9 -> 1025 px (2^(9+1)+1), matching terrain.hf in the blank track.
    n = 2 ** (dimension + 1) + 1
    world = (n - 1) * res

    if base is None:
        base = build_base(desc, n, res)
    track = desc["track"]
    hw = half_widths(samples, track, gates_cfg)
    falloff = float(track.get("edge_falloff", track.get("falloff", 18.0)))
    crown = float(track.get("crown", 0.0))
    shoulder_smooth = float(terrain_cfg.get("shoulder_smooth", 0.0))

    ribbon, weight = stamp_ribbon(
        (n, n),
        res,
        samples.x,
        samples.z,
        samples.nx,
        samples.nz,
        hw,
        falloff,
        sample_value=profile,
        bank=bank,
        rut=rut,
        crown=crown,
        sample_spacing=samples.ds,
        interpolate_sample_value=True,
    )

    grid = base * (1.0 - weight) + ribbon * weight
    grid = _smooth_heightfield(grid, int(terrain_cfg.get("smooth_iterations", 0)))
    if shoulder_smooth > 0.0:
        grid = _smooth_shoulders(grid, weight, shoulder_smooth, res)

    margin = float(terrain_cfg.get("margin", 1.0))
    low = float(np.floor(grid.min() - margin))
    high = float(np.ceil(grid.max() + margin))
    if high - low < 2.0:
        high = low + 2.0

    encoded = np.clip((grid - low) / (high - low) * 65535.0, 0, 65535).astype(np.uint16)

    return {
        "grid": grid,
        "weight": weight,
        "encoded": encoded,
        "dimension": dimension,
        "resolution": res,
        "n": n,
        "world": world,
        "low": low,
        "high": high,
        "half_width": hw,
        "falloff": falloff,
        "shoulder_smooth": shoulder_smooth,
    }
