"""Low-level file writers for MX Simulator track files.

MX Simulator reads these as plain text with unix line endings, so every text
writer here normalises to LF.  terrain.png is written by hand instead of via
Pillow so the PNG is guaranteed to be 16-bit greyscale (the game's heightfield
format) on every Pillow version.
"""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

import numpy as np


def write_text(path: Path, text: str) -> None:
    """Write a game text file with unix line endings."""
    path.parent.mkdir(parents=True, exist_ok=True)
    normalised = text.replace("\r\n", "\n").replace("\r", "\n")
    path.write_bytes(normalised.encode("utf-8"))


def write_png16_gray(path: Path, array: np.ndarray) -> None:
    """Write an 8/16-bit greyscale PNG without external image libraries.

    ``array`` is a 2-D array.  Values are clipped to 0..65535.
    """
    arr = np.asarray(array)
    if arr.ndim != 2:
        raise ValueError("png16_gray expects a 2-D array")
    arr = np.clip(arr, 0, 65535).astype(np.uint16)
    height, width = arr.shape

    # PNG stores 16-bit samples big-endian and each scanline starts with a
    # filter byte (0 = None, which keeps the encoder simple and deterministic).
    raw = b"".join(
        b"\x00" + arr[row].astype(">u2").tobytes() for row in range(height)
    )

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    ihdr = struct.pack(">IIBBBBB", width, height, 16, 0, 0, 0, 0)
    png = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(raw, 6))
        + chunk(b"IEND", b"")
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(png)


def decode_png16_gray(path: Path) -> np.ndarray:
    """Read back a 16-bit greyscale PNG written by :func:`write_png16_gray`.

    Used by the validator so it does not need Pillow's mode handling.
    """
    data = path.read_bytes()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError(f"{path} is not a PNG")
    pos = 8
    width = height = bit_depth = colour = None
    idat = b""
    while pos < len(data):
        length = struct.unpack(">I", data[pos : pos + 4])[0]
        tag = data[pos + 4 : pos + 8]
        payload = data[pos + 8 : pos + 8 + length]
        pos += 12 + length
        if tag == b"IHDR":
            width, height, bit_depth, colour = struct.unpack(">IIBB", payload[:10])
        elif tag == b"IDAT":
            idat += payload
        elif tag == b"IEND":
            break
    if bit_depth != 16 or colour != 0:
        raise ValueError(f"{path} is not a 16-bit greyscale PNG")
    raw = zlib.decompress(idat)
    stride = width * 2
    out = np.empty((height, width), dtype=np.uint16)
    for row in range(height):
        start = row * (stride + 1)
        filt = raw[start]
        if filt != 0:
            raise ValueError(f"{path}: unsupported PNG filter {filt}")
        out[row] = np.frombuffer(raw[start + 1 : start + 1 + stride], dtype=">u2")
    return out


def terrain_hf(dimension: int, resolution: float, low: float, high: float) -> str:
    """terrain.hf: '[dimension] [resolution] [lowest point] [highest point]'."""
    return f"{int(dimension)} {resolution:.6f} {low:.1f} {high:.1f}\n"


def lighting_file(
    sun_vector=(1.0, 1.0, 1.0),
    sun_color=(1.0, 1.0, 0.50),
    ambient=(0.25, 0.25, 0.50),
) -> str:
    def vec(values):
        return "[ " + " ".join(f"{float(v):.2f}" for v in values) + " ]"

    return (
        f"sun_vector {vec(sun_vector)}\n"
        f"sun_color {vec(sun_color)}\n"
        f"ambient {vec(ambient)}\n"
    )


def tileinfo_file(
    track_name: str,
    friction=(1.0, 6.0),
    roll_resist=(5.0, 15.0, 10.0),
    texture: str = "ground/tile.png",
) -> str:
    """One modern ground tile for tilemap index 0."""
    if len(friction) != 2:
        raise ValueError("theme.ground.friction must be [coefficient, slip_speed]")
    if len(roll_resist) != 3:
        raise ValueError("theme.ground.roll_resist must be [low, high, value]")
    coefficient, slip = (float(v) for v in friction)
    low, high, value = (float(v) for v in roll_resist)
    return (
        f"friction {coefficient:.2f} {slip:.2f}\n"
        f"roll_resist {low:.2f} {high:.2f} {value:.2f}\n"
        f"texture @{track_name}/{texture}\n"
        "addtile\n"
    )


def write_tilemap(path: Path, dimension: int, tile: int = 0) -> None:
    """Write a raw tilemap: one byte per terrain cell, all set to ``tile``."""
    tile = int(tile)
    if not 0 <= tile <= 255:
        raise ValueError("tilemap tile index must be 0..255")
    size = 2 ** int(dimension)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(bytes([tile]) * (size * size))


def decal_line(x: float, z: float, rotation: float, size: float, aspect: float, path: str) -> str:
    return f"[{x:.6f} {z:.6f}] {rotation:.6f} {size:.6f} {aspect:.6f} {path}\n"


def statue_line(x: float, y: float, z: float, rotation: float, model: str, texture: str, shape: str | None) -> str:
    shape = shape or "null"
    return f"[{x:.6f} {y:.6f} {z:.6f}] {rotation:.6f} {model} {texture} {shape}\n"


def billboard_line(x: float, y: float, z: float, height: float, aspect: float, texture: str) -> str:
    return f"[{x:.6f} {y:.6f} {z:.6f}] {height:.6f} {aspect:.6f} {texture}\n"


def start_gate_line(x: float, y: float, z: float, rotation: float) -> str:
    return f"[{x:.6f} {y:.6f} {z:.6f}] {rotation:.6f}\n"


def checkpoint_line(width: float, x: float, y: float, z: float, nx: float, nz: float) -> str:
    return (
        f"{width:.6f} [{x:.6f} {y:.6f} {z:.6f}] "
        f"[{nx:.6f} 0.000000 {nz:.6f}]\n"
    )
