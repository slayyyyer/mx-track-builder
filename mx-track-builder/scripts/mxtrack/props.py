"""Statue and billboard scattering with track exclusion distance."""

from __future__ import annotations

import math

import numpy as np

from .files import billboard_line, statue_line

ASSET_WARNING = (
    "statues/billboards point at model assets; use real @Track/... paths or the "
    "game will silently skip the missing files"
)


class SpacingGrid:
    """Rejection sampling grid for minimum spacing between props."""

    def __init__(self, spacing: float):
        self.spacing = max(0.5, float(spacing))
        self.cells: dict[tuple[int, int], list[tuple[float, float]]] = {}

    def _key(self, x: float, z: float) -> tuple[int, int]:
        return int(math.floor(x / self.spacing)), int(math.floor(z / self.spacing))

    def is_free(self, x: float, z: float) -> bool:
        cx, cz = self._key(x, z)
        for dx in (-1, 0, 1):
            for dz in (-1, 0, 1):
                for px, pz in self.cells.get((cx + dx, cz + dz), ()):
                    if (px - x) ** 2 + (pz - z) ** 2 < self.spacing**2:
                        return False
        return True

    def add(self, x: float, z: float) -> None:
        self.cells.setdefault(self._key(x, z), []).append((x, z))


def _rotation(rng: np.random.Generator, value) -> float:
    """Descriptions use degrees; the statues file stores radians."""
    if value is None or (isinstance(value, str) and value.lower() == "random"):
        return float(rng.uniform(0.0, 2.0 * math.pi))
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return math.radians(float(value))
    if isinstance(value, (list, tuple)) and len(value) == 2:
        return math.radians(float(rng.uniform(float(value[0]), float(value[1]))))
    raise ValueError(
        f"rotation_degrees must be a number, 'random' or [min, max]; got {value!r}"
    )


def _scatter(
    samples,
    terrain_data: dict,
    rule: dict,
    rng: np.random.Generator,
    world_margin: float,
    spacing: SpacingGrid,
) -> list[tuple[float, float]]:
    count = int(rule.get("count", 0))
    if count <= 0:
        return []
    min_distance = float(rule.get("min_distance", 20.0))
    max_distance = float(rule.get("max_distance", 200.0))
    if max_distance < min_distance:
        raise ValueError("max_distance must be >= min_distance")
    side_cfg = str(rule.get("side", "both")).lower()
    if side_cfg not in ("both", "left", "right"):
        raise ValueError("prop side must be both, left or right")

    world = terrain_data["world"]
    half = terrain_data["half_width"]
    found: list[tuple[float, float]] = []
    attempts = 0
    max_attempts = count * 80

    while len(found) < count and attempts < max_attempts:
        attempts += 1
        s = float(rng.uniform(0.0, samples.length))
        side = 1
        if side_cfg == "both":
            side = 1 if rng.random() < 0.5 else -1
        elif side_cfg == "right":
            side = -1

        idx = int(s / samples.ds) % len(samples.x)
        lateral = float(half[idx]) + float(rng.uniform(min_distance, max_distance))
        x = float(samples.x[idx] + samples.nx[idx] * lateral * side)
        z = float(samples.z[idx] + samples.nz[idx] * lateral * side)
        if not (
            world_margin <= x <= world - world_margin
            and world_margin <= z <= world - world_margin
        ):
            continue
        if not spacing.is_free(x, z):
            continue
        spacing.add(x, z)
        found.append((x, z))

    return found


def build_statues(desc: dict, samples, terrain_data: dict, rng: np.random.Generator) -> tuple[str, list[str]]:
    rules = desc.get("statues") or []
    lines: list[str] = []
    warnings: list[str] = []
    spacing = SpacingGrid(min((float(r.get("min_spacing", 12.0)) for r in rules), default=12.0))

    for rule in rules:
        if rule.get("enabled", True) is False:
            continue
        model = str(rule.get("model", "")).strip()
        texture = str(rule.get("texture", "")).strip()
        if not model or not texture:
            warnings.append("statue rule missing model/texture; skipped")
            continue
        model = model if model.startswith("@") else "@" + model
        texture = texture if texture.startswith("@") else "@" + texture
        shape = rule.get("shape")
        if shape and str(shape).lower() != "null" and not str(shape).startswith("@"):
            shape = "@" + str(shape)
        spacing.spacing = max(0.5, float(rule.get("min_spacing", spacing.spacing)))

        placed = _scatter(samples, terrain_data, rule, rng, 8.0, spacing)
        if len(placed) < int(rule.get("count", 0)):
            warnings.append(
                f"statue '{rule.get('name', model)}': placed {len(placed)} of {rule.get('count')} "
                "(no room left at this spacing/distance)"
            )

        for x, z in placed:
            rotation = _rotation(rng, rule.get("rotation_degrees", "random"))
            # The statues format stores Y as height above ground, not absolute
            # terrain elevation. 0 places the model's origin on the terrain.
            y = float(rule.get("y_offset", 0.0))
            lines.append(statue_line(x, y, z, rotation, model, texture, shape))

    if lines:
        warnings.append(ASSET_WARNING)
    return "".join(lines), warnings


def build_billboards(desc: dict, samples, terrain_data: dict, rng: np.random.Generator) -> tuple[str, list[str]]:
    rules = desc.get("billboards") or []
    lines: list[str] = []
    warnings: list[str] = []
    spacing = SpacingGrid(min((float(r.get("min_spacing", 15.0)) for r in rules), default=15.0))

    for rule in rules:
        if rule.get("enabled", True) is False:
            continue
        texture = str(rule.get("texture", "")).strip()
        if not texture:
            warnings.append("billboard rule missing texture; skipped")
            continue
        texture = texture if texture.startswith("@") else "@" + texture
        spacing.spacing = max(0.5, float(rule.get("min_spacing", spacing.spacing)))

        placed = _scatter(samples, terrain_data, rule, rng, 8.0, spacing)
        if len(placed) < int(rule.get("count", 0)):
            warnings.append(
                f"billboard '{texture}': placed {len(placed)} of {rule.get('count')} "
                "(no room left at this spacing/distance)"
            )

        # The billboard file's size field is the sprite's height in feet;
        # aspect is width / height. 'width' is accepted for older descriptions.
        height = float(rule.get("height", rule.get("width", 40.0)))
        aspect = float(rule.get("aspect", 1.0))
        for x, z in placed:
            y = float(rule.get("y_offset", 0.0))
            # Billboards are camera-facing sprites; there is no rotation field.
            lines.append(billboard_line(x, y, z, height, aspect, texture))

    return "".join(lines), warnings
