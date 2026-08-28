"""Decide what a chart-sized raster is, from its content, never its caption.

The captions lie. From sitrep 084 the brief-format reports print the caption
"Evolution de cas par date de debut des symptomes au cours de 21 derniers
jours" above whatever chart the day's report carries: a daily bar chart by
notification date (084, 085), a weekly notification-week curve (086), and
only from 087 the actual onset curve. A reader keyed on the caption ingests
notification-dated counts as onset-dated counts and never notices. So
identification here looks only at the pixels.

The chart families separate cleanly on fill colour and furniture, with wide
margins, measured on the archive (fractions of all pixels):

                          light blue   incomplete-band   dark blue   pale
                          ~(192,227,238)  pink            fill        yellow
  onset curve (3 imgs)    0.074-0.085   0.017-0.024      0.0000      0.0000
  notification daily 084  0.011         0.003            0.188       0
  notification weekly 086 0.013         0.001            0.119       0
  health-zone maps        0.38-0.40     0.003            0.0001      0.17-0.19

The onset curve is the only family with the pale Vivant fill *and* the pink
"donnees potentiellement incompletes" band; the notification charts are the
only ones with a dark blue fill; the maps are the only things with pale
yellow zones. Thresholds sit mid-margin, an order of magnitude from both
sides. If a future render drifts past them the result is a refusal -- loud,
in the inventory, with the measured fractions as evidence -- never a silent
misclassification.

Photographs are the trap the colour fractions alone do not catch: the annex
pages carry field photos in which skin tones read as band pink and sky as
Vivant blue (sitreps 063 and 074 each carry one that passes both). What a
photograph never has is a chart's white background -- measured white
fractions are 0.71-0.76 on every onset render against 0.07-0.10 on the
photos -- so a white floor is a required condition for any chart kind.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from PIL import Image

# Reference colours the families are measured against. These identify chart
# families only; the reader never uses them -- it calibrates its palette from
# each image's own legend swatches.
LIGHT_BLUE = (192.0, 227.0, 238.0)      # the onset curve's Vivant fill
BAND_PINK = (250.0, 214.0, 216.0)       # the incomplete-band overlay

YELLOW_MAP_MIN = 0.05                   # maps 0.17+; charts below 0.002
LIGHT_BLUE_MIN = 0.04                   # onset 0.074+; others below 0.013
BAND_PINK_MIN = 0.008                   # onset 0.017+; others below 0.0031
DARK_BLUE_MIN = 0.05                    # notification 0.119+; others ~0.0001
WHITE_CHART_MIN = 0.40                  # charts 0.71+; photographs below 0.11


@dataclass(frozen=True)
class Identification:
    kind: str      # onset_daily | notification | map | other
    evidence: str  # the measured fractions this decision rests on


def _near_frac(im: np.ndarray, colour: tuple, radius: float) -> float:
    return float((np.linalg.norm(im - np.array(colour), axis=2) < radius).mean())


def measure(im: np.ndarray) -> dict[str, float]:
    """The classification features, as fractions of all pixels."""
    r, g, b = im[:, :, 0], im[:, :, 1], im[:, :, 2]
    return {
        "light_blue": _near_frac(im, LIGHT_BLUE, 40.0),
        "band_pink": _near_frac(im, BAND_PINK, 18.0),
        "dark_blue": float(((b > 110) & (b < 220) & (b - r > 40)
                            & (b - g > 25) & (r < 120)).mean()),
        "yellow": float(((r > 225) & (g > 215) & (b < 200)
                         & (r - b > 40)).mean()),
        "white": float((im.min(axis=2) > 225).mean()),
    }


def identify(png_path) -> Identification:
    with Image.open(png_path) as img:
        im = np.asarray(img.convert("RGB")).astype(float)
    f = measure(im)
    ev = ("light_blue={light_blue:.4f} band_pink={band_pink:.4f} "
          "dark_blue={dark_blue:.4f} yellow={yellow:.4f} "
          "white={white:.4f}").format(**f)
    if f["white"] < WHITE_CHART_MIN:
        # Photographs, whatever colours they happen to contain.
        return Identification("other", ev)
    if f["yellow"] > YELLOW_MAP_MIN:
        return Identification("map", ev)
    if f["dark_blue"] > DARK_BLUE_MIN:
        return Identification("notification", ev)
    if f["light_blue"] > LIGHT_BLUE_MIN and f["band_pink"] > BAND_PINK_MIN:
        return Identification("onset_daily", ev)
    return Identification("other", ev)
