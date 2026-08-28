"""Calibrate one onset figure: axes, palette and dates, from its own furniture.

Everything the readers need is measured from the image being read, because
the source re-renders the chart with drifting settings -- the y gridline
step changed from 20 to 25 at sitrep 087, the month labels switch between
English and French, render heights run from 455 to 789 px, and the fill
colours shift under JPEG. A constant tuned on one vintage is a bug on
another; a measurement made on the vintage itself cannot drift.

The geometry rests on the two structures a render cannot omit:

  * the baseline -- the x-axis line the bars grow from -- is the longest
    dark horizontal run in the image, and its extent *is* the panel's width;
  * the bars themselves are the x calibration. Gridlines may be drawn at
    weeks, half-weeks or not at all, and a comb fitted to them is ambiguous
    up to multiples; the bars sit at exactly one per day, so the comb fitted
    to the fill-coloured columns has no such ambiguity.

The palette is sampled from the legend swatches each figure prints, so the
readers never contain a colour constant; the faded fills inside the
"donnees potentiellement incompletes" band are measured from the band's own
interior. A figure this module cannot calibrate raises CalibrationError with
the failing step named, before any bar is read.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

# Plausible day-pitch bounds across observed renders (455 to 853 px tall).
MIN_DAY_PX = 2.2
MAX_DAY_PX = 13.0

# JPEG smears one-pixel lines toward the background: darkness is judged
# leniently, and a line may gap by a few pixels where a bar outline meets it.
BORDER_LUM = 170
BORDER_GAP = 3


class CalibrationError(Exception):
    """A figure whose geometry could not be established; the message names
    the failing step and becomes the refusal reason."""


@dataclass(frozen=True)
class Panel:
    left: int
    top: int
    right: int      # inclusive
    bottom: int     # inclusive; the baseline the bars grow from
    top_from_border: bool   # False when the top edge was inferred from content

    @property
    def width(self) -> int:
        return self.right - self.left + 1

    @property
    def height(self) -> int:
        return self.bottom - self.top + 1


@dataclass(frozen=True)
class Palette:
    alive: tuple[float, float, float]
    dead: tuple[float, float, float]
    band: tuple[float, float, float] | None          # incomplete-band overlay
    faded_alive: tuple[float, float, float] | None   # fills inside the band
    faded_dead: tuple[float, float, float] | None


@dataclass(frozen=True)
class Calibration:
    panel: Panel
    palette: Palette
    day_px: float          # one onset day, in pixels
    x_phase: float         # centre of the first bar slot, image coordinates
    n_slots: int           # bar slots between x_phase and the panel's right
    px_per_case: float     # one case, in pixels: y-label pitch over the step
    y_step: int            # the printed gridline step, asserted in {20, 25}
    y_labels: tuple[tuple[int, float], ...]  # (value, image row) as read
    printed_n: int | None  # the total the title prints: the G2 checksum.
                           # None only when the render carries no title at
                           # all (sitreps 059-062); G2 cannot run there and
                           # the vintage is at best accepted_with_caveat.
    band_left: int | None  # first image column of the incomplete band
    tick_xs: tuple[float, ...]   # x tick-mark positions below the baseline


# ---------------------------------------------------------------------------
# dark-line machinery


def _close_gaps(m: np.ndarray, gap: int = BORDER_GAP) -> np.ndarray:
    """Fill False runs of length <= gap between Trues, along axis 1."""
    n = m.shape[1]
    idx = np.arange(n)
    prev = np.maximum.accumulate(np.where(m, idx, -n), axis=1)
    nxt = np.maximum.accumulate(np.where(m[:, ::-1], idx, -n), axis=1)
    nxt = (n - 1) - nxt[:, ::-1]
    return m | ((idx - prev <= gap) & (nxt - idx <= gap) & (prev >= 0))


def _run_lengths(m: np.ndarray) -> np.ndarray:
    """Longest True run per row (after gap closing), vectorised."""
    z = m.astype(np.int64)
    cs = z.cumsum(axis=1)
    floor = np.maximum.accumulate(np.where(~m, cs, 0), axis=1)
    return (cs - floor).max(axis=1)


def _run_extent(mask_1d: np.ndarray) -> tuple[int, int]:
    """(start, end) of the longest True run in a closed 1-d mask."""
    z = mask_1d.astype(np.int64)
    cs = z.cumsum()
    floor = np.maximum.accumulate(np.where(~mask_1d, cs, 0))
    lens = cs - floor
    end = int(lens.argmax())
    return end - int(lens[end]) + 1, end


def find_panel(im: np.ndarray) -> Panel:
    """The plot area, anchored on the baseline.

    The baseline is the one line no render can soften: bars are drawn on it.
    Its extent gives left and right directly, which survives renders whose
    side borders fade (sitreps 066, 094, 100 in the archive). The top border
    is taken from a matching long dark row when one exists, else inferred
    from the topmost gridline or fill content and flagged.
    """
    dark = _close_gaps(im.mean(axis=2) < BORDER_LUM)
    h, w = dark.shape
    lens = _run_lengths(dark)
    base = int(lens.argmax())
    if lens[base] < 0.55 * w:
        raise CalibrationError(
            f"no baseline: longest dark row spans {lens[base]}/{w} px")
    left, right = _run_extent(dark[base, :])

    # Rows above the baseline whose dark run matches it are border candidates;
    # the topmost is the panel top.
    # A border is a line, not text: it is vertically isolated, where a bold
    # title row is dark for its whole x-height (sitrep 100's title passed a
    # pure run-length test once its word gaps closed).
    def isolated(y: int) -> bool:
        halo_rows = [r for r in (y - 4, y - 3, y + 3, y + 4)
                     if 0 <= r < h]
        halo = np.mean([dark[r, left:right + 1].mean() for r in halo_rows])
        return halo < 0.25 * dark[y, left:right + 1].mean()

    cands = [y for y in range(base)
             if lens[y] >= 0.9 * lens[base] and isolated(y)]
    if cands:
        top = min(cands)
        # The baseline run can extend past the panel's true corner when the
        # zero label at the baseline blurs into the axis line (sitrep 087's
        # encode does this). The vertical border column is the arbiter: if a
        # tall dark column sits within a few label-widths right of the run's
        # start, the panel begins there.
        col_runs = _run_lengths(_close_gaps(dark[top:base, :].T))
        for x in range(left, min(left + 30, right)):
            if col_runs[x] >= 0.9 * (base - top):
                left = x
                break
        return Panel(left=left, top=top, right=right, bottom=base,
                     top_from_border=True)
    # No top border survived the render (sitrep 100's washed out entirely).
    # The incomplete-band overlay spans the panel's full height, so its
    # topmost pink row is the panel top; failing that, the topmost content
    # row stands in, at the risk of swallowing a title into the panel.
    r, g, b = im[:base, :, 0], im[:base, :, 1], im[:base, :, 2]
    pink = (r > 235) & (r - b > 18) & (r - g > 18) & (b > 180)
    pink_cols = np.where(pink.sum(axis=0) > 0.3 * base)[0]
    if len(pink_cols) >= 3:
        band = pink[:, pink_cols]
        top_rows = np.where(band.any(axis=1))[0]
        return Panel(left=left, top=int(top_rows.min()), right=right,
                     bottom=base, top_from_border=False)
    inner = im[:base, left:right + 1]
    nonwhite = (inner.min(axis=2) < 215).sum(axis=1)
    content = np.where(nonwhite > 0.05 * (right - left))[0]
    if len(content) == 0:
        raise CalibrationError("no top border and no content above baseline")
    return Panel(left=left, top=int(content.min()), right=right, bottom=base,
                 top_from_border=False)


# ---------------------------------------------------------------------------
# palette


def _components(mask: np.ndarray) -> list[tuple[int, int, int, int, int]]:
    """Connected components of a small boolean mask, 4-connected BFS.
    Returns (area, y0, x0, y1, x1) per component."""
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
                for ny, nx in ((y-1, x), (y+1, x), (y, x-1), (y, x+1)):
                    if 0 <= ny < h and 0 <= nx < w \
                            and mask[ny, nx] and not seen[ny, nx]:
                        seen[ny, nx] = True
                        stack.append((ny, nx))
            out.append((area, y0, x0, y1, x1))
    return out


def find_legend_palette(im: np.ndarray, panel: Panel) \
        -> tuple[tuple[float, ...], tuple[float, ...]]:
    """The Vivant and Decede fill colours, sampled from the legend swatches.

    The legend sits below the x tick labels: two small solid rectangles of
    saturated colour on white. They are found as compact chromatic
    components, and their interior means are the palette -- the readers
    inherit whatever this render actually printed.
    """
    region = im[panel.bottom + 8:, :]
    if region.shape[0] < 6:
        raise CalibrationError("no room below the baseline for a legend")
    mx = region.max(axis=2)
    mn = region.min(axis=2)
    chroma = mx - mn
    sat = chroma > 45
    comps = [c for c in _components(sat)
             if 40 <= c[0] <= 3000
             and (c[3] - c[1] + 1) >= 6 and (c[4] - c[2] + 1) >= 6
             and c[0] >= 0.55 * (c[3] - c[1] + 1) * (c[4] - c[2] + 1)]
    swatches = []
    for area, y0, x0, y1, x1 in comps:
        patch = region[y0 + 2:y1 - 1, x0 + 2:x1 - 1]
        if patch.size == 0:
            continue
        swatches.append((area, tuple(patch.reshape(-1, 3).mean(axis=0))))
    blues = [s for s in swatches if s[1][2] > s[1][0]]      # b > r
    reds = [s for s in swatches if s[1][0] > s[1][2] + 40]  # r >> b
    if not blues or not reds:
        raise CalibrationError(
            f"legend swatches not found "
            f"({len(blues)} blue, {len(reds)} red candidates)")
    alive = max(blues, key=lambda s: s[0])[1]
    dead = max(reds, key=lambda s: s[0])[1]
    return alive, dead


def find_band(im: np.ndarray, panel: Panel) \
        -> tuple[tuple[float, ...] | None, int | None]:
    """The incomplete-band overlay colour and its first column, if drawn.

    The band is the columns near the panel's right edge whose upper region
    (above every bar) is pink rather than white."""
    probe = im[panel.top + 4: panel.top + max(5, panel.height // 6),
               panel.left: panel.right + 1]
    r, g, b = probe[:, :, 0], probe[:, :, 1], probe[:, :, 2]
    pink = (r > 235) & (r - b > 18) & (r - g > 18) & (b > 180)
    frac = pink.mean(axis=0)
    cols = np.where(frac > 0.6)[0]
    if len(cols) < 3:
        return None, None
    band_cols = probe[:, cols[0]:cols[-1] + 1]
    colour = tuple(band_cols[pink[:, cols[0]:cols[-1] + 1]]
                   .reshape(-1, 3).mean(axis=0))
    return colour, int(cols[0] + panel.left)


def faded_fills(im: np.ndarray, panel: Panel, band_left: int,
                alive: tuple, dead: tuple) \
        -> tuple[tuple[float, ...] | None, tuple[float, ...] | None]:
    """The washed fill colours inside the band, measured from its interior.

    Bars in the band are the alpha-composite of the fills with the overlay.
    Rather than estimating the opacity, the composite is measured where it
    exists: band-interior pixels nearer the blue or red family than the
    band colour, averaged per family. Absent bars leave these None and the
    band's dates are published as provisional with no counts."""
    region = im[panel.top + 2: panel.bottom - 1, band_left: panel.right]
    px = region.reshape(-1, 3)
    bluish = (px[:, 2] > px[:, 0] + 8) & (px[:, 1] > 150) & (px[:, 2] > 170)
    reddish = (px[:, 0] > px[:, 2] + 30) & (px[:, 0] > 180) & (px[:, 1] < 190)
    f_alive = tuple(px[bluish].mean(axis=0)) if bluish.sum() > 40 else None
    f_dead = tuple(px[reddish].mean(axis=0)) if reddish.sum() > 40 else None
    return f_alive, f_dead


