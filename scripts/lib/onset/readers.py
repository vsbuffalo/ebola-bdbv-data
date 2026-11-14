"""Measure each bar twice, by mechanisms that share no blind spot.

Reader one never asks a pixel to decide anything: for one bar the truth is a
pair of integers (alive, dead), so every admissible pair is rendered --
the baseline colour's fill up its count from the baseline, the other
colour's fill for the next, background above -- and scored against the observed pixels as a robust cost.
The argmax over the enumerated lattice is the exact global best; a smeared
pixel moves one candidate's score by a sliver and can truncate nothing.
The two rows at a hypothesised boundary are not scored as fill or as
background, because JPEG concentrates its damage exactly there: the seven
washed rows that amputated upstream's 25 July bar sit in that band of
every candidate. They are scored for one thing only -- the outline the
chart draws at every segment's edge must be in one of them (see
`_fit_lattice`). Where a count puts a boundary is the chart's geometry and
nothing else: `Calibration.y_zero` (the centre of the baseline axis line)
plus the count times the scale, rounded once.

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

The readers are not blind to the same things, but they are not fully
independent either: reader one needs an outline to be visible at each
boundary it proposes, and reader two reads nothing else. A render with no
outlines defeats both.

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
# Weight of the unscored rows' own colour when two hypotheses tie on
# everything scored: a whole panel of wrong-colour rows at this weight is
# under a third of one scored row.
TIE_WEIGHT = 1e-3
# The two readers must agree within this many cases on each component.
AGREE_CASES = 1.0
# Rows under the panel's top border that reader two never takes for a bar top.
TOP_BORDER_ROWS = 2


@dataclass(frozen=True)
class BarMeasure:
    slot: int              # bar index from the left edge of the axis
    alive: int | None      # None, with `dead`, where the slot was not read
    dead: int | None
    margin: float | None   # cost gap, best to second-best (a, d)
    edge_alive: int | None     # reader two's counts; None where it refused
    edge_dead: int | None
    reader_agreement: bool     # the two readers within AGREE_CASES
    provisional: bool      # inside the "donnees potentiellement incompletes" band
    resolution_cases: float
    # The two readers give the same alive and the same dead count. Recorded
    # beside `reader_agreement`, which the reader-disagreement gate uses
    # and which, at one case of tolerance, cannot see a one-case error.
    reader_exact: bool = False
    # Why the slot carries no count, where it does not. A slot that is not
    # read is unobserved on this chart -- not zero, and not a refusal of
    # the chart.
    not_read: str | None = None

    @property
    def read(self) -> bool:
        return self.not_read is None


NOT_READ_DASHED_LINE = ("a red dashed vertical line runs through this "
                        "date's columns")


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


def _stroke_mask(strip: np.ndarray) -> np.ndarray:
    """Pixels that are bar outline: dark *and desaturated*. Darkness alone
    also selects the red fill (luminance ~95 against the stroke's ~84),
    which made the "topmost dark run" land mid-cap; the fill's strong
    red-blue excess is what the stroke never has. Masked (NaN) pixels are
    not stroke."""
    lum = strip.mean(axis=2)
    return (lum < 135) & (strip[:, :, 0] - strip[:, :, 2] < 90) \
        & (strip[:, :, 0] < 170)


def _outline_costs(strip: np.ndarray) -> np.ndarray:
    """Per-row cost of taking a row for a bar's outline: the share of its
    seen pixels that are not stroke, in the same units as a row of fill.
    A row with nothing seen (the band's label) costs nothing."""
    seen = ~np.isnan(strip).any(axis=2)
    n = seen.sum(axis=1)
    hit = (_stroke_mask(strip) & seen).sum(axis=1)
    return np.where(n > 0, COST_CLIP * (1.0 - hit / np.maximum(n, 1)), 0.0)


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
    compares across the two orders.

    Where a hypothesis puts its boundaries. A count k has its edge at
    `y_zero + k * c` pixels, and that is rounded once. The lower segment's
    top is the edge of its own count; the bar's top is the edge of the
    *total*. Building the top as two rounded segments added together put
    it up to a pixel from where the chart draws it, and counting from the
    top edge of row `panel.bottom` instead of the baseline's centre added
    up to 1.3 px more. At 7 px per case neither matters. At 2.6-3 px per
    case, with the two rows at each boundary unscored, the candidates a
    case apart differ by one scored row or none, and a pixel of
    misplacement chose between them: sitrep 127's 14 June bar (24 alive,
    20 dead on the image, outline ink ending at row 131) had its 44-case
    candidate placed at row 132 and its 43-case candidate at 129, and
    read 43.

    What the boundary rows are scored for. An outline 1.3 px thick always
    covers most of one of the two rows at a correctly placed boundary, so
    each boundary a hypothesis proposes -- the bar's top, and the edge
    between two segments when both are present -- is charged the outline
    cost of the better of its two rows. Without this a one-case segment
    can be all boundary: at 2.6 px per case it spans two or three rows,
    two of them unscored, so adding a case to an empty slot or to the top
    of a bar could cost nothing and remove a row of background cost. With
    it, a proposed boundary with no outline pays a full row."""
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

    amax = int((R - cal.y_zero) / c)
    a_idx = np.arange(amax + 1)
    # edge[k] = rows below the edge of a count of k, measured from the
    # baseline's centre and rounded once; a count of zero has no edge.
    edge = np.clip(np.round(cal.y_zero + np.arange(2 * amax + 1) * c),
                   0, None).astype(int)
    edge[0] = 0
    ha = edge[:amax + 1]                                    # lower top, px
    total = a_idx[:, None] + a_idx[None, :]
    # h2[l, u] = pixel row of the bar's top, from the total count
    top = edge[total]
    h2 = np.minimum(top, R)
    valid = top <= R + int(c)

    cost_lower = rng(PL, np.zeros_like(ha), ha)             # per l
    h1 = np.broadcast_to(ha[:, None], h2.shape)
    cost_upper = rng(PU, h1, h2)
    cost_bg = rng(PB, h2, np.full_like(h2, R))
    # The outline: the better of the two rows at each proposed boundary.
    so = np.concatenate([_outline_costs(strip), [COST_CLIP]])

    def outline(h: np.ndarray) -> np.ndarray:
        h = np.clip(h, 1, R)
        return np.minimum(so[h - 1], so[h])

    cost_outline = np.where(total > 0, outline(h2), 0.0) \
        + np.where((a_idx[:, None] > 0) & (a_idx[None, :] > 0),
                   outline(h1), 0.0)
    obj = cost_lower[:, None] + cost_upper + cost_bg + cost_outline
    # A segment of two rows is all boundary and has no scored row of its
    # own, so one case alive and one case dead would tie. The tie goes to
    # the colour of the segment's own rows, boundary rows included, at a
    # weight too small to move any hypothesis the scored rows separate.
    obj = obj + TIE_WEIGHT * ((PL[ha] - PL[0])[:, None] + PU[h2] - PU[h1])
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
    from those sums by index shift and scored for the outline instead. Which colour is the
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
    stroke = _stroke_mask(strip)
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
    # Heights to here are counted from row `panel.bottom`; a count is the
    # height above the bars' zero, the baseline's measured centre.
    total_px = float(np.median(tops_a)) - cal.y_zero
    inner_px = float(np.median(bounds_a[bounds_a > 0])) - cal.y_zero \
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
        stroke = _stroke_mask(strip)
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
    design requires (G7).

    The lattice has an origin as well as a pitch, and this fits the pitch
    only, so the heights must be counted from where the bars' zero really
    is (`Calibration.y_zero`). Counted from the top edge of row
    `panel.bottom` they all carry the same offset of up to 1.3 px, and the
    one free parameter absorbed it: the scale came out 0.2-0.9% small on
    every render whose baseline centre sits near a pixel below that edge
    (sitrep 102: 2.7921 against 2.8169 from the y tick marks), and on two
    it jumped to another minimum altogether (114: +3.9%, which read the
    chart 255 cases short of its printed total; 154: +1.2%, 179 short).
    From the measured zero it agrees with the tick marks to within 0.25%
    on all 60 renders read."""
    heights = _confident_heights(im, cal) - cal.y_zero
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


# The dashed line. Its ink is red -- the red channel exceeds both others by
# at least this much. That is loose on purpose: the line is pure red in the
# lossless renders, the dead fill's red after JPEG, and paler still where it
# covers half a column in the small renders (154, 69, 76 in sitrep 129),
# and the colour is not what identifies it. What does is the spacing: the
# starts of the red runs up one column are even -- successive starts within
# this share of their median spacing -- and the evenly spaced stretch
# covers at least this share of the panel's height. A bar is one run; the
# annotation's lettering and the band's rotated label are a few runs at
# uneven spacings. On the 62 renders read at sitrep 159 this marks 14 May
# on every one and no other date.
DASH_RED_EXCESS = 50.0
DASH_SPACING_TOLERANCE = 0.2
DASH_MIN_EXTENT = 0.5


def dashed_line_columns(im: np.ndarray, cal: Calibration) -> np.ndarray:
    """Image columns a red vertical dashed line runs up.

    The source marks the date of the first laboratory confirmation
    ("Premier resultat positif", 14 May) with a dashed vertical red line
    from the baseline to the top of the panel, drawn over that date's bar.
    A dash is about two cases tall and a gap about three, at a phase that
    changes with every render's scale, so on the columns it crosses a dash
    reads as dead cases and a gap as background or as a break in the alive
    segment: the date read 8 + 2, 4 + 6, 5 + 8, 4 + 9, 1 + 6 and 4 + 4
    across the archive. Nothing in the column says which red is bar and
    which is line.

    Returns a boolean per image column. `read_bars` does not read a slot
    any of whose columns is one."""
    p = cal.panel
    region = im[p.top + 1: p.bottom, :]
    red = region[:, :, 0] - region[:, :, 1:].max(axis=2) > DASH_RED_EXCESS
    starts = red & ~np.vstack([np.zeros((1, red.shape[1]), bool), red[:-1]])
    out = np.zeros(im.shape[1], dtype=bool)
    for x in range(p.left + 1, p.right):
        rows = np.where(starts[:, x])[0]
        if len(rows) < 4:
            continue
        gaps = np.diff(rows)
        period = float(np.median(gaps))
        even = np.abs(gaps - period) <= DASH_SPACING_TOLERANCE * period
        out[x] = even.sum() * period >= DASH_MIN_EXTENT * red.shape[0]
    return out


def read_bars(im: np.ndarray, cal: Calibration) -> list[BarMeasure]:
    _require_stacking(cal)
    out = []
    res = 1.0 / cal.px_per_case
    line = dashed_line_columns(im, cal)
    im = cal.see_through_band(im)
    p = cal.panel
    for slot in range(cal.n_slots):
        centre = cal.x_phase + slot * cal.day_px
        half = max(1.0, 0.32 * cal.day_px)
        x0 = max(int(np.ceil(centre - half)), p.left + 1)
        x1 = min(int(np.floor(centre + half)), p.right - 1)
        if line[x0:x1 + 1].any():
            out.append(BarMeasure(
                slot=slot, alive=None, dead=None, margin=None,
                edge_alive=None, edge_dead=None, reader_agreement=False,
                provisional=(cal.band_left is not None
                             and centre >= cal.band_left),
                resolution_cases=res, not_read=NOT_READ_DASHED_LINE))
            continue
        a1, d1, margin, prov = fit_bar(im, cal, slot)
        edge = edge_bar(im, cal, slot)
        if edge is None:
            agree = exact = False
            ea = ed = None
        else:
            ea, ed = edge
            agree = (abs(a1 - ea) <= max(AGREE_CASES, res)
                     and abs(d1 - ed) <= max(AGREE_CASES, res))
            exact = (a1, d1) == (ea, ed)
        out.append(BarMeasure(slot=slot, alive=a1, dead=d1, margin=margin,
                              edge_alive=ea, edge_dead=ed,
                              reader_agreement=agree, provisional=prov,
                              resolution_cases=res, reader_exact=exact))
    return out
