"""Figures for the onset-digitiser blog post: how two readers handle one chart
saved at two JPEG compressions.

    python scripts/blog_onset_figures.py      # -> data/build/blog/onset/

Which source: the onset charts `make onset` extracts from the INSP situation
reports (primary), sitreps 087 and 088 -- the same chart, the second PDF
compressed harder (651 KB against 2.63 MB). The bar shown is 25 July, the one
whose red segment the upstream reader lost on 088
(notes/2026-08-28-onset-digitiser-requirements.md, section 1.2).

What it produces: one PNG per figure, for exposition only. Fitted: no.
Validated by: the bar is located by our own calibration and dating, and the
script checks that the column the requirements note quotes (797) falls inside
it.
"""

from __future__ import annotations

import datetime as dt
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.patches import Rectangle  # noqa: E402
from PIL import Image  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from lib.onset.assemble import load_anchors, slot_dates  # noqa: E402
from lib.onset.calibrate import calibrate, fill_mask  # noqa: E402
from lib.onset.readers import (_background_cost, _class_costs,  # noqa: E402
                               fit_bar, refine_scale)

sys.path.insert(0, str(ROOT / "scripts/vendor"))
import epiforecasts_onset_bfe9014 as U  # noqa: E402

IMAGES = ROOT / "data/build/onset/images"
PDFS = ROOT / "data/raw/sitrep_pdfs"
OUT = ROOT / "data/build/blog/onset"
BAR = dt.date(2026, 7, 25)
NOTE_COLUMN = 797          # the column the requirements note prints row by row
NEIGHBOURS = 4             # bars either side of the 25 July bar in the crop


def load(sitrep: int) -> tuple[Path, np.ndarray]:
    [path] = sorted(IMAGES.glob(f"*-{sitrep:03d}-*.png"))
    return path, np.asarray(Image.open(path).convert("RGB"))


def bar_columns(path: Path, im: np.ndarray) -> tuple[int, int, int, int]:
    """Image columns of the 25 July bar slot, plus the crop's column span."""
    cal = refine_scale(im.astype(float), calibrate(im.astype(float)))
    sha12 = path.stem.rsplit("-", 1)[1]
    dates = slot_dates(cal, load_anchors()[sha12])
    k = dates.index(BAR)
    centre = cal.x_phase + k * cal.day_px
    half = cal.day_px / 2
    lo, hi = int(np.floor(centre - half)), int(np.ceil(centre + half))
    assert lo <= NOTE_COLUMN <= hi, (path.name, lo, hi)
    span = NEIGHBOURS * cal.day_px + half
    return lo, hi, int(centre - span), int(centre + span)


def pdf_size(sitrep: int) -> str:
    [pdf] = sorted(PDFS.glob(f"sitrep_{sitrep:03d}_*.pdf"))
    b = pdf.stat().st_size
    return f"{b / 1e6:.2f} MB" if b >= 1e6 else f"{b / 1e3:.0f} KB"


def window() -> tuple[np.ndarray, np.ndarray, tuple[int, int], tuple[int, int, int, int]]:
    """Both images, the bar's columns, and the crop every figure shares.

    Rows run from above the bar top to below the red/blue boundary, which is
    where the upstream reader stopped on 088; found on 087's note column."""
    (p87, a), (p88, b) = load(87), load(88)
    assert a.shape == b.shape
    lo, hi, c0, c1 = bar_columns(p87, a)
    assert (lo, hi) == bar_columns(p88, b)[:2], "the two renders disagree on the bar"
    px = a[:, NOTE_COLUMN].astype(int)
    red = np.where((px[:, 0] - px[:, 1] > 60) & (px[:, 0] - px[:, 2] > 60))[0]
    return a, b, (lo, hi), (red.min() - 22, red.max() + 45, c0, c1)


