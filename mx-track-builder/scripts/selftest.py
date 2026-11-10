#!/usr/bin/env python3
"""Self-test: build every bundled example, validate it, and check determinism.

Usage:
    python selftest.py
"""

from __future__ import annotations

import hashlib
import re
import sys
import tempfile
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

from build_track import build  # noqa: E402
from mxtrack.files import decode_png16_gray  # noqa: E402
from mxtrack.obstacles import (  # noqa: E402
    OBSTACLE_DEFAULTS,
    _jump_delta,
    _mirror_delta,
    _rut,
    _whoops_delta,
    bank_cross_section,
    jump_clear_speed_mph,
    rut_cross_section,
)
from mxtrack.terrain import sample_grid_many, stamp_ribbon  # noqa: E402
from validate_track import validate_folder  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
EXAMPLES = sorted((ROOT / "assets" / "examples").glob("*.yaml"))


def hashes(folder: Path) -> dict[str, str]:
    result = {}
    for path in sorted(folder.rglob("*")):
        if path.is_file():
            result[str(path.relative_to(folder))] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def check_geometry() -> list[str]:
    """Check the parametric jump/whoop geometry without needing the game."""
    problems: list[str] = []
    s = np.arange(0.0, 260.0, 0.25)

    jump = dict(OBSTACLE_DEFAULTS["jump"])
    jump.update(height=8.0, takeoff_angle=22.0, gap=50.0, landing_length=35.0)
    delta, span, meta = _jump_delta(s, 10.0, jump)
    lip = 10.0 + meta["takeoff_len"]
    lip_index = np.searchsorted(s, lip) - 1
    if abs(float(delta[lip_index]) - 8.0) > 0.35:
        problems.append("jump lip does not reach the requested height")
    lip_slope = (float(delta[lip_index]) - float(delta[lip_index - 1])) / 0.25
    requested_slope = float(np.tan(np.deg2rad(jump["takeoff_angle"])))
    if abs(lip_slope - requested_slope) > 0.15:
        problems.append(
            f"jump lip slope is {lip_slope:.2f}, expected {requested_slope:.2f}"
        )
    gap_mid = lip + meta["backside_len"] + 5.0
    if float(delta[np.searchsorted(s, gap_mid)]) > 0.05:
        problems.append("jump gap floor is not at baseline")
    downslope_start = meta["crest"]
    near_peak = float(delta[np.searchsorted(s, downslope_start)])
    if near_peak < 8.0 * jump["landing_ratio"] - 0.6:
        problems.append("jump landing crest is too low")
    after_crest = float(delta[np.searchsorted(s, downslope_start + 2.0)])
    if after_crest >= near_peak:
        problems.append("jump landing does not fall away after the crest")
    if abs(span - (meta["end"] - 10.0)) > 1e-6:
        problems.append("jump span disagrees with its end point")
    speed = jump_clear_speed_mph(jump, meta)
    if speed is None or not (20.0 <= speed <= 45.0):
        problems.append(f"jump clearing speed is not sane ({speed})")

    # The smootherstep faces must not exceed the requested angle.  This is
    # what keeps the backside from becoming a near-vertical serrated wall.
    for label, start_s, length_s, requested in (
        ("backside", meta["lip"], meta["backside_len"], jump["backside_angle"]),
        (
            "landing face",
            meta["crest"] - meta["face_len"],
            meta["face_len"],
            jump["landing_face_angle"],
        ),
    ):
        probe_s = np.linspace(start_s + 0.05, start_s + length_s - 0.05, 200)
        probe = _jump_delta(probe_s, 10.0, jump)[0]
        probe_slope = np.max(np.abs(np.diff(probe) / np.diff(probe_s)))
        probe_angle = float(np.degrees(np.arctan(probe_slope)))
        if probe_angle > float(requested) + 1.0:
            problems.append(
                f"jump {label} is {probe_angle:.1f} deg, over {requested:g} deg"
            )

    whoops = dict(OBSTACLE_DEFAULTS["whoops"])
    whoops.update(count=5, spacing=20.0, height=2.0)
    wdelta, wspan, wmeta = _whoops_delta(s, 4.0, whoops)
    if abs(float(wdelta.max()) - 2.0) > 0.01:
        problems.append("whoop peak does not match configured height")
    if abs(wspan - 100.0) > 1e-6:
        problems.append("whoop section span is wrong")
    after_last = 4.0 + (whoops["count"] - 1) * whoops["spacing"] + whoops["spacing"] * 0.92 + 2.0
    if float(wdelta[np.searchsorted(s, after_last)]) > 0.05:
        problems.append("whoops do not return to baseline after the last bump")

    table = dict(OBSTACLE_DEFAULTS["tabletop"])
    table.update(height=6.0, table=18.0, landing_length=25.0)
    tdelta, tspan, tmeta = _jump_delta(s, 0.0, table)
    if abs(float(tdelta[np.searchsorted(s, tmeta["lip"] + 9.0)]) - 6.0) > 1e-6:
        problems.append("tabletop plateau is not flat at the requested height")

    if abs(bank_cross_section(3.0, -1.0)) > 1e-9:
        problems.append("berm banks the inside of the turn")
    if abs(bank_cross_section(3.0, 1.0) - 3.0) > 1e-6:
        problems.append("berm does not reach full bank at the outside edge")
    if abs(bank_cross_section(-3.0, -1.0) - 3.0) > 1e-6:
        problems.append("negative-side berm does not raise its outside edge")
    if bank_cross_section(3.0, 0.0) != 0.0:
        problems.append("berm is not flat at the centreline")
    if abs(bank_cross_section(3.0, 0.40)) > 1e-9:
        problems.append("berm rises across the flat inside of the turn")
    h50 = float(bank_cross_section(3.0, 0.50))
    h75 = float(bank_cross_section(3.0, 0.75))
    h100 = float(bank_cross_section(3.0, 1.00))
    if (h75 - h50) >= (h100 - h75):
        problems.append("berm face is not concave toward the outer lip")

    rut_cross = rut_cross_section(
        np.array([6.0, 3.4, 0.32]), np.array([6.0, 9.4, 2.6])
    )
    if abs(float(rut_cross[0]) + 0.32) > 1e-6:
        problems.append("rut does not reach its requested depth at the centre")
    if abs(float(rut_cross[1])) > 1e-9 or abs(float(rut_cross[2])) > 1e-9:
        problems.append("rut does not return to the flat track at its edges")

    from types import SimpleNamespace

    flat_turn = SimpleNamespace(curvature=lambda position: 0.02)
    ruts, rut_span, rut_meta = _rut(
        s,
        10.0,
        {"length": 80.0, "width": 3.4, "depth": 0.32, "offset": 6.0, "side": "auto"},
        flat_turn,
        {"width": 26.0},
    )
    rut_mid = int(np.searchsorted(s, 50.0))
    if abs(rut_span - 80.0) > 1e-6:
        problems.append("rut span is wrong")
    if abs(float(ruts[rut_mid, 2]) - 0.32) > 1e-6:
        problems.append("rut does not reach full depth at its midpoint")
    if abs(float(ruts[rut_mid, 0]) - 6.0) > 1e-6:
        problems.append("rut is not on the inside of the turn")
    if abs(float(ruts[rut_mid, 1]) - 3.4) > 1e-6:
        problems.append("rut width was widened by inactive rows")
    if abs(float(ruts[0, 2])) > 1e-9:
        problems.append("rut does not taper to zero at its start")
    if rut_meta["side"] != "left":
        problems.append("rut auto side chose the outside of the turn")
    return problems


