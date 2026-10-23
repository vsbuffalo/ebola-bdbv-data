"""Measure each bar twice, by mechanisms that share no blind spot.

Reader one never asks a pixel to decide anything: for one bar the truth is a
pair of integers (alive, dead), so every admissible pair is rendered --
the baseline colour's fill up its count from the baseline, the other
colour's fill for the next, background above -- and scored against the observed pixels as a robust cost.
The argmax over the enumerated lattice is the exact global best; a smeared
pixel moves one candidate's score by a sliver and can truncate nothing.
Rows adjacent to a hypothesised boundary carry no weight, because JPEG
concentrates its damage exactly there: the seven washed rows that amputated
upstream's 25 July bar sit in the zero-weight band of every candidate.

Reader two reads the same two quantities out of the chart's *strokes*: every
segment is outlined darker than either fill, so the bar top and the
alive/dead boundary exist a second time as thin dark lines, found per column
as luminance minima with no colour classification at all. The two readers
fail in different renders -- compression washes fills but spares strokes,
downsampling blurs strokes but spares fills -- so their agreement is
evidence and their disagreement is a flag, never an average.

Both readers look at the image through the "donnees potentiellement
incompletes" band (`Calibration.see_through_band`): the band is a translucent
overlay, and a bar under it is the same bar in washed colours, outlines
included. Read as-is, the washed fills matched neither legend colour and the
washed outlines were too light to be strokes, so reader one fitted most of a
bar as background (sitrep 106's 24 August bar, 29 cases, read as 2) and
reader two fell silent -- a single-reader bar no gate could question.

Which colour sits at the baseline is not a constant: sitreps 059-062 stack
dead under alive, every later render alive under dead. Both readers take the
order from the calibration, where `detect_stacking` has measured it from the
render's own two-colour bars or refused the image.

Everything here consumes a Calibration and returns integer counts with the
evidence attached: the fit margin (cost gap between the best and runner-up
hypothesis), the outline reader's verdict, and the render's resolution in
cases per pixel.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass

import numpy as np

from .calibrate import Calibration, CalibrationError, Stacking

# Robust-cost ceiling: one aberrant pixel can cost at most this much, so no
# single pixel outvotes a row and no row outvotes a bar.
COST_CLIP = 90.0
# The two readers must agree within this many cases on each component.
AGREE_CASES = 1.0
# A fit whose runner-up sits closer than this (cost units per case of
# segment) is not a confident read.
MIN_MARGIN = 1.0
# Rows under the panel's top border that reader two never takes for a bar top.
TOP_BORDER_ROWS = 2


@dataclass(frozen=True)
class BarMeasure:
    slot: int              # bar index from the left edge of the axis
    alive: int
    dead: int
    margin: float          # cost gap, best to second-best (a, d)
    edge_alive: int | None     # reader two's counts; None where it refused
    edge_dead: int | None
    reader_agreement: bool
    provisional: bool      # inside the "donnees potentiellement incompletes" band
    resolution_cases: float


def _class_costs(strip: np.ndarray, colour: tuple | None) -> np.ndarray:
    """Per-row mean clipped distance to a palette colour (rows x 1).
    Masked (NaN) pixels -- the band's label -- carry no weight; a row with
    nothing else costs every class the same, nothing."""
    if colour is None:
        return np.full(strip.shape[0], COST_CLIP)
    d = np.linalg.norm(strip - np.array(colour), axis=2)
    return _row_mean(np.minimum(d, COST_CLIP))


def _row_mean(d: np.ndarray) -> np.ndarray:
    seen = ~np.isnan(d)
    n = seen.sum(axis=1)
    return np.where(n > 0, np.where(seen, d, 0.0).sum(axis=1)
                    / np.maximum(n, 1), 0.0)


def _background_cost(strip: np.ndarray, band_colour: tuple | None,
                     in_band: bool, seen_through: bool = False) -> np.ndarray:
    """Background is white, gridline grey, or the band overlay -- whichever
    is nearest, per pixel, so a gridline crossing costs nothing. Seen
    through the band, white alone (see fit_bar)."""
    refs = [(255.0, 255.0, 255.0), (178.0, 178.0, 178.0)]
    if in_band and band_colour is not None:
        refs.append(band_colour)
    if seen_through:
        refs = refs[:1]
    d = np.min(np.stack([np.linalg.norm(strip - np.array(c), axis=2)
                         for c in refs]), axis=0)
    return _row_mean(np.minimum(d, COST_CLIP))


def _require_stacking(cal: Calibration) -> Stacking:
    if cal.stacking is None:
        raise ValueError("stacking order not measured; run detect_stacking "
                         "on the calibration before reading bars")
    return cal.stacking


def _fit_lattice(im: np.ndarray, cal: Calibration, slot: int,
                 stacking: Stacking) -> tuple[int, int, float, bool, float]:
    """The enumeration behind reader one, for one stacking order.

    Returns (lower, upper, margin, provisional, objective): the counts of
    the segment at the baseline and of the one above it, the normalised
    margin, and the best hypothesis's raw cost, which detect_stacking
    compares across the two orders."""
    p = cal.panel
    c = cal.px_per_case
    centre = cal.x_phase + slot * cal.day_px
    half = max(1.0, 0.32 * cal.day_px)
    x0, x1 = int(np.ceil(centre - half)), int(np.floor(centre + half))
    x0, x1 = max(x0, p.left + 1), min(x1, p.right - 1)
    if x1 < x0:
        raise ValueError(f"slot {slot} has no interior columns")
    provisional = cal.band_left is not None and centre >= cal.band_left

    # Rows indexed upward from the baseline: i = 0 is the row just above it.
    # `im` is already seen through the band (read_bars); where the band's
    # transmission could not be measured its colour stays a background.
    strip = im[p.top + 1: p.bottom, x0:x1 + 1][::-1]
    pal = cal.palette
    sa = _class_costs(strip, pal.alive)
    sd = _class_costs(strip, pal.dead)
    s_lo, s_up = (sa, sd) if stacking is Stacking.ALIVE_BOTTOM else (sd, sa)
    # A slot is read as seen through the band when any of its columns is
    # band, even with its centre just outside (149's 5 October bar). There
    # the background is white alone: inversion pushes a bar's antialiased
    # outline column toward gridline grey, and with grey as a background
    # the fill and background hypotheses tie (143's 30 September bar, 23
    # cases, read as 2). Under the band the dotted gridlines are faint.
    through = (pal.transmission is not None and cal.band_left is not None
               and x1 >= cal.band_left)
    sb = _background_cost(strip, pal.band,
                          provisional and pal.transmission is None, through)
    R = len(sa)
    PL = np.concatenate([[0.0], np.cumsum(s_lo)])
    PU = np.concatenate([[0.0], np.cumsum(s_up)])
    PB = np.concatenate([[0.0], np.cumsum(sb)])

    def rng(P: np.ndarray, lo: np.ndarray, hi: np.ndarray) -> np.ndarray:
        """Sum of a cost series over rows [lo, hi) with a one-row margin
        shaved off each end -- the boundary's zero-weight band."""
        lo2 = np.minimum(lo + 1, hi)
        hi2 = np.maximum(hi - 1, lo2)
        return P[hi2] - P[lo2]

    amax = int(R / c)
    ha = np.round(np.arange(amax + 1) * c).astype(int)      # lower top, px
    a_idx = np.arange(amax + 1)
    # h2[l, u] = pixel row of the upper segment's top
    h2 = np.minimum(ha[:, None] + ha[None, :], R)
    valid = (ha[:, None] + ha[None, :]) <= R + int(c)

    cost_lower = rng(PL, np.zeros_like(ha), ha)             # per l
    cost_upper = rng(PU, np.broadcast_to(ha[:, None], h2.shape), h2)
    cost_bg = rng(PB, h2, np.full_like(h2, R))
    obj = cost_lower[:, None] + cost_upper + cost_bg
    obj = np.where(valid, obj, np.inf)

    flat = np.argsort(obj, axis=None)
    b0 = np.unravel_index(flat[0], obj.shape)
    # The runner-up must be a genuinely different hypothesis, not the same
    # counts rounded to the same pixel rows.
    margin = np.inf
    for k in flat[1:200]:
        cand = np.unravel_index(k, obj.shape)
        if cand != b0:
            margin = float(obj[cand] - obj[b0])
            break
    lo, up = int(a_idx[b0[0]]), int(a_idx[b0[1]])
    seg_px = max(1.0, (lo + up) * c)
    return (lo, up, margin / max(1.0, seg_px / c), provisional,
            float(obj[b0]))


