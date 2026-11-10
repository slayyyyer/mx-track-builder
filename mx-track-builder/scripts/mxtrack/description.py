"""Load and validate a track description (YAML or JSON), applying defaults."""

from __future__ import annotations

import json
import re
from copy import deepcopy
from pathlib import Path

try:
    import yaml
except ImportError as exc:  # pragma: no cover
    raise SystemExit(
        "PyYAML is required: python -m pip install -r requirements.txt"
    ) from exc

DEFAULTS: dict = {
    "name": None,
    "title": None,
    "desc": None,
    "seed": 1,
    "terrain": {
        "dimension": 9,
        "resolution": 2.0,
        "base_height": 55.0,
        "relief": 16.0,
        "roughness": 0.35,
        "margin": 1.0,
        "hills": [],
        "smooth_iterations": 0,
        "shoulder_smooth": 0.0,
    },
    "track": {
        "control_points": [],
        "width": 26.0,
        "start_width": None,
        "start_taper": 160.0,
        "start_flat": 90.0,
        "smooth": 45.0,
        "elevation_smooth": 80.0,
        "crown": 0.0,
        "edge_falloff": 18.0,
        "elevation": [],
    },
    "obstacles": [],
    "theme": {
        "map": {
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
        },
        "ground": {
            "size": 2048,
            "base_color": "#8d9a6a",
            "dirt_color": "#8a5a35",
            "edge_falloff": 12.0,
            "noise": 0.45,
            "noise_scale": 120.0,
            "friction": [1.0, 6.0],
            "roll_resist": [5.0, 15.0, 10.0],
        },
    },
    "statues": [],
    "billboards": [],
    "gates": {
        "start_at": 0,
        "start_count": 20,
        "spacing": 4.0,
        "checkpoint_count": 7,
        "checkpoint_offset": 0.0,
        "width_margin": 8.0,
        "y_offset": 0.0,
        "checkpoint_width": None,
    },
}

KNOWN_KEYS = {
    "name", "title", "desc", "seed", "terrain", "track", "obstacles",
    "theme", "statues", "billboards", "gates",
}
KNOWN_NESTED = {
    "terrain": set(DEFAULTS["terrain"]),
    "track": set(DEFAULTS["track"]),
    "gates": set(DEFAULTS["gates"]),
}


def _merge(base, override):
    if isinstance(base, dict) and isinstance(override, dict):
        result = deepcopy(base)
        for key, value in override.items():
            result[key] = _merge(base.get(key), value) if key in base else value
        return result
    return deepcopy(override)


def folder_name(name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "_", str(name).strip()).strip("_")
    if not cleaned:
        raise ValueError("track name must contain letters or digits")
    return cleaned


def load_description(path: str | Path) -> tuple[dict, list[str]]:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(path)
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        raw = json.loads(text)
    else:
        raw = yaml.safe_load(text)
    if not isinstance(raw, dict):
        raise ValueError("track description must be a mapping at the top level")

    warnings: list[str] = []
    for key in raw:
        if key not in KNOWN_KEYS:
            warnings.append(f"unknown top-level key {key!r}")
    for section, allowed in KNOWN_NESTED.items():
        if isinstance(raw.get(section), dict):
            for key in raw[section]:
                if key not in allowed:
                    warnings.append(f"unknown {section} key {key!r}")

    if not raw.get("name"):
        raise ValueError("description needs a 'name' (used as the track folder)")

    if "points" in (raw.get("track") or {}) and "control_points" not in raw["track"]:
        raw["track"]["control_points"] = raw["track"].pop("points")
        warnings.append("track.points is deprecated; use track.control_points")

    desc = _merge(DEFAULTS, raw)
    desc["name"] = folder_name(desc["name"])
    desc["title"] = desc["title"] or desc["name"].replace("_", " ").upper()
    desc["desc"] = desc["desc"] or desc["title"]

    points = desc["track"].get("control_points") or []
    if len(points) < 3:
        raise ValueError("track.control_points needs at least 3 [x, z] points")
    for i, point in enumerate(points):
        if not isinstance(point, (list, tuple)) or len(point) != 2:
            raise ValueError(f"control point {i} must be [x, z]")

    dimension = int(desc["terrain"]["dimension"])
    if not (6 <= dimension <= 12):
        raise ValueError("terrain.dimension should be 6..12 (9 = 1025 px, 10 = 2049 px)")
    resolution = float(desc["terrain"]["resolution"])
    if resolution <= 0:
        raise ValueError("terrain.resolution must be > 0")
    # MX Sim: dimension 9 is a 1025 px heightfield (2^(9+1)+1 points).
    world = (2 ** (dimension + 1)) * resolution

    clearance = float(desc["track"]["width"]) * 0.5 + float(desc["track"].get("edge_falloff", 18.0))
    for i, (x, z) in enumerate(points):
        if not (0 <= float(x) <= world and 0 <= float(z) <= world):
            warnings.append(
                f"control point {i} ({x}, {z}) is outside the {world:g} ft terrain; "
                "it will be clipped by the heightfield edge"
            )
        elif not (clearance <= float(x) <= world - clearance and clearance <= float(z) <= world - clearance):
            warnings.append(
                f"control point {i} ({x}, {z}) is close to the terrain edge; "
                "the ribbon may be cut off"
            )

    for i, obstacle in enumerate(desc["obstacles"]):
        if not isinstance(obstacle, dict) or "type" not in obstacle:
            raise ValueError(f"obstacle {i} needs a type")
        if "at" not in obstacle:
            raise ValueError(f"obstacle {i} needs 'at' (feet or a percentage like '35%')")

    return desc, warnings


def world_size(desc: dict) -> float:
    dimension = int(desc["terrain"]["dimension"])
    return (2 ** (dimension + 1)) * float(desc["terrain"]["resolution"])