def figure_two_encodings() -> Path:
    """Figure 1: the same bar in both encodings, and what differs."""
    a, b, _, (r0, r1, c0, c1) = window()
    crop87, crop88 = a[r0:r1, c0:c1], b[r0:r1, c0:c1]
    diff = np.abs(crop87.astype(int) - crop88.astype(int)).max(axis=2)

    fig = plt.figure(figsize=(11, 8.6), layout="constrained")
    top, bottom = fig.subfigures(2, 1, height_ratios=[1, 1.2])
    for ax, im, s in zip(top.subplots(1, 2), (a, b), (87, 88)):
        ax.imshow(im)
        ax.add_patch(Rectangle((c0, r0), c1 - c0, r1 - r0, fill=False,
                               ec="#e8590c", lw=1.5))
        ax.set_title(f"SitRep {s:03d}: PDF {pdf_size(s)}", fontsize=11)
        ax.set_axis_off()
    axes = bottom.subplots(1, 3)
    for ax, im, s in zip(axes[:2], (crop87, crop88), (87, 88)):
        ax.imshow(im, interpolation="nearest")
        ax.axvline(NOTE_COLUMN - c0, color="#e8590c", lw=0.8, ls=":")
        ax.set_title(f"{s:03d}: the 25 July bar and its neighbours", fontsize=10)
        ax.set_axis_off()
    im = axes[2].imshow(diff, cmap="magma", vmin=0, vmax=60,
                        interpolation="nearest")
    axes[2].set_title("|087 − 088|, largest colour channel", fontsize=10)
    axes[2].set_axis_off()
    bottom.colorbar(im, ax=axes[2], shrink=0.7)
    fig.suptitle("The same chart, saved at two JPEG compressions",
                 fontsize=13, fontweight="bold")
    OUT.mkdir(parents=True, exist_ok=True)
    out = OUT / "fig1_two_encodings.png"
    fig.savefig(out, dpi=150)
    plt.close(fig)
    return out


@dataclass(frozen=True)
class Climb:
    """The upstream reader's per-column decisions, kept instead of summed."""
    blue: np.ndarray       # its blue mask, whole image
    red: np.ndarray        # its red mask
    stop: np.ndarray       # per column: the last row the climb examined
    nblue: np.ndarray      # per column: blue pixels counted
    nred: np.ndarray       # per column: red pixels counted
    ppc: float             # its pixels per case
    y0: int                # the row the climb starts from
    windows: dict[str, float]  # its tick geometry: lastx, ppd, bar extent


def upstream_climb(im: np.ndarray) -> Climb:
    """Upstream's column flood from `digitize` (vendored, commit bfe9014),
    with the row each climb stopped at recorded. The scale comes from the
    vendored functions themselves; only the loop is restated, to keep what
    `digitize` discards. `check_upstream` holds it to the vendored output."""
    im = im.astype(int)
    H, W, _ = im.shape
    blue, red, _, dark = U._masks(im)
    base = U._baseline_row(im, H)
    yt = U._y_axis_ticks(dark, base, W)
    ppc = float(np.median(np.diff(yt))) / 25.0      # y_step 25 from SitRep 087
    ytop, y0 = yt[0], yt[-1]
    stop, nb, nr = np.zeros(W, int), np.zeros(W), np.zeros(W)
    for x in range(W):
        r, miss = y0 - 1, 0
        while r > ytop - 2 and r >= 0:
            if blue[r, x]:
                nb[x] += 1
                miss = 0
            elif red[r, x]:
                nr[x] += 1
                miss = 0
            else:
                miss += 1
                if miss > 6:
                    break
            r -= 1
        stop[x] = r
    return Climb(blue, red, stop, nb, nr, ppc, y0, _windows(im, dark, base, nb + nr))


def _windows(im, dark, base, tot) -> dict[str, tuple[int, int]]:
    """Upstream's day windows: its weekly-tick row and pixels-per-day, then
    each day's columns, restated from `digitize` line for line."""
    H, W, _ = im.shape

    def weekly(mask):
        band = mask[base + 2:base + 7, :].sum(axis=0)
        best_n, best = 0, np.array([])
        for cut in (4, 3, 2, 1):
            cand = np.array(U._cluster([x for x in range(W) if band[x] >= cut]))
            if len(cand) >= 8 and len(cand) > best_n:
                best_n, best = len(cand), cand
        return best

    xt = weekly(dark)
    if len(xt) == 0:
        R, G, B = im[:, :, 0], im[:, :, 1], im[:, :, 2]
        xt = weekly((R < 180) & (G < 180) & (B < 180))
    ppd = float(np.median(np.diff(xt))) / 7.0
    lastx = xt[-1] + 1
    nz = np.where(tot > 2)[0] + 1
    barmin, barmax = nz.min(), nz.max()
    return {"lastx": lastx, "ppd": ppd, "barmin": barmin, "barmax": barmax}


