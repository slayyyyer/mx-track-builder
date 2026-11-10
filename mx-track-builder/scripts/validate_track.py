#!/usr/bin/env python3
"""Validate a built MX Simulator track folder against the game's formats.

Usage:
    python validate_track.py path/to/TrackFolder
"""

from __future__ import annotations

import argparse
import math
import re
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mxtrack.files import decode_png16_gray  # noqa: E402

STATUE_RE = re.compile(
    r"^\[\s*(-?[\d.]+)\s+(-?[\d.]+)\s+(-?[\d.]+)\s*\]\s+"
    r"(-?[\d.]+)\s+(\S+)\s+(\S+)\s+(\S+)\s*$"
)
BILLBOARD_RE = re.compile(
    r"^\[\s*(-?[\d.]+)\s+(-?[\d.]+)\s+(-?[\d.]+)\s*\]\s+"
    r"(-?[\d.]+)\s+(-?[\d.]+)\s+(\S+)\s*$"
)
GATE_RE = re.compile(r"^\[(-?[\d.]+)\s+(-?[\d.]+)\s+(-?[\d.]+)\]\s+(-?[\d.]+)\s*$")
CHECKPOINT_RE = re.compile(
    r"^(-?[\d.]+)\s+\[(-?[\d.]+)\s+(-?[\d.]+)\s+(-?[\d.]+)\]\s+"
    r"\[(-?[\d.]+)\s+(-?[\d.]+)\s+(-?[\d.]+)\]\s*$"
)
DECAL_RE = re.compile(
    r"^\[(-?[\d.]+)\s+(-?[\d.]+)\]\s+(-?[\d.]+)\s+(-?[\d.]+)\s+(-?[\d.]+)\s+(\S+)\s*$"
)


def _power_of_two(value: int) -> bool:
    return value > 0 and (value & (value - 1)) == 0