def fit_bar(im: np.ndarray, cal: Calibration, slot: int) \
        -> tuple[int, int, float, bool]:
    """Reader one: exact integer maximum-likelihood by enumeration.

    Returns (alive, dead, margin, provisional). The objective for a
    (lower, upper) pair decomposes into three contiguous row-range sums of
    per-row class costs -- the baseline segment's colour, the other
    colour, background -- so with prefix sums the whole lattice is scored
    as one broadcast; the rows at each hypothesised boundary are excluded
    by index shift, which is the zero-weight band. Which colour is the
    baseline segment is the render's measured stacking order
    (`cal.stacking`), never assumed."""
    stacking = _require_stacking(cal)
    lo, up, margin, prov, _ = _fit_lattice(im, cal, slot, stacking)
    alive, dead = (lo, up) if stacking is Stacking.ALIVE_BOTTOM else (up, lo)
    return alive, dead, margin, prov


# Stacking-order detection. A bar votes only when its better order needs
# both colours (each segment at least this many cases) and beats the other
# order by at least this much cost per case of bar: a one-colour bar fits
# both orders identically and says nothing.
STACK_MIN_SEGMENT = 2
STACK_MIN_GAP = 5.0
# The render's order is accepted only from at least this many voting bars,
# with at most this share dissenting. Anything else refuses.
STACK_MIN_VOTES = 10
STACK_MAX_DISSENT = 0.05