def upstream_read(sitrep: int) -> dict[str, tuple[int, int]]:
    """The vendored reader's own output for one report: date -> (alive, dead)."""
    [pdf] = sorted(PDFS.glob(f"sitrep_{sitrep:03d}_*.pdf"))
    with tempfile.TemporaryDirectory() as d:
        im = U.extract_onset_image(str(pdf), d)
    rows = U.digitize(im, U.CONFIG[f"{sitrep:03d}"][1], y_step=25)
    return {date: (alive, dead) for date, alive, dead in rows}


def upstream_bar(c: Climb, sitrep: int, date: dt.date) -> tuple[range, int, int]:
    """One day's columns and reading, as `digitize` computes them."""
    w = c.windows
    last = dt.date.fromisoformat(U.CONFIG[f"{sitrep:03d}"][1])
    cx = w["lastx"] + (date - last).days * w["ppd"]
    lo, hi = int(round(cx - w["ppd"] * 0.45)), int(round(cx + w["ppd"] * 0.45))
    cols = range(max(1, lo) - 1, min(len(c.stop), hi))
    alive = round(float(np.percentile([c.nblue[x] for x in cols], 75)) / c.ppc)
    dead = round(float(np.percentile([c.nred[x] for x in cols], 75)) / c.ppc)
    return cols, alive, dead


def check_upstream(c: Climb, sitrep: int) -> None:
    """The restatement must reproduce the vendored reader on every date."""
    for date, read in upstream_read(sitrep).items():
        _, alive, dead = upstream_bar(c, sitrep, dt.date.fromisoformat(date))
        assert (alive, dead) == read, (sitrep, date, (alive, dead), read)


def figure_upstream_reader() -> Path:
    """Figure 2a: where the upstream reader's climb stopped in every column, on both encodings,
    and on the difference between them."""
    a, b, cols, (r0, r1, c0, c1) = window()
    panels = []
    for im, s in ((a, 87), (b, 88)):
        c = upstream_climb(im)
        alive, dead = upstream_read(s)[BAR.isoformat()]
        check_upstream(c, s)
        panels.append((im, s, c, alive, dead))
    fig, axes = plt.subplots(1, 3, figsize=(11, 7.5), layout="constrained")
    xs = np.arange(c0, c1)
    for ax, (im, s, c, alive, dead) in zip(axes[:2], panels):
        crop = im[r0:r1, c0:c1].astype(float) / 255
        rows = np.arange(r0, r1)[:, None]
        examined = (rows <= c.y0 - 1) & (rows > c.stop[None, xs])
        miss = examined & ~c.blue[r0:r1, c0:c1] & ~c.red[r0:r1, c0:c1]
        unseen = rows <= c.stop[None, xs]
        shown = crop.copy()
        lum = shown.mean(axis=2, keepdims=True)
        shown = np.where(unseen[..., None], 0.55 + 0.4 * lum, shown)
        shown[miss] = (1.0, 0.85, 0.0)
        ax.imshow(shown, interpolation="nearest")
        inside = (c.stop[xs] >= r0) & (c.stop[xs] < r1)
        ax.plot((xs - c0)[inside], (c.stop[xs] - r0)[inside], "_",
                color="black", ms=9, mew=2)
        ucols, _, _ = upstream_bar(c, s, BAR)
        ax.annotate("", xy=(ucols[0] - c0 - 0.5, r1 - r0 + 2),
                    xytext=(ucols[-1] - c0 + 0.5, r1 - r0 + 2),
                    arrowprops=dict(arrowstyle="|-|", color="#1c7ed6", lw=1.5),
                    annotation_clip=False)
        ax.text((ucols[0] + ucols[-1]) / 2 - c0, r1 - r0 + 6, "25 July",
                ha="center", va="top", fontsize=8, color="#1c7ed6")
        top = c.y0 - (alive + dead) * c.ppc
        ax.hlines(top - r0, ucols[0] - c0 - 0.5, ucols[-1] - c0 + 0.5,
                  color="#1c7ed6", lw=2.5)
        ax.set_title(f"{s:03d}: upstream reads 25 July as {alive} + {dead}",
                     fontsize=10)
        ax.set_xlim(-0.5, c1 - c0 - 0.5)
        ax.set_ylim(r1 - r0 - 0.5, -0.5)
        ax.set_axis_off()
    diff = np.abs(a[r0:r1, c0:c1].astype(int)
                  - b[r0:r1, c0:c1].astype(int)).max(axis=2)
    axes[2].imshow(diff, cmap="magma", vmin=0, vmax=60, interpolation="nearest")
    c88 = panels[1][2]
    inside = (c88.stop[xs] >= r0) & (c88.stop[xs] < r1)
    axes[2].plot((xs - c0)[inside], (c88.stop[xs] - r0)[inside], "_",
                 color="#4dabf7", ms=9, mew=2)
    axes[2].set_xlim(-0.5, c1 - c0 - 0.5)
    axes[2].set_ylim(r1 - r0 - 0.5, -0.5)
    axes[2].set_title("|087 − 088|, with 088's stopping rows", fontsize=10)
    axes[2].set_axis_off()
    fig.suptitle("Where the upstream reader stops climbing each pixel column",
                 fontsize=13, fontweight="bold")
    fig.text(0.5, -0.02,
             "Yellow: a pixel the climb examined and matched to neither colour; "
             "seven in a row end the column (black tick). Grey: above the stop, never counted. "
             "Blue line: the bar top the reader reports.",
             ha="center", fontsize=9)
    out = OUT / "fig2a_upstream_climb_all_columns.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out


