"""timing_gates generation: start gate row plus lap checkpoints."""

from __future__ import annotations

import math

from .files import checkpoint_line, start_gate_line
from .obstacles import resolve_distance

DEFAULTS = {
    "start_at": 0,
    "start_count": 20,
    "spacing": 4.0,
    "checkpoint_count": 7,
    "checkpoint_offset": 0.0,
    "width_margin": 8.0,
    "y_offset": 0.0,
    "checkpoint_width": None,
}


def build_gates(desc: dict, samples, terrain_data: dict) -> tuple[str, list[str]]:
    cfg = dict(DEFAULTS)
    cfg.update(desc.get("gates") or {})
    warnings: list[str] = []

    start_s = resolve_distance(cfg["start_at"], samples.length, "gates.start_at") % samples.length
    start_count = int(cfg["start_count"])
    spacing = float(cfg["spacing"])
    if start_count < 1:
        raise ValueError("gates.start_count must be at least 1")

    nx, nz = samples.normal(start_s)
    # Start gates are laid out along the cross-track normal, but MX Simulator's
    # text yaw is clockwise in x/z (z points down), so the row angle is negated.
    # The gate models are also directional: without the half turn they line up
    # with the row but face backwards. Normalize the result to (-pi, pi].
    rotation = math.pi - math.atan2(nz, nx)
    if rotation > math.pi:
        rotation -= 2.0 * math.pi

    start_lines: list[str] = []
    for i in range(start_count):
        lateral = (i - (start_count - 1) / 2.0) * spacing
        x = float(samples.point(start_s)[0] + nx * lateral)
        z = float(samples.point(start_s)[1] + nz * lateral)
        # Gates also store height above ground; 0 sits on the terrain.
        y = float(cfg["y_offset"])
        start_lines.append(start_gate_line(x, y, z, rotation))

    checkpoint_count = int(cfg["checkpoint_count"])
    if checkpoint_count < 3:
        raise ValueError("gates.checkpoint_count must be at least 3 for a valid first lap")

    checkpoint_width = cfg.get("checkpoint_width")
    if checkpoint_width is None:
        checkpoint_width = float(desc["track"]["width"]) + float(cfg["width_margin"])

    offset = float(cfg["checkpoint_offset"])
    check_lines: list[str] = []
    for i in range(checkpoint_count):
        s = (start_s + offset + i * samples.length / checkpoint_count) % samples.length
        x, z = samples.point(s)
        y = float(cfg["y_offset"])
        cx, cz = samples.tangent(s)
        check_lines.append(checkpoint_line(checkpoint_width, x, y, z, cx, cz))

    gate_width = start_count * spacing
    track_width = float(desc["track"]["width"])
    if gate_width > float(desc["track"].get("start_width") or max(track_width, gate_width + 8.0)):
        warnings.append("start gate row is wider than the start straight; widen track.start_width")

    lap = " ".join(str(i) for i in range(checkpoint_count))
    text = (
        "startinggate:\n"
        + "".join(start_lines)
        + "checkpoints:\n"
        + "".join(check_lines)
        + "firstlap:\n"
        + lap
        + "\nnormallap:\n"
        + lap
        + "\n"
    )
    return text, warnings