def detect_stacking(im: np.ndarray, cal: Calibration) -> Calibration:
    """Measure which colour a render stacks at the baseline.

    Every slot is fitted under both orders; on a two-colour bar the wrong
    order must either fit one colour's rows against the other's palette
    or give up a segment, and both cost far more than the right order. The
    order is a property of the render (one ggplot call draws every bar), so
    the bars vote once per image and a near-unanimous verdict from enough
    of them is required. A split or thin vote raises CalibrationError: a
    wrong order would silently move every death into "alive" (sitreps
    059-062, read 27 dead of 1,792 before this check existed), and no
    printed total can catch that, because the total survives."""
    seen = cal.see_through_band(im)
    votes = {Stacking.ALIVE_BOTTOM: 0, Stacking.DEAD_BOTTOM: 0}
    for slot in range(cal.n_slots):
        fits = {s: _fit_lattice(seen, cal, slot, s) for s in Stacking}
        best = min(fits, key=lambda s: fits[s][4])
        other = next(s for s in Stacking if s is not best)
        lo, up = fits[best][0], fits[best][1]
        if min(lo, up) < STACK_MIN_SEGMENT:
            continue
        gap = (fits[other][4] - fits[best][4]) / (lo + up)
        if gap >= STACK_MIN_GAP:
            votes[best] += 1
    n = sum(votes.values())
    win = max(votes, key=lambda s: votes[s])
    evidence = (f"{votes[Stacking.ALIVE_BOTTOM]} alive_bottom / "
                f"{votes[Stacking.DEAD_BOTTOM]} dead_bottom")
    if n < STACK_MIN_VOTES or (n - votes[win]) > STACK_MAX_DISSENT * n:
        raise CalibrationError(
            f"stacking order not determined from the render: two-colour "
            f"bars voted {evidence} (need {STACK_MIN_VOTES} votes, at most "
            f"{STACK_MAX_DISSENT:.0%} dissent)")
    return dataclasses.replace(cal, stacking=win, stacking_evidence=evidence)