def figure_upstream_window() -> Path:
    """Figure 2b: the 25 July bar as upstream reads it -- one climb per pixel
    column of its day window, then the 75th percentile across them."""
    a, b, _, (r0, r1, c0, c1) = window()
    fig = plt.figure(figsize=(11, 9), layout="constrained")
    for sub, im, s in zip(fig.subfigures(1, 2), (a, b), (87, 88)):
        c = upstream_climb(im)
        check_upstream(c, s)
        cols, alive, dead = upstream_bar(c, s, BAR)
        ax_img, ax_bar = sub.subplots(2, 1, height_ratios=[2.2, 1])
        crop = im[r0:r1, c0:c1].astype(float) / 255
        shown = 0.55 + 0.4 * crop.mean(axis=2, keepdims=True).repeat(3, axis=2)
        xs = np.array(cols)
        shown[:, xs - c0] = crop[:, xs - c0]
        rows = np.arange(r0, r1)[:, None]
        miss = ((rows <= c.y0 - 1) & (rows > c.stop[None, xs])
                & ~c.blue[r0:r1][:, xs] & ~c.red[r0:r1][:, xs])
        sel = shown[:, xs - c0]
        sel[miss] = (1.0, 0.85, 0.0)
        shown[:, xs - c0] = sel
        ax_img.imshow(shown, interpolation="nearest")
        inside = (c.stop[xs] >= r0) & (c.stop[xs] < r1)
        ax_img.plot((xs - c0)[inside], (c.stop[xs] - r0)[inside], "_",
                    color="black", ms=9, mew=2)
        ax_img.set_xlim(-0.5, c1 - c0 - 0.5)
        ax_img.set_ylim(r1 - r0 - 0.5, -0.5)
        ax_img.set_title(f"{s:03d}: the six columns of the 25 July window",
                         fontsize=10)
        ax_img.set_axis_off()
        nb, nr = c.nblue[xs], c.nred[xs]
        w = 0.38
        ax_bar.bar(xs - w / 2, nb, w, color="#a5d8ff", ec="#1c7ed6", label="blue pixels")
        ax_bar.bar(xs + w / 2, nr, w, color="#ff8787", ec="#c92a2a", label="red pixels")
        for v, col, n in ((np.percentile(nb, 75), "#1c7ed6", alive),
                          (np.percentile(nr, 75), "#c92a2a", dead)):
            ax_bar.axhline(v, color=col, ls="--", lw=1.2)
            ax_bar.text(xs[-1] + 0.6, v, f"75th pct {v:.1f} px\n→ {n} cases",
                        va="center", fontsize=8, color=col)
        ax_bar.set_xticks(xs)
        ax_bar.set_xlabel("pixel column")
        ax_bar.set_ylabel("pixels counted by the climb")
        ax_bar.set_xlim(xs[0] - 0.7, xs[-1] + 2.6)
        ax_bar.spines[["top", "right"]].set_visible(False)
        ax_bar.legend(frameon=False, fontsize=8, loc="upper left")
        ax_bar.set_title(f"read as {alive} + {dead}", fontsize=10)
    fig.suptitle("Upstream's reader: climb each column, then take the 75th "
                 "percentile across the day's window", fontsize=13,
                 fontweight="bold")
    fig.text(0.5, -0.02, "Only the window's columns are in full colour. Yellow: "
             "pixels the climb examined and matched to neither colour; seven in "
             "a row end the column (black tick).", ha="center", fontsize=9)
    out = OUT / "fig2b_upstream_window.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out


