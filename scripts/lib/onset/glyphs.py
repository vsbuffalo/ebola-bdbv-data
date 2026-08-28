"""Read the figure's printed numbers by template match against a committed atlas.

Two numbers in the raster are load-bearing and nothing in the PDF text layer
carries them: the y-axis tick labels (which decide the pixels-per-case
exchange rate and the gridline step, requirement G7) and the total the title
prints -- `(n = 3 767)` -- which is the checksum every digitised vintage
must reconcile against (G2).

Recognition is nearest-template over `scripts/lib/onset/glyphs/`, a
committed atlas of glyph exemplars cut from the archive's own renders (see
the README there for provenance). Committed data beats a system OCR binary
here: the match is deterministic, the exemplars are auditable one PNG at a
time, and a version bump of nothing can change a reading. A glyph that
matches no exemplar above threshold is unknown -- callers treat unknowns as
refusals, never as guesses.

Normalisation must mirror the atlas build exactly: crop to the component's
box, invert so ink is bright, resize to 14x18 with Lanczos.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image

ATLAS_DIR = Path(__file__).resolve().parent / "glyphs"
TILE = (14, 18)                 # (width, height) every exemplar is stored at
DARK_LUM = 150                  # ink threshold for segmentation
MIN_H, MAX_H = 5, 30            # component size bounds, pixels
MIN_W, MAX_W = 2, 26
MIN_AREA = 8
MATCH_MIN = 0.72                # below this a glyph is unknown

DIGITS = set("0123456789")


@lru_cache(maxsize=1)
def load_atlas() -> dict[str, list[np.ndarray]]:
    atlas: dict[str, list[np.ndarray]] = {}
    for d in sorted(ATLAS_DIR.iterdir()):
        if not d.is_dir():
            continue
        char = {"lparen": "(", "rparen": ")"}.get(d.name, d.name)
        tiles = [np.asarray(Image.open(p).convert("L")).astype(float)
                 for p in sorted(d.glob("*.png"))]
        if tiles:
            atlas[char] = tiles
    if not atlas:
        raise RuntimeError(f"glyph atlas is empty at {ATLAS_DIR}")
    return atlas


def _normalise(gray: np.ndarray, y0: int, x0: int, y1: int, x1: int) \
        -> np.ndarray:
    tile = 255.0 - gray[y0:y1 + 1, x0:x1 + 1]
    img = Image.fromarray(tile.astype(np.uint8))
    return np.asarray(img.resize(TILE, Image.LANCZOS)).astype(float)


def _corr(a: np.ndarray, b: np.ndarray) -> float:
    a = a - a.mean()
    b = b - b.mean()
    d = np.linalg.norm(a) * np.linalg.norm(b)
    return float((a * b).sum() / d) if d > 0 else 0.0


def match(vec: np.ndarray) -> tuple[str, float]:
    """Best (char, score) over the whole atlas."""
    best = ("?", -1.0)
    for char, tiles in load_atlas().items():
        for t in tiles:
            s = _corr(vec, t)
            if s > best[1]:
                best = (char, s)
    return best


def components(mask: np.ndarray) -> list[tuple[int, int, int, int, int]]:
    """8-connected components of an ink mask: (y0, x0, y1, x1, area)."""
    h, w = mask.shape
    seen = np.zeros_like(mask, dtype=bool)
    out = []
    for sy in range(h):
        for sx in range(w):
            if not mask[sy, sx] or seen[sy, sx]:
                continue
            stack = [(sy, sx)]
            seen[sy, sx] = True
            area = 0
            y0 = y1 = sy
            x0 = x1 = sx
            while stack:
                y, x = stack.pop()
                area += 1
                y0, y1 = min(y0, y), max(y1, y)
                x0, x1 = min(x0, x), max(x1, x)
                for ny in (y - 1, y, y + 1):
                    for nx in (x - 1, x, x + 1):
                        if 0 <= ny < h and 0 <= nx < w \
                                and mask[ny, nx] and not seen[ny, nx]:
                            seen[ny, nx] = True
                            stack.append((ny, nx))
            out.append((y0, x0, y1, x1, area))
    return out


def read_region(gray: np.ndarray) -> list[dict]:
    """Segment and classify every glyph-sized component in a grayscale
    region. Returns dicts with box, centre, char and score; char is '?'
    below the match threshold."""
    mask = gray < DARK_LUM
    out = []
    for y0, x0, y1, x1, area in components(mask):
        h_, w_ = y1 - y0 + 1, x1 - x0 + 1
        if not (MIN_H <= h_ <= MAX_H and MIN_W <= w_ <= MAX_W
                and area >= MIN_AREA):
            continue
        best, score = match(_normalise(gray, y0, x0, y1, x1))
        out.append({"y0": y0, "x0": x0, "y1": y1, "x1": x1,
                    "yc": (y0 + y1) / 2.0, "xc": (x0 + x1) / 2.0,
                    "char": best if score >= MATCH_MIN else "?",
                    "best": best, "score": score})
    return out


def group_rows(glyphs: list[dict], row_gap: int = 4) -> list[list[dict]]:
    """Cluster glyphs into text rows by vertical overlap, left-to-right."""
    rows: list[list[dict]] = []
    for g in sorted(glyphs, key=lambda g: g["y0"]):
        placed = False
        for row in rows:
            if any(g["y0"] <= o["y1"] + row_gap and o["y0"] <= g["y1"] + row_gap
                   for o in row):
                row.append(g)
                placed = True
                break
        if not placed:
            rows.append([g])
    for row in rows:
        row.sort(key=lambda g: g["x0"])
    return rows