def edge_bar(im: np.ndarray, cal: Calibration, slot: int) \
        -> tuple[int, int] | None:
    """Reader two: the outline-edge read, or None where the bar was not
    measurable -- columns disagreeing beyond a case is a refusal, because a
    percentile over truncated columns is how upstream turned five bad
    columns and one good one into a confident wrong answer.

    The internal edge it looks for is the one between the render's two
    segments in its measured stacking order: red over blue where alive is
    at the baseline, blue over red where dead is (059-062). Looking only
    for red over blue, it found no boundary on those renders and called
    every bar all alive -- agreeing with reader one's same mistake, which
    is why the order is measured once and handed to both."""
    stacking = _require_stacking(cal)
    dead_low = stacking is Stacking.DEAD_BOTTOM
    p = cal.panel
    c = cal.px_per_case
    centre = cal.x_phase + slot * cal.day_px
    half = max(1.0, 0.32 * cal.day_px)
    x0, x1 = int(np.ceil(centre - half)), int(np.floor(centre + half))
    x0, x1 = max(x0, p.left + 1), min(x1, p.right - 1)
    if x1 < x0:
        return None
    strip = im[p.top + 1: p.bottom, x0:x1 + 1]
    lum = strip.mean(axis=2)
    rgb = strip
    # The stroke is dark *and desaturated*. Darkness alone also selects the
    # red fill (luminance ~95 against the stroke's ~84), which made the
    # "topmost dark run" land mid-cap; the fill's strong red-blue excess is
    # what the stroke never has.
    stroke = (lum < 135) & (rgb[:, :, 0] - rgb[:, :, 2] < 90) \
        & (rgb[:, :, 0] < 170)
    # The panel's top border can fall in the strip's first rows (sitrep
    # 127); no bar reaches it, so those rows are never a bar top.
    stroke[:TOP_BORDER_ROWS] = False
    tops, bounds = [], []
    for col in range(lum.shape[1]):
        dark = np.where(stroke[:, col])[0]
        if len(dark) == 0:
            tops.append(0.0)
            bounds.append(0.0)
            continue
        # Edges are dark runs; the topmost is the bar top. An internal edge
        # with the upper segment's colour above and the lower's below is
        # the alive/dead boundary.
        runs: list[list[int]] = []
        for r in dark:
            if runs and r - runs[-1][-1] <= 1:
                runs[-1].append(int(r))
            else:
                runs.append([int(r)])
        top_run = runs[0]
        tops.append(lum.shape[0] - float(np.mean(top_run)))
        inner = None
        for run in runs[1:]:
            above = int(run[0]) - 2
            below = int(run[-1]) + 2
            if above < 0 or below >= lum.shape[0]:
                continue
            ab = rgb[above, col]
            be = rgb[below, col]
            red, blue = (be, ab) if dead_low else (ab, be)
            if red[0] > red[2] + 20 and blue[2] >= blue[0]:
                inner = lum.shape[0] - float(np.mean(run))
                break
        bounds.append(inner if inner is not None else 0.0)
    tops_a = np.array(tops)
    bounds_a = np.array(bounds)
    if tops_a.max() < 2:                                   # empty slot
        return 0, 0
    spread = np.percentile(tops_a, 84) - np.percentile(tops_a, 16)
    if spread > max(2.0, AGREE_CASES * c):
        return None
    total_px = float(np.median(tops_a))
    inner_px = float(np.median(bounds_a[bounds_a > 0])) \
        if (bounds_a > 0).sum() >= max(1, len(bounds_a) // 3) else 0.0
    total = int(round(total_px / c))
    # No internal edge: a one-colour bar, read as the baseline colour.
    lower = int(round(inner_px / c)) if inner_px > 0 else total
    lower = min(lower, total)
    if dead_low:
        return total - lower, lower
    return lower, total - lower


def _confident_heights(im: np.ndarray, cal: Calibration) -> np.ndarray:
    """Bar-top heights in pixels from the outline reader, for bars whose
    columns agree tightly -- the measurement set the lattice check runs on."""
    p = cal.panel
    heights = []
    for slot in range(cal.n_slots):
        centre = cal.x_phase + slot * cal.day_px
        half = max(1.0, 0.32 * cal.day_px)
        x0 = max(int(np.ceil(centre - half)), p.left + 1)
        x1 = min(int(np.floor(centre + half)), p.right - 1)
        if x1 < x0:
            continue
        strip = im[p.top + 1: p.bottom, x0:x1 + 1]
        lum = strip.mean(axis=2)
        stroke = (lum < 135) & (strip[:, :, 0] - strip[:, :, 2] < 90) \
            & (strip[:, :, 0] < 170)
        tops = []
        for col in range(lum.shape[1]):
            dk = np.where(stroke[:, col])[0]
            if len(dk):
                tops.append(lum.shape[0] - float(dk[0]))
        # Three agreeing columns where the slot has them; at ~3 px a day a
        # slot is two columns wide, and demanding three left sitreps 141,
        # 143, 147, 149 and 159 with too few tops to refine the scale (149
        # read 1.7% short of its printed n, a case low on most bars).
        if len(tops) >= min(3, lum.shape[1]):
            t = np.array(tops)
            if np.percentile(t, 84) - np.percentile(t, 16) <= 2.0 \
                    and np.median(t) > 3:
                heights.append(float(np.median(t)))
    return np.array(heights)


def refine_scale(im: np.ndarray, cal: Calibration) -> Calibration:
    """Snap the pixels-per-case rate to the integer lattice.

    The label regression fixes the scale to about a percent; over a
    hundred-case bar that is a whole case. But every true bar top sits at
    an integer multiple of the scale, so the residual-to-lattice of the
    confidently measured tops, swept over a narrow window around the
    regression value, recovers the scale to a tenth of a percent. A wrong
    scale cannot minimise the lattice residual -- that is the alarm the
    design requires (G7)."""
    heights = _confident_heights(im, cal)
    if len(heights) < 15:
        return cal
    c0 = cal.px_per_case
    best_c, best_r = c0, np.inf
    for c in np.arange(c0 * 0.95, c0 * 1.05, c0 * 0.0005):
        k = heights / c
        r = float(np.mean(np.minimum(np.abs(k - np.round(k)), 0.5)))
        if r < best_r:
            best_c, best_r = c, r
    return dataclasses.replace(cal, px_per_case=float(best_c))


def read_bars(im: np.ndarray, cal: Calibration) -> list[BarMeasure]:
    _require_stacking(cal)
    out = []
    res = 1.0 / cal.px_per_case
    im = cal.see_through_band(im)
    for slot in range(cal.n_slots):
        a1, d1, margin, prov = fit_bar(im, cal, slot)
        edge = edge_bar(im, cal, slot)
        if edge is None:
            agree = False
            ea = ed = None
        else:
            ea, ed = edge
            agree = (abs(a1 - ea) <= max(AGREE_CASES, res)
                     and abs(d1 - ed) <= max(AGREE_CASES, res))
        out.append(BarMeasure(slot=slot, alive=a1, dead=d1, margin=margin,
                              edge_alive=ea, edge_dead=ed,
                              reader_agreement=agree, provisional=prov,
                              resolution_cases=res))
    return out