def check_layout(result) -> tuple[list[str], float]:
    """Reject hairpins that are tight enough to fold the ribbon."""
    samples = result["samples"]
    width = float(result["desc"]["track"]["width"])
    min_radius = 1.0 / max(float(np.max(np.abs(samples.k))), 1e-9)
    if min_radius < width * 0.6:
        return (
            [
                f"tightest corner radius {min_radius:.1f} ft is below "
                f"0.6 x track width ({width * 0.6:.1f} ft)"
            ],
            min_radius,
        )
    return [], min_radius


def check_ribbon_coverage() -> list[str]:
    """A zero-coverage station must not overwrite a covered one."""
    shape = (61, 61)
    value, weight = stamp_ribbon(
        shape,
        1.0,
        np.array([10.0, 30.0]),
        np.array([30.0, 30.0]),
        np.array([1.0, 1.0]),
        np.array([0.0, 0.0]),
        np.array([2.0, 2.0]),
        0.0,
        np.array([10.0, 20.0]),
        sample_spacing=1.0,
    )
    problems = []
    if abs(float(value[30, 10]) - 10.0) > 1e-6:
        problems.append("ribbon lost the covered station's height")
    if abs(float(value[30, 30]) - 20.0) > 1e-6:
        problems.append("a zero-coverage station overwrote the ribbon height")
    if abs(float(weight[30, 30]) - 1.0) > 1e-6:
        problems.append("ribbon coverage is not full at the station centre")
    return problems