def bar_centres(im: np.ndarray) -> tuple[list[dt.date], np.ndarray, np.ndarray]:
    """Per dated slot: our slot centre and the bar's measured centre, the
    midpoint of its filled run of columns three rows above the baseline
    (NaN where no bar stands within half a day of the slot)."""
    f = im.astype(float)
    cal = refine_scale(f, calibrate(f))
    row = fill_mask(f, cal.palette)[cal.panel.bottom - 3]
    xs = np.where(row)[0]
    runs = np.split(xs, np.where(np.diff(xs) > 1)[0] + 1)
    mids = np.array([(r[0] + r[-1]) / 2 for r in runs if len(r) >= 3])
    ours = cal.x_phase + np.arange(cal.n_slots) * cal.day_px
    near = mids[np.abs(mids[None, :] - ours[:, None]).argmin(axis=1)]
    actual = np.where(np.abs(near - ours) < cal.day_px / 2, near, np.nan)
    return cal, ours, actual


def figure_day_placement() -> Path:
    """Figure 2c: where each reader puts each day's window, against where the
    bar actually stands."""
    fig = plt.figure(figsize=(11, 8), layout="constrained")
    top, bottom = fig.subfigures(2, 1, height_ratios=[1, 0.7])
    ax = top.subplots()
    insets = {}
    for s, mk in ((87, "o"), (88, "s")):
        path, im = load(s)
        cal, ours, actual = bar_centres(im)
        dates = slot_dates(cal, load_anchors()[path.stem.rsplit("-", 1)[1]])
        c = upstream_climb(im)
        w = c.windows
        last = dt.date.fromisoformat(U.CONFIG[f"{s:03d}"][1])
        theirs = np.array([w["lastx"] + (d - last).days * w["ppd"] - 1
                           for d in dates])        # 0-based, as indexed
        ok = ~np.isnan(actual)
        d = np.array(dates)[ok]
        ax.plot(d, (theirs - actual)[ok] / cal.day_px, mk, ms=3.5,
                color="#e8590c", label=f"upstream (bfe9014), {s:03d}: "
                f"{w['ppd']:.3f} px/day")
        ax.plot(d, (ours - actual)[ok] / cal.day_px, mk, ms=3.5,
                color="#1c7ed6", label=f"ours, {s:03d}: {cal.day_px:.3f} px/day")
        insets[s] = (im, cal, dates, ours, theirs, w)
    half = 0.45 * insets[87][5]["ppd"] / insets[87][1].day_px
    ax.axhspan(-0.5, 0.5, color="#ebfbee", zorder=0)
    for y in (-1, 1):
        ax.axhline(y * 0.5, color="#2f9e44", lw=0.8, ls=":")
    ax.axhline(-1, color="grey", lw=0.8)
    ax.text(dt.date(2026, 4, 22), -0.95, "one whole day: the window sits on the "
            "previous day's bar", fontsize=8, color="grey", va="bottom")
    ax.set_ylabel("window centre − bar centre (days)")
    ax.set_title("Each window's offset from the bar it is meant to read "
                 "(green: within half a day)", fontsize=10)
    ax.legend(frameon=False, fontsize=8, loc="lower right")
    ax.spines[["top", "right"]].set_visible(False)
    # A close-up in early May on 087: both readers' windows over the bars.
    im, cal, dates, ours, theirs, w = insets[87]
    ax2 = bottom.subplots()
    k = dates.index(dt.date(2026, 5, 12))
    x0, x1 = int(ours[k - 3] - cal.day_px / 2), int(ours[k + 3] + cal.day_px / 2)
    y1 = cal.panel.bottom + 1
    y0 = y1 - 60
    H = y1 - y0
    ax2.imshow(im[y0:y1, x0:x1], interpolation="nearest", aspect="auto",
               extent=(x0 - 0.5, x1 - 0.5, H - 0.5, -0.5))
    hw = 0.45 * w["ppd"]
    for j in range(k - 3, k + 4):
        shade = 0.55 if j % 2 else 1.0
        for cx, col, yy in ((ours[j], "#1c7ed6", H + 1),
                            (theirs[j], "#e8590c", H + 9)):
            ax2.add_patch(Rectangle((cx - hw, yy), 2 * hw, 6, color=col,
                                    alpha=shade, clip_on=False))
        ax2.text(ours[j], -2, dates[j].strftime("%-d %b"), ha="center",
                 va="bottom", fontsize=9)
    ax2.text(x1 + 0.5, H + 4, "ours", va="center", fontsize=9, color="#1c7ed6")
    ax2.text(x1 + 0.5, H + 12, "upstream", va="center", fontsize=9,
             color="#e8590c")
    ax2.set_xlim(x0 - 0.5, x1 - 0.5)
    ax2.set_ylim(H + 16, -0.5)
    ax2.set_axis_off()
    ax2.set_title("087, early May: our windows (blue) sit on the bars; "
                  "upstream's (orange) sit most of a bar to the left", fontsize=10, pad=24)
    fig.suptitle("Placing the days: a pitch rounded to a whole pixel per week "
                 "drifts a day across the chart", fontsize=13, fontweight="bold")
    out = OUT / "fig2c_day_placement.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out


