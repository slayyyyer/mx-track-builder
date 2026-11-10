"""map.png generation: the in-game minimap.

The ribbon is rasterised with the same distance-field stamp used for the
terrain, then colour bands are assigned by nearest sample.  Filling by polygon
or by thousands of thick line segments leaves hairline seams (the black outline
shows through); the stamp has neither problem and cannot self-intersect on
tight corners.
"""

from __future__ import annotations

import os

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from .obstacles import resolve_distance
from .terrain import stamp_ribbon

FONT_CANDIDATES = [
    r"C:\Windows\Fonts\arialbd.ttf",
    r"C:\Windows\Fonts\impact.ttf",
    r"C:\Windows\Fonts\arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
]

DEFAULTS = {
    "size": 1024,
    "background": None,
    "track_colors": ["#8a5a35"],
    "outline": "#111111",
    "outline_width": 10,
    "track_width": 22,
    "stripe_length": 260.0,
    "title": None,
    "title_color": "#ffffff",
    "title_outline": "#111111",
    "title_size": 76,
    "title_position": "bottom",
    "show_start": True,
    "show_gates": True,
}


def _font(size: int):
    for path in FONT_CANDIDATES:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # Pillow < 10.1
        return ImageFont.load_default()


def _rgb(colour: str) -> tuple[int, int, int, int]:
    colour = colour.strip().lstrip("#")
    if len(colour) == 3:
        colour = "".join(c * 2 for c in colour)
    if len(colour) != 6:
        raise ValueError(f"bad colour {colour!r}; use #rrggbb")
    return (int(colour[0:2], 16), int(colour[2:4], 16), int(colour[4:6], 16), 255)


def render_map(desc: dict, samples, world: float, gates: dict | None = None) -> Image.Image:
    theme = (desc.get("theme") or {}).get("map") or {}
    cfg = dict(DEFAULTS)
    cfg.update(theme)
    size = int(cfg["size"])
    supersample = 2
    pixels = size * supersample
    feet_per_pixel = world / pixels

    track_px = max(1.0, float(cfg["track_width"]) * size / 1024.0)
    outline_px = max(0.0, float(cfg["outline_width"]) * size / 1024.0)
    outline_rgb = _rgb(cfg["outline"])
    colours = cfg.get("track_colors") or ["#8a5a35"]
    if isinstance(colours, str):
        colours = [colours]
    colours = [_rgb(c) for c in colours]

    count = len(samples.x)
    half = track_px * 0.5 * supersample * feet_per_pixel
    half_outline = (track_px * 0.5 + outline_px) * supersample * feet_per_pixel
    edge = 1.25 * feet_per_pixel  # soft edge over roughly one supersampled pixel

    stripe_len = max(1.0, float(cfg["stripe_length"]))
    band_ids = ((samples.s / stripe_len).astype(int) % len(colours)).astype(np.float32)

    band_values, ribbon_alpha = stamp_ribbon(
        (pixels, pixels),
        feet_per_pixel,
        samples.x,
        samples.z,
        samples.nx,
        samples.nz,
        np.full(count, half, dtype=np.float32),
        edge,
        sample_value=band_ids,
    )
    _, outline_alpha = stamp_ribbon(
        (pixels, pixels),
        feet_per_pixel,
        samples.x,
        samples.z,
        samples.nx,
        samples.nz,
        np.full(count, half_outline, dtype=np.float32),
        edge,
        sample_value=np.ones(count, dtype=np.float32),
    )

    # Composite ribbon bands over the outline with soft alpha, so both the
    # outer edge and the ribbon edge are anti-aliased instead of stair-stepped.
    layer = np.zeros((pixels, pixels, 4), dtype=np.float64)
    outline_rgb_f = np.array(outline_rgb[:3], dtype=np.float64)
    layer[:, :, :3] = outline_rgb_f
    layer[:, :, 3] = np.clip(outline_alpha, 0.0, 1.0)
    ids = np.rint(band_values).astype(int)
    for index, colour in enumerate(colours):
        alpha = np.where(ids == index, np.clip(ribbon_alpha, 0.0, 1.0), 0.0)
        colour_f = np.array(colour[:3], dtype=np.float64)
        layer[:, :, :3] = colour_f * alpha[:, :, None] + layer[:, :, :3] * (1.0 - alpha[:, :, None])
        layer[:, :, 3] = alpha + layer[:, :, 3] * (1.0 - alpha)
    rgb = np.clip(layer[:, :, :3], 0, 255).astype(np.uint8)
    alpha = np.clip(layer[:, :, 3] * 255.0, 0, 255).astype(np.uint8)
    layer = np.dstack([rgb, alpha])

    background = cfg.get("background")
    if background:
        canvas = Image.new("RGBA", (pixels, pixels), _rgb(background))
        canvas.alpha_composite(Image.fromarray(layer, mode="RGBA"))
    else:
        canvas = Image.fromarray(layer, mode="RGBA")
    image = canvas.resize((size, size), Image.LANCZOS)
    draw = ImageDraw.Draw(image)
    scale = size / world

    gates_cfg = gates or {}
    start_at = gates_cfg.get("start_at", 0)
    start_s = (
        resolve_distance(start_at, samples.length, "gates.start_at") % samples.length
        if start_at is not None
        else 0.0
    )

    if cfg.get("show_start", True):
        x, z = samples.point(start_s)
        nx, nz = samples.normal(start_s)
        gate_half = float(gates_cfg.get("start_count", 20)) * float(gates_cfg.get("spacing", 4.0)) * 0.5
        gate_half = max(gate_half, float(desc["track"]["width"]) * 0.5)
        a = ((x - nx * gate_half) * scale, (z - nz * gate_half) * scale)
        b = ((x + nx * gate_half) * scale, (z + nz * gate_half) * scale)
        draw.line([a, b], fill=outline_rgb, width=max(3, int(track_px * 0.4)))
        draw.line([a, b], fill=(255, 255, 255, 255), width=max(1, int(track_px * 0.18)))

    if cfg.get("show_gates", True):
        gate_count = int(gates_cfg.get("checkpoint_count", 0))
        offset = float(gates_cfg.get("checkpoint_offset", 0.0))
        radius = max(2, int(track_px * 0.22))
        for i in range(gate_count):
            s = (start_s + offset + i * samples.length / max(gate_count, 1)) % samples.length
            px, pz = samples.point(s)
            gx, gz = px * scale, pz * scale
            draw.ellipse([gx - radius, gz - radius, gx + radius, gz + radius], fill=outline_rgb)

    title = cfg.get("title")
    if title is None:
        title = desc.get("title") or desc.get("name")
    if title:
        font_size = int(float(cfg["title_size"]) * size / 1024.0)
        font = _font(font_size)
        stroke = max(1, font_size // 22)
        bbox = draw.textbbox((0, 0), str(title), font=font, stroke_width=stroke)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
        margin = int(size * 0.045)
        if str(cfg.get("title_position", "bottom")).lower() == "top":
            y = margin - bbox[1]
        else:
            y = size - margin - text_h - bbox[1]
        x = (size - text_w) // 2 - bbox[0]
        draw.text(
            (x, y),
            str(title),
            font=font,
            fill=_rgb(cfg["title_color"]),
            stroke_width=stroke,
            stroke_fill=_rgb(cfg["title_outline"]),
        )

    return image
