"""Hillshade preview so a build can be checked without opening the game."""

from __future__ import annotations

import numpy as np
from PIL import Image, ImageDraw

from .mapimage import _font, _rgb
from .obstacles import resolve_distance


def render_preview(
    desc: dict,
    samples,
    terrain_data: dict,
    gates_cfg: dict,
    reports: list | None = None,
    size: int = 1024,
) -> Image.Image:
    world = terrain_data["world"]
    grid = terrain_data["grid"]
    weight = terrain_data["weight"]

    def resize(array, resample=Image.BILINEAR):
        image = Image.fromarray(np.asarray(array, dtype=np.float32), mode="F")
        return np.asarray(image.resize((size, size), resample), dtype=np.float64)

    height = resize(grid)
    band = np.clip(resize(weight), 0, 1)
    pixel = world / size
    # Exaggerate relief a little so jump faces and berms are visible in a preview.
    gy, gx = np.gradient(height * 1.6, pixel, pixel)

    normal = np.dstack([-gx, -gy, np.ones_like(height)])
    normal /= np.linalg.norm(normal, axis=2, keepdims=True)
    light = np.array([0.55, 0.45, 0.72])
    light /= np.linalg.norm(light)
    shade = np.clip((normal * light).sum(axis=2), 0, 1)

    ground_cfg = ((desc.get("theme") or {}).get("ground") or {})
    grass = _rgb(ground_cfg.get("base_color") or "#8d9a6a")[:3]
    dirt = _rgb(ground_cfg.get("dirt_color") or "#8a5a35")[:3]

    rgb = np.zeros((size, size, 3), dtype=np.float64)
    for channel in range(3):
        surface = grass[channel] * (1 - band) + dirt[channel] * band
        rgb[:, :, channel] = surface * (0.30 + 0.95 * shade)
    image = Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8), mode="RGB")
    draw = ImageDraw.Draw(image)

    scale = size / world
    points = [
        (float(x) * scale, float(z) * scale)
        for x, z in zip(samples.x[::2], samples.z[::2])
    ]
    if len(points) > 2:
        draw.line(points + points[:1], fill=(25, 25, 25), width=2)

    gates = gates_cfg or {}
    start_at = resolve_distance(gates.get("start_at", 0), samples.length, "gates.start_at")
    x, z = samples.point(start_at)
    nx, nz = samples.normal(start_at)
    half = max(float(desc["track"]["width"]) * 0.5, float(gates.get("start_count", 20)) * float(gates.get("spacing", 4.0)) / 2)
    draw.line(
        [
            ((x - nx * half) * scale, (z - nz * half) * scale),
            ((x + nx * half) * scale, (z + nz * half) * scale),
        ],
        fill=(255, 255, 255),
        width=4,
    )

    count = int(gates.get("checkpoint_count", 0))
    for i in range(count):
        s = (start_at + i * samples.length / max(count, 1)) % samples.length
        gx_, gz_ = samples.point(s)
        cx, cz = samples.normal(s)
        length = float(desc["track"]["width"]) * 0.7
        draw.line(
            [
                ((gx_ - cx * length) * scale, (gz_ - cz * length) * scale),
                ((gx_ + cx * length) * scale, (gz_ + cz * length) * scale),
            ],
            fill=(220, 40, 40),
            width=3,
        )

    labels = {"jump": (255, 150, 40), "tabletop": (255, 194, 40), "whoops": (70, 150, 255), "rollers": (70, 200, 200), "berm": (190, 90, 220)}
    font = _font(max(12, size // 55))
    for report in reports or []:
        if report.kind not in labels:
            continue
        px, pz = samples.point(report.at % samples.length)
        cx = px * scale
        cz = pz * scale
        colour = labels[report.kind]
        draw.ellipse([cx - 5, cz - 5, cx + 5, cz + 5], fill=colour, outline=(20, 20, 20))
        draw.text((cx + 7, cz - 6), report.kind[:1].upper(), font=font, fill=colour, stroke_width=2, stroke_fill=(10, 10, 10))

    title_font = _font(max(18, size // 30))
    subtitle_font = _font(max(13, size // 55))
    draw.text((18, 14), str(desc.get("title") or desc["name"]), font=title_font, fill=(255, 255, 255), stroke_width=3, stroke_fill=(0, 0, 0))
    stats = (
        f"{samples.length:,.0f} ft lap   |   {world:g} x {world:g} ft terrain   |   "
        f"height {terrain_data['low']:.0f}..{terrain_data['high']:.0f} ft"
    )
    draw.text((20, 18 + title_font.size + 4), stats, font=subtitle_font, fill=(245, 245, 245), stroke_width=2, stroke_fill=(0, 0, 0))
    return image
