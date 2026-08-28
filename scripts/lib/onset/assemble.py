"""Dates, deduplication and the reporting triangle.

The reader measures bars in slot space; this module gives slots their onset
dates from `registers/onset_axis_anchors.tsv` -- the one human input, a
printed tick label per distinct image -- and refuses any vintage whose
detected geometry cannot carry the register's dates. Then vintages that are
the same observation are collapsed: byte-identical reprints first, then
re-encodes and re-renders of one data snapshot, which read as equal within
the stated resolution and share a printed total. Two readings of one chart
are one observation of the epidemic.

The triangle is derived, never primary: increments between consecutive
surviving vintages, clipped to the intersection of the two axis extents --
dates one figure does not plot are unobserved, not zero -- and refusing to
span a vintage the gates did not accept.
"""

from __future__ import annotations

import csv
import datetime as dt
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .calibrate import Calibration, CalibrationError
from .readers import BarMeasure

REGISTERS = Path(__file__).resolve().parents[3] / "registers"
ANCHORS = REGISTERS / "onset_axis_anchors.tsv"

# Two vintages are one observation when at least this share of overlapping
# dates agree within one case and their printed totals match.
DEDUP_AGREE = 0.95


@dataclass(frozen=True)
class Anchor:
    sha12: str
    first_label: str
    first_date: dt.date
    last_label: str
    last_date: dt.date


def load_anchors() -> dict[str, Anchor]:
    out: dict[str, Anchor] = {}
    with open(ANCHORS, newline="") as f:
        rows = [r for r in csv.DictReader(
            (line for line in f if not line.startswith("#")),
            delimiter="\t")]
    for r in rows:
        out[r["sha12"]] = Anchor(
            sha12=r["sha12"], first_label=r["first_label"],
            first_date=dt.date.fromisoformat(r["first_date"]),
            last_label=r["last_label"],
            last_date=dt.date.fromisoformat(r["last_date"]))
    return out


def slot_dates(cal: Calibration, anchor: Anchor) -> list[dt.date]:
    """The onset date of every bar slot, anchored on the first printed tick.

    Validated against the geometry before use: the register's two labels
    must sit a whole number of weeks apart, that span must fit the detected
    tick count (renders may end with up to two unlabelled ticks past the
    last label), and the first tick must land on a bar slot. A register row
    that fails any of these refuses the vintage rather than dating it."""
    span = (anchor.last_date - anchor.first_date).days
    if span <= 0 or span % 7:
        raise CalibrationError(
            f"anchor labels {anchor.first_label!r}..{anchor.last_label!r} "
            f"are {span} days apart, not a whole number of weeks")
    weeks = span // 7
    n = len(cal.tick_xs)
    if not weeks + 1 <= n <= weeks + 3:
        raise CalibrationError(
            f"anchor span of {weeks} weeks does not fit {n} detected ticks")
    first_x = cal.tick_xs[0]
    offset = (cal.x_phase - first_x) / cal.day_px
    slot0 = anchor.first_date + dt.timedelta(days=round(offset))
    if abs(offset - round(offset)) > 0.3:
        raise CalibrationError(
            f"first tick sits {offset:.2f} slots from the bar grid")
    return [slot0 + dt.timedelta(days=k) for k in range(cal.n_slots)]


@dataclass(frozen=True)
class Vintage:
    """One distinct decoded image, read and dated."""
    sha256: str
    image_file: str
    sitreps: tuple[int, ...]          # every report that carried this image
    report_date: dt.date              # the earliest carrier's data date
    printed_n: int | None
    calibration: Calibration
    bars: tuple[BarMeasure, ...]
    dates: tuple[dt.date, ...]        # one per slot

    def series(self) -> dict[dt.date, tuple[int, int]]:
        return {d: (b.alive, b.dead) for d, b in zip(self.dates, self.bars)}

    @property
    def total(self) -> int:
        return sum(b.alive + b.dead for b in self.bars)


def value_dedup(vintages: list[Vintage]) -> list[tuple[Vintage, list[Vintage]]]:
    """Collapse consecutive vintages that are one data snapshot.

    Byte-level deduplication happened upstream (one Vintage per decoded
    image); this collapses re-encodes and re-renders: same printed total,
    and at least DEDUP_AGREE of overlapping dates within one case. The
    earliest survives -- with its full read, not an average -- and the
    collapsed ones are recorded against it. The 087/088 re-encode pair and
    the 098/099 re-render pair fall together here."""
    groups: list[tuple[Vintage, list[Vintage]]] = []
    for v in sorted(vintages, key=lambda v: v.report_date):
        if groups:
            head, members = groups[-1]
            if head.printed_n is not None and v.printed_n == head.printed_n:
                a, b = head.series(), v.series()
                common = sorted(set(a) & set(b))
                if common:
                    near = np.mean([
                        abs(sum(a[d]) - sum(b[d])) <= 1 for d in common])
                    if near >= DEDUP_AGREE:
                        members.append(v)
                        continue
        groups.append((v, []))
    return groups


def triangle(accepted: list[Vintage]) -> list[dict]:
    """Vintage-to-vintage increments on the intersection of axis extents.

    Only consecutive accepted vintages are differenced; every row carries
    both endpoints' identities so nothing downstream can span a refused
    vintage without noticing."""
    rows: list[dict] = []
    ordered = sorted(accepted, key=lambda v: v.report_date)
    for prev, cur in zip(ordered, ordered[1:]):
        a, b = prev.series(), cur.series()
        for d in sorted(set(a) & set(b)):
            (pa, pd_), (ca, cd) = a[d], b[d]
            rows.append({
                "onset_date": d.isoformat(),
                "report_date_from": prev.report_date.isoformat(),
                "report_date_to": cur.report_date.isoformat(),
                "sha12_from": prev.sha256[:12],
                "sha12_to": cur.sha256[:12],
                "delay_days": (cur.report_date - d).days,
                "d_alive": ca - pa,
                "d_dead": cd - pd_,
                "d_total": (ca + cd) - (pa + pd_),
            })
    return rows
