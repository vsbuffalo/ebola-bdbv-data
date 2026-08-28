"""Locate the chart-sized rasters a sitrep embeds, and pin their identity.

A sitrep page carries logos, photos, maps and charts as separate embedded
image objects. `pdfimages` extracts each object's pixels exactly as the PDF
holds them -- no page rendering, no resampling -- so what this module hands
onward is the same array of numbers every later measurement is made from.

Identity is the SHA-256 of the decoded RGB pixels (dimensions prepended),
not of the compressed stream: two PDFs that embed byte-identical JPEG data
share a hash, and so do two that embed the same pixels under different
lossless encodings. Re-encodes of the same chart (the 087/088 pair) hash
differently here by design -- collapsing those is the value-level
deduplication's job, downstream, once both have been read.

The `pdfimages -list` table and the files `pdfimages -png -p` writes are
matched by the image-number column, which is the NNN in `prefix-PPP-NNN.png`;
verified against poppler's output rather than assumed.
"""

from __future__ import annotations

import hashlib
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

# Below this, an embedded image is a logo, a photo or a decoration. The
# smallest chart seen in the archive is 683x455; the largest non-chart
# clutter is ~320 px wide.
MIN_WIDTH = 380
MIN_HEIGHT = 260


@dataclass(frozen=True)
class EmbeddedImage:
    """One chart-sized raster pulled from a sitrep, before we know what it is."""
    page: int
    num: int                  # pdfimages' image counter, ties list row to file
    width: int
    height: int
    encoding: str             # "jpeg" | "lossless"
    compressed_bytes: int
    png_path: Path            # the decoded pixels, on disk
    decoded_sha256: str


def _parse_size(text: str) -> int:
    """pdfimages prints '25B', '16.9K', '1.2M'."""
    m = re.fullmatch(r"([\d.]+)([BKM])", text)
    if m is None:
        return 0
    return int(float(m.group(1)) * {"B": 1, "K": 1024, "M": 1024 ** 2}[m.group(2)])


def _list_rows(pdf: Path) -> list[dict]:
    out = subprocess.run(["pdfimages", "-list", str(pdf)],
                         capture_output=True, text=True, check=True).stdout
    rows = []
    for line in out.splitlines()[2:]:
        parts = line.split()
        if len(parts) < 16:
            continue
        rows.append({
            "page": int(parts[0]),
            "num": int(parts[1]),
            "type": parts[2],                     # image | smask | stencil
            "width": int(parts[3]),
            "height": int(parts[4]),
            "enc": parts[8],                      # jpeg | image | jbig2 | ...
            "size": _parse_size(parts[14]),
        })
    return rows


def decoded_hash(png_path: Path) -> tuple[str, tuple[int, int]]:
    """SHA-256 over the decoded RGB bytes, dimensions prepended so equal byte
    streams at different shapes cannot collide."""
    with Image.open(png_path) as im:
        rgb = im.convert("RGB")
        h = hashlib.sha256()
        h.update(f"{rgb.width}x{rgb.height}:".encode())
        h.update(rgb.tobytes())
        return h.hexdigest(), (rgb.width, rgb.height)


def extract_chart_candidates(pdf: Path, workdir: Path) -> list[EmbeddedImage]:
    """Every chart-sized embedded raster in the PDF, decoded to PNG in
    `workdir` and hashed. Smasks (transparency channels) are not images."""
    workdir.mkdir(parents=True, exist_ok=True)
    rows = [r for r in _list_rows(pdf)
            if r["type"] == "image"
            and r["width"] >= MIN_WIDTH and r["height"] >= MIN_HEIGHT]
    if not rows:
        return []
    prefix = workdir / pdf.stem
    subprocess.run(["pdfimages", "-png", "-p", str(pdf), str(prefix)],
                   capture_output=True, check=True)
    out = []
    for r in rows:
        p = workdir / f"{pdf.stem}-{r['page']:03d}-{r['num']:03d}.png"
        if not p.exists():
            # A listed image that did not extract is a poppler surprise worth
            # hearing about loudly, not skipping.
            raise RuntimeError(f"{pdf.name}: listed image {r['num']} "
                               f"on page {r['page']} was not extracted")
        sha, (w, h) = decoded_hash(p)
        out.append(EmbeddedImage(
            page=r["page"], num=r["num"], width=w, height=h,
            encoding="jpeg" if r["enc"] == "jpeg" else "lossless",
            compressed_bytes=r["size"], png_path=p, decoded_sha256=sha))
    # The rest of the extracted files are logos and photos; leave them for the
    # caller's workdir policy to clean.
    return out


def tool_version() -> str:
    """pdfimages prints its version to stderr, like the rest of poppler."""
    pv = subprocess.run(["pdfimages", "-v"], capture_output=True, text=True)
    lines = (pv.stderr or pv.stdout).splitlines()
    return lines[0].strip() if lines else "unknown"