def check_reverse_delta() -> list[str]:
    """A reversed obstacle must swap ends without changing its footprint."""
    from types import SimpleNamespace

    s = np.arange(0.0, 40.0, 0.5)
    delta = np.zeros_like(s)
    # Two unequal blocks make it obvious if the ends fail to swap.
    delta[(s >= 10.0) & (s < 12.0)] = 1.0
    delta[(s >= 18.0) & (s < 20.0)] = 2.0
    mirrored = _mirror_delta(
        delta, SimpleNamespace(s=s, length=40.0), 10.0, 10.0
    )
    problems = []
    if abs(float(mirrored[np.searchsorted(s, 11.0)]) - 2.0) > 1e-6:
        problems.append("reversed jump did not move the far end to the start")
    if abs(float(mirrored[np.searchsorted(s, 19.0)]) - 1.0) > 1e-6:
        problems.append("reversed jump did not move the start to the far end")
    if np.any(mirrored < 0.0) or np.any(mirrored > 2.0):
        problems.append("reversed jump changes the height range")
    return problems


def check_ribbon_direction() -> list[str]:
    """The interpolated ribbon must advance with the spline tangent."""
    value, _ = stamp_ribbon(
        (31, 31),
        1.0,
        np.arange(8.0, 18.0, 2.0),
        np.full(5, 15.0),
        np.zeros(5),
        np.ones(5),
        np.full(5, 2.0),
        0.0,
        np.arange(0.0, 50.0, 10.0),
        sample_spacing=2.0,
        interpolate_sample_value=True,
    )
    expected = np.arange(0.0, 45.0, 5.0)
    actual = value[15, 8:17]
    if not np.allclose(actual, expected):
        return [
            "ribbon height runs backward along the track: "
            f"{np.round(actual, 2).tolist()} != {expected.tolist()}"
        ]
    return []


def check_heightmap(result) -> list[str]:
    """The decoded heightfield must match the profile along the centreline."""
    problems: list[str] = []
    terrain = result["terrain"]
    decoded = decode_png16_gray(result["folder"] / "terrain.png")
    if decoded.shape != terrain["encoded"].shape or not np.array_equal(decoded, terrain["encoded"]):
        problems.append("terrain.png does not round-trip to the encoded heightfield")
    values = sample_grid_many(
        terrain["grid"], terrain["resolution"], result["samples"].x, result["samples"].z
    )
    error = np.abs(values - result["profile"])
    if float(error.mean()) > 0.3:
        problems.append(f"centreline mean height error is {error.mean():.2f} ft")
    if float(error.max()) > 4.0:
        problems.append(f"centreline max height error is {error.max():.2f} ft")
    return problems


