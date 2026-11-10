"""Ground decal generation and the decals text file."""

from __future__ import annotations

import numpy as np
from PIL import Image, ImageFilter

from .terrain import stamp_ribbon

DEFAULTS = {
    "size": 2048,
    "base_color": "#8d9a6a",
    "dirt_color": "#8a5a35",
    "edge_falloff": 12.0,
    "noise": 0.45,
    "noise_scale": 120.0,
    "friction": [1.0, 6.0],
    "roll_resist": [5.0, 15.0, 10.0],
}


def settings(desc: dict) -> dict:
    """theme.ground defaults merged with the description."""
    theme = ((desc.get("theme") or {}).get("ground") or {})
    cfg = dict(DEFAULTS)
    cfg.update(theme)
    return cfg


def _rgb(colour: str | None) -> tuple[int, int, int] | None:
    if colour is None:
        return None
    value = colour.strip().lstrip("#")
    if len(value) == 3:
        value = "".join(c * 2 for c in value)
    if len(value) != 6:
        raise ValueError(f"bad colour {colour!r}; use #rrggbb")
    return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)


def _noise(shape, rng: np.random.Generator, feature_px: float) -> np.ndarray:
    feature_px = max(2.0, feature_px)
    h, w = shape
    cells = max(2, int(round(h / feature_px)))
    small = rng.random((cells + 1, cells + 1))
    image = Image.fromarray((small * 255).astype(np.uint8), mode="L")
    image = image.resize((w, h), Image.BICUBIC)
    return np.asarray(image, dtype=np.float64) / 255.0


def render_ground(desc: dict, samples, terrain_data: dict, rng: np.random.Generator) -> Image.Image:
    cfg = settings(desc)
    size = int(cfg["size"])
    world = terrain_data["world"]
    px_per_ft = size / world

    base_colour = _rgb(cfg.get("base_color"))
    dirt_colour = _rgb(cfg.get("dirt_color"))
    if dirt_colour is None:
        raise ValueError("theme.ground.dirt_color is required")

    falloff = float(cfg["edge_falloff"])
    _, weight = stamp_ribbon(
        (size, size),
        world / size,
        samples.x,
        samples.z,
        samples.nx,
        samples.nz,
        terrain_data["half_width"],
        falloff,
        sample_value=np.ones(len(samples.x)),
        bank=None,
        crown=0.0,
        sample_spacing=samples.ds,
    )

    # Slight blur softens the 1 px/ft raster edge into a real falloff.
    mask_img = Image.fromarray((np.clip(weight, 0, 1) * 255).astype(np.uint8), mode="L")
    mask_img = mask_img.filter(ImageFilter.GaussianBlur(radius=max(0.5, falloff * px_per_ft * 0.35)))
    alpha = np.asarray(mask_img, dtype=np.float64) / 255.0

    noise_amount = float(np.clip(float(cfg["noise"]), 0.0, 1.0))
    feature = float(cfg["noise_scale"]) * px_per_ft
    mottle = _noise((size, size), rng, feature) - 0.5
    fine = _noise((size, size), rng, max(2.0, feature * 0.15)) - 0.5

    dirt = np.zeros((size, size, 3), dtype=np.float64)
    for channel in range(3):
        dirt[:, :, channel] = dirt_colour[channel] * (
            1.0 + noise_amount * (mottle * 0.55 + fine * 0.25)
        )

    if base_colour is None:
        rgb = np.clip(dirt, 0, 255)
        out = np.dstack([rgb, alpha * 255.0]).astype(np.uint8)
        return Image.fromarray(out, mode="RGBA")

    base = np.zeros((size, size, 3), dtype=np.float64)
    for channel in range(3):
        base[:, :, channel] = base_colour[channel] * (1.0 + noise_amount * 0.35 * (mottle + fine))
    blended = base * (1.0 - alpha[:, :, None]) + dirt * alpha[:, :, None]
    out = np.dstack([np.clip(blended, 0, 255), np.full((size, size), 255.0)]).astype(np.uint8)
    return Image.fromarray(out, mode="RGBA")


def render_tile(desc: dict, size: int = 16) -> Image.Image:
    """A tiny flat tile texture; decals cover it in normal play."""
    colour = _rgb(settings(desc).get("dirt_color"))
    if colour is None:
        raise ValueError("theme.ground.dirt_color is required")
    return Image.new("RGB", (size, size), colour)


def decals_file(folder: str, world: float, texture_name: str = "ground.png") -> str:
    # The decal list itself is a file named 'decals'; on Windows the texture
    # folder therefore cannot also be called 'decals'.  Any path works in game.
    centre = world * 0.5
    return (
        f"[{centre:.6f} {centre:.6f}] 0.000000 {world:.6f} 1.000000 "
        f"@{folder}/ground/{texture_name}\n"
    )
