#!/usr/bin/env python3
"""Build a complete MX Simulator track folder from a YAML/JSON description.

Usage:
    python build_track.py my-track.yaml [--out DIR] [--no-preview] [--seed N]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mxtrack.description import load_description, world_size  # noqa: E402
from mxtrack.files import (  # noqa: E402
    decal_line,
    lighting_file,
    terrain_hf,
    tileinfo_file,
    write_png16_gray,
    write_text,
    write_tilemap,
)
from mxtrack.gates import build_gates  # noqa: E402
from mxtrack.ground import (  # noqa: E402
    decals_file,
    render_ground,
    render_tile,
    settings as ground_settings,
)
from mxtrack.mapimage import render_map  # noqa: E402
from mxtrack.obstacles import build_profile, half_widths  # noqa: E402
from mxtrack.preview import render_preview  # noqa: E402
from mxtrack.props import build_billboards, build_statues  # noqa: E402
from mxtrack.spline import ClosedSpline  # noqa: E402
from mxtrack.terrain import (  # noqa: E402
    build_base,
    build_heightmap,
    sample_grid_many,
)


def build(description_path, out_dir=".", preview=True, seed=None) -> dict:
    desc, warnings = load_description(description_path)
    if seed is not None:
        desc["seed"] = int(seed)

    dimension = int(desc["terrain"]["dimension"])
    resolution = float(desc["terrain"]["resolution"])
    n = 2 ** (dimension + 1) + 1
    world = world_size(desc)

    spline = ClosedSpline(desc["track"]["control_points"])
    # Keep the ribbon stations finer than the heightfield: otherwise the
    # surface is a 1 ft polyline sampled into a 0.625 ft grid, which reads as
    # stair steps even after the grid itself is smoothed.
    step = min(2.0, max(0.5, resolution * 0.5))
    samples = spline.resample(step)
    if samples.length < 400:
        warnings.append("track is shorter than 400 ft; that is very small for an MX track")

    width = float(desc["track"]["width"])
    min_radius = 1.0 / max(float(np.max(np.abs(samples.k))), 1e-9)
    if min_radius < width * 0.6:
        warnings.append(
            f"tightest corner radius is {min_radius:.1f} ft; below 0.6 x track "
            f"width ({width * 0.6:.1f} ft), the ribbon can pinch"
        )

    base = build_base(desc, n, resolution)
    base_along = sample_grid_many(base, resolution, samples.x, samples.z)
    profile, bank, ruts, reports = build_profile(
        samples, base_along, desc["track"], desc["obstacles"]
    )

    terrain_data = build_heightmap(
        desc, samples, profile, bank, desc["gates"], base=base, rut=ruts
    )
    terrain_data["half_width"] = half_widths(samples, desc["track"], desc["gates"])

    folder = Path(out_dir) / desc["name"]
    folder.mkdir(parents=True, exist_ok=True)

    write_text(
        folder / "terrain.hf",
        terrain_hf(terrain_data["dimension"], terrain_data["resolution"], terrain_data["low"], terrain_data["high"]),
    )
    write_png16_gray(folder / "terrain.png", terrain_data["encoded"])
    write_text(folder / "desc", str(desc["desc"]).strip() + "\n")

    map_image = render_map(desc, samples, world, desc["gates"])
    map_image.save(folder / "map.png")

    ground_rng = np.random.default_rng(int(desc["seed"]) + 101)
    ground_image = render_ground(desc, samples, terrain_data, ground_rng)
    (folder / "ground").mkdir(exist_ok=True)
    ground_image.save(folder / "ground" / "ground.png")
    write_text(folder / "decals", decals_file(desc["name"], world))

    tile_image = render_tile(desc)
    tile_image.save(folder / "ground" / "tile.png")
    ground = ground_settings(desc)
    write_text(
        folder / "tileinfo",
        tileinfo_file(desc["name"], ground["friction"], ground["roll_resist"]),
    )
    write_tilemap(folder / "tilemap", dimension)
    write_text(folder / "lighting", lighting_file())

    props_rng = np.random.default_rng(int(desc["seed"]) + 202)
    statues, statue_warnings = build_statues(desc, samples, terrain_data, props_rng)
    billboards, billboard_warnings = build_billboards(desc, samples, terrain_data, props_rng)
    write_text(folder / "statues", statues)
    write_text(folder / "billboards", billboards)
    warnings.extend(statue_warnings)
    warnings.extend(billboard_warnings)

    gates_text, gate_warnings = build_gates(desc, samples, terrain_data)
    write_text(folder / "timing_gates", gates_text)
    warnings.extend(gate_warnings)

    preview_path = None
    if preview:
        preview_image = render_preview(desc, samples, terrain_data, desc["gates"], reports)
        preview_path = Path(out_dir) / f"{desc['name']}_preview.png"
        preview_image.save(preview_path)

    for report in reports:
        warnings.extend(report.warnings)
    warnings = list(dict.fromkeys(warnings))

    return {
        "folder": folder,
        "preview": preview_path,
        "desc": desc,
        "samples": samples,
        "terrain": terrain_data,
        "profile": profile,
        "bank": bank,
        "rut": ruts,
        "reports": reports,
        "warnings": warnings,
        "statues": statues.count("\n"),
        "billboards": billboards.count("\n"),
        "checkpoints": int(desc["gates"]["checkpoint_count"]),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("description", help="track description (.yaml, .yml or .json)")
    parser.add_argument("--out", default=".", help="parent directory for the track folder")
    parser.add_argument("--no-preview", action="store_true", help="skip the hillshade preview")
    parser.add_argument("--seed", type=int, default=None, help="override the description seed")
    args = parser.parse_args(argv)

    result = build(args.description, args.out, preview=not args.no_preview, seed=args.seed)
    desc = result["desc"]
    terrain = result["terrain"]

    print(f"\nBuilt {desc['name']}  ->  {result['folder'].resolve()}")
    print(
        f"  terrain   {terrain['world']:g} x {terrain['world']:g} ft "
        f"({terrain['n']} px @ {terrain['resolution']:g} ft)  "
        f"heights {terrain['low']:.1f}..{terrain['high']:.1f} ft"
    )
    print(f"  lap       {result['samples'].length:,.0f} ft, width {desc['track']['width']:g} ft")
    print(
        "  files     terrain.hf, terrain.png, map.png, desc, decals, "
        "ground/ground.png, ground/tile.png, tileinfo, tilemap, lighting"
    )
    print(
        f"  props     {result['statues']} statues, {result['billboards']} billboards, "
        f"{desc['gates']['start_count']} start gates, {result['checkpoints']} checkpoints"
    )
    if result["reports"]:
        print("  obstacles")
        for report in result["reports"]:
            if report.kind == "warning":
                print(f"    ! {report.detail}")
            else:
                print(f"    - {report.kind:<9} at {report.at:7.0f} ft  {report.detail}")
    if result["preview"]:
        print(f"  preview   {result['preview'].resolve()}")
    if result["warnings"]:
        print("\nWarnings")
        for warning in result["warnings"]:
            print(f"  ! {warning}")
    print(
        "\nDrop the folder in %LOCALAPPDATA%\\MX Simulator, then load it with"
        f" mx.exe --track {desc['name']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
