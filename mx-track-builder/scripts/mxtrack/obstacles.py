"""Parametric obstacle presets and track elevation profile.

Obstacles are height deltas painted along distance-along-spline.  A jump is a
takeoff ramp, a steep backside into the gap, then a landing face and landing
slope.  Nothing here is random: the same description always builds the same
terrain.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

GRAVITY = 32.174  # ft / s^2
BERM_FLAT_RATIO = 0.45
BERM_RISE_POWER = 1.3
BERM_END_RATIO = 0.20
RUT_END_RATIO = 0.20

OBSTACLE_DEFAULTS: dict[str, dict] = {
    "jump": {
        "height": 7.0,
        "takeoff_angle": 22.0,
        "gap": 45.0,
        "table": 0.0,
        "landing_length": 35.0,
        "landing_ratio": 0.85,
        "backside_angle": 45.0,
        "landing_face_angle": 42.0,
    },
    "tabletop": {
        "height": 6.0,
        "takeoff_angle": 20.0,
        "gap": 0.0,
        "table": 18.0,
        "landing_length": 30.0,
        "landing_ratio": 1.0,
        "backside_angle": 45.0,
        "landing_face_angle": 42.0,
    },
    "whoops": {
        "count": 6,
        "spacing": 26.0,
        "height": 2.6,
        "height_start_ratio": 0.6,
    },
    "rollers": {
        "count": 3,
        "spacing": 52.0,
        "height": 3.5,
        "height_start_ratio": 0.7,
    },
    "berm": {
        "length": 70.0,
        "height": 3.0,
        "side": "auto",
    },
    "rut": {
        "length": 80.0,
        "width": 3.4,
        "depth": 0.32,
        "offset": 6.0,
        "side": "auto",
    },
}


def smoothstep(x):
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3.0 - 2.0 * x)


def smootherstep(x):
    x = np.clip(x, 0.0, 1.0)
    return x * x * x * (x * (x * 6.0 - 15.0) + 10.0)


def resolve_distance(value, total: float, field_name: str = "at") -> float:
    """Accept feet (12, 12.5) or a percentage of the lap ('35%')."""
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be a distance in feet or a percentage")
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if text.endswith("%"):
        try:
            pct = float(text[:-1])
        except ValueError as exc:
            raise ValueError(f"{field_name}: bad percentage {value!r}") from exc
        return total * pct / 100.0
    try:
        return float(text)
    except ValueError as exc:
        raise ValueError(f"{field_name}: expected feet or '35%', got {value!r}") from exc


def _smooth_circular(values: np.ndarray, window_samples: int) -> np.ndarray:
    if window_samples <= 1:
        return values.copy()
    window_samples = min(window_samples, len(values))
    kernel = np.hanning(window_samples)
    kernel /= kernel.sum()
    pad = window_samples
    extended = np.concatenate([values[-pad:], values, values[:pad]])
    convolved = np.convolve(extended, kernel, mode="same")
    return convolved[pad : pad + len(values)]


@dataclass
class ObstacleReport:
    kind: str
    at: float
    length: float
    detail: str
    warnings: list[str] = field(default_factory=list)


def _jump_delta(s: np.ndarray, start: float, p: dict) -> tuple[np.ndarray, float, dict]:
    """Build a jump with a real lip, a clear gap, and a rideable landing.

    For a double, ``gap`` is measured from the takeoff lip to the landing
    crest.  The near face of the landing rises from the gap floor, then the
    landing slope falls away.  That makes the distance unambiguous and puts
    the touchdown surface on a downhill instead of the uphill wall the old
    generator produced.
    """
    height = float(p["height"])
    angle_deg = float(p["takeoff_angle"])
    if not (5.0 <= angle_deg <= 50.0):
        raise ValueError("takeoff_angle must be between 5 and 50 degrees")
    if height <= 0:
        raise ValueError("jump height must be positive")

    gap = max(0.0, float(p["gap"]))
    table = max(0.0, float(p["table"]))
    if table > 0.0 and gap > 0.0:
        raise ValueError(
            "a jump cannot use both table and gap; use a tabletop (gap: 0) "
            "or a double (table: 0)"
        )
    landing_len = max(4.0, float(p["landing_length"]))
    landing_ratio = float(p["landing_ratio"])
    if landing_ratio <= 0.0:
        raise ValueError("landing_ratio must be positive")
    landing_top = height * landing_ratio
    backside_angle = np.deg2rad(float(p.get("backside_angle", 62.0)))
    face_angle = np.deg2rad(float(p.get("landing_face_angle", 55.0)))
    tan_angle = max(np.tan(np.deg2rad(angle_deg)), 1e-3)

    delta = np.zeros_like(s)
    face_len = 0.0
    backside_len = 0.0

    if gap > 0.0:
        # Cubic ramp with zero slope at the base and exactly the configured
        # takeoff angle at the lip.  ``2u^2-u^3`` is the unique cubic with
        # those boundary slopes and unit height.
        takeoff_len = max(2.0, height / tan_angle)
        lip = start + takeoff_len
        m = (s >= start) & (s < lip)
        u = np.clip((s[m] - start) / takeoff_len, 0.0, 1.0)
        delta[m] += height * (u * u * (2.0 - u))

        # The backside is inside the gap.  It is intentionally a rounded
        # drop; the rider leaves at the lip, not over this face.
        # smootherstep's peak slope is 1.875 x its average slope.  Size the
        # face from that peak so the requested angle is a true maximum; the
        # old length made a 62-degree backside peak at almost 74 degrees.
        backside_len = max(
            2.0,
            1.875 * height / max(np.tan(backside_angle), 1e-3),
        )
        m = (s >= lip) & (s < lip + backside_len)
        v = np.clip((s[m] - lip) / backside_len, 0.0, 1.0)
        delta[m] += height * (1.0 - smootherstep(v))

        crest = lip + gap
        face_len = max(
            2.0,
            1.875 * landing_top / max(np.tan(face_angle), 1e-3),
        )
        face_start = crest - face_len
        if face_start <= lip + backside_len:
            raise ValueError(
                f"jump gap {gap:g} ft is too short for its backside and "
                "landing face; increase gap or reduce landing_ratio"
            )

        m = (s >= face_start) & (s < crest)
        w = np.clip((s[m] - face_start) / face_len, 0.0, 1.0)
        delta[m] += landing_top * smootherstep(w)

        m = (s >= crest) & (s < crest + landing_len)
        v = np.clip((s[m] - crest) / landing_len, 0.0, 1.0)
        delta[m] += landing_top * (1.0 - smootherstep(v))
        end = crest + landing_len
        meta_gap = gap
    elif table > 0.0:
        # Tabletop: a smooth ramp onto a flat top, then a smooth, rollable
        # descent.  The ramp's maximum grade is the requested takeoff angle.
        takeoff_len = max(2.0, 1.5 * height / tan_angle)
        lip = start + takeoff_len
        m = (s >= start) & (s < lip)
        u = np.clip((s[m] - start) / takeoff_len, 0.0, 1.0)
        delta[m] += height * smoothstep(u)

        plateau_end = lip + table
        m = (s >= lip) & (s < plateau_end)
        delta[m] += height

        m = (s >= plateau_end) & (s < plateau_end + landing_len)
        v = np.clip((s[m] - plateau_end) / landing_len, 0.0, 1.0)
        delta[m] += height * (1.0 - smootherstep(v))
        crest = plateau_end
        end = plateau_end + landing_len
        meta_gap = 0.0
    else:
        # A bare kicker: the same engineered takeoff as a double, then a
        # rounded backside and no landing mound.
        takeoff_len = max(2.0, height / tan_angle)
        lip = start + takeoff_len
        m = (s >= start) & (s < lip)
        u = np.clip((s[m] - start) / takeoff_len, 0.0, 1.0)
        delta[m] += height * (u * u * (2.0 - u))

        backside_len = max(
            2.0,
            1.875 * height / max(np.tan(backside_angle), 1e-3),
        )
        m = (s >= lip) & (s < lip + backside_len)
        v = np.clip((s[m] - lip) / backside_len, 0.0, 1.0)
        delta[m] += height * (1.0 - smootherstep(v))
        crest = lip
        end = lip + backside_len
        meta_gap = 0.0

    meta = {
        "takeoff_len": takeoff_len,
        "gap": meta_gap,
        "landing_len": landing_len,
        "landing_top": landing_top,
        "face_len": face_len,
        "backside_len": backside_len,
        "lip": lip,
        "lip_height": height,
        "crest": crest,
        "end": end,
    }
    return delta, end - start, meta


def _mirror_delta(delta: np.ndarray, samples, start: float, span: float) -> np.ndarray:
    """Mirror an obstacle profile inside its own footprint.

    Used for tracks ridden from the far end of the spline.  The obstacle stays
    at the same physical location, but the takeoff and landing swap ends.
    """
    s = np.asarray(samples.s, dtype=float)
    length = float(samples.length)
    reflected = (2.0 * float(start) + float(span) - s) % length
    extended_s = np.concatenate([s - length, s, s + length])
    extended_delta = np.concatenate([delta, delta, delta])
    return np.interp(reflected, extended_s, extended_delta, left=0.0, right=0.0)


def jump_clear_speed_mph(p: dict, meta: dict) -> float | None:
    """Rough projectile estimate of the speed needed to reach the landing crest.

    ``gap`` is horizontal lip-to-crest distance.  The landing can be lower or
    higher than the lip, so the vertical drop is included.  Suspension and
    slope shape are ignored; this is a sanity check, not a bike simulation.
    """
    gap = float(meta.get("gap", 0.0))
    if gap <= 0.0:
        return None
    angle = np.deg2rad(float(p["takeoff_angle"]))
    tan_angle = np.tan(angle)
    cos_angle = np.cos(angle)
    if cos_angle <= 1e-6:
        return None
    drop = float(meta.get("landing_top", 0.0)) - float(meta.get("lip_height", 0.0))
    denominator = gap * tan_angle - drop
    if denominator <= 1e-6:
        return None
    velocity_sq = GRAVITY * gap * gap / (2.0 * cos_angle * cos_angle * denominator)
    if velocity_sq <= 0.0:
        return None
    return float(np.sqrt(velocity_sq) * 3600.0 / 5280.0)


def _whoops_delta(s: np.ndarray, start: float, p: dict) -> tuple[np.ndarray, float, dict]:
    count = int(p["count"])
    spacing = float(p["spacing"])
    height = float(p["height"])
    first = float(p.get("height_start_ratio", 0.6))
    if count < 1:
        raise ValueError("whoops/rollers need count >= 1")
    if spacing < 1.0:
        raise ValueError("whoops/rollers spacing must be at least 1 ft")

    delta = np.zeros_like(s)
    bump_len = spacing * 0.92
    for i in range(count):
        bump_start = start + i * spacing
        scale = first + (1.0 - first) * (i / max(count - 1, 1))
        m = (s >= bump_start) & (s < bump_start + bump_len)
        u = (s[m] - bump_start) / bump_len
        delta[m] += height * scale * np.sin(np.pi * u) ** 2
    return delta, count * spacing, {"count": count, "spacing": spacing}


def bank_cross_section(bank: float, ratio):
    """Height of a one-sided berm at one or more lateral positions.

    ``bank`` is signed: positive means the berm is on the +normal side.  The
    inside 45% of the half-width stays flat; the outside then rises on a
    concave curve that is steepest at the lip.  A smootherstep made a rounded
    hump with a flat top, which reads as a mound rather than a berm.
    ``ratio`` is lateral position / half-width and may be a vector.
    """
    ratio = np.asarray(ratio, dtype=float)
    bank_value = np.asarray(bank, dtype=float)
    if bank_value.ndim == 0:
        if not np.isfinite(bank_value) or abs(float(bank_value)) < 1e-12:
            return np.zeros_like(ratio)
    # The sign selects which side is high; the magnitude is always the raised
    # shoulder height.  The old linear form used the sign as a slope and cut
    # the opposite side, which is exactly what a berm must not do.
    side = np.where(bank_value >= 0.0, 1.0, -1.0)
    q = np.clip(ratio * side, 0.0, 1.0)
    rise = np.clip((q - BERM_FLAT_RATIO) / (1.0 - BERM_FLAT_RATIO), 0.0, 1.0)
    result = np.abs(bank_value) * rise**BERM_RISE_POWER
    if bank_value.ndim > 0:
        result = np.where(np.isfinite(bank_value) & (np.abs(bank_value) >= 1e-12), result, 0.0)
    return result


def rut_cross_section(rut, lateral):
    """Depth of a single rut at one or more lateral positions.

    ``rut`` is ``(offset, width, depth)`` in feet.  The outer edges return to
    the flat track surface, so the rut reads as a line without building a
    shoulder or a berm.
    """
    values = np.asarray(rut, dtype=float)
    lateral = np.asarray(lateral, dtype=float)
    if values.ndim == 1:
        if values.size < 3 or values[2] <= 0.0:
            return np.zeros_like(lateral)
        offset, width, depth = values[0], values[1], values[2]
    else:
        offset, width, depth = values[0], values[1], values[2]
    half_width = np.maximum(0.5 * width, 1e-6)
    q = np.clip(np.abs(lateral - offset) / half_width, 0.0, 1.0)
    return -depth * (1.0 - smootherstep(q))


def _berm(s: np.ndarray, start: float, p: dict, samples) -> tuple[np.ndarray, float, dict]:
    length = max(8.0, float(p["length"]))
    height = float(p["height"])
    side = str(p["side"]).lower()
    if side == "outside":
        side = "auto"

    # Look across the whole berm, not just its midpoint: a long berm on an
    # S-turn can start outside one corner and finish inside the next.
    fractions = (0.1, 0.3, 0.5, 0.7, 0.9)
    curvatures = np.array(
        [samples.curvature(start + length * fraction) for fraction in fractions]
    )
    curvature = float(np.mean(curvatures))
    warnings: list[str] = []

    if side == "auto":
        if abs(curvature) < 1e-4:
            sign = 1.0
            warnings.append("berm is on a nearly straight section; move it into a corner")
        else:
            # Positive curvature turns left, so the outside of that turn is
            # right (negative normal side).
            sign = -1.0 if curvature > 0 else 1.0
        if float(np.min(curvatures)) < -1e-5 < float(np.max(curvatures)):
            warnings.append(
                "berm crosses a curvature reversal; split it or shorten it"
            )
    elif side == "left":
        sign = 1.0
    elif side == "right":
        sign = -1.0
    else:
        raise ValueError("berm side must be auto, left or right")

    if side in ("left", "right") and abs(curvature) >= 1e-4:
        outside_sign = -1.0 if curvature > 0.0 else 1.0
        if sign != outside_sign:
            warnings.append("forced berm side is inside the corner")

    u = np.clip((s - start) / length, 0.0, 1.0)
    envelope = smootherstep(np.minimum(u, 1.0 - u) / BERM_END_RATIO)
    bank = envelope * height * sign
    return bank, length, {
        "side": "left" if sign > 0 else "right",
        "requested_side": side,
        "bank": height,
        "curvature": curvature,
        "warnings": warnings,
    }


def _rut(s: np.ndarray, start: float, p: dict, samples, track: dict) -> tuple[np.ndarray, float, dict]:
    """Put a shallow groove on the inside of a flat corner."""
    length = max(8.0, float(p["length"]))
    width = max(1.0, float(p["width"]))
    depth = max(0.0, float(p["depth"]))
    requested_offset = max(0.0, float(p["offset"]))
    side = str(p["side"]).lower()
    if side == "outside":
        side = "auto"

    fractions = (0.1, 0.3, 0.5, 0.7, 0.9)
    curvatures = np.array(
        [samples.curvature(start + length * fraction) for fraction in fractions]
    )
    curvature = float(np.mean(curvatures))
    warnings: list[str] = []

    if side == "auto":
        if abs(curvature) < 1e-4:
            sign = 1.0
            warnings.append("rut is on a nearly straight section; move it into a corner")
        else:
            # Positive curvature turns left; the inside is the +normal side.
            sign = 1.0 if curvature > 0 else -1.0
        if float(np.min(curvatures)) < -1e-5 < float(np.max(curvatures)):
            warnings.append("rut crosses a curvature reversal; split it or shorten it")
    elif side == "left":
        sign = 1.0
    elif side == "right":
        sign = -1.0
    else:
        raise ValueError("rut side must be auto, left or right")

    if side in ("left", "right") and abs(curvature) >= 1e-4:
        inside_sign = 1.0 if curvature > 0.0 else -1.0
        if sign != inside_sign:
            warnings.append("forced rut side is outside the corner")

    half_width = float(track["width"]) * 0.5
    max_offset = max(0.0, half_width - width * 0.5 - 1.5)
    offset = min(requested_offset, max_offset)
    if offset < requested_offset:
        warnings.append("rut offset was clamped to keep it inside the track edge")

    u = np.clip((s - start) / length, 0.0, 1.0)
    envelope = smootherstep(np.minimum(u, 1.0 - u) / RUT_END_RATIO)
    result = np.zeros((len(s), 3), dtype=float)
    active = envelope > 0.0
    result[:, 0] = np.where(active, sign * offset, 0.0)
    result[:, 1] = np.where(active, width, 0.0)
    result[:, 2] = envelope * depth
    if depth > 0.6:
        warnings.append("rut depth above 0.6 ft is very deep")
    return result, length, {
        "side": "left" if sign > 0 else "right",
        "requested_side": side,
        "offset": offset,
        "width": width,
        "depth": depth,
        "curvature": curvature,
        "warnings": warnings,
    }


def build_profile(
    samples,
    base_heights: np.ndarray,
    track: dict,
    obstacles: list[dict],
) -> tuple[np.ndarray, np.ndarray, np.ndarray, list[ObstacleReport]]:
    """Return (absolute track heights, bank at +normal edge, ruts, reports)."""
    s = samples.s
    length = samples.length

    smooth_ft = float(track.get("smooth", 45.0))
    window = max(1, int(round(smooth_ft / samples.ds)))
    profile = _smooth_circular(np.asarray(base_heights, dtype=float), window)

    elevation = track.get("elevation") or []
    if elevation:
        points = sorted(
            (resolve_distance(item["at"], length, "track.elevation.at"), float(item["height"]))
            for item in elevation
        )
        if len(points) < 2:
            raise ValueError("track.elevation needs at least two {at, height} entries")
        targets = np.array([p[0] for p in points])
        values = np.array([p[1] for p in points])
        extended_s = np.concatenate([targets - length, targets, targets + length])
        extended_v = np.concatenate([values, values, values])
        target_profile = np.interp(s, extended_s, extended_v)
        elevation_smooth = max(20.0, float(track.get("elevation_smooth", 80.0)))
        profile = _smooth_circular(
            target_profile, max(3, int(elevation_smooth / samples.ds))
        )

    bank = np.zeros_like(profile)
    ruts = np.zeros((len(s), 3), dtype=float)
    reports: list[ObstacleReport] = []
    intervals: list[tuple[float, float, str]] = []

    for entry in obstacles:
        kind = str(entry.get("type", "")).lower()
        if kind not in OBSTACLE_DEFAULTS:
            raise ValueError(
                f"unknown obstacle type {kind!r}; use one of {sorted(OBSTACLE_DEFAULTS)}"
            )
        params = dict(OBSTACLE_DEFAULTS[kind])
        params.update({k: v for k, v in entry.items() if k not in ("type", "at")})
        start = resolve_distance(entry.get("at", 0.0), length, "obstacle.at")
        warnings: list[str] = []
        if start >= length:
            warnings.append("obstacle starts past the end of the lap; move it earlier")
            start = start % length

        if kind in ("jump", "tabletop"):
            delta, span, meta = _jump_delta(s, start, params)
            if start + span > length:
                # The obstacle crosses the start line: continue it at s+L so it
                # does not vanish at the lap seam.
                extra, _, _ = _jump_delta(s + length, start, params)
                delta = delta + extra
            if bool(entry.get("reverse", False)):
                delta = _mirror_delta(delta, samples, start, span)
            profile += delta
            detail = (
                f"h={params['height']:g}ft takeoff={params['takeoff_angle']:g}deg "
            )
            if float(params["gap"]) > 0.0:
                detail += f"gap={params['gap']:g}ft "
            if float(params["table"]) > 0.0:
                detail += f"table={params['table']:g}ft "
            detail += f"landing={params['landing_length']:g}ft"
            if bool(entry.get("reverse", False)):
                detail += " reversed"
            speed = jump_clear_speed_mph(params, meta)
            if speed is not None:
                detail += f" est_clear={speed:.0f}mph"
                if speed > 70:
                    warnings.append("estimated clearing speed is very high; shorten the gap")
                if speed < 12:
                    warnings.append("estimated clearing speed is very low; check gap and height")
            elif float(meta.get("gap", 0.0)) > 0.0:
                warnings.append(
                    "landing crest is above the available ballistic arc; "
                    "lower landing_ratio or increase the gap"
                )
            if float(params["height"]) > 15:
                warnings.append("jump height above 15 ft is extreme for MX Sim")
            mid_curvature = samples.curvature(start + span * 0.5)
            if abs(mid_curvature) > 1.0 / 150.0:
                warnings.append(
                    "jump is on a tight corner; move it to a straighter section"
                )
        elif kind in ("whoops", "rollers"):
            delta, span, meta = _whoops_delta(s, start, params)
            if start + span > length:
                extra, _, _ = _whoops_delta(s + length, start, params)
                delta = delta + extra
            profile += delta
            detail = f"{meta['count']} bumps, {meta['spacing']:g}ft spacing, h={params['height']:g}ft"
            if float(params["height"]) > 5:
                warnings.append("whoop/roller height above 5 ft is very tall")
        elif kind == "rut":
            rut_delta, span, meta = _rut(s, start, params, samples, track)
            if start + span > length:
                extra, _, _ = _rut(s + length, start, params, samples, track)
                rut_delta = rut_delta + extra
            active = rut_delta[:, 2] > 0.0
            ruts[active] += rut_delta[active]
            side_label = meta["side"]
            if meta["requested_side"] == "auto":
                side_label += " (auto)"
            detail = (
                f"{span:g}ft, offset={meta['offset']:g}ft, "
                f"width={meta['width']:g}ft, depth={meta['depth']:g}ft, "
                f"side={side_label}"
            )
            warnings.extend(meta.get("warnings", []))
        else:
            bank_delta, span, meta = _berm(s, start, params, samples)
            if start + span > length:
                extra, _, _ = _berm(s + length, start, params, samples)
                bank_delta = bank_delta + extra
            bank += bank_delta
            side_label = meta["side"]
            if meta["requested_side"] == "auto":
                side_label += " (auto)"
            detail = (
                f"{params['length']:g}ft, bank={params['height']:g}ft, "
                f"side={side_label}"
            )
            warnings.extend(meta.get("warnings", []))
            if float(params["height"]) > 8:
                warnings.append("berm bank above 8 ft is extreme")

        reports.append(ObstacleReport(kind, start, span, detail, warnings))
        intervals.append((start, start + span, kind))

    for i in range(len(intervals)):
        a_start, a_end, a_kind = intervals[i]
        for b_start, b_end, b_kind in intervals[i + 1 :]:
            overlap = min(a_end, b_end) - max(a_start, b_start)
            if overlap > 2.0:
                reports.append(
                    ObstacleReport(
                        "warning",
                        max(a_start, b_start),
                        overlap,
                        f"{a_kind} overlaps {b_kind} by {overlap:.0f}ft",
                        ["overlapping obstacle height deltas add up"],
                    )
                )

    # Flatten the start pad so the gate row and first metres are level.
    flat_ft = float(track.get("start_flat", 90.0))
    if flat_ft > 0:
        near_start = profile[(s < 10.0) | (s > length - 10.0)]
        target = float(np.mean(near_start)) if len(near_start) else float(profile[0])
        distance = np.minimum(s, length - s)
        blend = 1.0 - smootherstep(distance / flat_ft)
        profile = profile * (1.0 - blend) + target * blend

    return profile, bank, ruts, reports


def half_widths(samples, track: dict, gates: dict) -> np.ndarray:
    """Ribbon half-width per sample; the start straight widens for the gate row."""
    width = float(track["width"])
    start_width = track.get("start_width")
    if start_width is None:
        start_width = max(
            width,
            float(gates.get("start_count", 20)) * float(gates.get("spacing", 4.0)) + 8.0,
        )
    start_width = float(start_width)
    taper = max(1.0, float(track.get("start_taper", 160.0)))
    distance = np.minimum(samples.s, samples.length - samples.s)
    blend = 1.0 - smootherstep(distance / taper)
    width_s = width * (1.0 - blend) + start_width * blend
    return width_s * 0.5
