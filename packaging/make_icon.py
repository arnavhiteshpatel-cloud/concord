"""Draw the Windows program icon (``concord.ico``) with the standard library only.

    python packaging/make_icon.py OUT.ico

packaging/concord.spec calls ``write_ico`` while building on Windows, so no binary icon file is
kept in the repository. The design: a white open ring (a "C") on a dark slate rounded square.
Every size is an uncompressed 32-bit BGRA bitmap with an alpha channel, the ICO form that both
Windows Explorer and Tk (the status window's title bar) read.
"""

from __future__ import annotations

import math
import struct
import sys
from pathlib import Path

SIZES = (16, 24, 32, 48, 64, 256)
BACKGROUND = (0x2B, 0x3A, 0x42)  # RGB
RING = (0xFF, 0xFF, 0xFF)


def _coverage(size: int, x: float, y: float) -> tuple[float, float]:
    """(inside the rounded square, on the ring) for one sample point."""
    c = size / 2
    corner = size * 0.2
    half = c - size * 0.02
    dx = max(abs(x - c) - (half - corner), 0.0)
    dy = max(abs(y - c) - (half - corner), 0.0)
    square = 1.0 if dx * dx + dy * dy <= corner * corner and abs(x - c) <= half else 0.0
    if abs(y - c) > half:
        square = 0.0
    d = math.hypot(x - c, y - c)
    ring = size * 0.22 <= d <= size * 0.36
    gap = x > c and abs(y - c) < size * 0.11  # the opening of the "C"
    return square, 1.0 if ring and not gap else 0.0


def pixels(size: int) -> list[tuple[int, int, int, int]]:
    """Row-major RGBA pixels, top row first (4x4 supersampling for smooth edges)."""
    out = []
    n = 4
    for py in range(size):
        for px in range(size):
            sq = ring = 0.0
            for sy in range(n):
                for sx in range(n):
                    a, b = _coverage(size, px + (sx + 0.5) / n, py + (sy + 0.5) / n)
                    sq += a
                    ring += a * b
            sq /= n * n
            ring /= n * n
            if sq == 0:
                out.append((0, 0, 0, 0))
                continue
            t = ring / sq
            rgb = tuple(round(bg + (fg - bg) * t) for bg, fg in zip(BACKGROUND, RING, strict=True))
            out.append((rgb[0], rgb[1], rgb[2], round(255 * sq)))
    return out


def bitmap(size: int) -> bytes:
    """One ICO image: BITMAPINFOHEADER, BGRA rows bottom-up, then an all-zero AND mask."""
    px = pixels(size)
    rows = []
    for y in range(size - 1, -1, -1):
        row = px[y * size : (y + 1) * size]
        rows.append(b"".join(struct.pack("BBBB", b, g, r, a) for r, g, b, a in row))
    mask_row = ((size + 31) // 32) * 4
    image = b"".join(rows)
    header = struct.pack(
        "<IiiHHIIiiII", 40, size, size * 2, 1, 32, 0, len(image) + mask_row * size, 0, 0, 0, 0
    )
    return header + image + bytes(mask_row * size)


def ico(sizes: tuple[int, ...] = SIZES) -> bytes:
    images = [bitmap(s) for s in sizes]
    out = struct.pack("<HHH", 0, 1, len(images))
    offset = 6 + 16 * len(images)
    for s, img in zip(sizes, images, strict=True):
        out += struct.pack("<BBBBHHII", s % 256, s % 256, 0, 0, 1, 32, len(img), offset)
        offset += len(img)
    return out + b"".join(images)


def write_ico(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(ico())
    return path


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    print(write_ico(Path(sys.argv[1])))