TRIPLE_RE = re.compile(r"\[\s*(-?[\d.]+)\s+(-?[\d.]+)\s+(-?[\d.]+)\s*\]")


def check_ground_relative(folder: Path) -> list[str]:
    """Props and gates store height above ground; bundled examples use 0."""
    problems: list[str] = []
    for name in ("statues", "billboards", "timing_gates"):
        for lineno, line in enumerate((folder / name).read_text().splitlines(), 1):
            for match in TRIPLE_RE.finditer(line):
                y = float(match.group(2))
                if abs(y) > 1e-6:
                    problems.append(
                        f"{name}:{lineno} has y={y:g}; props and gates must store "
                        "height above ground (0)"
                    )
    return problems


def main() -> int:
    if not EXAMPLES:
        print("no examples found")
        return 1
    failures = 0

    geometry = check_geometry()
    print("obstacle geometry checks: " + ("PASS" if not geometry else "FAIL"))
    for problem in geometry:
        print(f"  [FAIL] {problem}")
    if geometry:
        failures += len(geometry)

    coverage = check_ribbon_coverage()
    print("ribbon station coverage: " + ("PASS" if not coverage else "FAIL"))
    for problem in coverage:
        print(f"  [FAIL] {problem}")
    if coverage:
        failures += len(coverage)

    direction = check_ribbon_direction()
    print("ribbon direction: " + ("PASS" if not direction else "FAIL"))
    for problem in direction:
        print(f"  [FAIL] {problem}")
    if direction:
        failures += len(direction)

    reverse = check_reverse_delta()
    print("reversed jump profile: " + ("PASS" if not reverse else "FAIL"))
    for problem in reverse:
        print(f"  [FAIL] {problem}")
    if reverse:
        failures += len(reverse)
    with tempfile.TemporaryDirectory() as tmp:
        for example in EXAMPLES:
            print(f"\n=== {example.name} ===")
            first = Path(tmp) / f"{example.stem}-a"
            second = Path(tmp) / f"{example.stem}-b"
            try:
                one = build(example, first, preview=True)
                twice = build(example, second, preview=True)
            except Exception as exc:  # noqa: BLE001
                print(f"BUILD FAILED: {exc!r}")
                failures += 1
                continue

            checks = validate_folder(one["folder"])
            failed = [c for c in checks if not c[1]]
            for name, ok, detail in checks:
                if not ok:
                    print(f"  [FAIL] {name} ({detail})")
            print(f"  {len(checks) - len(failed)}/{len(checks)} format checks passed")

            heightmap = check_heightmap(one)
            print("  heightmap round-trip/centreline: " + ("PASS" if not heightmap else "FAIL"))
            for problem in heightmap:
                print(f"  [FAIL] {problem}")
            failures += len(heightmap)

            layout, min_radius = check_layout(one)
            print(
                f"  layout radius: {'PASS' if not layout else 'FAIL'} "
                f"(min {min_radius:.1f} ft)"
            )
            for problem in layout:
                print(f"  [FAIL] {problem}")
            failures += len(layout)

            relative = check_ground_relative(one["folder"])
            print("  props/gates ground-relative Y: " + ("PASS" if not relative else "FAIL"))
            for problem in relative:
                print(f"  [FAIL] {problem}")
            failures += len(relative)

            same = hashes(one["folder"]) == hashes(twice["folder"])
            print(f"  deterministic rebuild: {'yes' if same else 'NO'}")
            print(f"  lap {one['samples'].length:,.0f} ft, {len(one['reports'])} obstacle reports, "
                  f"{one['statues']} statues, {one['billboards']} billboards")
            if failed:
                failures += 1
            if not same:
                failures += 1

    print(f"\n{'ALL PASSED' if failures == 0 else str(failures) + ' FAILURES'}")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