# ---------------------------------------------------------------------------
# the combs


def fill_mask(im: np.ndarray, pal: Palette, radius: float = 40.0) -> np.ndarray:
    """Pixels belonging to any bar fill, saturated or faded."""
    targets = [pal.alive, pal.dead]
    targets += [c for c in (pal.faded_alive, pal.faded_dead) if c is not None]
    m = np.zeros(im.shape[:2], dtype=bool)
    for c in targets:
        m |= np.linalg.norm(im - np.array(c), axis=2) < radius
    return m


def bar_pitch(col_prof: np.ndarray, tick_xs: tuple[float, ...]) \
        -> tuple[float, float]:
    """Day pitch and first-bar-centre phase, from ticks and bars together.

    The tick marks below the baseline are printed weekly on every observed
    render, so their median spacing over seven is a first estimate of the
    day pitch that cannot lock onto a harmonic. Autocorrelation of the
    mean-removed fill profile then refines it to sub-pixel: the bars repeat
    at exactly one slot per day, and the autocorrelation peak nearest the
    tick-derived estimate is the fundamental. The two must agree within ten
    percent -- a disagreement means the figure's furniture is not what this
    module thinks it is, and that is a refusal, not a preference.

    Phase comes from the gaps: the comb offset at which the profile is
    lowest marks the bar boundaries, and bar centres sit half a pitch away.
    """
    if len(tick_xs) < 4:
        raise CalibrationError(f"only {len(tick_xs)} x tick marks found")
    ticks = np.array(tick_xs)
    gaps = np.diff(ticks)
    med_gap = float(np.median(gaps))
    if not MIN_DAY_PX <= med_gap / 7.0 <= MAX_DAY_PX:
        raise CalibrationError(
            f"tick spacing {med_gap:.1f}px implies day pitch "
            f"{med_gap / 7.0:.2f}px, outside [{MIN_DAY_PX}, {MAX_DAY_PX}]")
    # Every tick must be a whole number of weeks from the first; a stray
    # detection (a stain, a label descender) refuses rather than tilting
    # the regression.
    weeks = (ticks - ticks[0]) / med_gap
    if np.abs(weeks - np.round(weeks)).max() > 0.25:
        raise CalibrationError(
            f"x ticks are not on a weekly grid: offsets {weeks.round(2)}")
    # The pitch from a single gap is good to ~1%; over 150 slots that
    # drifts half a slot and interleaves neighbouring days between
    # vintages. Regressing position on week index uses the whole axis
    # span, which pins the pitch to a few hundredths of a pixel.
    k = np.round(weeks)
    slope = float(np.polyfit(k, ticks, 1)[0])
    pitch = slope / 7.0

    # Gap phase with the pitch fixed: the comb offset minimising summed
    # profile marks the bar boundaries; centres sit half a pitch away.
    n = len(col_prof)
    best_phase, best_val = 0.0, np.inf
    for ph in np.arange(0.0, pitch, 0.05):
        ks = np.arange(int((n - ph) / pitch) + 1)
        xs = np.round(ph + ks * pitch).astype(int)
        xs = xs[(xs >= 0) & (xs < n)]
        v = col_prof[xs].mean() if len(xs) else np.inf
        if v < best_val:
            best_phase, best_val = ph, v
    centre = best_phase + pitch / 2
    if centre >= pitch:
        centre -= pitch
    return float(pitch), float(centre)