@dataclass(frozen=True)
class Fit:
    obj: np.ndarray        # cost of every (alive, dead) hypothesis
    best: tuple[int, int]
    c: float               # pixels per case
    x0: int                # the slot's interior columns
    x1: int
    bottom: int            # the baseline row


def our_objective(im: np.ndarray, sitrep: int) -> Fit:
    """Reader one's cost lattice for the 25 July bar, restated from
    `readers.fit_bar` so the whole surface can be drawn; `check` below
    asserts its argmin is the reader's answer."""
    path, _ = load(sitrep)
    f = im.astype(float)
    cal = refine_scale(f, calibrate(f))
    slot = slot_dates(cal, load_anchors()[path.stem.rsplit("-", 1)[1]]).index(BAR)
    p, c, pal = cal.panel, cal.px_per_case, cal.palette
    centre = cal.x_phase + slot * cal.day_px
    half = max(1.0, 0.32 * cal.day_px)
    x0, x1 = int(np.ceil(centre - half)), int(np.floor(centre + half))
    strip = f[p.top + 1: p.bottom, x0:x1 + 1][::-1]
    P = [np.concatenate([[0.0], np.cumsum(s)]) for s in
         (_class_costs(strip, pal.alive), _class_costs(strip, pal.dead),
          _background_cost(strip, pal.band, False))]
    R = strip.shape[0]

    def rng(P, lo, hi):
        lo2 = np.minimum(lo + 1, hi)
        return P[np.maximum(hi - 1, lo2)] - P[lo2]

    ha = np.round(np.arange(int(R / c) + 1) * c).astype(int)
    h2 = np.minimum(ha[:, None] + ha[None, :], R)
    obj = (rng(P[0], np.zeros_like(ha), ha)[:, None]
           + rng(P[1], np.broadcast_to(ha[:, None], h2.shape), h2)
           + rng(P[2], h2, np.full_like(h2, R)))
    obj = np.where(ha[:, None] + ha[None, :] <= R + int(c), obj, np.inf)
    best = tuple(int(i) for i in np.unravel_index(np.argmin(obj), obj.shape))
    a, d, _, _ = fit_bar(f, cal, slot)
    assert best == (a, d), (sitrep, best, (a, d))
    return Fit(obj, best, c, x0, x1, p.bottom)