def validate_folder(folder: str | Path) -> list[tuple[str, bool, str]]:
    folder = Path(folder)
    checks: list[tuple[str, bool, str]] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        checks.append((name, bool(ok), detail))

    required = [
        "terrain.hf", "terrain.png", "map.png", "desc", "timing_gates", "decals",
        "statues", "billboards", "tileinfo", "tilemap", "lighting",
    ]
    for name in required:
        check(f"exists {name}", (folder / name).is_file(), str(folder / name))
    if not all(ok for _, ok, _ in checks):
        return checks

    # terrain.hf and the 16-bit heightfield.
    try:
        tokens = (folder / "terrain.hf").read_text().split()
        dimension = int(tokens[0])
        resolution = float(tokens[1])
        low, high = float(tokens[2]), float(tokens[3])
        expected = 2 ** (dimension + 1) + 1
        check("terrain.hf has 4 fields", len(tokens) == 4, " ".join(tokens))
        check("terrain.hf height range", high > low, f"{low} .. {high}")
        check("terrain.hf resolution", resolution > 0, f"{resolution} ft/px")
        heights = decode_png16_gray(folder / "terrain.png")
        check(
            "terrain.png is 16-bit greyscale",
            heights.dtype == np.uint16,
            str(heights.dtype),
        )
        check(
            "terrain.png size matches terrain.hf",
            heights.shape == (expected, expected),
            f"{heights.shape} vs {expected}x{expected}",
        )
        check("terrain has height variation", int(heights.min()) != int(heights.max()),
              f"min {heights.min()} max {heights.max()}")
    except Exception as exc:  # noqa: BLE001
        check("terrain files parse", False, repr(exc))

    # Map.
    try:
        with Image.open(folder / "map.png") as image:
            check("map.png is RGBA", image.mode == "RGBA", image.mode)
            check(
                "map.png is power of two",
                _power_of_two(image.width) and _power_of_two(image.height),
                f"{image.width}x{image.height}",
            )
    except Exception as exc:  # noqa: BLE001
        check("map.png parses", False, repr(exc))

    # Text files must use unix line endings.
    for name in ("desc", "timing_gates", "statues", "billboards", "decals", "terrain.hf", "tileinfo", "lighting"):
        data = (folder / name).read_bytes()
        check(f"{name} uses LF endings", b"\r" not in data, "found CR")

    # Gates.
    gates_path = folder / "timing_gates"
    lines = [line.strip() for line in gates_path.read_text().splitlines()]
    try:
        start_index = lines.index("startinggate:") + 1
        checkpoint_index = lines.index("checkpoints:") + 1
        firstlap_index = lines.index("firstlap:")
        normallap_index = lines.index("normallap:")
        start_lines = [l for l in lines[start_index:checkpoint_index - 1] if l]
        check_lines = [l for l in lines[checkpoint_index:firstlap_index] if l]
        lap_first = lines[firstlap_index + 1].split()
        lap_normal = lines[normallap_index + 1].split()

        start_matches = [GATE_RE.match(l) for l in start_lines]
        check("start gates parse", all(start_matches), f"{len(start_lines)} lines")
        check("start gate count >= 2", len(start_lines) >= 2, str(len(start_lines)))
        if all(start_matches) and len(start_matches) >= 2:
            first, last = start_matches[0], start_matches[-1]
            row_angle = math.atan2(
                float(last.group(3)) - float(first.group(3)),
                float(last.group(1)) - float(first.group(1)),
            )
            deviations = []
            for match in start_matches:
                angle = float(match.group(4))
                # Gate models are directional: the stored yaw is the reversed
                # row angle plus half a turn, normalized modulo 2*pi.
                target = math.pi - row_angle
                if target > math.pi:
                    target -= 2.0 * math.pi
                deviations.append(abs((angle - target + math.pi) % (2.0 * math.pi) - math.pi))
            check(
                "start gates face the right way across the start row",
                max(deviations) < math.radians(2.0),
                f"max {math.degrees(max(deviations)):.1f} deg off the row",
            )
        parsed = [CHECKPOINT_RE.match(l) for l in check_lines]
        check("checkpoints parse", all(parsed), f"{len(check_lines)} lines")
        check("checkpoint count >= 3", len(check_lines) >= 3, str(len(check_lines)))
        if all(parsed):
            widths = [float(m.group(1)) for m in parsed]
            normals = [(float(m.group(5)), float(m.group(6)), float(m.group(7))) for m in parsed]
            check("checkpoint widths positive", all(w > 0 for w in widths), f"{min(widths):.1f}..{max(widths):.1f} ft")
            check(
                "checkpoint normals non-zero",
                all(abs(n[0]) + abs(n[2]) > 0.5 for n in normals),
                "travel direction vectors",
            )
        check(
            "lap gate lists reference checkpoints",
            len(lap_first) == len(check_lines) and len(lap_normal) == len(check_lines)
            and all(0 <= int(v) < len(check_lines) for v in lap_first + lap_normal),
            f"{len(lap_first)} / {len(lap_normal)}",
        )
    except Exception as exc:  # noqa: BLE001
        check("timing_gates parses", False, repr(exc))

    # Ground tiles and lighting.
    try:
        dimension = int((folder / "terrain.hf").read_text().split()[0])
        tilemap = (folder / "tilemap").read_bytes()
        expected_tiles = (2 ** dimension) ** 2
        check(
            "tilemap size matches terrain dimension",
            len(tilemap) == expected_tiles,
            f"{len(tilemap)} vs {expected_tiles} bytes",
        )
    except Exception as exc:  # noqa: BLE001
        check("tilemap parses", False, repr(exc))

    try:
        tileinfo = (folder / "tileinfo").read_text()
        check("tileinfo has friction", re.search(r"^friction\s+", tileinfo, re.M) is not None, "")
        check("tileinfo has roll_resist", re.search(r"^roll_resist\s+", tileinfo, re.M) is not None, "")
        check("tileinfo closes with addtile", re.search(r"^addtile\s*$", tileinfo, re.M) is not None, "")
        texture_match = re.search(r"^texture\s+(\S+)\s*$", tileinfo, re.M)
        check("tileinfo has texture", texture_match is not None, "")
        if texture_match:
            texture = texture_match.group(1)
            if texture.startswith("@"):
                relative = texture[1:]
                if relative.startswith(folder.name + "/"):
                    check(
                        f"tile texture exists ({relative})",
                        (folder.parent / relative).is_file(),
                        str(folder.parent / relative),
                    )
    except Exception as exc:  # noqa: BLE001
        check("tileinfo parses", False, repr(exc))

    try:
        lighting = (folder / "lighting").read_text()
        fields = set(re.findall(r"^(\w+)", lighting, re.M))
        for field in ("sun_vector", "sun_color", "ambient"):
            check(f"lighting has {field}", field in fields, "")
    except Exception as exc:  # noqa: BLE001
        check("lighting parses", False, repr(exc))

    # World bounds for props.
    try:
        dimension = int((folder / "terrain.hf").read_text().split()[0])
        resolution = float((folder / "terrain.hf").read_text().split()[1])
        world = (2 ** (dimension + 1)) * resolution
    except Exception:  # noqa: BLE001
        world = 0.0

    for name, pattern in (("statues", STATUE_RE), ("billboards", BILLBOARD_RE)):
        rows = [l for l in (folder / name).read_text().splitlines() if l.strip()]
        matches = [pattern.match(l) for l in rows]
        check(f"{name} lines parse", all(matches), f"{len(rows)} lines")
        if all(matches) and world:
            xs = [float(m.group(1)) for m in matches]
            zs = [float(m.group(3)) for m in matches]
            check(
                f"{name} inside terrain",
                min(xs) >= 0 and max(xs) <= world and min(zs) >= 0 and max(zs) <= world,
                f"x {min(xs):.0f}..{max(xs):.0f}, z {min(zs):.0f}..{max(zs):.0f}",
            )

    # Decals reference real files in this folder.
    decal_rows = [l for l in (folder / "decals").read_text().splitlines() if l.strip()]
    parsed_decals = [DECAL_RE.match(l) for l in decal_rows]
    check("decals parse", bool(parsed_decals) and all(parsed_decals), f"{len(decal_rows)} lines")
    if parsed_decals and all(parsed_decals):
        for match in parsed_decals:
            texture = match.group(6)
            if texture.startswith("@"):
                relative = texture[1:]
                if relative.startswith(folder.name + "/"):
                    check(
                        f"decal asset exists ({relative})",
                        (folder.parent / relative).is_file(),
                        str(folder.parent / relative),
                    )

    return checks


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder")
    args = parser.parse_args(argv)

    checks = validate_folder(args.folder)
    failed = [c for c in checks if not c[1]]
    for name, ok, detail in checks:
        mark = "PASS" if ok else "FAIL"
        print(f"[{mark}] {name}" + (f"  ({detail})" if detail and not ok else ""))
    print(f"\n{len(checks) - len(failed)}/{len(checks)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