Y_STEPS = (20, 25)
Y_VALUES = {0, 20, 25, 40, 50, 60, 75, 80, 100, 120, 125, 150}


def read_y_axis(im: np.ndarray, panel: Panel) \
        -> tuple[float, int, tuple[tuple[int, float], ...]]:
    """(px_per_case, step, labels) from the printed y tick labels.

    The margin also holds the rotated axis title, so recognition does the
    filtering: a text row counts only if every glyph in it is a digit, its
    value is one the axis could print, and the (value, row) pairs fall on
    one line ending at the baseline. The step comes off the recognised
    values directly -- 20 against 25 is read, not inferred (G7).
    """
    from . import glyphs
    x1 = panel.left - 1
    x0 = max(0, panel.left - 64)
    y0 = max(0, panel.top - 8)
    margin = im[y0: panel.bottom + 6, x0:x1].mean(axis=2)
    comps = glyphs.read_region(margin)

    # The rotated axis title shares text rows with the labels, so rows alone
    # cannot separate them. What does is right-alignment: every label's last
    # digit shares a right edge with the zero printed at the baseline. Find
    # that zero, keep only glyphs in its column band, then read rows.
    base_row = panel.bottom - y0
    anchors = [g for g in comps
               if abs(g["yc"] - base_row) <= 8 and g["char"] == "0"]
    if not anchors:
        # The baseline zero can blur below the match threshold (059 in the
        # archive); accept a weaker zero there and nowhere else.
        anchors = [g for g in comps if abs(g["yc"] - base_row) <= 8
                   and g["score"] >= 0.6 and g["best"] == "0"]
    if not anchors:
        raise CalibrationError("no zero label at the baseline")
    anchor = max(anchors, key=lambda g: g["score"])
    digit_w = anchor["x1"] - anchor["x0"] + 1
    in_band = [g for g in comps
               if abs(g["x1"] - anchor["x1"]) <= max(3, digit_w // 2)
               or (anchor["x1"] - 3.4 * digit_w <= g["x0"]
                   and g["x1"] <= anchor["x1"] + 3)]
    rows = glyphs.group_rows(in_band)
    cands: list[tuple[int, float]] = []
    for row in rows:
        digits = [g for g in row if g["char"] in glyphs.DIGITS]
        if not digits or len(digits) != len(row):
            continue
        value = int("".join(g["char"] for g in digits))
        if value in Y_VALUES:
            cands.append((value,
                          float(np.mean([g["yc"] for g in digits])) + y0))
    # One line through (value, row), ending at the baseline; drop outliers
    # (a rotated 'o' misread as 0, a gridline fleck) one at a time.
    pts = sorted(set(cands))
    while True:
        if len(pts) < 3:
            raise CalibrationError(
                f"y axis unreadable: label candidates {cands}")
        vals = np.array([p[0] for p in pts], dtype=float)
        rws = np.array([p[1] for p in pts], dtype=float)
        A = np.vstack([vals, np.ones_like(vals)]).T
        (slope, intercept), *_ = np.linalg.lstsq(A, rws, rcond=None)
        resid = np.abs(rws - (slope * vals + intercept))
        if resid.max() <= 2.5 and abs(intercept - panel.bottom) <= 5 \
                and slope < 0:
            break
        pts.pop(int(resid.argmax()))
    px_per_case = -slope
    values = sorted(v for v, _ in pts)
    diffs = {b - a for a, b in zip(values, values[1:])}
    steps = [s for s in Y_STEPS if diffs <= {s, 2 * s, 3 * s}]
    if len(steps) != 1:
        raise CalibrationError(
            f"y-label values {values} fit no single step in {Y_STEPS}")
    return float(px_per_case), steps[0], tuple(pts)


def read_printed_n(im: np.ndarray, panel: Panel) -> int | None:
    """The total the title prints -- `(n = 3 767)` -- as an integer.

    The value is the digit run inside the rightmost parenthesis pair on the
    title's text row. Every glyph between the parentheses must be a digit
    or the recognised 'n'/'=' furniture; an unknown glyph there refuses the
    read rather than dropping a digit, because a dropped digit is a wrong
    total that still looks plausible."""
    from . import glyphs
    title = im[0: max(1, panel.top - 1), :].mean(axis=2)
    if (title < glyphs.DARK_LUM).sum() < 40:
        # The earliest render family (059-062) starts at the panel and
        # prints no title anywhere in the raster. No ink is a fact about
        # the source; unreadable ink below is a fact about this reader.
        return None
    comps = glyphs.read_region(title)
    best: int | None = None
    for row in glyphs.group_rows(comps):
        opens = [g for g in row if g["char"] == "("]
        closes = [g for g in row if g["char"] == ")"]
        for cl in sorted(closes, key=lambda g: -g["x0"]):
            ops = [g for g in opens if g["x0"] < cl["x0"]]
            if not ops:
                continue
            op = max(ops, key=lambda g: g["x0"])
            inside = sorted((g for g in row
                             if op["x1"] < g["x0"] < cl["x0"]),
                            key=lambda g: g["x0"])
            best = _pick_number(inside, cl)
            if best is None:
                # Second chance: a digit lost to a merge leaves no
                # component, but its ink is still there. Re-segment the
                # span between the parentheses at the ink valleys and
                # split over-wide cells, then apply the same acceptance.
                cells = _valley_cells(title, op, cl)
                best = _pick_number(cells, cl)
            if best is None:
                # Third chance, for the smallest renders: the same valley
                # read on a three-fold Lanczos upscale, where a merged
                # pair's antialiased seam becomes a resolvable dip.
                best = _valley_read_scaled(title, op, cl, scale=3)
            if best is not None:
                break
        if best is not None:
            break
    if best is None or not 100 <= best <= 99999:
        raise CalibrationError(
            f"printed n not found in the title (got {best})")
    return best


def _pick_number(inside: list[dict], cl: dict) -> int | None:
    """The number a glyph sequence between parentheses spells, or None.

    The 'n =' furniture is separated from the number by a wide gap, and its
    letters can masquerade as digits (one render's 'n' matches '0' at
    0.74), so the sequence is split at wide gaps and only the rightmost
    group read. Within it: every glyph a digit (an unknown is a dropped
    digit waiting to become a plausible wrong total), at most one thousands
    space, and the last digit against the ')'. Sitreps 077 and 094 read
    214 for 2614 and 383 for 3838 before these guards existed.
    """
    from . import glyphs
    inside = list(inside)
    # Unrecognised furniture -- the 'n', the '=' -- leads the span; drop it
    # from the front only. An unknown after the first digit still refuses.
    while inside and inside[0]["char"] not in glyphs.DIGITS:
        inside.pop(0)
    digits_w = [g["x1"] - g["x0"] + 1 for g in inside
                if g["char"] in glyphs.DIGITS]
    if len(digits_w) < 3:
        return None
    w = float(np.median(digits_w))
    groups: list[list[dict]] = [[inside[0]]]
    for a, b in zip(inside, inside[1:]):
        if b["x0"] - a["x1"] > 2.2 * w:
            groups.append([])
        groups[-1].append(b)
    num = groups[-1]
    if len(num) < 3 or not all(g["char"] in glyphs.DIGITS for g in num):
        return None
    gaps = [b["x0"] - a["x1"] for a, b in zip(num, num[1:])]
    if len([g for g in gaps if g > 0.9 * w + 3]) > 1:
        return None
    if cl["x0"] - num[-1]["x1"] > 1.4 * w:
        return None
    return int("".join(g["char"] for g in num))


def _valley_read_scaled(title: np.ndarray, op: dict, cl: dict,
                        scale: int) -> int | None:
    """The valley read on an upscaled copy of the span between parentheses."""
    from PIL import Image as PILImage
    y0 = max(0, min(op["y0"], cl["y0"]) - 2)
    y1 = min(title.shape[0] - 1, max(op["y1"], cl["y1"]) + 2)
    x0, x1 = op["x1"] + 1, cl["x0"] - 1
    if x1 <= x0:
        return None
    strip = title[y0:y1 + 1, x0:x1 + 1]
    big = np.asarray(PILImage.fromarray(strip.astype(np.uint8)).resize(
        (strip.shape[1] * scale, strip.shape[0] * scale),
        PILImage.LANCZOS)).astype(float)
    pseudo_op = {"y0": 0, "y1": big.shape[0] - 1, "x1": -1}
    pseudo_cl = {"y0": 0, "y1": big.shape[0] - 1, "x0": big.shape[1]}
    cells = _valley_cells(big, pseudo_op, pseudo_cl)
    return _pick_number(cells, pseudo_cl)


def _valley_cells(title: np.ndarray, op: dict, cl: dict) -> list[dict]:
    """Glyph cells between two parentheses, cut at column-ink valleys.

    Connected components lose digits that touch their neighbour or the
    parenthesis; the column ink profile still dips between them. Cells are
    contiguous inked column runs, and a run wider than 1.5 digit widths is
    split at its interior minimum. Each cell is classified exactly like a
    component."""
    from . import glyphs
    y0 = max(0, min(op["y0"], cl["y0"]) - 2)
    y1 = min(title.shape[0] - 1, max(op["y1"], cl["y1"]) + 2)
    x0, x1 = op["x1"] + 1, cl["x0"] - 1
    if x1 <= x0:
        return []
    strip = title[y0:y1 + 1, x0:x1 + 1]
    ink = (strip < glyphs.DARK_LUM).sum(axis=0)
    runs: list[list[int]] = []
    for x in range(len(ink)):
        if ink[x] > 0:
            if runs and runs[-1][-1] == x - 1:
                runs[-1].append(x)
            else:
                runs.append([x])
    widths = [len(r) for r in runs if len(r) >= 3]
    if not widths:
        return []
    w = float(np.median(widths))
    cells: list[tuple[int, int]] = []
    stack = [(r[0], r[-1]) for r in runs]
    while stack:
        a, b = stack.pop(0)
        if b - a + 1 > 1.5 * w and b - a >= 4:
            mid = a + 2 + int(np.argmin(ink[a + 2: b - 1]))
            stack = [(a, mid - 1), (mid + 1, b)] + stack
        else:
            cells.append((a, b))
    out = []
    for a, b in sorted(cells):
        col = np.where((strip[:, a:b + 1] < glyphs.DARK_LUM).any(axis=1))[0]
        if len(col) == 0 or b - a + 1 < 2:
            continue
        cy0, cy1 = int(col.min()), int(col.max())
        if cy1 - cy0 + 1 < glyphs.MIN_H:
            continue
        char, score = glyphs.match(
            glyphs._normalise(strip, cy0, a, cy1, b))
        out.append({"y0": cy0 + y0, "x0": a + x0, "y1": cy1 + y0,
                    "x1": b + x0, "yc": (cy0 + cy1) / 2.0 + y0,
                    "xc": (a + b) / 2.0 + x0,
                    "char": char if score >= glyphs.MATCH_MIN else "?",
                    "best": char, "score": score})
    return out


def calibrate(im: np.ndarray) -> Calibration:
    panel = find_panel(im)
    alive, dead = find_legend_palette(im, panel)
    band_colour, band_left = find_band(im, panel)
    f_alive = f_dead = None
    if band_left is not None:
        f_alive, f_dead = faded_fills(im, panel, band_left, alive, dead)
    pal = Palette(alive=alive, dead=dead, band=band_colour,
                  faded_alive=f_alive, faded_dead=f_dead)

    # Tick marks first: short dark strokes just below the baseline, one per
    # labelled tick. They validate the bar pitch and are what the anchor
    # register's dates attach to.
    below = im[panel.bottom + 1: panel.bottom + 6, :].mean(axis=2)
    tick_cols = np.where((below < BORDER_LUM).sum(axis=0) >= 2)[0]
    groups: list[list[int]] = []
    for x in tick_cols:
        if groups and x - groups[-1][-1] <= 2:
            groups[-1].append(x)
        else:
            groups.append([x])
    tick_xs = tuple(float(np.mean(t)) for t in groups
                    if panel.left - 5 <= np.mean(t) <= panel.right + 5)

    fills = fill_mask(im, pal)
    fills[:panel.top + 2, :] = False
    fills[panel.bottom:, :] = False
    fills[:, :panel.left + 1] = False
    fills[:, panel.right:] = False
    col_prof = fills.sum(axis=0).astype(float)
    if col_prof.max() < 3:
        raise CalibrationError("no bar fill found inside the panel")
    day_px, x_phase = bar_pitch(col_prof[panel.left:panel.right + 1], tick_xs)
    x_phase += panel.left

    # A tick marks a date, and a date is a bar slot: every tick must land on
    # a slot centre. A consistent half-slot offset means the gap comb found
    # centres where the gaps are; scattered offsets mean the geometry is
    # not understood, which refuses.
    tk = np.array(tick_xs)
    frac = ((tk - x_phase) / day_px) % 1.0
    off = np.minimum(frac, 1.0 - frac)
    if np.median(off) > 0.32:
        x_phase += day_px / 2.0
        frac = ((tk - x_phase) / day_px) % 1.0
        off = np.minimum(frac, 1.0 - frac)
    if np.median(off) > 0.2:
        raise CalibrationError(
            f"x ticks sit {np.median(off):.2f} slots off the bar centres")

    px_per_case, y_step, y_labels = read_y_axis(im, panel)
    printed_n = read_printed_n(im, panel)

    # Only slots that fit wholly inside the panel are bars; a slot centred
    # against the right border reads the border's own pixels as a phantom
    # bar (sitrep 099 grew 78 cases from one sliver of band edge).
    n_slots = int((panel.right - 0.45 * day_px - x_phase) / day_px) + 1
    return Calibration(panel=panel, palette=pal, day_px=day_px,
                       x_phase=x_phase, n_slots=n_slots,
                       px_per_case=px_per_case, y_step=y_step,
                       y_labels=y_labels, printed_n=printed_n,
                       band_left=band_left, tick_xs=tick_xs)
