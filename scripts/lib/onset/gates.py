"""The vintage-level gates: pure functions over what the pipeline publishes.

Every gate takes read results, never images, so the whole history re-runs on
every build -- the process requirement the design note draws from upstream's
failure, where the decisive check existed, needed only the committed CSV,
and lived in a comment beside the one vintage it had caught.

Statuses compose: any refusal wins; else any caveat; else accepted. Each
verdict carries its reasons verbatim into `vintages.csv`.

One deliberate deviation from the design note, recorded here: G1 (render
fingerprint) flags instead of refusing on its own. The note calibrated G1
on a reader whose output tracked the render; this reader reconciles the
098 lossless outlier and the 455-px 102 render with their own printed
totals to within half a percent, so a render change alone is attention,
not exclusion. G1 still refuses in combination with a failed G2 or G3 --
a strange render that also misreconciles is exactly the 098 scenario the
note describes.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

import numpy as np

from .assemble import Vintage

# G2: the printed-total band. Undercounts to 2% are expected -- the axis
# stops short of the report date, so the most recent onsets are printed in
# n but not plotted -- while overcounts have no honest source, so the
# ceiling is tight.
G2_UNDER = 0.02
G2_OVER = 0.005

# G3: the stable region is settled onset dates; its total may crawl up and
# never down. Deviation from both neighbours, same direction, beyond
# 3 sigma of the local scatter refuses (floor of 15 cases, the requirement
# note's measured good-vintage scatter).
G3_MIN_AGE_DAYS = 28
G3_SIGMA = 3.0
G3_SCATTER_FLOOR = 15.0

# G-R: reader-two disagreement, over the bars where reader two spoke.
GR_DISAGREE_MAX = 0.25
GR_SILENT_MAX = 0.8


@dataclass(frozen=True)
class Verdict:
    status: str                 # accepted | accepted_with_caveat | refused
    reasons: tuple[str, ...]


def stable_total(v: Vintage) -> int:
    cutoff = v.report_date - dt.timedelta(days=G3_MIN_AGE_DAYS)
    return sum(b.alive + b.dead
               for b, d in zip(v.bars, v.dates) if d <= cutoff)


def _g1_render(v: Vintage, window: list[Vintage]) -> str | None:
    if not window:
        return None
    p = v.calibration.panel
    heights = [w.calibration.panel.height for w in window]
    med = float(np.median(heights))
    if abs(p.height - med) > 0.25 * med:
        return (f"G1: panel height {p.height}px against a trailing "
                f"median of {med:.0f}px")
    return None


def _g2_printed_n(v: Vintage) -> tuple[str | None, bool]:
    """(reason, is_refusal)."""
    if v.printed_n is None:
        return "G2: no printed total on this render; reconciliation " \
               "cannot run", False
    deficit = v.total - v.printed_n
    if deficit > G2_OVER * v.printed_n:
        return (f"G2: read {v.total} exceeds printed {v.printed_n} "
                f"by {deficit}", True)
    if deficit < -G2_UNDER * v.printed_n:
        return (f"G2: read {v.total} falls {-deficit} short of printed "
                f"{v.printed_n}", True)
    return None, False


def _g3_stable(idx: int, stables: list[int]) -> str | None:
    mine = stables[idx]
    neigh = [stables[i] for i in (idx - 1, idx + 1)
             if 0 <= i < len(stables)]
    if len(neigh) < 2:
        return None
    deltas = np.abs(np.diff(stables))
    scatter = max(float(np.median(deltas)), G3_SCATTER_FLOOR)
    lo = [mine - n for n in neigh]
    if all(d < -G3_SIGMA * scatter for d in lo) \
            or all(d > G3_SIGMA * scatter for d in lo):
        return (f"G3: stable-region total {mine} sits "
                f"{[int(d) for d in lo]} from both neighbours against a "
                f"scatter of {scatter:.0f}")
    return None


def _g5_alignment(v: Vintage, prev: Vintage | None) -> str | None:
    if prev is None:
        return None
    a, b = prev.series(), v.series()
    common = sorted(set(a) & set(b))
    if len(common) < 30:
        return None
    x = np.array([sum(a[d]) for d in common], dtype=float)
    y = np.array([sum(b[d]) for d in common], dtype=float)
    l1 = {s: float(np.abs(y[max(0, s):len(y) + min(0, s)]
                          - x[max(0, -s):len(x) - max(0, s)]).mean())
          for s in (-1, 0, 1)}
    if min(l1, key=l1.get) != 0:
        return (f"G5: alignment against {prev.report_date} minimises at "
                f"shift {min(l1, key=l1.get)} "
                f"(L1 {l1[-1]:.1f}/{l1[0]:.1f}/{l1[1]:.1f})")
    return None


def _gr_readers(v: Vintage) -> tuple[str | None, bool]:
    spoke = [b for b in v.bars if b.edge_alive is not None]
    if len(spoke) < 0.2 * len(v.bars):
        return ("G-R: the outline reader measured "
                f"{len(spoke)}/{len(v.bars)} bars; a single-reader "
                "vintage", False)
    dis = [b for b in spoke if not b.reader_agreement]
    frac = len(dis) / len(spoke)
    if frac > GR_DISAGREE_MAX:
        return (f"G-R: readers disagree on {len(dis)}/{len(spoke)} "
                "measured bars", True)
    return None, False


def judge(vintages: list[Vintage]) -> dict[str, Verdict]:
    """Verdicts for a report-date-ordered list of deduplicated vintages."""
    ordered = sorted(vintages, key=lambda v: v.report_date)
    stables = [stable_total(v) for v in ordered]
    out: dict[str, Verdict] = {}
    for i, v in enumerate(ordered):
        refusals: list[str] = []
        caveats: list[str] = []
        g1 = _g1_render(v, ordered[max(0, i - 5):i])
        g2, g2_refuses = _g2_printed_n(v)
        g3 = _g3_stable(i, stables)
        g5 = _g5_alignment(v, ordered[i - 1] if i else None)
        gr, gr_refuses = _gr_readers(v)
        if g2 and g2_refuses:
            refusals.append(g2)
        elif g2:
            caveats.append(g2)
        if g3:
            refusals.append(g3)
        if g5:
            refusals.append(g5)
        if gr and gr_refuses:
            refusals.append(gr)
        elif gr:
            caveats.append(gr)
        if g1 and refusals:
            refusals.append(g1)
        elif g1:
            caveats.append(g1)
        if refusals:
            out[v.sha256] = Verdict("refused", tuple(refusals + caveats))
        elif caveats:
            out[v.sha256] = Verdict("accepted_with_caveat", tuple(caveats))
        else:
            out[v.sha256] = Verdict("accepted", ())
    return out