def figure_our_reader() -> Path:
    """Figure 3: reader one scores every (alive, dead) pair; the surface,
    its minimum, and where upstream's answer sits on it."""
    a, b, _, (r0, r1, c0, c1) = window()
    fig = plt.figure(figsize=(11, 9.5), layout="constrained")
    rows = fig.subfigures(3, 1, height_ratios=[1, 1, 0.7])
    fits = {}
    for sub, im, s in zip(rows[:2], (a, b), (87, 88)):
        fit = our_objective(im, s)
        fits[s] = fit
        ua, ud = upstream_read(s)[BAR.isoformat()]
        ba, bd = fit.best
        ax_img, ax_map = sub.subplots(1, 2, width_ratios=[1, 1.4])
        # The bar with the winning hypothesis drawn as its three row ranges.
        ax_img.imshow(im[r0:r1, c0:c1], interpolation="nearest")
        X = (fit.x0 - c0 - 0.5, fit.x1 - c0 + 0.5)
        for h, col in ((ba, "#1c7ed6"), (ba + bd, "#000000")):
            ax_img.hlines(fit.bottom - 1 - h * fit.c - r0, *X, color=col, lw=2.5)
        ax_img.hlines(fit.bottom - 1 - (ua + ud) * fit.c - r0, *X,
                      color="#e8590c", lw=2, ls="--")
        ax_img.set_xlim(-0.5, c1 - c0 - 0.5)
        ax_img.set_ylim(r1 - r0 - 0.5, -0.5)
        ax_img.set_title(f"{s:03d}: best fit {ba} + {bd} (solid); "
                         f"upstream's top (dashed)", fontsize=10)
        ax_img.set_axis_off()
        # The cost surface around the optimum, relative to its minimum.
        A = slice(max(0, ba - 15), ba + 16)
        D = slice(0, bd + 16)
        z = fit.obj[A, D] - fit.obj[ba, bd]
        m = ax_map.imshow(np.log10(1 + z), origin="lower", cmap="viridis",
                          aspect="auto", extent=(D.start - 0.5, D.stop - 0.5,
                                                 A.start - 0.5, A.stop - 0.5))
        ax_map.plot(bd, ba, "*", color="white", ms=14, mec="black")
        ax_map.plot(ud, ua, "X", color="#e8590c", ms=10, mec="black")
        ax_map.set_xlabel("dead cases hypothesised")
        ax_map.set_ylabel("alive cases hypothesised")
        ax_map.set_title(f"cost of every (alive, dead): minimum ★ {ba} + {bd}; "
                         f"upstream ✕ {ua} + {ud} costs "
                         f"{fit.obj[ua, ud] - fit.obj[ba, bd]:.0f} more",
                         fontsize=10)
        sub.colorbar(m, ax=ax_map, label="log10(1 + cost above minimum)")
    ax = rows[2].subplots()
    for s, col in ((87, "#1c7ed6"), (88, "#e8590c")):
        fit = fits[s]
        ba, bd = fit.best
        d = np.arange(0, bd + 16)
        ax.plot(d, fit.obj[ba, d] - fit.obj[ba, bd], "o-", ms=3, color=col,
                label=f"{s:03d}")
    ax.axvline(fits[87].best[1], color="grey", lw=0.8, ls=":")
    ax.set_xlabel("dead cases hypothesised, alive held at its best value")
    ax.set_ylabel("cost above minimum")
    ax.set_title("One slice through each surface: both encodings bottom out at "
                 "the same count", fontsize=10)
    ax.legend(frameon=False)
    fig.suptitle("Our first reader: score every whole-number bar, keep the best",
                 fontsize=13, fontweight="bold")
    out = OUT / "fig3_our_reader.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    print(figure_two_encodings().relative_to(ROOT))
    print(figure_upstream_reader().relative_to(ROOT))
    print(figure_upstream_window().relative_to(ROOT))
    print(figure_day_placement().relative_to(ROOT))
    print(figure_our_reader().relative_to(ROOT))


if __name__ == "__main__":
    main()
