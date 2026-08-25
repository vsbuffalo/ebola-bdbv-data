"""The EDA figures, each a pure function of declared inputs.

ONE DRAWING FUNCTION PER FIGURE, and a registry mapping name -> function, so the
Makefile and any document share one source of truth about which figures exist.
Every figure is a build target; nothing here is run ad hoc.

WHAT THE FIGURES ARGUE
`availability` answers: which quantities exist, at what geographic level, over
which spans -- and through which route each report was read. The point it must
carry is that coverage is not a rectangle: streams start and stop, the zone
table appears on 1 June and disappears for the 084-086 vintage, the daily
ascertainment split begins 13 July, and three reports print their data only as
prose. The reader should leave knowing what the dataset can and cannot say
before ever seeing a count.

`province_series` answers: what do the extracted cumulative series actually look
like, per province -- with the zone-DERIVED sums as the line (they are the
trunk) and the printed provincial-summary values overlaid as open rings. Where
ring and line coincide the two routes agree; a visible gap IS a finding, and the
known ones are in the exception register.

`streams_detail` and `national_detail` are two halves of what was one figure.
The per-province flows and the four series the source prints only for the
country answer different questions and neither was readable at the aspect the
concatenation forced. They share one calendar, taken from the report index
rather than from either figure's own data, so a reader can still hold them side
by side.

`care_ledger` answers: can the treatment-centre ledger the reports state in
WORDS be believed, and what does it say. Its leading panel is the argument
rather than the payload -- two readers in this repository take the isolation
census off different parts of the same page and agree -- because everything
below it depends on that, and because the front-page tile stops printing the
confirmed half of the census partway through the archive while the prose does
not.

`outcomes` answers: of everyone ever confirmed, where is the record of what
happened to them. It is the same four published counts a reader could add up
by hand -- the case total, the death total, the cumulative recoveries and the
isolation census -- arranged so that what NONE of them holds is the visible
band. The point it must carry is that the residual is a count of people rather
than a discrepancy between estimates, which is true only because the
decomposition closes against the published case total exactly. Its second
requirement is negative: the isolation census stops partway along, and the
figure may not draw that as the ward emptying, nor stop there as though the
residual stopped growing too.

A FIGURE MAY NOT STATE A NUMBER IT DID NOT COMPUTE. Every count `care_ledger`
asserts in words comes from one of the small pure functions above its drawing
code, and each of those is pinned by a test, so the claim in the caption and
the claim in the test suite cannot drift apart.

AND A COMMITTED FIGURE MAY NOT SHIP WITHOUT A CAPTION. `docs/figures/README.md`
holds one section per figure in `docs/figures/`, naming what it shows and the
caveats that travel with it wherever it is used; a test fails if a committed
figure has no section, or a section names no figure. What belongs there rather
than on the figure is anything a reader can consult at leisure -- the limits on
what a band licenses, the causes of a break, why one stretch of a series is not
comparable with another. What stays on the figure is only what would make it
MISLEAD if removed.

COLOUR
Provinces are identities, so they take a fixed categorical assignment in
population order -- the Okabe-Ito palette, validated for colour-vision
deficiency (worst adjacent pair dE 7.6, which is legal only with a secondary
encoding: every line is therefore direct-labelled at its end). Geographic level
is ORDINAL (zone is finer than province is finer than national), so it takes a
single-hue sequential treatment, dark to light, never three unrelated hues.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import sys
import textwrap
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import polars as pl
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from matplotlib.ticker import MaxNLocator, MultipleLocator

#: Fixed identity -> colour, in outbreak-size order. Colour follows the
#: province, never its rank in any particular chart.
PROVINCE_COLOR = {
    "Ituri": "#0072B2",
    "Nord-Kivu": "#D55E00",
    "Haut-Uélé": "#009E73",
    "Tshopo": "#CC79A7",
    "Sud-Kivu": "#56B4E9",
    "Bas-Uélé": "#E69F00",
}

#: Level is ordinal: one hue, finest darkest.
LEVEL_COLOR = {"zone": "#1a4f72", "province": "#4d94c4", "national": "#a8cbe0"}

GRID = dict(color="#dddddd", linewidth=0.6)

#: Inches reserved at the top of a figure for the left-aligned bold title and
#: the subtitle beneath it. Held in INCHES rather than as a figure fraction
#: because the figures that use it differ by a factor of three in height, and
#: one fraction cannot clear the same two lines of text on both.
HEADER_IN = 0.95


def _dates(col: pl.Series) -> list:
    return [mdates.datestr2num(d) for d in col.to_list()]


def _header(fig, title: str, subtitle: str, *, title_size: float = 12,
            sub_size: float = 8.5) -> None:
    """Left-aligned bold title with the subtitle as a second block beneath it,
    and the axes area constrained to end below both.

    `rect` IS (left, bottom, WIDTH, HEIGHT), not (left, bottom, right, top).
    Read as the latter, a call meaning "stop the axes at 0.96" asks instead for
    a top edge at bottom + 0.96, leaves the top unconstrained, and lets the
    topmost panel's ticks print through this band. Both coordinates below are
    therefore derived from the figure's own height in inches.
    """
    h = fig.get_figheight()
    fig.get_layout_engine().set(rect=(0, 0, 1, 1 - HEADER_IN / h))
    fig.suptitle(title, x=0.01, y=1 - 0.10 / h, ha="left", va="top",
                 fontsize=title_size, fontweight="bold")
    fig.text(0.01, 1 - 0.42 / h, subtitle, ha="left", va="top",
             fontsize=sub_size, color="#444444")


def _report_calendar(caveat: pl.DataFrame) -> tuple[float, float]:
    """The x limits every report-day figure shares: the span of the ARCHIVE,
    not of whichever series a panel happens to hold.

    The caveat file carries one row per report whether or not that report said
    anything, so it is the calendar itself. A stream that starts on 13 July
    must show the ten empty weeks before it, or its late start reads as a full
    history -- and two figures split apart from one must keep the same axis,
    or a reader comparing them silently compares different spans.
    """
    xs = _dates(caveat["date"])
    lo, hi = min(xs), max(xs)
    pad = 0.02 * (hi - lo)
    return lo - pad, hi + pad


def draw_availability(inputs: dict[str, Path], out: Path) -> None:
    zone = pl.read_csv(inputs["zone_table"], infer_schema_length=None)
    status = pl.read_csv(inputs["zone_status"], infer_schema_length=None)
    summary = pl.read_csv(inputs["summary"], infer_schema_length=None)
    prose = pl.read_csv(inputs["prose"], infer_schema_length=None)

    quantities = [
        ("cum_cases", "confirmed cases (cumulative)"),
        ("cum_deaths", "confirmed deaths (cumulative)"),
        ("new_cases", "new cases (24 h)"),
        ("deaths_community", "community deaths, swab-confirmed (24 h)"),
        ("deaths_treatment_centre", "deaths in treatment centres (24 h)"),
        ("suspected", "suspected cases"),
        ("suspected_deaths", "suspected deaths"),
        ("contacts", "contacts listed"),
    ]

    fig, (ax, cal) = plt.subplots(
        2, 1, figsize=(11, 6.8), height_ratios=[len(quantities), 3.2],
        sharex=True, constrained_layout=True)

    # Top: one row per quantity; a tick per report, coloured by the FINEST
    # geographic level at which that report states the quantity.
    for yi, (col, label) in enumerate(reversed(quantities)):
        for level in ("national", "province", "zone"):   # coarse under fine
            sub = (zone.filter((pl.col("level") == level)
                               & pl.col(col).is_not_null())
                   .select("date").unique())
            if level in ("province", "national"):
                extra = summary.filter((pl.col("level") == level)
                                       & pl.col(col).is_not_null()) \
                    if col in summary.columns else None
                if extra is not None and extra.height:
                    sub = pl.concat([sub, extra.select("date").unique()]).unique()
                if col == "cum_cases":
                    pr = prose.filter(pl.col("level") == level)
                    if pr.height:
                        sub = pl.concat([sub, pr.select("date").unique()]).unique()
            if sub.height:
                ax.scatter(_dates(sub["date"]), [yi] * sub.height, marker="|",
                           s=90, linewidths=1.6, color=LEVEL_COLOR[level],
                           zorder=3 if level == "zone" else 2)
        ax.text(-0.01, yi, label, transform=ax.get_yaxis_transform(),
                ha="right", va="center", fontsize=8.5)

    ax.set_yticks([])
    ax.set_ylim(-0.7, len(quantities) - 0.3)
    ax.set_title("What each report states, and at what geographic level",
                 loc="left", fontsize=11)
    for lv, c in LEVEL_COLOR.items():
        ax.scatter([], [], marker="|", s=90, linewidths=1.6, color=c,
                   label=f"{lv} level")
    ax.legend(loc="lower right", frameon=False, fontsize=8, ncol=3)
    ax.grid(axis="x", **GRID)

    # Bottom: the route each report was read through -- the layout eras.
    routes = [("zone_cumulative", "zone table (cumulative)"),
              ("zone_mixed", "zone table (mixed daily/cumulative)"),
              ("zone_early", "zone table (early layout)"),
              ("zone_daily", "zone table (daily flows only)"),
              ("summary_only", "provincial summary only"),
              ("prose", "prose sentence only")]
    zone_route = dict(zone.select("date", "table").unique().iter_rows())
    summary_dates = set(summary["date"].unique().to_list())
    prose_dates = set(prose["date"].unique().to_list())
    for date in sorted(set(status["date"].to_list())):
        r = zone_route.get(date)
        if r is None:
            r = "summary_only" if date in summary_dates else (
                "prose" if date in prose_dates else None)
        if r is None:
            continue
        yi = len(routes) - 1 - [k for k, _ in routes].index(r)
        cal.scatter([mdates.datestr2num(date)], [yi], marker="|", s=80,
                    linewidths=1.4, color="#444444")
    for yi, (_, label) in enumerate(reversed(routes)):
        cal.text(-0.01, yi, label, transform=cal.get_yaxis_transform(),
                 ha="right", va="center", fontsize=8.5)
    cal.set_yticks([])
    cal.set_ylim(-0.7, len(routes) - 0.3)
    cal.set_title("The route each report was read through", loc="left",
                  fontsize=10)
    cal.grid(axis="x", **GRID)
    cal.xaxis.set_major_formatter(mdates.DateFormatter("%b %-d"))

    for a in (ax, cal):
        for s in ("top", "right", "left"):
            a.spines[s].set_visible(False)

    fig.suptitle("2026 DRC Bundibugyo outbreak — what the situation reports "
                 "make available", x=0.01, ha="left", fontsize=12,
                 fontweight="bold")
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=160)
    plt.close(fig)


#: The released streams, grouped by quantity. WITHIN A GROUP THE NATIONAL ROW
#: SITS LAST, i.e. beneath its provinces, because it is their total: the eye
#: reads the parts and then the sum, the same order the page prints them.
#: The group name is carried by a bracket rather than repeated in every row
#: label. Stocks come last because they are instants, not flows.
RELEASE_GROUPS = [
    ("cases", [
        ("cases_daily_ituri", "Ituri"),
        ("cases_daily_nord_kivu", "Nord-Kivu"),
        ("cases_daily_haut_uele", "Haut-Uélé"),
        ("cases_daily_national", "national"),
    ]),
    ("deaths", [
        ("deaths_daily_ituri", "Ituri"),
        ("deaths_daily_nord_kivu", "Nord-Kivu"),
        ("deaths_daily_haut_uele", "Haut-Uélé"),
        ("deaths_daily_national", "national"),
    ]),
    ("community\ndeaths", [
        ("community_deaths_daily_ituri", "Ituri"),
        ("community_deaths_daily_nord_kivu", "Nord-Kivu"),
        ("community_deaths_daily_haut_uele", "Haut-Uélé"),
        ("community_deaths_daily_national", "national"),
    ]),
    ("laboratory", [
        ("lab_daily_ituri", "Ituri"),
        ("lab_daily_nord_kivu", "Nord-Kivu"),
        ("lab_daily_haut_uele", "Haut-Uélé"),
        ("lab_daily_national", "national"),
    ]),
    ("stocks", [
        ("patients_isolated", "in isolation"),
        ("patients_isolated_confirmed", "isolation, confirmed"),
        ("cumul_recovered", "recovered, cumul."),
    ]),
    # THE CONFIRMED CARE CENSUS, which is the one row of the care ledger that
    # belongs on this figure: it carries the confirmed isolation census past
    # 2 August, where the national `patients_isolated_confirmed` row above it
    # stops, and the two together are the argument for reading it at all. The
    # rest of the care ledger -- admissions, exits and their decomposition --
    # is published and documented but not drawn here, because thirty more
    # rows would make the grid unreadable and say nothing this one does not.
    ("care census\n(confirmed)", [
        ("care_census_confirmed_ituri", "Ituri"),
        ("care_census_confirmed_nord_kivu", "Nord-Kivu"),
        ("care_census_confirmed_haut_uele", "Haut-Uélé"),
        ("care_census_confirmed_national", "national"),
    ]),
]

#: Flattened, top to bottom -- the registry's dependency set is derived from
#: this, so the grouping above stays the single source of row order.
RELEASE_ROWS = [r for _, group in RELEASE_GROUPS for r in group]

#: What a published cell can be. Status, not identity, so these are a reserved
#: status ramp and every one is labelled in the legend -- never colour alone.
FLAG_COLOR = {
    "-": "#1a4f72",                       # clean
    "consolidating": "#E69F00",           # a backlog release
    "harmonisation": "#CC79A7",           # the source restating earlier days
    "harmonisation_undercount": "#B05A8A",
    "stale_distribution": "#D55E00",      # zone breakdown older than the total
}
FLAG_LABEL = {
    "-": "no caveat printed",
    "consolidating": "source calls recent data provisional",
    "harmonisation": "may be revised",
    "harmonisation_undercount": "source says too low",
    "stale_distribution": "zone breakdown out of date",
}

#: Extraction route -> the report layout it implies. A change here is a change
#: in the source's FORMAT, which is why the route is worth plotting: it is the
#: only record we keep of when INSP reformatted the bulletin.
ROUTE_LABEL = {
    "zone_early": "early zone table",
    "zone_cumulative": "zone table (cumulative)",
    "zone_mixed": "mixed daily/cumulative",
    "zone_daily": "daily flows only",
    "summary_only": "province table only, no zone table",
    "prose": "prose only",
    "none": "no route",
}


def _flag_of(row: dict) -> str:
    """The dominant flag on a stream row. A row can carry several, pipe
    separated; the first recognised one wins, so a cell is one colour."""
    raw = str(row.get("flags") or "-")
    for part in raw.split("|"):
        if part in FLAG_COLOR:
            return part
    return "-"


def draw_release_grid(inputs: dict[str, Path], out: Path) -> None:
    """One cell per (released stream x report day), at slide proportions.

    THIS IS THE FIGURE THAT SAYS WHAT WE ACTUALLY SHIP. `availability` shows
    what the SOURCE states; this shows what survives into the release, which
    is a different and smaller thing. Coverage is not a rectangle, and the
    holes are the argument: the laboratory rows stop where the paragraph stops
    naming provinces, and the two stock rows begin late because the early
    dashboard prints its tiles above their labels rather than below.

    ONE ROW PER STREAM, AT ONE RESOLUTION, over a chosen set: the daily
    companion of each incidence family, the national stocks, and the confirmed
    care census. The weekly files are the same quantities re-binned and would
    draw the same picture at a coarser pitch; the rest of the care ledger is
    published and documented in `data/build/streams/README.md` but not drawn,
    because thirty further rows would cost the grid its legibility. RELEASE
    GROUPS above is the list, and it is what a reader should be pointed at
    when they ask whether the release contains something not on this slide.

    Three annotation layers, all drawn from artefacts rather than typed in:
      * cell colour   -- the row's own `flags`, so backlog and harmonisation
                         days are visible rather than averaged away;
      * era bands     -- the extraction route from `zone_table.table`, which
                         changes exactly when the bulletin is reformatted;
      * event ticks   -- the reconciliation exception register, i.e. the days
                         the page's own arithmetic does not close.
    """
    # A CELL IS AN OBSERVATION, NOT A ROW. The flow files carry a row on every
    # report day they span, holding `NA` where the source said nothing of that
    # quantity -- the row is there so that a model accumulating between
    # observations closes its interval on schedule, and painting it would
    # claim a datum the release does not contain. `n_report_days` is 0 on
    # exactly those rows. `NA` is also declared as the null token here for the
    # second half of the same trap: polars does not parse it as null by
    # default, so one hole turns a count column into a string column and a
    # plotting library draws the strings at the axis baseline.
    streams = {name: pl.read_csv(p, separator="\t", infer_schema_length=None,
                                 null_values="NA")
               for name, p in inputs.items() if name.startswith("stream_")}
    streams = {n: (d.filter(pl.col("n_report_days") > 0)
                   if "n_report_days" in d.columns else d)
               for n, d in streams.items()}
    zone = pl.read_csv(inputs["zone_table"], infer_schema_length=None)
    exc = pl.read_csv(inputs["exceptions"], separator="\t", comment_prefix="#",
                      infer_schema_length=None)

    rows = [(k, lab) for k, lab in RELEASE_ROWS if f"stream_{k}" in streams]
    all_dates = sorted({d for s in streams.values() for d in s["time"].to_list()})
    x = {d: i for i, d in enumerate(all_dates)}
    nx, ny = len(all_dates), len(rows)

    fig, (ax, era) = plt.subplots(
        2, 1, figsize=(13.333, 7.5), height_ratios=[ny, 2.4],
        constrained_layout=True)

    # --- the grid itself -------------------------------------------------
    # THE GROUND IS "NO OBSERVATION", so it must not extend past the rows that
    # could carry one. The axes is white and the grey is painted only over the
    # stream rows; the tick band above them is annotation, not a stream, and
    # colouring it grey would claim a missing observation where there is no
    # series to miss.
    ax.set_facecolor("#ffffff")
    ax.add_patch(plt.Rectangle((0, 0), nx, ny, facecolor="#f7f7f7",
                               edgecolor="none", zorder=0))
    seen_flags: set[str] = set()
    for yi, (key, label) in enumerate(reversed(rows)):
        df = streams[f"stream_{key}"]
        has_flags = "flags" in df.columns
        for r in df.iter_rows(named=True):
            xi = x.get(r["time"])
            if xi is None:
                continue
            flag = _flag_of(r) if has_flags else "-"
            seen_flags.add(flag)
            ax.add_patch(plt.Rectangle(
                (xi + 0.12, yi + 0.12), 0.76, 0.76,
                facecolor=FLAG_COLOR[flag], edgecolor="none"))
        ax.text(-0.006, yi + 0.5, label, transform=ax.get_yaxis_transform(),
                ha="right", va="center", fontsize=8.5)

    # --- group brackets ---------------------------------------------------
    # A bracket per quantity, spanning its rows, so the group name is stated
    # once instead of prefixing every label. Drawn in (axes-x, data-y) so the
    # bracket keeps its distance from the axis whatever the label widths.
    tr = ax.get_yaxis_transform()
    present = [k for k, _ in rows]
    i = 0
    for gname, group in RELEASE_GROUPS:
        members = [k for k, _ in group if k in present]
        if not members:
            continue
        i0, i1 = i, i + len(members)
        i = i1
        y0, y1 = ny - i1, ny - i0          # rows are drawn top-down from ny
        xb, tick = -0.175, 0.012
        ax.plot([xb, xb], [y0 + 0.15, y1 - 0.15], transform=tr,
                color="#888888", linewidth=1.0, clip_on=False)
        for yy in (y0 + 0.15, y1 - 0.15):
            ax.plot([xb, xb + tick], [yy, yy], transform=tr,
                    color="#888888", linewidth=1.0, clip_on=False)
        ax.text(xb - 0.010, (y0 + y1) / 2, gname, transform=tr,
                ha="right", va="center", fontsize=10, color="#222222")
        # a hairline between groups, so the bands read as families
        if i1 < ny:
            ax.axhline(y0, color="#ffffff", linewidth=2.4)

    ax.set_xlim(0, nx)
    # HEADROOM FOR THE EVENT TICKS, INSIDE THE AXES. They sit above the top
    # row, and drawing them outside the axes (`clip_on=False`) put them in
    # whatever space the figure had left -- which is the subtitle's. Reserving
    # the band in DATA coordinates makes the collision impossible instead of
    # merely unlikely, and keeps the tick row anchored to the grid it annotates
    # rather than to the canvas.
    ax.set_ylim(0, ny + 1.15)
    ax.set_yticks([])
    ax.set_xticks([])
    for s in ax.spines.values():
        s.set_visible(False)

    # --- reconciliation events, with the size of the disagreement --------
    # The marker says a day's arithmetic does not close; the number says by
    # how much, because "does not close" covers both a single miscounted case
    # and the 66 Ituri cases of 12 July. Where a date carries several
    # residuals the largest is shown, so it bounds the rest. One row, each
    # label centred on its own marker.
    worst: dict[str, int] = {}
    for r in exc.iter_rows(named=True):
        d, g = r["date"], int(r["expected_gap"])
        if abs(g) > abs(worst.get(d, 0)):
            worst[d] = g
    hi = ny + 0.42
    for d in sorted(k for k in worst if k in x):
        cx = x[d] + 0.5
        ax.plot([cx], [hi], marker="v", markersize=5,
                color="#D55E00", clip_on=False)
        ax.text(cx, hi + 0.30, f"{worst[d]:+d}", ha="center", va="bottom",
                fontsize=7.5, color="#D55E00", clip_on=False)

    # --- format eras, from the route each report was read through --------
    # A report with no zone table is not a gap in the format record: it IS a
    # format, and one worth seeing, so it gets its own band rather than
    # breaking the span either side of it into two.
    # A report with no health-zone table still HAS a format and still yields
    # observations -- sitreps 084-086 (6-8 Aug) dropped the zone table but
    # kept the provincial summary, and the late-May reports carried only
    # prose. Showing those as an unlabelled grey made the band look like a
    # gap in the record when it is a change of route, which is exactly the
    # thing this band exists to show. Every day therefore resolves to a named
    # route, in the order the extractor tries them.
    summary = pl.read_csv(inputs["summary"], infer_schema_length=None)
    prose = pl.read_csv(inputs["prose"], infer_schema_length=None)
    summary_dates = set(summary["date"].to_list())
    prose_dates = set(prose["date"].to_list())
    route = {d: r for d, r in zone.select("date", "table").unique().iter_rows()}
    for d in all_dates:
        if route.get(d):
            continue
        route[d] = ("summary_only" if d in summary_dates
                    else "prose" if d in prose_dates else "none")
    era.set_xlim(0, nx)
    era.set_ylim(0, 1)
    spans, start, cur = [], 0, route.get(all_dates[0], "none")
    for i, d in enumerate(all_dates):
        r = route.get(d, "none")
        if r != cur:
            spans.append((start, i, cur))
            start, cur = i, r
    spans.append((start, nx, cur))

    era_fill = {"zone_early": "#c9dcea", "zone_cumulative": "#7fb2d4",
                "zone_mixed": "#4d94c4", "zone_daily": "#2c6e9e",
                "summary_only": "#E8B96A", "prose": "#C98A4B",
                "none": "#e4e4e4"}
    widest: dict[str, tuple[int, int]] = {}
    for a, b, r in spans:
        if r not in widest or (b - a) > (widest[r][1] - widest[r][0]):
            widest[r] = (a, b)
    for a, b, r in spans:
        era.add_patch(plt.Rectangle((a, 0.62), b - a, 0.34,
                                    facecolor=era_fill.get(r, "#e4e4e4"),
                                    edgecolor="white", linewidth=1.0))
        lab = ROUTE_LABEL.get(r, "no zone table")
        # only the widest run of each route is labelled: a format that resumes
        # after an interruption is the same format, not a new one
    era.text(-0.006, 0.79, "report format", transform=era.get_yaxis_transform(),
             ha="right", va="center", fontsize=8.5)

    # month ticks, under the era band and clear of the legend
    month_at: dict[str, int] = {}
    for i, d in enumerate(all_dates):
        month_at.setdefault(d[:7], i)
    for m, i in month_at.items():
        era.axvline(i, ymin=0.48, ymax=0.62, color="#999999", linewidth=0.8)
        era.text(i + 0.5, 0.40,
                 mdates.num2date(mdates.datestr2num(m + "-01")).strftime("%B %Y"),
                 ha="left", va="center", fontsize=9, color="#333333")
    era.set_xticks([])
    era.set_yticks([])
    for s in era.spines.values():
        s.set_visible(False)

    # --- legend, along the very bottom so nothing collides ---------------
    handles = [plt.Rectangle((0, 0), 1, 1, facecolor=FLAG_COLOR[f],
                             label=FLAG_LABEL[f])
               for f in FLAG_COLOR if f in seen_flags]
    handles.append(plt.Rectangle((0, 0), 1, 1, facecolor="#f7f7f7",
                                 edgecolor="#cccccc", label="no observation"))
    handles.append(plt.Line2D([], [], linestyle="none", marker="v",
                              color="#D55E00", markersize=6,
                              label="the page's own arithmetic does not close"))
    # Two rows: seven entries in one row overflows a 13.3 in canvas.
    # constrained_layout does not reserve space for a figure legend, so the
    # band is carved out of the layout rect explicitly or the second row
    # falls off the page.
    # `rect` HERE IS (left, bottom, WIDTH, HEIGHT), not (left, bottom, right,
    # top). Read as the latter, `(0, 0.105, 1, 0.90)` asks for a top edge at
    # 0.105 + 0.90 = 1.005 -- so the bottom band was reserved as intended and
    # the TOP was never constrained at all. That is why the event ticks sat
    # hard against the top of the canvas and printed through anything placed
    # up there. Height is the figure fraction between the legend band and the
    # header: 0.105 + 0.79 puts the axes top at 0.895, clear of the subtitle.
    fig.get_layout_engine().set(rect=(0, 0.105, 1, 0.79))
    leg1 = fig.legend(handles=handles, loc="lower left", ncol=2,
                      frameon=False, fontsize=8.5, handlelength=1.1,
                      handleheight=1.1, columnspacing=1.6, labelspacing=0.6,
                      bbox_to_anchor=(0.055, -0.012),
                      title="Observation status")
    leg1.get_title().set_fontsize(8.5)
    leg1.get_title().set_ha("left")

    # The format band is a SECOND encoding -- which table the report printed,
    # not what the observation is like -- so it gets its own key. Every route
    # that occurs is listed, which is why no stretch of the band is an
    # unexplained grey: a report with no zone table still has a format.
    order = ["zone_early", "zone_cumulative", "zone_mixed", "zone_daily",
             "summary_only", "prose", "none"]
    seen_routes = {r for _, _, r in spans}
    rhandles = [plt.Rectangle((0, 0), 1, 1, facecolor=era_fill[r],
                              edgecolor="#ffffff",
                              label=ROUTE_LABEL.get(r, r))
                for r in order if r in seen_routes]
    leg2 = fig.legend(handles=rhandles, loc="lower right", ncol=2,
                      frameon=False, fontsize=8.5, handlelength=1.1,
                      handleheight=1.1, columnspacing=1.6, labelspacing=0.6,
                      bbox_to_anchor=(0.985, -0.012),
                      title="Report table type")
    leg2.get_title().set_fontsize(8.5)
    fig.add_artist(leg1)

    # Title and subtitle are both FIGURE-level and left-aligned to the same
    # x, so the subtitle reads as the title's second line. As an axes title it
    # started at the grid's left edge instead, which put it under the event
    # ticks rather than under the title.
    fig.suptitle("What the release contains, report by report",
                 x=0.008, y=0.988, ha="left", fontsize=14, fontweight="bold")
    # The span is bolded with mathtext, the same way the sibling slide figure
    # does it. That works here because the dates are set as `19 May to 22 Aug
    # 2026` rather than ISO: in math mode a hyphen is a BINARY MINUS, so
    # `2026-05-19` would come out spaced like arithmetic. Spaces inside the
    # math run have to be escaped or they are dropped.
    d0 = dt.date.fromisoformat(all_dates[0])
    d1 = dt.date.fromisoformat(all_dates[-1])
    span = f"{d0:%b\\ %-d}\\ to\\ {d1:%b\\ %-d,%Y}"
    # `streams drawn`, NOT `published streams`. The release ships more files
    # than this grid has rows -- the weekly re-binnings of these same
    # quantities, and the rest of the care ledger -- and a subtitle that
    # counted rows while calling them the release would understate it.
    fig.text(0.008, 0.951,
             f"{nx} report-days carrying at least one observation \u00b7 "
             f"{ny} streams drawn \u00b7 $\\bf{{{span}}}$",
             ha="left", va="top", fontsize=11, color="#555555")
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=200)
    plt.close(fig)


#: Lower segment height / upper segment height in the broken axes below. The
#: upper segment only has to hold the top of one bar, and giving it more than
#: that steals room from the curve.
BREAK_RATIO = 11


def _nice_step(top: float) -> float:
    """A round gridline interval for a 0..top axis, chosen once and used by
    BOTH segments of a broken axis so their grids share a spacing."""
    ticks = MaxNLocator(nbins=7, steps=[1, 2, 2.5, 5, 10]).tick_values(0, top)
    return ticks[1] - ticks[0]


def draw_epi_curve(inputs: dict[str, Path], out: Path) -> None:
    """The outbreak itself: confirmed cases and deaths per day, nationally.

    THE OPENING FIGURE. Everything else in this repo argues about how the
    numbers were obtained; this one shows what they say.

    Three decisions carry the honesty of it.

    A BAR'S HEIGHT IS A DAILY RATE AND ITS WIDTH ITS OWN WINDOW, so its area
    is the count. Both of these streams are built by DIFFERENCING a published
    cumulative, which absorbs days when no report appeared -- so here
    `days_covered` genuinely is the span the count covers and dividing by it
    is right. (It would be wrong for the flow-summed streams, where the same
    column means the gap since the last observation. The column carries two
    meanings across this repo; see notes/2026-08-22-pipeline-audit.md.)

    A SPIKE IS NOT ALWAYS AN EPIDEMIC. Bars are coloured by the source's own
    caveat for that report, in the same vocabulary the release-grid figure
    uses, because the tallest bar in the case series -- 369 confirmations on
    22 July against a norm near 80 -- is a backlog release, not a day when
    369 people were found.

    AND A CUT AXIS MUST LOOK CUT. That release is twice the height of any
    real day, so letting it set the scale flattens the curve this figure
    exists to show. Each panel is therefore a BROKEN axis: a narrow upper
    segment carrying the outlier's top, a full lower segment for everything
    else, and diagonal break marks across the join. Simply truncating a bar
    and hoping a label explains it invites the eye to compare heights that
    are not on one scale.
    """
    cases = pl.read_csv(inputs["cases"], separator="\t", try_parse_dates=True)
    deaths = pl.read_csv(inputs["deaths"], separator="\t", try_parse_dates=True)

    fig = plt.figure(figsize=(13.333, 7.5), constrained_layout=True)
    outer = fig.add_gridspec(2, 1, height_ratios=[1.25, 1], hspace=0.08)
    gc = outer[0].subgridspec(2, 1, height_ratios=[1, BREAK_RATIO], hspace=0.012)
    gd = outer[1].subgridspec(2, 1, height_ratios=[1, BREAK_RATIO], hspace=0.012)
    c_hi, c_lo = fig.add_subplot(gc[0]), fig.add_subplot(gc[1])
    d_hi, d_lo = fig.add_subplot(gd[0]), fig.add_subplot(gd[1])

    seen: set[str] = set()

    def panel(hi, lo, df, col, label):
        span = [max(1, int(v or 1)) for v in df["days_covered"].to_list()]
        edge = [mdates.date2num(x) + 0.5 for x in df["time"].to_list()]
        xs = [e - w / 2 for e, w in zip(edge, span)]
        ys = [c / w for c, w in zip(df[col].to_list(), span)]
        # The axis top sits half a gridline step above the last tick: it
        # keeps the headroom tight AND guarantees the break mark never lands
        # on a tick label, which is what happened when the top was a bare
        # multiple of the data range.
        bulk = max(sorted(ys)[:-1])             # ignore the single outlier
        step = _nice_step(bulk * 1.12)
        cut = (math.ceil(bulk / step) + 0.5) * step
        peak = max(ys)

        for ax in (hi, lo):
            for x, y, w, r in zip(xs, ys, span, df.iter_rows(named=True)):
                f = _flag_of(r)
                seen.add(f)
                ax.bar(x, y, width=w * 0.9, color=FLAG_COLOR[f], zorder=2)
            ax.set_axisbelow(True)
            ax.grid(axis="y", **GRID)
            for sp in ("top", "right"):
                ax.spines[sp].set_visible(False)
            ax.spines["left"].set_color("#999999")

        # THE TWO SEGMENTS MUST SHARE A SCALE. A broken axis whose halves
        # run at different units-per-pixel is a second, hidden distortion on
        # top of the break itself: gridlines drawn at one interval would sit
        # at two different spacings, and the eye reads spacing as magnitude.
        # The upper segment is 1/BREAK_RATIO of the lower's height, so it
        # gets 1/BREAK_RATIO of its data range, and one tick interval is then
        # the same distance in both.
        hi_range = cut / BREAK_RATIO
        lo.set_ylim(0, cut)
        hi.set_ylim(peak - hi_range * 0.62, peak + hi_range * 0.38)
        for ax in (hi, lo):
            ax.yaxis.set_major_locator(MultipleLocator(step))
        # The peak's true value goes on the bar, not on a tick: the tick
        # positions now belong to the shared grid.
        hi.annotate(f"{int(round(peak * span[ys.index(peak)]))}",
                    xy=(xs[ys.index(peak)], peak), xytext=(0, 4),
                    textcoords="offset points", ha="center", va="bottom",
                    fontsize=8.5, fontweight="bold", color="#7a5200",
                    annotation_clip=False)
        hi.tick_params(labelbottom=False, length=0)
        lo.spines["bottom"].set_color("#999999")
        hi.spines["bottom"].set_visible(False)
        hi.spines["left"].set_color("#999999")
        lo.set_ylabel(label, fontsize=10)
        lo.yaxis.set_label_coords(-0.055, 0.62)

        # diagonal break marks, drawn in axes coordinates on both edges
        # The break symbol is a PAIR of parallel diagonals, one on each side
        # of the gap. They only read as one symbol if the gap between them is
        # about as tall as a diagonal is wide, which is what the tight hspace
        # above is for.
        kw = dict(marker=[(-1, -0.6), (1, 0.6)], markersize=6,
                  linestyle="none", color="#666666", mec="#666666", mew=1.0,
                  clip_on=False)
        hi.plot([0, 1], [0, 0], transform=hi.transAxes, **kw)
        lo.plot([0, 1], [1, 1], transform=lo.transAxes, **kw)
        return xs, ys, cut

    xs, ys, cut = panel(c_hi, c_lo, cases, "cases_national",
                        "confirmed cases per day")
    panel(d_hi, d_lo, deaths, "deaths_national", "confirmed deaths per day")

    peak = max(range(len(ys)), key=lambda i: ys[i])
    c_lo.annotate("one report released a backlog of earlier\n"
                  "confirmations — not a day's incidence",
                  xy=(xs[peak] - 0.6, cut * 0.86), xytext=(-150, 10),
                  textcoords="offset points", ha="left", va="center",
                  fontsize=9, color="#7a5200",
                  arrowprops=dict(arrowstyle="->", color="#b98b00",
                                  linewidth=1.1, shrinkA=3, shrinkB=3))

    for ax in (c_hi, c_lo, d_hi):
        ax.tick_params(labelbottom=False)
    for ax in (c_hi, c_lo, d_hi, d_lo):
        ax.set_xlim(min(xs) - 2, max(xs) + 2)
    d_lo.xaxis.set_major_locator(mdates.WeekdayLocator(byweekday=mdates.MO,
                                                       interval=2))
    d_lo.xaxis.set_major_formatter(mdates.DateFormatter("%b %-d"))

    handles = [plt.Rectangle((0, 0), 1, 1, facecolor=FLAG_COLOR[f],
                             label=FLAG_LABEL[f])
               for f in FLAG_COLOR if f in seen]

    tot_c = int(cases["cases_national"].sum())
    tot_d = int(deaths["deaths_national"].sum())
    # Same header block as the ascertainment figure: headline, subtitle just
    # beneath it, and the legend floating across the top axes boundary so it
    # occupies space that is otherwise empty in both the header and the panel.
    fig.get_layout_engine().set(rect=(0, 0, 1, 0.895))
    fig.suptitle("The 2026 Bundibugyo outbreak, as the situation reports "
                 "record it", x=0.006, y=0.988, ha="left", va="top",
                 fontsize=15, fontweight="bold")
    fig.text(0.006, 0.938,
             f"{tot_c:,} confirmed cases and {tot_d:,} confirmed deaths · "
             f"$\\bf{{{cases['time'].min():%b\\ %-d}\\ to\\ "
             f"{cases['time'].max():%b\\ %-d,%Y}}}$",
             ha="left", va="top", fontsize=11, color="#333333")
    # constrained_layout owns inter-axes spacing and overrides a subgridspec
    # hspace, so the two halves of each break are pinned by hand once it has
    # run: freeze the engine, then drop each upper segment to sit a hair above
    # its lower one. The pair of diagonals only reads as ONE break symbol when
    # the gap between them is about as tall as a diagonal is wide.
    fig.canvas.draw()
    fig.set_layout_engine("none")
    GAP = 0.006                      # figure fraction
    for hi, lo in ((c_hi, c_lo), (d_hi, d_lo)):
        lp, hp = lo.get_position(), hi.get_position()
        lo.set_position([lp.x0, lp.y0, lp.width, hp.y0 - GAP - lp.y0])

    # The legend straddles the real top edge of the plot area -- computed
    # after the pinning above, not guessed -- so it fills space that is empty
    # in both the header and the panel, as in the ascertainment figure.
    leg = fig.legend(handles=handles, loc="center right",
                     bbox_to_anchor=(0.995, c_hi.get_position().y1),
                     bbox_transform=fig.transFigure, fontsize=9.5,
                     frameon=True, framealpha=0.95, facecolor="white",
                     edgecolor="#8a8a8a", borderpad=0.6, ncol=1,
                     labelspacing=0.5, handlelength=1.3)
    leg.get_frame().set_linewidth(0.7)

    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=200)
    plt.close(fig)


def draw_validation(inputs: dict[str, Path], out: Path) -> None:
    """Three independent readings of the same PDFs, and what each one covers.

    THE VALIDATION SLIDE, and it has to make two claims that pull in opposite
    directions without letting either one swallow the other.

    THE AGREEMENT CLAIM. Three lineages read the same pages: ours, the
    epiforecasts hand transcription, and INRB-UMIE's. Where they overlap they
    agree — 71 of 71 national figures against the scan, 2,135 of 2,144
    zone-day case values against INRB. Drawn as one curve with the others
    over it, because the point is that you cannot see three lines.

    THE LIMIT OF THAT CLAIM, which the figure must not let a viewer forget:
    agreement between two readings of one document is evidence about
    TRANSCRIPTION, never about whether the document is right. All three
    inherit whatever the source got wrong. That is why the caption says so
    rather than leaving "validated" to be read as "correct".

    THE COVERAGE CLAIM. Agreement is cheap where lineages overlap; the
    overlap is the smaller part of the story. We hold 2,940 zone-days against
    INRB's 2,323 and run a week later, so the lower panel puts the extents
    side by side. A slide that showed only agreement would imply the lineages
    are interchangeable, and they are not.
    """
    zc = pl.read_csv(inputs["zone_comparison"], infer_schema_length=None)
    sc = pl.read_csv(inputs["scan"], infer_schema_length=None)
    zt = pl.read_csv(inputs["zone_table"], infer_schema_length=None)
    summ = pl.read_csv(inputs["summary"], infer_schema_length=None)
    meta = json.loads(Path(inputs["meta"]).read_text())

    fig = plt.figure(figsize=(13.333, 7.5), constrained_layout=True)
    gs = fig.add_gridspec(2, 1, height_ratios=[3.2, 1], hspace=0.05)
    ax, cov = fig.add_subplot(gs[0]), fig.add_subplot(gs[1])
    fig.get_layout_engine().set(rect=(0, 0, 1, 0.885))

    OURS, SCAN, INRB = "#0072B2", "#111111", "#D55E00"

    # OURS IS THE PRINTED NATIONAL CUMULATIVE, not a running sum of the daily
    # stream. Summing increments from zero starts the curve 51 cases low --
    # the total already standing when the daily series opens on 20 May -- and
    # would have shown us permanently below two lineages we in fact match.
    ours = (pl.concat([
        zt.filter(pl.col("level") == "national")
          .select("date", "cum_cases"),
        summ.filter(pl.col("level") == "national")
            .select("date", "cum_cases")])
        .drop_nulls("cum_cases")
        .group_by("date").agg(pl.col("cum_cases").max())
        .with_columns(pl.col("date").str.to_date()).sort("date"))
    t = [mdates.date2num(x) for x in ours["date"].to_list()]
    ax.plot(t, ours["cum_cases"].to_list(), color=OURS, linewidth=2.6,
            label="ours", zorder=2)

    s = sc.with_columns(pl.col("date").str.to_date()).sort("date")
    ax.scatter([mdates.date2num(x) for x in s["date"].to_list()],
               s["scan_cases"].to_list(), s=42, facecolor="none",
               edgecolor=SCAN, linewidths=1.3, zorder=3,
               label="epiforecasts hand transcription")

    inrb = (zc.with_columns(pl.col("date").str.to_date())
            .drop_nulls("inrb_cases").group_by("date")
            .agg(pl.col("inrb_cases").sum()).sort("date"))
    ax.plot([mdates.date2num(x) for x in inrb["date"].to_list()],
            inrb["inrb_cases"].to_list(), color=INRB, linewidth=1.6,
            linestyle=(0, (5, 3)), zorder=4, label="INRB-UMIE transcription")

    ax.set_ylabel("cumulative confirmed cases, national", fontsize=10)
    ax.set_axisbelow(True)
    ax.grid(axis="y", **GRID)
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    for sp in ("left", "bottom"):
        ax.spines[sp].set_color("#999999")
    ax.xaxis.set_major_locator(mdates.WeekdayLocator(byweekday=mdates.MO,
                                                     interval=2))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %-d"))

    sm, im = meta["scan"], meta["inrb"]
    ax.annotate(f"{sm['equal']} of {sm['compared']} national figures identical "
                f"to the hand transcription\n"
                f"{im['cases_equal']:,} of {im['cases_compared']:,} zone-day "
                f"case values identical to INRB",
                xy=(0.015, 0.965), xycoords="axes fraction", ha="left",
                va="top", fontsize=10.5, color="#333333")

    # --- coverage, the half of the story agreement cannot tell -------------
    ours_days = (zt.filter(pl.col("level") == "zone")
                 .with_columns(pl.col("date").str.to_date()))
    # THE INRB SIDE IS A PINNED SNAPSHOT, NOT INRB TODAY. external.lock fixes
    # their repository at one commit so the comparison is reproducible, which
    # means their extent here is bounded by when that pin was taken. Reporting
    # "we run later" without saying so compares our current data against their
    # stale checkout and calls the difference a coverage win. The pin date is
    # therefore on the label, and it is read from the lockfile rather than
    # typed, so it cannot drift from the checkout it describes.
    pin = "unknown"
    for line in Path(inputs["lock"]).read_text().splitlines():
        if line.startswith("BDBV2026-Data"):
            pin = line.split("\t")[-1].strip()
    rows = [
        ("ours", ours_days["date"].min(), ours_days["date"].max(),
         im["ours_zone_days"], OURS, "to " + f"{dt.date.fromisoformat(str(ours_days['date'].max())):%b %-d}"),
        ("INRB-UMIE", zc["date"].min(), im["inrb_last_date"],
         im["inrb_zone_days"], INRB,
         f"to {dt.date.fromisoformat(im['inrb_last_date']):%b %-d} "
         f"in the snapshot pinned {dt.date.fromisoformat(pin):%b %-d}"),
    ]
    for yi, (name, lo, hi, n, colour, extent) in enumerate(reversed(rows)):
        a = mdates.date2num(dt.date.fromisoformat(str(lo)))
        b = mdates.date2num(dt.date.fromisoformat(str(hi)))
        cov.barh(yi, b - a, left=a, height=0.32, color=colour, alpha=0.85)
        cov.text(b + 1.5, yi, f"{n:,} zone-days  ·  {extent}",
                 va="center", ha="left", fontsize=9.5, color="#333333")
        cov.text(-0.008, yi, name, transform=cov.get_yaxis_transform(),
                 ha="right", va="center", fontsize=10)
    cov.set_ylim(-0.6, len(rows) - 0.4)
    cov.set_yticks([])
    cov.set_xlim(ax.get_xlim())
    cov.set_title("…but the lineages do not cover the same ground "
                  "(INRB as pinned, not as it stands today)",
                  loc="left", fontsize=10.5, color="#333333", pad=6)
    for sp in cov.spines.values():
        sp.set_visible(False)
    cov.tick_params(labelbottom=False, length=0)

    fig.suptitle("Three independent readings of the same situation reports",
                 x=0.006, y=0.985, ha="left", va="top", fontsize=15,
                 fontweight="bold")
    fig.text(0.006, 0.932,
             "Agreement between two readings of one document is evidence "
             "about transcription — never about whether the document is right.",
             ha="left", va="top", fontsize=11, color="#333333")

    leg = ax.legend(loc="center right", bbox_to_anchor=(1.004, 1.0),
                    fontsize=9.5, frameon=True, framealpha=0.95,
                    facecolor="white", edgecolor="#8a8a8a", borderpad=0.6,
                    labelspacing=0.5, handlelength=1.8)
    leg.get_frame().set_linewidth(0.7)

    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=200)
    plt.close(fig)


def draw_ascertainment(inputs: dict[str, Path], out: Path) -> None:
    """Where confirmed deaths were found, and what share of them the
    surveillance system never had in care -- at slide proportions.

    THIS IS THE QUANTITY THE MODELS MOST NEED, and the reason the pipeline
    checks every page's arithmetic rather than trusting what parsed. A death
    confirmed by post-mortem swab is a death the response never isolated, so
    the community share is the closest thing the source prints to a
    measurement of how much transmission is being missed.

    Two panels on one time axis: the daily split in counts, then the share.
    The share is drawn per report-day rather than smoothed, because its
    STABILITY is the finding -- it sits near 0.6 for five weeks, and an
    extraction defect that made it climb toward 1.0 would read as collapsing
    isolation rather than as a parsing artifact.
    """
    # `null_values="NA"`: the daily split carries a row on every report day it
    # spans, holding `NA` where no page classified a death that way, so that a
    # model accumulating between observations closes its interval on schedule.
    # Read without the token those rows come back as the STRING "NA", the
    # `drop_nulls` below does not remove them, and matplotlib draws them as
    # categorical values at the axis baseline -- a hole rendered as an
    # observed zero.
    d = pl.read_csv(inputs["split"], separator="\t", try_parse_dates=True,
                    null_values="NA")
    deaths = pl.read_csv(inputs["deaths"], separator="\t", try_parse_dates=True,
                         null_values="NA")
    d = (d.drop_nulls(["community_deaths_national", "deaths_split_national"])
         .filter(pl.col("deaths_split_national") > 0)
         .join(deaths.select("time", "deaths_national"), on="time", how="left")
         .sort("time"))

    # DO NOT DIVIDE THESE BY days_covered, even though it is now the true span.
    # The split is the report's own 24-hour figure, and the file's rows sit on
    # the report-day grid, so `days_covered` is 1 on all but the one row after
    # the 28-29 July silence. Drawing a per-day rate would still be the wrong
    # picture here: these bars are counts of classified deaths per report, and
    # the point of the panel is the SHARE, which is scale-free. The national
    # total below IS cumulative-differenced over its own window.
    t = [mdates.date2num(x) for x in d["time"].to_list()]
    comm_n = comm = d["community_deaths_national"].to_list()
    total_n = total = d["deaths_split_national"].to_list()
    etc = [a - b for a, b in zip(total, comm)]
    # Deaths counted as confirmed but never classified either way. Clamped at
    # zero: on three days the classified split EXCEEDS the day's cumulative
    # movement (2 Aug by 22, from sitrep 080, whose daily block is displaced
    # by one row), which is a source inconsistency, not a negative quantity.
    unclass = [max(0, (a or 0) - b)
               for a, b in zip(d["deaths_national"].to_list(), total_n)]
    share = [c / s for c, s in zip(comm_n, total_n)]
    pooled = sum(comm_n) / sum(total_n)


    COMM, ETC = "#D55E00", "#0072B2"
    fig, (ax, sh) = plt.subplots(
        2, 1, figsize=(13.333, 7.5), height_ratios=[1.45, 1],
        sharex=True, constrained_layout=True)

    ax.bar(t, comm, width=0.8, color=COMM,
           label="died in the community — found by post-mortem swab")
    ax.bar(t, etc, width=0.8, bottom=comm, color=ETC,
           label="died in a treatment centre")
    ax.bar(t, unclass, width=0.8, bottom=[a + b for a, b in zip(comm, etc)],
           color="#c4c4c4", label="confirmed death, unclassified")
    # TWO BACKLOG RELEASES WOULD OTHERWISE SET THE SCALE. 22 July carries 174
    # unclassified deaths and 30 July 76, against a daily norm near 5, so an
    # honest full-height axis squashes every other day into illegibility. The
    # axis is clipped to the classified range and the clipped bars are
    # labelled with their true totals -- the reader loses no number.
    top = max(a + b for a, b in zip(comm, etc)) * 1.30
    for xi, c, e, u in zip(t, comm, etc, unclass):
        if c + e + u > top:
            ax.annotate(f"{u} unclassified of {c + e + u}\n"
                        f"(batch consolidation)",
                        xy=(xi - 0.45, top * 0.90), xytext=(-58, 10),
                        textcoords="offset points", ha="right", va="center",
                        fontsize=8, color="#4a4a4a",
                        arrowprops=dict(arrowstyle="->", color="#8a8a8a",
                                        linewidth=0.8,
                                        shrinkA=2, shrinkB=2))
    unsplit = deaths.filter(
        pl.col("time").is_between(d["time"].min(), d["time"].max())
        & ~pl.col("time").is_in(d["time"].to_list()))
    for r in unsplit.iter_rows(named=True):
        sp = max(1, int(r["days_covered"] or 1))
        edge = mdates.date2num(r["time"]) + 0.5
        ax.bar(edge - sp / 2, r["deaths_national"] / sp, width=sp * 0.94,
               facecolor="none", edgecolor="#6a6a6a", linewidth=1.1,
               linestyle=(0, (3, 2)), zorder=3,
               label="_" if r["time"] != unsplit["time"][0]
                     else "confirmed deaths, no split published")

    # THE TWO GAPS HAVE DIFFERENT CAUSES, and a reader cannot tell them apart
    # from absence alone. 28-29 July is INSP publishing nothing; 6-8 August is
    # three reports that were published but printed no health-zone table, and
    # the community/treatment-centre split is only ever printed there.
    status = pl.read_csv(inputs["zone_status"], infer_schema_length=None)
    published = {r["date"]: str(r["status"]) for r in status.iter_rows(named=True)}
    have = {str(v) for v in d["time"].to_list()}
    day = dt.timedelta(days=1)
    cur, runs = None, []
    span_lo, span_hi = d["time"].min(), d["time"].max()
    probe = span_lo
    while probe <= span_hi:
        key = str(probe)
        missing = key not in have
        # THREE CAUSES, NOT TWO, and they are not interchangeable. A report
        # that was never published, a report that printed no health-zone
        # table, and a report whose daily block WE withdrew are different
        # claims about who is missing what. The third appeared the moment
        # sitrep 080 was quarantined, and until this read the status the
        # figure called it "no health-zone table" -- blaming the source for
        # our own deliberate rejection of a page that does print one.
        st = published.get(key)
        why = ("no report published" if st is None
               else "daily block withdrawn" if "reject" in st
               else "no health-zone table")
        if missing:
            if cur and cur[2] == why and cur[1] + day == probe:
                cur = (cur[0], probe, why)
            else:
                if cur:
                    runs.append(cur)
                cur = (probe, probe, why)
        probe += day
    if cur:
        runs.append(cur)
    for lo_d, hi_d, why in runs:
        mid = mdates.date2num(lo_d) + (mdates.date2num(hi_d)
                                       - mdates.date2num(lo_d)) / 2
        ax.axvspan(mdates.date2num(lo_d) - 0.5, mdates.date2num(hi_d) + 0.5,
                   color="#f0f0f0", zorder=0)
        # Both bands carry their label at the SAME height, lifted above the
        # dashed national-total outlines that sit inside the August band.
        ax.text(mid, top * 0.56, why, rotation=90, ha="center", va="center",
                fontsize=7.5, color="#8a8a8a")

    ax.set_ylim(0, top)
    ax.set_axisbelow(True)          # gridlines behind the bars, not through them
    ax.set_ylabel("confirmed deaths per day", fontsize=10)
    # ABOVE the axes, not inside them. The header band is empty to the right
    # of the subtitle, and a legend sitting in the plot area covers data --
    # here the August gap band and the clipped 22 July bar.
    # OUT of the plot area, into the empty right half of the header band --
    # but keeping its box. Placement and framing are independent in
    # matplotlib; an earlier attempt lost the border only because it also
    # switched the frame off.
    leg = ax.legend(loc="center right", bbox_to_anchor=(1.004, 1.0),
                    fontsize=9.5, frameon=True, framealpha=0.95,
                    facecolor="white", edgecolor="#8a8a8a", borderpad=0.6,
                    ncol=1, labelspacing=0.5, handlelength=1.3)
    leg.get_frame().set_linewidth(0.7)
    ax.grid(axis="y", **GRID)

    sh.plot(t, share, marker="o", markersize=4.5, linewidth=1.4, color=COMM)
    sh.axhline(pooled, color="#555555", linewidth=1.0, linestyle=(0, (4, 3)))
    # text starts at the left edge of the series and points up to the line
    sh.annotate(f"pooled share of\nclassified deaths  {pooled:.0%}",
                xy=(t[2], pooled), xytext=(t[0], 0.30),
                textcoords="data", ha="left", va="center",
                fontsize=9.5, color="#444444", linespacing=1.5,
                arrowprops=dict(arrowstyle="->", color="#777777",
                                linewidth=1.3, shrinkA=4, shrinkB=4))
    sh.set_axisbelow(True)
    sh.set_ylim(0, 1.05)
    sh.set_yticks([0, 0.2, 0.4, 0.6, 0.8, 1.0])
    sh.set_yticklabels([f"{v:.0%}" for v in (0, .2, .4, .6, .8, 1.0)])
    sh.set_ylabel("community share", fontsize=10)
    sh.set_title(f"The share never in care — flat near {pooled:.0%}",
                 loc="left", fontsize=11, color="#333333")
    sh.grid(axis="y", **GRID)
    sh.xaxis.set_major_locator(mdates.WeekdayLocator(byweekday=mdates.MO))
    sh.xaxis.set_major_formatter(mdates.DateFormatter("%b %-d"))

    for a in (ax, sh):
        for s in ("top", "right"):
            a.spines[s].set_visible(False)
        a.spines["left"].set_color("#999999")
        a.spines["bottom"].set_color("#999999")

    bold_span = (f"{d['time'].min():%b\\ %-d}\\ to\\ "
                 f"{d['time'].max():%b\\ %-d,%Y}")
    fig.suptitle("Confirmed deaths found in the community, not in care",
                 x=0.006, ha="left", fontsize=15, fontweight="bold")
    ax.set_title("Every confirmed death the reports classify, by where it was "
                 f"found · $\\bf{{{bold_span}}}$",
                 loc="left", fontsize=11, color="#333333")
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=200)
    plt.close(fig)


#: The bands of the outcome composition, bottom to top, with the one the
#: figure is about drawn last. Hues are the file's existing palette. The three
#: ledgers that DO hold a record are washed out with alpha so they recede; the
#: residual takes the vermillion at full strength -- the same hue
#: `ascertainment` gives the quantity it exists to show.
OUTCOME_DEAD = ("#555555", 0.45)
OUTCOME_RECOVERED = ("#009E73", 0.42)
#: Opaque, unlike the two beneath it: the undivided band is painted first and
#: hatched, and a translucent ward band would let that hatching print through
#: on exactly the days the census DOES pin the split.
OUTCOME_WARD = ("#56B4E9", 1.00)
OUTCOME_GONE = ("#D55E00", 1.00)

#: The two marks that stand for something the source did NOT publish, and so
#: must be legible as absences rather than as values: the pale span over a
#: report day carrying no national cumulative, and the line style the share
#: panel switches to once the ward census stops and only a bound survives.
OUTCOME_BREAK = "#f4f4f4"
OUTCOME_BOUND = "#9a6a4a"

#: Inches reserved above the axes for the title, the one-line subtitle and the
#: two-row legend beneath them. Wider than HEADER_IN because the legend lives
#: in that band: a legend box laid over the composition would cover the very
#: band the figure is about.
OUTCOME_HEADER_IN = 1.34


def _fmt_day(iso: str) -> str:
    """A published date in the deck's month-day order."""
    return f"{dt.date.fromisoformat(iso):%b %-d}"


def _span(frame: pl.DataFrame, col: str = "date") -> str:
    """The frame's own span, in the deck's month-day order, so a subtitle can
    carry the dates without either of them being written in."""
    lo = dt.date.fromisoformat(frame[col].min())
    hi = dt.date.fromisoformat(frame[col].max())
    return f"{lo:%b %-d} to {hi:%b %-d, %Y}"


def outcome_ledger(zone: pl.DataFrame, banner: pl.DataFrame) -> pl.DataFrame:
    """Every confirmed case the reports have counted, set against the three
    published ledgers that could say what became of that person.

    WHICH SOURCE, and both are ours and primary: the national row of the
    health-zone table (`cum_cases`, `cum_deaths`) and the front-page dashboard
    tiles (`cumul_recovered`, `patients_isolated_confirmed` -- the count of
    confirmed patients in an isolation ward at the end of the day). All four
    are numbers the reports print. Nothing here is fitted, nothing is a rate,
    and no assumption about how long a patient stays in care enters, so

        unaccounted = cum_cases - cum_deaths - cumul_recovered
                      - patients_isolated_confirmed

    is arithmetic over four printed counts: the people inside the
    confirmed-case total and inside none of the other three.

    ONE ROW PER REPORT DAY ON WHICH THE FIRST THREE ARE PUBLISHED, not all
    four. The isolation census stops partway through the archive, and
    requiring it would end the series there and hide the fact that the
    outbreak did not. So `in_ward`, `unaccounted` and `unaccounted_share` are
    null wherever the census is missing, while `residual` -- cases minus dead
    minus recovered, the ward and the unaccounted undivided -- is present on
    every row and is an upper bound on `unaccounted`, because a ward census
    cannot be negative.
    """
    nat = (zone.filter(pl.col("level") == "national")
           .select("date", "cum_cases", "cum_deaths")
           .drop_nulls(["cum_cases", "cum_deaths"]))
    tiles = banner.select("date", "cumul_recovered",
                          "patients_isolated_confirmed")
    led = (nat.join(tiles, on="date", how="inner")
           .drop_nulls("cumul_recovered")
           .rename({"patients_isolated_confirmed": "in_ward"})
           .sort("date"))
    return led.with_columns(
        (pl.col("cum_cases") - pl.col("cum_deaths")
         - pl.col("cumul_recovered")).alias("residual"),
    ).with_columns(
        (pl.col("residual") - pl.col("in_ward")).alias("unaccounted"),
    ).with_columns(
        (pl.col("unaccounted") / pl.col("cum_cases")).alias("unaccounted_share"),
        (pl.col("residual") / pl.col("cum_cases")).alias("residual_share"),
    )


def outcome_headline(led: pl.DataFrame) -> dict:
    """The numbers this figure states in words, every one of them read off the
    ledger above rather than written in.

    Two moments matter and they are different moments. `census` is the last
    report day on which all four counts exist -- the last day the decomposition
    can be completed at all, and the day the headline count belongs to.
    `last` is the final row of the ledger, where only the undivided residual
    survives, and is what says the quantity kept growing after the census
    stopped rather than stopping with it.

    `run_*` covers the final unbroken run of report days carrying a census. A
    single day's share could be an artefact of one report; the run is what
    licenses calling the share steady, and its endpoints give the growth in the
    count over exactly the window the share was flat across.
    """
    full = led.drop_nulls("unaccounted")
    if not full.height:
        raise ValueError("no report day carries all four published counts")
    c = full.row(-1, named=True)

    # The final unbroken run of consecutive REPORT DAYS carrying a census --
    # consecutive in the ledger, not in the calendar. A weekend INSP published
    # nothing over is not the census going missing, and counting it as one
    # would cut this run at 28 July and report four days where there are
    # fourteen. A day the reports DID appear on and printed no census is a
    # genuine break, and does cut it.
    dates = led["date"].to_list()
    seen = set(full["date"].to_list())
    i = dates.index(c["date"])
    while i > 0 and dates[i - 1] in seen:
        i -= 1
    run = full.filter(pl.col("date") >= dates[i])
    run0 = run.row(0, named=True)
    last = led.row(-1, named=True)

    return {
        "census_date": c["date"], "cum_cases": c["cum_cases"],
        "cum_deaths": c["cum_deaths"], "cumul_recovered": c["cumul_recovered"],
        "in_ward": c["in_ward"], "unaccounted": c["unaccounted"],
        "share": c["unaccounted_share"],
        "census_residual": c["residual"],
        "census_residual_share": c["residual_share"],
        "ward_share": c["in_ward"] / c["cum_cases"],
        "n_census_days": full.height,
        "run_start": run0["date"], "run_days": run.height,
        "run_start_unaccounted": run0["unaccounted"],
        "run_share_min": run["unaccounted_share"].min(),
        "run_share_max": run["unaccounted_share"].max(),
        "last_date": last["date"], "last_cum_cases": last["cum_cases"],
        "last_residual": last["residual"],
        "last_residual_share": last["residual_share"],
    }


#: Why a report day inside the ledger's span carries no national cumulative,
#: keyed by the health-zone table's own status for that report. Three
#: different claims, and absence alone cannot tell them apart: a report that
#: was never published, a report that printed no health-zone table at all, and
#: a table that printed only its 24-hour columns.
OUTCOME_GAP_WHY = {
    None: "no report\npublished",
    "no_matching_table": "no health-zone\ntable printed",
}
OUTCOME_GAP_DEFAULT = "no cumulative\ncolumns printed"


def outcome_gaps(led: pl.DataFrame, status: pl.DataFrame) -> list[dict]:
    """Runs of report days inside the ledger's span that the composition cannot
    be drawn on, each carrying the reason it cannot.

    `zone_table_status` holds exactly one row per report, so it IS the
    calendar: a date absent from it is a day INSP published nothing, which is a
    different failure from a report that appeared and printed no table. The
    composition is drawn segment by segment between these runs rather than
    across them, because a cumulative band carried over a hole is an observed
    value the source never printed.
    """
    published = {r["date"]: str(r["status"]) for r in status.iter_rows(named=True)}
    have = set(led["date"].to_list())
    lo = dt.date.fromisoformat(led["date"].min())
    hi = dt.date.fromisoformat(led["date"].max())

    runs: list[dict] = []
    cur: dict | None = None
    probe = lo
    while probe <= hi:
        key = probe.isoformat()
        if key not in have:
            st = published.get(key)
            why = OUTCOME_GAP_WHY.get(st, OUTCOME_GAP_DEFAULT)
            if cur and cur["why"] == why and cur["hi"] + dt.timedelta(1) == probe:
                cur["hi"] = probe
            else:
                if cur:
                    runs.append(cur)
                cur = {"lo": probe, "hi": probe, "why": why}
        probe += dt.timedelta(days=1)
    if cur:
        runs.append(cur)
    for r in runs:
        r["days"] = (r["hi"] - r["lo"]).days + 1
    return runs


def _outcome_segments(led: pl.DataFrame) -> list[pl.DataFrame]:
    """The ledger split at every hole, so nothing is drawn across one."""
    days = [dt.date.fromisoformat(d) for d in led["date"].to_list()]
    cuts = [0] + [i for i in range(1, len(days))
                  if days[i - 1] + dt.timedelta(days=1) != days[i]] + [len(days)]
    return [led[a:b] for a, b in zip(cuts, cuts[1:]) if b > a]


#: Half-width, in days, given to the end of every drawn run. A published count
#: is a reading for ITS day, so a run of one -- 29 May, and the two isolated
#: census days in early July -- has to be drawn with the width of a day or it
#: is a zero-width polygon and silently disappears. Smaller than half a day, so
#: two runs either side of a one-day hole still leave the hole open.
OUTCOME_PAD = 0.4


def _outcome_pad(xs: list[float], *series: list[float]):
    """A run widened to cover its end days, holding the endpoint values."""
    out = [[xs[0] - OUTCOME_PAD] + list(xs) + [xs[-1] + OUTCOME_PAD]]
    out += [[s[0]] + list(s) + [s[-1]] for s in series]
    return out


def draw_outcomes(inputs: dict[str, Path], out: Path) -> None:
    """Of everyone confirmed with Ebola, where is the record of what happened
    to them -- at slide proportions.

    ONE FACT. On the last day all four published counts exist, more than a
    quarter of everyone ever confirmed appears in none of them: not in the
    death total, not in the cumulative recoveries, not in the ward census. The
    count is not steady either; it grows through the whole window over which
    its share is flat.

    THE COMPOSITION IS AN IDENTITY, NOT A MODEL. Its four bands sum to the
    published cumulative case total by construction, which is why the top band
    can be read as a count of people rather than as a discrepancy between two
    estimates.

    WHY THE COMPOSITION CHANGES SHAPE PARTWAY ALONG. The national census of
    confirmed patients in isolation is published for the last time on the
    report of 2 August; both routes this repository reads it by -- the
    front-page tile and the care pillar's whole-response sentence -- stop on
    that same report, and the per-province bullets that continue do not sum to
    a country (see `census_agreement`, `province_census_is_not_national`). So
    after that day the boundary BETWEEN the ward band and the residual is not
    drawn, because nothing published locates it, and the two are shown as one
    hatched band. Continuing the ward band at zero would draw every patient in
    a bed as unaccounted for; ending the figure there would imply the residual
    stopped growing. Neither is true and neither is drawn.

    WHAT THE BAND IS NOT. It is not a count of untraced people. These are the
    four ledgers INSP publishes; the response works from a case line list that
    is not published and that this figure cannot see. Recorded exits from care
    are also incomplete -- a patient who absconds is booked as neither
    recovered nor dead (`scripts/care_ledger.py`) -- so the recovery ledger is
    a floor and unrecorded recoveries land in this band instead. Absconding,
    unrecorded recovery, unrecorded death and reporting lag all sit inside it
    in unknown proportion, and nothing in these four series separates them.
    The figure therefore asserts no cause.

    WHERE THOSE LIMITS ARE WRITTEN DOWN. In `docs/figures/README.md`, the
    caption every use of this figure carries, along with the three distinct
    causes of the breaks and the reason the June share is not comparable with
    the August one. They are not on the figure: this is a slide, read in
    seconds, and the paragraph that used to sit under it was read by nobody.
    What stays on the figure is only what would make it MISLEAD if removed --
    the hatching where no ward census exists, the rule at the census's last
    day, and the share panel's switch from a measurement to a bound there.

    WHY THE SHARE PANEL STARTS LATE. It is drawn from `run_start`, the first
    day of the final unbroken run of report days carrying all four counts.
    Before that the share falls steeply for two reasons that have nothing to
    do with the response -- a case confirmed last week has no outcome to
    record yet, and the recovery and ward ledgers themselves begin inside that
    window -- so a slope drawn there reads as improvement and is not one.
    Starting where the ledgers are established removes the misreading instead
    of arguing with it.
    """
    zone = pl.read_csv(inputs["zone_table"], infer_schema_length=None)
    banner = pl.read_csv(inputs["banner"], infer_schema_length=None)
    status = pl.read_csv(inputs["zone_status"], infer_schema_length=None)

    led = outcome_ledger(zone, banner)
    h = outcome_headline(led)
    gaps = outcome_gaps(led, status)
    census_x = mdates.datestr2num(h["census_date"])

    dead_c, dead_a = OUTCOME_DEAD
    rec_c, rec_a = OUTCOME_RECOVERED
    ward_c, ward_a = OUTCOME_WARD
    gone_c, gone_a = OUTCOME_GONE

    fig, (ax, sh) = plt.subplots(
        2, 1, figsize=(13.333, 7.5), height_ratios=[2.35, 1],
        sharex=True, constrained_layout=True)
    fh = fig.get_figheight()
    # ONE TITLE LINE AND ONE SUBTITLE LINE. `_header` sets the axes rect from
    # HEADER_IN, which clears two lines of text and nothing else; this figure
    # needs the legend in that band too, so the rect is set again afterwards.
    # `rect` IS (left, bottom, WIDTH, HEIGHT), not (left, bottom, right, top).
    _header(fig,
            "Of everyone confirmed with Ebola, where is the record of what "
            "happened to them?",
            "Cumulative confirmed cases against the four counts the reports "
            f"publish, {_span(led)} — arithmetic over printed numbers, not a "
            "model.",
            title_size=15, sub_size=9.5)
    fig.get_layout_engine().set(rect=(0, 0, 1, 1 - OUTCOME_HEADER_IN / fh),
                                hspace=0.05)

    top = h["last_cum_cases"] * 1.12
    for seg in _outcome_segments(led):
        base = [a + b for a, b in zip(seg["cum_deaths"].to_list(),
                                      seg["cumul_recovered"].to_list())]
        xs, dead, rec, cases = _outcome_pad(
            _dates(seg["date"]), seg["cum_deaths"].to_list(), base,
            seg["cum_cases"].to_list())
        ax.fill_between(xs, 0, dead, facecolor=dead_c, alpha=dead_a, linewidth=0)
        ax.fill_between(xs, dead, rec, facecolor=rec_c, alpha=rec_a, linewidth=0)
        # THE TOP REGION IS DRAWN UNDIVIDED FIRST, everywhere. Its outer
        # boundary is the published case total and its inner one the published
        # dead-plus-recovered, so it is always a real quantity; what is not
        # always known is where the line inside it falls. Painting it first
        # means a day the census skipped is a day the split is not asserted --
        # never a hole, which would read as a collapse in the case total.
        ax.fill_between(xs, rec, cases, facecolor=gone_c, alpha=0.18,
                        hatch="///", edgecolor=gone_c, linewidth=0.0)
        # AND THE SPLIT IS OVERPAINTED ONLY WHERE THE CENSUS IS PUBLISHED, run
        # by contiguous run. Every other boundary here joins two days the
        # source printed a number on; this one would otherwise be interpolated
        # across the twenty days after the census ends, out of nothing.
        for run in _outcome_segments(seg.drop_nulls("in_ward")):
            rbase = [a + b for a, b in zip(run["cum_deaths"].to_list(),
                                           run["cumul_recovered"].to_list())]
            rx, rb, rw, rc = _outcome_pad(
                _dates(run["date"]), rbase,
                [a + b for a, b in zip(rbase, run["in_ward"].to_list())],
                run["cum_cases"].to_list())
            ax.fill_between(rx, rb, rw, facecolor=ward_c, alpha=ward_a,
                            linewidth=0)
            ax.fill_between(rx, rw, rc, facecolor=gone_c, alpha=gone_a,
                            linewidth=0)
        ax.plot(xs, cases, color="#3d3d3d", linewidth=1.0)

    # GAPS ARE HOLES, never a band drawn through them -- but they are no
    # longer labelled one by one. Eight rotated captions at slide size are
    # eight things nobody reads; the legend says what a pale span means, and
    # the three distinct causes are named in `docs/figures/README.md`.
    for g in gaps:
        lo_x = mdates.date2num(g["lo"]) - (1 - OUTCOME_PAD)
        hi_x = mdates.date2num(g["hi"]) + (1 - OUTCOME_PAD)
        ax.axvspan(lo_x, hi_x, color=OUTCOME_BREAK, zorder=0)

    ax.axvline(census_x, color="#3d3d3d", linewidth=1.0, linestyle=(0, (4, 3)),
               zorder=5)

    # A LEGEND, NOT DIRECT LABELS. Four bands, a hatch and a pale span are six
    # marks, and four of the six were previously named by text sitting inside
    # the composition while the other two were explained in a panel header
    # nobody had time to read. The legend lives in the header band rather than
    # over the data, because the band it would have to cover is the one the
    # figure is about.
    marks = [
        Patch(facecolor=dead_c, alpha=dead_a, linewidth=0,
              label="recorded dead"),
        Patch(facecolor=rec_c, alpha=rec_a, linewidth=0,
              label="recorded recovered"),
        Patch(facecolor=ward_c, alpha=ward_a, linewidth=0,
              label="confirmed and in a ward"),
        Patch(facecolor=gone_c, alpha=gone_a, linewidth=0, label="no record"),
        Patch(facecolor=gone_c, alpha=0.18, hatch="///", edgecolor=gone_c,
              linewidth=0.0,
              label="no ward census that day — top two bands not separable"),
        Patch(facecolor=OUTCOME_BREAK, edgecolor="#cbcbcb", linewidth=0.7,
              label="no national cumulative published"),
    ]
    # Column-major in three columns, which is what puts the two bottom bands
    # in the first column, the two top bands in the second and the two
    # absences in the third.
    leg = ax.legend(handles=marks, ncols=3, loc="upper left",
                    bbox_to_anchor=(0.008, 1 - 0.63 / fh),
                    bbox_transform=fig.transFigure, frameon=False,
                    fontsize=9, handlelength=1.7, handleheight=1.0,
                    handletextpad=0.6, columnspacing=2.2, labelspacing=0.5,
                    borderaxespad=0.0, borderpad=0.0)
    leg.set_in_layout(False)

    # THE ONE LINE THE ROOM HAS TIME FOR. Both numbers are read off the
    # ledger; the date they belong to is the one the dashed rule is labelled
    # with, so it is not repeated here.
    ax.text(0.021, 0.925,
            f"{h['unaccounted']:,} people with no record — {h['share']:.0%} of "
            "everyone confirmed",
            transform=ax.transAxes, ha="left", va="center", fontsize=17.5,
            fontweight="bold", color=gone_c)
    # The dashed rule is the only thing on this panel that is neither a band
    # nor a legend entry, so it is the only thing still labelled in place.
    ax.text(census_x - 1.2, top * 0.965,
            f"last national ward census · {_fmt_day(h['census_date'])}",
            ha="right", va="center", fontsize=8.5, color="#555555")

    ax.set_ylim(0, top)
    ax.set_xlim(mdates.datestr2num(led["date"].min()) - 1.4,
                mdates.datestr2num(led["date"].max()) + 1.4)
    ticks = [t for t in range(0, int(top) + 1, 1000)]
    ax.set_yticks(ticks)
    ax.set_yticklabels([f"{t:,}" for t in ticks])
    ax.set_ylabel("cumulative confirmed cases", fontsize=10)
    ax.set_axisbelow(True)
    ax.grid(axis="y", **GRID)
    # NO PANEL HEADER. It carried the span, which the subtitle now carries and
    # the date axis shows, and the two sentences about the hatch and the pale
    # spans, which are legend entries.

    # THE SHARE, PER REPORT DAY AND UNSMOOTHED, for the reason `ascertainment`
    # draws its share the same way: the flatness is the finding, and a smoother
    # would manufacture it.
    #
    # DRAWN FROM `run_start` ONLY, on the shared calendar rather than on a
    # calendar of its own. Before that day the share falls from two thirds to
    # under a third for reasons that are not the response finding people --
    # recent cases have no outcome recorded yet, and the recovery and ward
    # ledgers begin inside that window -- so the slope reads as an improvement
    # it is not. Cutting it out states nothing; explaining it took two lines
    # of prose on a slide. The axis is still panel A's, so the rule at the
    # census's last day stands in the same place on both.
    shown = led.filter(pl.col("date") >= pl.lit(h["run_start"]))
    for seg in _outcome_segments(shown):
        c = seg.drop_nulls("unaccounted_share")
        if c.height:
            sh.plot(_dates(c["date"]), c["unaccounted_share"].to_list(),
                    marker="o", markersize=4.0, linewidth=1.5, color=gone_c)
    tail = led.filter(pl.col("date") >= h["census_date"])
    sh.plot(_dates(tail["date"]), tail["residual_share"].to_list(),
            linewidth=1.2, linestyle=(0, (4, 3)), color=OUTCOME_BOUND)
    sh.plot([census_x], [h["census_residual_share"]], marker="o",
            markersize=4.0, markerfacecolor="white",
            markeredgecolor=OUTCOME_BOUND, markeredgewidth=1.2,
            linestyle="none")
    # THE STEP AT THIS DATE IS THE WARD CENSUS ITSELF -- the last quantity that
    # could be subtracted. Drawing the two points unjoined would read as a
    # break in one series rather than as the handover from a measurement to a
    # bound.
    sh.plot([census_x, census_x], [h["share"], h["census_residual_share"]],
            linewidth=0.9, linestyle=(0, (1, 2)), color=OUTCOME_BOUND)
    sh.axvline(census_x, color="#3d3d3d", linewidth=1.0, linestyle=(0, (4, 3)))
    sh.annotate(f"{h['share']:.0%}", xy=(census_x, h["share"]),
                xytext=(-9, -15), textcoords="offset points", ha="right",
                va="center", fontsize=13, fontweight="bold", color=gone_c)
    # WHAT THE DASHED CONTINUATION IS, said in a legend rather than in an
    # arrowed sentence. Solid and dashed are two different quantities and the
    # panel would mislead without that; a legend says it in four words and
    # sits in the space the late start leaves empty.
    lines = [
        Line2D([], [], color=gone_c, linewidth=1.5, marker="o", markersize=4.0,
               label="share with no record"),
        Line2D([], [], color=OUTCOME_BOUND, linewidth=1.2,
               linestyle=(0, (4, 3)),
               label="upper bound: in a ward or with no record"),
    ]
    shleg = sh.legend(handles=lines, loc="center left", frameon=False,
                      fontsize=9, handlelength=2.6, handletextpad=0.6,
                      labelspacing=0.6, borderaxespad=1.2)
    shleg.set_in_layout(False)

    # THE PANEL'S ONE ANNOTATION, and it is the finding: the share does not
    # move while the count it is a share OF nearly doubles. Every number in it
    # comes off `outcome_headline`. It ends where the run ends rather than
    # being centred on it, so it stays clear of the rule and of the open
    # marker that opens the bound.
    sh.annotate(f"{h['run_days']} report days at {h['run_share_min']:.0%}–"
                f"{h['run_share_max']:.0%}, while the count went "
                f"{h['run_start_unaccounted']:,} → {h['unaccounted']:,}",
                xy=(census_x, h["share"]), xytext=(-16, 15),
                textcoords="offset points", ha="right", va="bottom",
                fontsize=8.5, color="#8a3b00")

    # The y range is read off what is actually drawn, so the flat stretch is
    # not squashed against the axis by an early value the panel no longer
    # shows.
    sh_max = max(shown["unaccounted_share"].max(),
                 tail["residual_share"].max())
    sh_top = math.ceil(sh_max * 1.1 * 10) / 10
    sh.set_ylim(0, sh_top)
    sh_ticks = [i / 10 for i in range(int(round(sh_top * 10)) + 1)]
    sh.set_yticks(sh_ticks)
    sh.set_yticklabels([f"{v:.0%}" for v in sh_ticks])
    sh.set_ylabel("share with no record", fontsize=10)
    sh.set_axisbelow(True)
    sh.grid(axis="y", **GRID)
    sh.xaxis.set_major_locator(mdates.WeekdayLocator(byweekday=mdates.MO))
    sh.xaxis.set_major_formatter(mdates.DateFormatter("%b %-d"))

    for a in (ax, sh):
        for s in ("top", "right"):
            a.spines[s].set_visible(False)
        a.spines["left"].set_color("#999999")
        a.spines["bottom"].set_color("#999999")

    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=200)
    plt.close(fig)


def draw_province_series(inputs: dict[str, Path], out: Path) -> None:
    series = pl.read_csv(inputs["province_series"], infer_schema_length=None)
    summary = pl.read_csv(inputs["summary"], infer_schema_length=None)
    prose = pl.read_csv(inputs["prose"], infer_schema_length=None)

    fig, axes = plt.subplots(1, 2, figsize=(11, 5), constrained_layout=True)

    for ax, col, title in ((axes[0], "cum_cases", "Confirmed cases (cumulative)"),
                           (axes[1], "cum_deaths", "Confirmed deaths (cumulative)")):
        # End labels carry series identity (the palette's worst adjacent pair
        # needs the secondary encoding), so two labels may not sit on top of
        # each other: ends closer than ~12% in log-space are staggered.
        ends: list[tuple[float, str, str]] = []
        for prov, color in PROVINCE_COLOR.items():
            line = (series.filter((pl.col("province") == prov)
                                  & pl.col(col).is_not_null())
                    .sort("date"))
            if line.height:
                x, y = _dates(line["date"]), line[col].to_list()
                ax.plot(x, y, color=color, linewidth=1.8, zorder=3)
                if y[-1] and y[-1] > 0:
                    ends.append((y[-1], prov, color))
            rings = (summary.filter((pl.col("zone_reported")
                                     .map_elements(lambda s: s.strip("*†‡ "),
                                                   return_dtype=pl.Utf8) == prov)
                            & pl.col(col).is_not_null())
                     if "zone_reported" in summary.columns else pl.DataFrame())
            if rings.height:
                ax.scatter(_dates(rings["date"]), rings[col].to_list(),
                           facecolors="none", edgecolors=color, s=14,
                           linewidths=0.9, zorder=4)
            if col == "cum_cases":
                pr = prose.filter(pl.col("province") == prov)
                if pr.height:
                    ax.scatter(_dates(pr["date"]), pr["cum_cases"].to_list(),
                               marker="s", facecolors="none", edgecolors=color,
                               s=18, linewidths=0.9, zorder=4)
        import math
        ends.sort()
        placed: list[float] = []
        for yv, prov, color in ends:
            ly = math.log10(yv)
            while placed and ly - placed[-1] < 0.12:
                ly = placed[-1] + 0.12
            placed.append(ly)
            last_x = ax.lines[-1].get_xdata()[-1] if ax.lines else 0
            ax.annotate(prov, (last_x, 10 ** ly), xytext=(5, 0),
                        textcoords="offset points", va="center",
                        fontsize=8, color=color)
        ax.set_yscale("log")
        ax.set_title(title, loc="left", fontsize=11)
        ax.grid(True, **GRID)
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %-d"))
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
        ax.margins(x=0.09)

    line_h = plt.Line2D([], [], color="#555555", linewidth=1.8,
                        label="sum of the printed health-zone rows")
    ring_h = plt.Line2D([], [], marker="o", linestyle="", markerfacecolor="none",
                        markeredgecolor="#555555",
                        label="printed provincial-summary row (check)")
    sq_h = plt.Line2D([], [], marker="s", linestyle="", markerfacecolor="none",
                      markeredgecolor="#555555",
                      label="prose sentence (self-checking)")
    axes[0].legend(handles=[line_h, ring_h, sq_h], loc="lower right",
                   frameon=False, fontsize=7.5)

    fig.suptitle("Cumulative confirmed cases and deaths by province — "
                 "zone-derived line, printed-summary rings",
                 x=0.01, ha="left", fontsize=12, fontweight="bold")
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=160)
    plt.close(fig)


def _caveat_rug(ax, caveat: pl.DataFrame) -> None:
    """One pink bar per report whose SOURCE says its recent data are still
    consolidating -- one day wide, at the panel's foot. A bar per report rather
    than a shaded period, because the sentence is a rolling statement about
    each report's own trailing edge: shading the whole span would assert that
    late July is still provisional when most of it has since consolidated.
    """
    flagged = caveat.filter(pl.col("kind") == "recent_data_provisional")
    for d in flagged["date"].to_list():
        x = mdates.datestr2num(d)
        ax.axvspan(x - 0.45, x + 0.45, ymin=0.0, ymax=0.045,
                   color="#d4699e", linewidth=0)


def _roll_geomean(xs, ys, window=7, max_gap=4.0):
    """Centred rolling geometric mean, BROKEN across reporting gaps.

    A line drawn across a gap asserts a level on days the source said nothing
    about: sitrep 015 prints one early 24-hour figure and the next is 13 July,
    and joining them drew a six-week plateau out of a single point. Where
    consecutive observations are more than `max_gap` days apart the line is
    interrupted instead.

    NEGATIVE INCREMENTS ARE EXCLUDED FROM THE WINDOW, NOT CLIPPED TO ZERO.
    A clipped revision enters as log1p(0) = 0 and depresses the local mean
    for its whole neighbourhood -- two revisions (-23 and -39) lifted twelve
    neighbouring residuals by +0.44 on average and manufactured a +0.62 right
    skew in Ituri's residual histogram that vanished (to -0.12) once they
    were excluded. A revision is not an observation of zero incidence; it is
    the source editing its past, and it carries no information about the
    local level.
    """
    import math
    out = []
    for i in range(len(ys)):
        lo, hi = max(0, i - window // 2), min(len(ys), i + window // 2 + 1)
        vals = [math.log1p(v) for v in ys[lo:hi] if v is not None and v >= 0]
        v = math.expm1(sum(vals) / len(vals)) if vals else None
        if i > 0 and xs[i] - xs[i - 1] > max_gap:
            out.append(None)
            continue
        out.append(v)
    return out


def _load_panel(inputs: dict[str, Path]):
    """The forward-filled health-zone panel, shared by the two figures below.

    `carry_province` is the same carry the province aggregation applies, so a
    figure never shows a province recovering a zone the pipeline had already
    decided was carried forward.
    """
    import sys as _sys
    _sys.path.insert(0, str(Path(__file__).resolve().parent))
    from aggregate_provinces import carry_province
    from build_streams import ALIASES, load_aliases

    ALIASES.update(load_aliases(Path("data/raw/zone_aliases.csv"),
                                Path("registers/zone_aliases_local.csv")))
    return carry_province(pl.read_csv(inputs["zone_table"],
                                      infer_schema_length=None))


def draw_streams_detail(inputs: dict[str, Path], out: Path) -> None:
    """Every flow we extract, by province. Grey points are observations as
    published, one per report at its own reporting date; the line is a centred
    seven-day rolling geometric mean. The pink strip marks reports whose source
    cautions its own recent data are still consolidating; a gap in the strip is
    a report that did not say it.

    The four series the source publishes for the country and nowhere else are
    in `national_detail`, on the same calendar. They were once concatenated
    below these rows, which made one figure eleven inches wide and twenty-six
    long: the province rows and the national stocks answer different questions
    and neither was readable at that aspect.
    """
    from build_streams import daily_cumulative

    panel = _load_panel(inputs)
    caveat = pl.read_csv(inputs["caveat"], infer_schema_length=None)
    lab = pl.read_csv(inputs["lab"], infer_schema_length=None)

    provinces = ["Ituri", "Nord-Kivu"]
    rows = [
        ("cases_diff", "Confirmed cases / day\ndifferenced cumulative"),
        ("new_cases", "New confirmed cases / day\nthe source's own 24 h figure"),
        ("deaths_diff", "Confirmed deaths / day\ndifferenced cumulative"),
        ("deaths_community", "Community deaths / day\npost-mortem swab"),
        ("deaths_treatment_centre",
         "Treatment-centre deaths / day\nthe other half of the split"),
        # WRAPPED, not shortened. The row labels are drawn to the left of the
        # first column and constrained_layout reserves the width of the widest
        # of them, so one long line steals a quarter of the canvas from the
        # panels.
        ("lab_tests", "Samples analysed / day\nlaboratory prose, licensed\n"
         "by its own printed positivity"),
    ]

    fig = plt.figure(figsize=(11, 3.1 * len(rows) + HEADER_IN),
                     constrained_layout=True)
    all_axes: list = []
    gs = fig.add_gridspec(len(rows), 2)

    for ri, (kind, label) in enumerate(rows):
        axs = []
        for ci, prov in enumerate(provinces):
            ax = fig.add_subplot(gs[ri, ci])
            axs.append(ax)
            if kind.endswith("_diff"):
                col = "cum_cases" if kind.startswith("cases") else "cum_deaths"
                cum = daily_cumulative(panel, prov, col)
                if cum.is_empty():
                    continue
                # ONE POINT PER REPORT, NEVER PER GRID DAY. Differencing the
                # forward-filled daily grid manufactures a zero on every day
                # with no report -- the fill is flat, so the difference is 0 --
                # and those are not observations of zero, they are days the
                # source said nothing. A zero that survives here is real: a
                # report that printed an unchanged cumulative. The increment
                # between consecutive reports is attributed to the report's own
                # date, exactly as the source published it.
                rep_dates = (panel.filter(
                    (pl.col("province") == prov)
                    & pl.col("level").is_in(["zone", "unassigned"])
                    & pl.col(col).is_not_null())
                    .select(pl.col("date").str.to_date()).unique().sort("date"))
                d = (rep_dates.join(cum, on="date", how="inner")
                     .with_columns((pl.col("cum") - pl.col("cum").shift(1))
                                   .alias("v")).drop_nulls("v"))
                xs = [mdates.date2num(x) for x in d["date"].to_list()]
                ys = d["v"].to_list()
            elif kind == "lab_tests":
                d = (lab.filter(pl.col("province") == prov)
                     .group_by("date").agg(pl.col("samples").sum().alias("v"))
                     .sort("date"))
                if d.is_empty():
                    continue
                xs = _dates(d["date"])
                ys = d["v"].to_list()
            else:
                d = (panel.filter((pl.col("province") == prov)
                                  & pl.col("level").is_in(["zone", "unassigned"])
                                  & pl.col(kind).is_not_null())
                     .group_by("date").agg(pl.col(kind).sum().alias("v"))
                     .sort("date"))
                if d.is_empty():
                    continue
                xs = _dates(d["date"])
                ys = d["v"].to_list()
            color = PROVINCE_COLOR[prov]
            ax.scatter(xs, ys, s=7, color="#9a9a9a", zorder=2)
            smoothed = _roll_geomean(xs, ys)
            ax.plot(xs, smoothed, color=color, linewidth=1.7, zorder=3)
            neg = [v for v in ys if v is not None and v < 0]
            if neg:
                ax.set_yscale("symlog", linthresh=1)
                ax.set_ylim(bottom=min(neg) * 2)
            else:
                ax.set_yscale("symlog", linthresh=1)
                ax.set_ylim(bottom=-0.4)
            ax.grid(True, **GRID)
            _caveat_rug(ax, caveat)
            for sp in ("top", "right"):
                ax.spines[sp].set_visible(False)
            ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %-d"))
            if ri == 0:
                ax.set_title(prov, loc="left", fontsize=11, fontweight="bold",
                             color=color)
            if ci == 0:
                ax.text(-0.16, 0.5, label, transform=ax.transAxes,
                        ha="right", va="center", fontsize=8.5)
        if len(axs) == 2:
            lo = min(a.get_ylim()[0] for a in axs)
            hi = max(a.get_ylim()[1] for a in axs)
            for a in axs:
                a.set_ylim(lo, hi)
        all_axes.extend(axs)

    # ONE CALENDAR FOR EVERY PANEL, AND FOR THE SIBLING FIGURE. The span comes
    # from the archive rather than from the panels' own data, so that a stream
    # starting on 13 July shows the ten empty weeks before it, and so that this
    # figure and `national_detail` -- which were one figure until they became
    # unreadable at that length -- can still be read against each other.
    xlim = _report_calendar(caveat)
    for a in all_axes:
        a.set_xlim(xlim)

    _header(fig, "Every extracted flow, by province",
            "Grey points: one observation per report, at its reporting date. "
            "Line: centred 7-day rolling geometric mean, broken across "
            "reporting gaps.\nPink strip: reports whose source cautions its "
            "recent data are still consolidating — one bar per report, so a "
            "gap is a report that did not say it.\nThe national-only series "
            "are in national_detail.png, on this calendar.")
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=150)
    plt.close(fig)


def draw_national_detail(inputs: dict[str, Path], out: Path) -> None:
    """The four series the reports publish for the country and nowhere else.

    Split out of `streams_detail`, where they sat concatenated beneath six
    province rows at eleven by twenty-six inches. Two of them are STOCKS -- a
    reading at an instant rather than a flow over a day -- so they are drawn as
    levels and never smoothed, and the panel titles keep every caveat they
    carried before: the cumulative suspected series is a stock the source
    stopped printing early and is comparable to no flow, and the isolation
    census in its headline form counts suspected cases as well as confirmed
    ones. The one thing dropped in the move is the words "NATIONAL ONLY" from
    each of the four titles, because the figure is national throughout and now
    says so once, in its own; the dates those titles stated in words are now
    read off the series instead of written in.
    """
    panel = _load_panel(inputs)
    caveat = pl.read_csv(inputs["caveat"], infer_schema_length=None)
    summary = pl.read_csv(inputs["summary"], infer_schema_length=None)
    prose = pl.read_csv(inputs["prose"], infer_schema_length=None)

    fig = plt.figure(figsize=(11, 7.2 + HEADER_IN), constrained_layout=True)
    gs = fig.add_gridspec(2, 2)
    axn = fig.add_subplot(gs[0, 0])
    axs2 = fig.add_subplot(gs[0, 1])

    nat = (panel.filter((pl.col("level") == "national")
                        & pl.col("cum_cases").is_not_null())
           .group_by("date").agg(pl.col("cum_cases").last(),
                                 pl.col("cum_deaths").last()))
    nat_s = summary.filter((pl.col("level") == "national")
                           & pl.col("cum_cases").is_not_null())         .select("date", "cum_cases", "cum_deaths")
    nat_p = prose.filter(pl.col("level") == "national")         .select("date", "cum_cases").with_columns(cum_deaths=None)
    allnat = (pl.concat([nat, nat_s, nat_p.with_columns(
        pl.col("cum_deaths").cast(pl.Int64))])
        .group_by("date").agg(pl.col("cum_cases").max(),
                              pl.col("cum_deaths").max()).sort("date"))
    axn.plot(_dates(allnat["date"]), allnat["cum_cases"].to_list(),
             color="#333333", linewidth=1.7)
    dd = allnat.filter(pl.col("cum_deaths").is_not_null())
    axn.plot(_dates(dd["date"]), dd["cum_deaths"].to_list(),
             color="#888888", linewidth=1.4)
    axn.annotate("cases", xy=(0.99, 0.93), xycoords="axes fraction",
                 ha="right", fontsize=8, color="#333333")
    axn.annotate("deaths", xy=(0.99, 0.60), xycoords="axes fraction",
                 ha="right", fontsize=8, color="#888888")
    axn.set_yscale("log")
    axn.set_title("Cumulative confirmed", loc="left", fontsize=10,
                  fontweight="bold")
    _caveat_rug(axn, caveat)

    susp = (panel.filter((pl.col("level") == "national")
                         & pl.col("suspected").is_not_null())
            .group_by("date").agg(pl.col("suspected").last()).sort("date"))
    if susp.height:
        axs2.plot(_dates(susp["date"]), susp["suspected"].to_list(),
                  color="#333333", linewidth=1.7, marker="o", markersize=3)
    # THE DATE IS READ OFF THE SERIES, not written into the caption. It was
    # written in ("printed to 1 June only"), which is a claim that goes stale
    # the moment the source prints one more.
    susp_last = (dt.date.fromisoformat(susp["date"].max()) if susp.height
                 else None)
    axs2.set_title("Cumulative suspected, a stock\n"
                   + (f"(printed to {susp_last:%b %-d} only; " if susp_last
                      else "(")
                   + "not comparable to any flow)",
                   loc="left", fontsize=9.5, fontweight="bold")
    axs2.margins(x=0.05)
    _caveat_rug(axs2, caveat)
    for a in (axn, axs2):
        a.grid(True, **GRID)
        for sp in ("top", "right"):
            a.spines[sp].set_visible(False)
        a.xaxis.set_major_formatter(mdates.DateFormatter("%b %-d"))

    # THE NATIONAL STOCKS, on their own row. These are readings at an
    # instant, not flows, so they are drawn as levels rather than smoothed
    # rates -- and the isolation census is split, because the banner's
    # headline counts SUSPECTS TOO (a median 61% of it), so only the
    # confirmed part observes a confirmed-case compartment.
    axi = fig.add_subplot(gs[1, 0])
    axr = fig.add_subplot(gs[1, 1])
    bn = pl.read_csv(inputs["banner"], infer_schema_length=None)
    tot = bn.filter(pl.col("patients_isolated").is_not_null()).sort("date")
    cnf = bn.filter(pl.col("patients_isolated_confirmed").is_not_null()).sort("date")
    if tot.height:
        axi.plot(_dates(tot["date"]), tot["patients_isolated"].to_list(),
                 color="#777777", linewidth=1.7, marker="o", markersize=3,
                 label="all in isolation (confirmed + suspected)")
    if cnf.height:
        axi.plot(_dates(cnf["date"]),
                 cnf["patients_isolated_confirmed"].to_list(),
                 color="#0072B2", linewidth=1.9, marker="o", markersize=3,
                 label="of those, confirmed")
    axi.legend(frameon=False, fontsize=7.5, loc="upper left")
    # THE CONFIRMED HALF STOPS FIRST, and the split is the only half that
    # observes a confirmed-case compartment, so the date it stops is the one
    # a reader needs. It is read off the series; `care_ledger` argues from the
    # same date, derived the same way, that the care prose carries the
    # quantity onward.
    cnf_last = (dt.date.fromisoformat(cnf["date"].max()) if cnf.height
                else None)
    axi.set_title("Patients in isolation, a stock\n"
                  "the headline census counts suspects too",
                  loc="left", fontsize=9.5, fontweight="bold")
    if cnf_last:
        # The date goes INSIDE the panel, not into the title: at this width a
        # title long enough to carry it runs into the panel beside it.
        axi.axvline(mdates.date2num(cnf_last), color="#D55E00",
                    linewidth=1.0, linestyle=(0, (3, 2)), zorder=1)
        axi.annotate(f"confirmed half\nlast printed {cnf_last:%b %-d}",
                     xy=(mdates.date2num(cnf_last), 0.98),
                     xycoords=("data", "axes fraction"), xytext=(-5, 0),
                     textcoords="offset points", ha="right", va="top",
                     fontsize=7.5, color="#D55E00", linespacing=1.4)
    rec = bn.filter(pl.col("cumul_recovered").is_not_null()).sort("date")
    if rec.height:
        axr.plot(_dates(rec["date"]), rec["cumul_recovered"].to_list(),
                 color="#009E73", linewidth=1.9, marker="o", markersize=3)
    rec_first = (dt.date.fromisoformat(rec["date"].min()) if rec.height
                 else None)
    axr.set_title("Cumulative recoveries\n"
                  + (f"a running total, printed from {rec_first:%b %-d}"
                     if rec_first else "a running total"),
                  loc="left", fontsize=9.5, fontweight="bold")
    for a in (axi, axr):
        a.grid(True, **GRID)
        a.margins(x=0.05)
        for sp in ("top", "right"):
            a.spines[sp].set_visible(False)
        a.xaxis.set_major_formatter(mdates.DateFormatter("%b %-d"))
        _caveat_rug(a, caveat)

    # THE SAME CALENDAR `streams_detail` USES, so the two halves of what was
    # one figure stay readable against each other.
    for a in (axn, axs2, axi, axr):
        a.set_xlim(_report_calendar(caveat))

    _header(fig, "The national-only series: what the source prints for the "
                 "country and nowhere else",
            "Two of the four are STOCKS — a reading at an instant, not a flow "
            "over a day — so they are drawn as levels and never smoothed.\n"
            "Pink strip: reports whose source cautions its recent data are "
            "still consolidating. The per-province flows are in "
            "streams_detail.png, on this calendar.")
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=150)
    plt.close(fig)


# --------------------------------------------------------------------------
# The care ledger: pure summaries first, then the figure that draws them.
# Everything the figure ASSERTS in words is computed here, so a test can pin
# the number rather than the pixels.
# --------------------------------------------------------------------------

#: Which of the care extraction's closures bear on the CENSUS specifically.
#: `census_licensed` is a single boolean and a figure that drew every false as
#: "the source contradicts itself" would accuse the reports of errors they did
#: not make: most false values are rows that print a census with nothing beside
#: it to check the census against.
CENSUS_CHECKS = ("census_split", "occupancy", "occupancy_confirmed",
                 "occupancy_suspect", "confirmed_le_census")

#: clean / contradicted / unchecked, and how each is drawn wherever a care row
#: appears. Three states, not two -- see `care_row_state`.
STATE_COLOR = {"clean": "#009E73", "contradicted": "#D55E00",
               "unchecked": "#bbbbbb"}
STATE_LABEL = {
    "clean": "the row's own arithmetic closes",
    "contradicted": "the REPORT's numbers disagree with each other (kept, flagged)",
    "unchecked": "the report printed nothing to check this row against",
}

#: The four ways out of a treatment centre, in the order the reports list them.
#: Absconders take the one hue no other series in this repository uses, because
#: they are the scarce quantity the modelling turns on.
EXIT_KIND = [
    ("exits_recovered", "recovered", "#009E73"),
    ("exits_noncase", "discharged, not a case", "#56B4E9"),
    ("exits_absconded", "absconded", "#CC79A7"),
    ("exits_deaths", "died", "#333333"),
]


def care_row_state(row: dict, flag: str = "licensed") -> str:
    """`clean`, `contradicted` or `unchecked` for one care-prose row.

    `licensed` conflates two rows that are not alike. One prints an occupancy
    percentage that disagrees with its own census over its own beds -- that is
    the SOURCE contradicting itself, and the value is suspect. The other prints
    a census and nothing at all to check it against -- unverified, not wrong.
    Drawing both the same way either accuses the reports of an error or hides
    one, so the figure separates them and shows all three states.
    """
    if row[flag]:
        return "clean"
    failed = {name for name, _, verdict in
              ((c.partition("=")) for c in (row["checks"] or "").split(";") if c)
              if verdict == "fail"}
    if flag == "census_licensed":
        failed &= set(CENSUS_CHECKS)
    return "contradicted" if failed else "unchecked"


def census_agreement(care: pl.DataFrame, banner: pl.DataFrame) -> dict:
    """The tile-versus-prose comparison the care figure leads with.

    Two routes read the isolation census off the same reports by different
    code: the front-page ISOLEMENT/CTE tile (`extract_banner`) and the care
    pillar's whole-response summary sentence, which the reports file under the
    word `Ensemble` (`extract_care_prose`). Where both print a figure they can
    be compared, and the comparison is the licence for believing the prose
    route where the tile has stopped.

    AGREEMENT HERE IS EVIDENCE ABOUT TRANSCRIPTION, NOT ABOUT THE COUNTS. It is
    one organisation's numbers on one page, read twice. What it rules out is a
    misreading, which is the failure this route is actually exposed to.

    Returns the counts, every disagreement in full, and the three dates that
    say where each route stops -- so nothing downstream has to write a date in.
    """
    ens = care.filter(pl.col("province") == "Ensemble")
    tile = banner.select("date", "patients_isolated",
                         "patients_isolated_confirmed")
    j = ens.join(tile, on="date", how="inner").sort("date")
    tot = j.filter(pl.col("census").is_not_null()
                   & pl.col("patients_isolated").is_not_null())
    cnf = j.filter(pl.col("census_confirmed").is_not_null()
                   & pl.col("patients_isolated_confirmed").is_not_null())

    dis = []
    for r in tot.filter(pl.col("census") != pl.col("patients_isolated")) \
                .iter_rows(named=True):
        half = (None if r["census_confirmed"] is None
                or r["census_suspect"] is None
                else r["census_confirmed"] + r["census_suspect"])
        dis.append({
            "date": r["date"], "sitrep": r["sitrep"],
            "prose_total": r["census"], "prose_split_sum": half,
            "tile_total": r["patients_isolated"],
            # WHICH HALF IS WRONG, not merely that the two disagree. Where the
            # sentence's own confirmed + suspected sums to what the tile says,
            # it is the sentence's stated TOTAL that is the bad number and the
            # split that is right -- a conclusion the tile alone cannot reach.
            "tile_matches_split": half is not None
                                  and half == r["patients_isolated"],
            "state": care_row_state(r, "census_licensed")})

    prov = care.filter(pl.col("province") != "Ensemble")
    return {
        "n_total_both": tot.height,
        "n_total_agree": tot.filter(
            pl.col("census") == pl.col("patients_isolated")).height,
        "n_confirmed_both": cnf.height,
        "n_confirmed_agree": cnf.filter(
            pl.col("census_confirmed")
            == pl.col("patients_isolated_confirmed")).height,
        "disagreements": dis,
        # The tile keeps printing a TOTAL census to the end of the archive; it
        # is only the confirmed half -- the half that observes a confirmed-case
        # compartment -- that stops. Naming the wrong one of these two would
        # misstate what was lost.
        "tile_total_last": banner.filter(
            pl.col("patients_isolated").is_not_null())["date"].max(),
        "tile_confirmed_last": banner.filter(
            pl.col("patients_isolated_confirmed").is_not_null())["date"].max(),
        "prose_national_last": ens.filter(
            pl.col("census").is_not_null())["date"].max(),
        "prose_province_last": prov.filter(
            pl.col("census_confirmed").is_not_null())["date"].max(),
    }


def province_census_is_not_national(care: pl.DataFrame) -> dict:
    """How far short of the country a day's province bullets fall.

    The obvious move once the whole-response sentence stops is to add the
    province bullets up. It does not work and this quantifies why: on most
    report days only one to three of the affected provinces print a care
    bullet at all, so the sum is a partial total that would read as a collapse
    in the census. Where both a whole-response sentence and province bullets
    exist, the shortfall is measured directly.
    """
    prov = care.filter(pl.col("province") != "Ensemble")
    ens = care.filter(pl.col("province") == "Ensemble")
    per_day = (prov.filter(pl.col("census_confirmed").is_not_null())
               .group_by("date").agg(pl.len().alias("n_prov")).sort("date"))
    both = (per_day.join(
        prov.filter(pl.col("census_confirmed").is_not_null())
            .group_by("date").agg(pl.col("census_confirmed").sum()
                                  .alias("sum_conf")), on="date")
        .join(ens.filter(pl.col("census_confirmed").is_not_null())
              .select("date", pl.col("census_confirmed").alias("national")),
              on="date", how="inner")
        .with_columns((pl.col("sum_conf") - pl.col("national")).alias("short")))
    return {
        "n_days": per_day.height,
        "median_provinces_per_day": (per_day["n_prov"].median()
                                     if per_day.height else None),
        "max_provinces_per_day": (per_day["n_prov"].max()
                                  if per_day.height else None),
        "n_compared": both.height,
        "n_short": both.filter(pl.col("short") < 0).height,
        "worst_shortfall": (both["short"].min() if both.height else None),
    }


def exits_double_counted_if_summed(care: pl.DataFrame) -> int:
    """Report days on which BOTH the whole-response sentence and at least one
    province bullet print an exit count.

    The two passages cover the same patients at different levels of geographic
    detail, so on these days a figure that added the facets together would
    count the same discharges twice. It is the reason panel C is faceted rather
    than stacked, and the number is stated in the panel so the choice is
    visible rather than asserted.
    """
    ens = set(care.filter((pl.col("province") == "Ensemble")
                          & pl.col("exits").is_not_null())["date"].to_list())
    prov = set(care.filter((pl.col("province") != "Ensemble")
                           & pl.col("exits").is_not_null())["date"].to_list())
    return len(ens & prov)


def occupancy_at_province_grain(care: pl.DataFrame) -> dict:
    """Census over beds, summed within a province.

    A RATIO OF SUMS IS NOT A MAXIMUM. A province can hold two centres, one
    empty and one turning people away, and report comfortable slack. The
    reports name saturated centres in their `Défis` prose, which the care
    extraction deliberately does not read, so nothing below can be read as
    evidence that no centre in a province is full.
    """
    d = (care.filter((pl.col("province") != "Ensemble")
                     & pl.col("census").is_not_null()
                     & pl.col("beds").is_not_null() & (pl.col("beds") > 0))
         .with_columns((100 * pl.col("census") / pl.col("beds")).alias("occ")))
    over = d.filter(pl.col("occ") > 100).sort("date")
    return {
        "n": d.height,
        "min": (d["occ"].min() if d.height else None),
        "median": (d["occ"].median() if d.height else None),
        "max": (d["occ"].max() if d.height else None),
        "n_over_100": over.height,
        "over_100": [{"date": r["date"], "province": r["province"],
                      "census": r["census"], "beds": r["beds"],
                      "occ": r["occ"]} for r in over.iter_rows(named=True)],
    }


def absconder_coverage(care: pl.DataFrame, after: str) -> dict:
    """How thin the absconder series is, on either side of `after`.

    An absconder is a confirmed patient who leaves care still infectious, so
    the count is the complement of the isolation census: together they measure
    one transition, and neither alone identifies it. That makes its sparsity a
    result, not a nuisance -- and the reason the figure draws one mark per
    printed value and never joins them.
    """
    a = care.filter(pl.col("exits_absconded").is_not_null())
    return {
        "n": a.height,
        "n_after": a.filter(pl.col("date") > after).height,
        "n_national": a.filter(pl.col("province") == "Ensemble").height,
        "n_zero": a.filter(pl.col("exits_absconded") == 0).height,
        "first": (a["date"].min() if a.height else None),
        "last": (a["date"].max() if a.height else None),
    }


def care_columns(care: pl.DataFrame) -> list[str]:
    """The small-multiple column order: every province the care prose ever
    carries a drawn quantity for, in outbreak-size order, with the
    whole-response `Ensemble` sentence last. Derived, and sorted, so the draw
    order cannot vary between runs.
    """
    drawn = ["census", "census_confirmed", "census_suspect", "beds",
             "admissions", "exits", *[c for c, _, _ in EXIT_KIND]]
    have = care.filter(
        pl.any_horizontal([pl.col(c).is_not_null() for c in drawn]))
    seen = set(have["province"].to_list())
    return [p for p in PROVINCE_COLOR if p in seen] + (
        ["Ensemble"] if "Ensemble" in seen else [])


def _state_rug(ax, rows: list[dict], flag: str) -> None:
    """One tick per drawn row, at the panel's head, saying what is known about
    that row's arithmetic. Placed above the data rather than on it, so the
    value and the confidence in the value never overplot.
    """
    for r in rows:
        x = mdates.datestr2num(r["date"])
        ax.axvspan(x - 0.45, x + 0.45, ymin=0.955, ymax=1.0,
                   color=STATE_COLOR[care_row_state(r, flag)],
                   linewidth=0, zorder=4)


def draw_care_ledger(inputs: dict[str, Path], out: Path) -> None:
    """The treatment-centre ledger the reports state in words, and the argument
    that it can be believed.

    PANEL A IS THE FIGURE'S POINT. The front-page tile and the care pillar's
    whole-response sentence are two readings of the same page by two different
    readers in this repository, and where both print a confirmed isolation
    census they agree exactly. That agreement is what licenses the prose route
    after the tile's confirmed half stops -- which is the same report on which
    the whole-response sentence itself stops, so what carries the confirmed
    census onward is the per-province bullets alone. The panel also shows why
    those bullets cannot simply be added up.

    PANEL B is occupancy against installed capacity, per province. It is a
    ratio of sums and it cannot see a full centre inside a half-full province;
    the panel says so rather than letting the slack be read as spare beds.

    PANEL C is the ledger itself -- admissions in, exits out, decomposed into
    the four ways a patient leaves a centre. Province bullets and the
    whole-response sentence are faceted apart and never added together: on
    eleven report days both print an exit count, and stacking them would
    double count.

    THE ABSCONDER STRIP at the foot is drawn as isolated marks because that is
    what the data are. An absconder is a confirmed patient who leaves care
    still infectious, so the count is the complement of the census: the two
    are halves of one transition and neither identifies it alone. Joining the
    marks into a line would assert values on days no report printed one.

    NOTHING IS DROPPED FOR FAILING A CHECK. Every row is drawn, and a rug at
    the head of each panel says whether the row's own arithmetic closed, failed
    to close, or had nothing to close against.
    """
    care = pl.read_csv(inputs["care"], infer_schema_length=None)
    banner = pl.read_csv(inputs["banner"], infer_schema_length=None)
    caveat = pl.read_csv(inputs["caveat"], infer_schema_length=None)

    agree = census_agreement(care, banner)
    partial = province_census_is_not_national(care)
    occ = occupancy_at_province_grain(care)
    absc = absconder_coverage(care, agree["tile_confirmed_last"])
    both_grains = exits_double_counted_if_summed(care)
    cols = care_columns(care)
    n_prov = len([c for c in cols if c != "Ensemble"])
    xlim = _report_calendar(caveat)
    handover = mdates.datestr2num(agree["tile_confirmed_last"])

    CONF, SUSP, BEDS, FLAG = "#0072B2", "#a8cbe0", "#444444", "#D55E00"
    TOTAL = "#777777"

    # Four bands, each with a caption row of its own beneath it. The captions
    # are ordinary axes with the frame switched off rather than `fig.text`,
    # because a figure-coordinate caption has to be positioned by hand and
    # goes wrong the moment a band changes height.
    fig = plt.figure(figsize=(14.0, 14.6 + HEADER_IN), constrained_layout=True)
    gs = fig.add_gridspec(7, len(cols),
                          height_ratios=[3.3, 0.62, 2.2, 0.62, 2.4, 1.15, 1.5])

    def caption(row: int, *paras: str) -> None:
        ax = fig.add_subplot(gs[row, :])
        ax.axis("off")
        # WRAPPED AT A FIXED COLUMN, not left to run off the canvas. The
        # caption axes is about thirteen inches wide and 8.5-point text runs
        # roughly 17 characters to the inch.
        text = "\n".join(textwrap.fill(x, 215) for x in paras)
        ax.text(0, 1.0, text, transform=ax.transAxes, ha="left", va="top",
                fontsize=8.5, color="#444444", linespacing=1.5)
        return ax

    # ---- A. the census, and that it can be believed -----------------------
    axa = fig.add_subplot(gs[0, :])
    tile_t = banner.filter(pl.col("patients_isolated").is_not_null()).sort("date")
    tile_c = banner.filter(
        pl.col("patients_isolated_confirmed").is_not_null()).sort("date")
    axa.plot(_dates(tile_t["date"]), tile_t["patients_isolated"].to_list(),
             color=TOTAL, linewidth=1.6, marker="o", markersize=3.2, zorder=2,
             label="front-page tile — everyone in isolation")
    axa.plot(_dates(tile_c["date"]),
             tile_c["patients_isolated_confirmed"].to_list(),
             color=CONF, linewidth=1.9, marker="o", markersize=3.4, zorder=3,
             label="front-page tile — of those, confirmed")

    ens = care.filter(pl.col("province") == "Ensemble").sort("date")
    et = ens.filter(pl.col("census").is_not_null())
    ec = ens.filter(pl.col("census_confirmed").is_not_null())
    axa.scatter(_dates(et["date"]), et["census"].to_list(), s=64,
                facecolors="none", edgecolors=TOTAL, linewidths=1.3, zorder=4,
                label="care prose, whole-response sentence — everyone")
    axa.scatter(_dates(ec["date"]), ec["census_confirmed"].to_list(), s=64,
                facecolors="none", edgecolors=CONF, linewidths=1.5, zorder=5,
                label="care prose, whole-response sentence — confirmed")

    # The province bullets, which are what survives the handover -- drawn in
    # their own colours and NEVER summed. ONE legend entry between them: the
    # colours are keyed by the province panels below, and six more entries
    # here would push the key over the data it is explaining.
    prov = care.filter(pl.col("province") != "Ensemble")
    first_triangle = True
    for p in [c for c in cols if c != "Ensemble"]:
        d = prov.filter((pl.col("province") == p)
                        & pl.col("census_confirmed").is_not_null()).sort("date")
        if not d.height:
            continue
        axa.scatter(_dates(d["date"]), d["census_confirmed"].to_list(), s=24,
                    marker="^", color=PROVINCE_COLOR[p], zorder=6,
                    label=("care prose, one province's bullet — confirmed "
                           "(colour keys the province panels below)"
                           if first_triangle else "_"))
        first_triangle = False

    for i, bad in enumerate(agree["disagreements"]):
        x = mdates.datestr2num(bad["date"])
        axa.scatter([x], [bad["prose_total"]], s=170, facecolors="none",
                    edgecolors=FLAG, linewidths=1.6, zorder=7,
                    label=("the sentence contradicts its own confirmed + "
                           "suspected split" if i == 0 else "_"))
        # SHORT, because two of these fall a week apart and any sentence long
        # enough to explain them would overlap the other. The caption below
        # carries the explanation; the label carries only which two numbers
        # are in conflict.
        axa.annotate(f"{bad['prose_total']} stated\n{bad['prose_split_sum']} "
                     "by its own split",
                     xy=(x, bad["prose_total"]),
                     xytext=(x, 0.44 - 0.13 * i),
                     textcoords=("data", "axes fraction"),
                     ha="right" if i % 2 == 0 else "left",
                     va="center", fontsize=7.5, color=FLAG, linespacing=1.4,
                     arrowprops=dict(arrowstyle="-", color=FLAG,
                                     linewidth=0.8, shrinkA=3, shrinkB=6))

    axa.axvline(handover, color=FLAG, linewidth=1.2, linestyle=(0, (4, 3)),
                zorder=1)
    hand = dt.date.fromisoformat(agree["tile_confirmed_last"])
    axa.axvspan(handover, xlim[1], color="#f4f4f4", zorder=0)
    axa.annotate(
        f"after {hand:%b %-d} the tile prints no confirmed split,\n"
        "and the whole-response sentence stops on the same report;\n"
        "the province bullets carry the confirmed census on alone",
        xy=(handover, 0.50), xycoords=("data", "axes fraction"),
        xytext=(7, 0), textcoords="offset points", ha="left", va="top",
        fontsize=8, color=FLAG, linespacing=1.5)
    axa.set_ylabel("patients in isolation", fontsize=9.5)
    # HEADROOM FOR THE KEY. The key names six things and there is no empty
    # quarter of this panel to hide it in, so the panel is given a third again
    # of its data range and the key sits above every series.
    axa.set_ylim(0, max(tile_t["patients_isolated"].max(),
                        et["census"].max()) * 1.42)
    axa.set_xlim(xlim)
    axa.grid(axis="y", **GRID)
    axa.set_axisbelow(True)
    axa.legend(frameon=False, fontsize=8, loc="upper left", ncol=3,
               labelspacing=0.4, columnspacing=1.6, handletextpad=0.6)
    axa.set_title(
        "A · Two readers, one page: the front-page tile and the care prose "
        "give the same isolation census",
        loc="left", fontsize=11, fontweight="bold")
    axa.xaxis.set_major_locator(mdates.WeekdayLocator(byweekday=mdates.MO))
    axa.xaxis.set_major_formatter(mdates.DateFormatter("%b %-d"))
    for sp in ("top", "right"):
        axa.spines[sp].set_visible(False)

    med_p = partial["median_provinces_per_day"]
    caption(
        1,
        f"Confirmed census: both routes print one on "
        f"{agree['n_confirmed_both']} report days and agree on "
        f"{agree['n_confirmed_agree']}. Everyone in isolation: both print one "
        f"on {agree['n_total_both']} days and agree on "
        f"{agree['n_total_agree']}; on the {len(agree['disagreements'])} that "
        "differ the sentence contradicts its own confirmed + suspected split "
        "and the tile agrees with the split, so it is the sentence's stated "
        "total that is wrong and not its halves. Agreement is evidence about "
        "transcription, not about the counts — one organisation's figures on "
        "one page, read twice.",
        f"The province bullets (triangles) are NOT summable to a national "
        f"total: a median of {med_p:.0f} of the {n_prov} affected provinces "
        f"prints a care bullet on a given day, at most "
        f"{partial['max_provinces_per_day']}, and on {partial['n_short']} of "
        f"{partial['n_compared']} days where the whole-response sentence is "
        f"also printed the sum falls short of it — by up to "
        f"{abs(partial['worst_shortfall'])} patients.")

    # ---- B. occupancy against capacity, per province ----------------------
    axb0 = None
    for ci, p in enumerate(cols):
        ax = fig.add_subplot(gs[2, ci])
        axb0 = axb0 or ax
        d = care.filter(pl.col("province") == p).sort("date")
        # A ROW WITH ONLY ONE HALF OF THE SPLIT IS STILL A CENSUS. Sud-Kivu is
        # only ever reported as a count of suspected cases in isolation, and a
        # filter on the total would drop the province entirely.
        split = d.filter(pl.col("census_confirmed").is_not_null()
                         | pl.col("census_suspect").is_not_null())
        whole = d.filter(pl.col("census_confirmed").is_null()
                         & pl.col("census_suspect").is_null()
                         & pl.col("census").is_not_null())
        drawn = split.height + whole.height
        if whole.height:
            ax.bar(_dates(whole["date"]), whole["census"].to_list(), width=1.0,
                   color="#c9c9c9", zorder=2)
        if split.height:
            conf = [v or 0 for v in split["census_confirmed"].to_list()]
            susp = [v or 0 for v in split["census_suspect"].to_list()]
            xs = _dates(split["date"])
            ax.bar(xs, conf, width=1.0, color=CONF, zorder=2)
            ax.bar(xs, susp, width=1.0, bottom=conf, color=SUSP, zorder=2)
        beds = d.filter(pl.col("beds").is_not_null())
        if beds.height:
            ax.step(_dates(beds["date"]), beds["beds"].to_list(), where="mid",
                    color=BEDS, linewidth=1.3, zorder=3)
            ax.scatter(_dates(beds["date"]), beds["beds"].to_list(), s=6,
                       color=BEDS, zorder=3)
        _state_rug(ax, d.filter(pl.col("census").is_not_null()
                                | pl.col("census_suspect").is_not_null())
                   .iter_rows(named=True), "census_licensed")

        rate = (d.filter(pl.col("census").is_not_null()
                         & pl.col("beds").is_not_null() & (pl.col("beds") > 0))
                .with_columns((100 * pl.col("census") / pl.col("beds"))
                              .alias("occ")))
        sub = (f"median {rate['occ'].median():.0f}% of beds" if rate.height
               else "no bed count printed")
        ax.set_title(f"{p}\n{sub}", loc="left", fontsize=9,
                     fontweight="bold",
                     color=PROVINCE_COLOR.get(p, "#333333"))
        if not drawn:
            ax.text(0.5, 0.5, "no census\nprinted", transform=ax.transAxes,
                    ha="center", va="center", fontsize=8, color="#999999")
            ax.set_yticks([])
        else:
            top = max([*[v for v in d["census"].to_list() if v is not None],
                       *[v for v in d["census_suspect"].to_list()
                         if v is not None],
                       *[v for v in beds["beds"].to_list()], 1]) * 1.28
            ax.set_ylim(0, top)
            ax.yaxis.set_major_locator(MaxNLocator(4))
        for r in occ["over_100"]:
            if r["province"] != p:
                continue
            ax.annotate(f"{r['occ']:.0f}%",
                        xy=(mdates.datestr2num(r["date"]), r["census"]),
                        xytext=(0, 9), textcoords="offset points",
                        ha="center", va="bottom", fontsize=7.5, color=FLAG,
                        arrowprops=dict(arrowstyle="-", color=FLAG,
                                        linewidth=0.8, shrinkA=1, shrinkB=2))
        ax.set_xlim(xlim)
        ax.grid(axis="y", **GRID)
        ax.set_axisbelow(True)
        ax.tick_params(labelsize=7.5)
        ax.xaxis.set_major_locator(mdates.MonthLocator())
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %-d"))
        for sp in ("top", "right"):
            ax.spines[sp].set_visible(False)
    axb0.set_ylabel("patients / beds", fontsize=8.5)

    caption(
        3,
        "B · Care occupancy against installed capacity. Bars are the "
        "end-of-day census — confirmed (dark) below suspected (light) where "
        "the report prints the split, one grey bar where it prints only the "
        "total; the step line is beds.",
        f"Province occupancy runs {occ['min']:.0f}% to {occ['max']:.0f}% over "
        f"{occ['n']} province-days and exceeds capacity on "
        f"{occ['n_over_100']}. IT CANNOT SEE A FULL CENTRE INSIDE A HALF-FULL "
        "PROVINCE: this is a ratio of sums over a whole province, and the "
        "reports name saturated individual treatment centres in a prose "
        "subsection the care extraction deliberately does not read. Slack "
        "here is not evidence of free beds where the patients are.")

    # ---- C. the ledger flows ---------------------------------------------
    axc0, cover = None, []
    for ci, p in enumerate(cols):
        ax = fig.add_subplot(gs[4, ci])
        axc0 = axc0 or ax
        d = care.filter(pl.col("province") == p).sort("date")
        adm = d.filter(pl.col("admissions").is_not_null())
        if adm.height:
            ax.bar(_dates(adm["date"]), adm["admissions"].to_list(), width=1.0,
                   color=PROVINCE_COLOR.get(p, "#666666"), alpha=0.85,
                   zorder=2)
        # Exits go DOWNWARD, decomposed where the report enumerates the ways
        # out and as a hollow outline where it prints only the total: the
        # difference between "no exits" and "exits, not broken down" is a fact
        # about the report and has to stay visible.
        ex = d.filter(pl.col("exits").is_not_null()
                      | pl.any_horizontal(
                          [pl.col(c).is_not_null() for c, _, _ in EXIT_KIND]))
        bottom = {r["date"]: 0.0 for r in ex.iter_rows(named=True)}
        for col, _, colour in EXIT_KIND:
            part = ex.filter(pl.col(col).is_not_null())
            if not part.height:
                continue
            xs = _dates(part["date"])
            vals = [-v for v in part[col].to_list()]
            base = [bottom[dd] for dd in part["date"].to_list()]
            ax.bar(xs, vals, width=1.0, bottom=base, color=colour, zorder=2)
            for dd, v in zip(part["date"].to_list(), vals):
                bottom[dd] += v
        undec = ex.filter(pl.col("exits").is_not_null())
        if undec.height:
            ax.bar(_dates(undec["date"]),
                   [-v for v in undec["exits"].to_list()], width=1.0,
                   facecolor="none", edgecolor="#8a8a8a", linewidth=0.8,
                   zorder=3)
        ax.axhline(0, color="#999999", linewidth=0.8, zorder=1)
        # THE RUG COVERS THE ROWS THIS PANEL DRAWS, not every row the province
        # has. Several rows carry only a contact-follow-up proportion, and a
        # tick for one of those would claim a ledger entry was checked when no
        # ledger entry was printed.
        ledger_dates = sorted(set(adm["date"].to_list()) | set(ex["date"].to_list()))
        _state_rug(ax, d.filter(pl.col("date").is_in(ledger_dates))
                   .iter_rows(named=True), "licensed")
        cover.append(f"{p} {adm.height}/{ex.height}")
        ax.set_title(p, loc="left", fontsize=9, fontweight="bold",
                     color=PROVINCE_COLOR.get(p, "#333333"))
        if not (adm.height or ex.height):
            ax.text(0.5, 0.5, "no ledger\nprinted", transform=ax.transAxes,
                    ha="center", va="center", fontsize=8, color="#999999")
            ax.set_yticks([])
        else:
            ax.yaxis.set_major_locator(MaxNLocator(5))
        ax.set_xlim(xlim)
        ax.grid(axis="y", **GRID)
        ax.set_axisbelow(True)
        ax.tick_params(labelsize=7.5)
        ax.xaxis.set_major_locator(mdates.MonthLocator())
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %-d"))
        for sp in ("top", "right"):
            ax.spines[sp].set_visible(False)
    axc0.set_ylabel("admissions  ↑ / ↓  exits", fontsize=8.5)

    capc = caption(
        5,
        "C · The ledger, faceted by the passage that printed it and never "
        "summed across facets: the whole-response sentence and a province "
        f"bullet cover the same patients, and on {both_grains} report days "
        "both print an exit count, so adding them would double count. "
        "Admissions are "
        "always above the line and exits always below it, so which a bar is "
        "never depends on its colour. Report-days with an admissions figure / "
        "with any exit figure: " + " · ".join(cover) + ".")
    handles = [plt.Rectangle((0, 0), 1, 1, facecolor=c, label=lab)
               for _, lab, c in EXIT_KIND]
    handles.append(plt.Rectangle((0, 0), 1, 1, facecolor="none",
                                 edgecolor="#8a8a8a", linewidth=0.8,
                                 label="exits printed, not broken down"))
    handles += [plt.Rectangle((0, 0), 1, 1, facecolor=STATE_COLOR[s],
                              label="head rug — " + STATE_LABEL[s])
                for s in ("clean", "contradicted", "unchecked")]
    capc.legend(handles=handles, frameon=False, fontsize=8, loc="lower left",
                bbox_to_anchor=(0, 0.0), ncol=4, handlelength=1.1,
                handleheight=1.1, labelspacing=0.45, columnspacing=1.8)

    # ---- D. the absconder counts, as marks ---------------------------------
    axd = fig.add_subplot(gs[6, :])
    axd.axvspan(handover, xlim[1], color="#f4f4f4", zorder=0)
    for p in cols:
        d = care.filter((pl.col("province") == p)
                        & pl.col("exits_absconded").is_not_null()).sort("date")
        if not d.height:
            continue
        colour = PROVINCE_COLOR.get(p, "#333333")
        for x, v in zip(_dates(d["date"]), d["exits_absconded"].to_list()):
            if v > 0:
                axd.plot([x, x], [0, v], color=colour, linewidth=1.4, zorder=2)
                axd.scatter([x], [v], s=26, color=colour, zorder=3)
            else:
                # A PRINTED ZERO IS AN OBSERVATION. "aucun évadé" is the report
                # saying nobody absconded, which is not the report saying
                # nothing, and showing only the positives would bias the
                # series upward.
                axd.scatter([x], [0], s=34, facecolors="none",
                            edgecolors=colour, linewidths=1.2, zorder=3)
        axd.scatter([], [], s=26, color=colour, label=p)
    axd.axvline(handover, color=FLAG, linewidth=1.2, linestyle=(0, (4, 3)),
                zorder=1)
    axd.axhline(0, color="#999999", linewidth=0.8, zorder=1)
    axd.set_xlim(xlim)
    peak = care["exits_absconded"].max() or 1
    axd.set_ylim(-1.2, peak * 1.30)
    axd.set_ylabel("absconded that day", fontsize=8.5)
    axd.grid(axis="y", **GRID)
    axd.set_axisbelow(True)
    axd.legend(frameon=False, fontsize=8, loc="upper left", ncol=6,
               labelspacing=0.3, columnspacing=1.4, handletextpad=0.4)
    axd.xaxis.set_major_locator(mdates.WeekdayLocator(byweekday=mdates.MO))
    axd.xaxis.set_major_formatter(mdates.DateFormatter("%b %-d"))
    axd.tick_params(labelsize=8)
    for sp in ("top", "right"):
        axd.spines[sp].set_visible(False)
    axd.set_title(
        textwrap.fill(
            f"D · Every absconder count the reports print — {absc['n']} "
            f"province-days in all, {absc['n_after']} of them after the "
            f"handover, {absc['n_national']} the whole-response figure rather "
            f"than a province's; printed zeroes, drawn as open rings, the "
            f"report saying nobody absconded rather than saying nothing: "
            f"{absc['n_zero']}. "
            "Marks and stems, never a line: an absconder is a confirmed "
            "patient who leaves care still infectious, the complement of the "
            "census, and there is nothing between these days to draw.", 150),
        loc="left", fontsize=9.5, fontweight="bold")

    _header(fig,
            "The care ledger the reports state in words",
            "One row per report and province from the care pillar's prose — "
            "admissions, exits and the four ways out, the end-of-day census "
            "with its confirmed and suspected halves, and the beds.\n"
            "Nothing is published as an observation stream. No row is dropped "
            "for failing a check: where a report's own numbers disagree the "
            "row is drawn and flagged, because the disagreement is the "
            "source's, not the reader's.",
            title_size=15)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=150)
    plt.close(fig)


def draw_residuals(inputs: dict[str, Path], out: Path) -> None:
    """Reporting-noise diagnostics: per-report residuals against the smoother.

    Computed as log1p(observed) - log1p(smoothed) because the rolling line is
    approximately the local mean in that space -- approximately, not by
    construction: the window includes the point itself (shrinking each
    residual by about 1 - 1/window) and truncates at the series' edges, so a
    small nonzero mean is mechanics, not signal. Read the SHAPE, not the
    mean. A strong right skew would suggest batching -- under-filled reports,
    then a catch-up dump -- but note that this figure once showed exactly
    that (+0.62) as an artefact of clipping the source's negative revisions
    to zero inside the smoother window; excluded properly, both provinces
    are near-symmetric. Negative increments are the source's own revisions:
    they enter neither the residual set nor any window, and are counted in
    the panel title instead. The weekday-median row underneath exists
    because a consistent weekday dip is a reporting-cycle artefact, not
    epidemiology.
    """
    import datetime as dt
    import math
    series = pl.read_csv(inputs["province_series"], infer_schema_length=None)
    provs = ["Ituri", "Nord-Kivu"]
    fig, axes = plt.subplots(2, 2, figsize=(11, 6.6), constrained_layout=True)

    for ci, prov in enumerate(provs):
        b = (series.filter((pl.col("province") == prov)
                           & pl.col("cum_cases").is_not_null()).sort("date"))
        dates = [dt.date.fromisoformat(d) for d in b["date"].to_list()][1:]
        vals = (b["cum_cases"] - b["cum_cases"].shift(1)).to_list()[1:]
        xs = [mdates.date2num(d) for d in dates]
        sm = _roll_geomean(xs, vals)
        res, wd, neg = [], {}, 0
        for d, v, m in zip(dates, vals, sm):
            if v is None or m is None:
                continue
            if v < 0:
                neg += 1
                continue
            r = math.log1p(v) - math.log1p(m)
            res.append(r)
            wd.setdefault(d.strftime("%a"), []).append(r)
        n = len(res)
        mean = sum(res) / n
        m2 = sum((x - mean) ** 2 for x in res) / n
        m3 = sum((x - mean) ** 3 for x in res) / n
        skew = m3 / m2 ** 1.5
        color = PROVINCE_COLOR[prov]

        ax = axes[0][ci]
        ax.hist(res, bins=25, color=color, alpha=0.85)
        ax.axvline(0, color="#444", linewidth=1)
        med = sorted(res)[n // 2]
        ax.axvline(med, color="#444", linewidth=1, linestyle=":")
        ax.set_title(f"{prov} — confirmed cases per report\n"
                     f"n={n} · skew {skew:+.2f} · median {med:+.2f}"
                     + (f" · {neg} revision(s) excluded" if neg else ""),
                     loc="left", fontsize=9)
        ax.set_xlabel("log1p(observed) − log1p(smoothed)", fontsize=8.5)

        ax2 = axes[1][ci]
        days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        meds = [sorted(wd[d])[len(wd[d]) // 2] if d in wd else 0 for d in days]
        ax2.bar(days, meds, color=color, alpha=0.85)
        ax2.axhline(0, color="#999", linewidth=0.8)
        ax2.set_title("median residual by weekday", loc="left", fontsize=9.5)
        for a in (ax, ax2):
            a.grid(True, axis="y", **GRID)
            for sp in ("top", "right"):
                a.spines[sp].set_visible(False)

    lo = min(a.get_ylim()[0] for a in axes[1])
    hi = max(a.get_ylim()[1] for a in axes[1])
    for a in axes[1]:
        a.set_ylim(lo, hi)

    fig.suptitle("Reporting noise: per-report residuals against the rolling "
                 "geometric mean, in its own (log1p) space",
                 x=0.01, ha="left", fontsize=12, fontweight="bold")
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=160)
    plt.close(fig)


FIGURES = {
    # The declared inputs ARE the dependency set, so the stream files are
    # listed one by one rather than hidden behind a directory glob.
    "validation": (draw_validation,
                   {"zone_comparison": "data/build/compare/zone_comparison.csv",
                    "scan": "data/build/compare/scan_comparison.csv",
                    "zone_table": "data/build/series/zone_table.csv",
                    "summary": "data/build/series/province_summary.csv",
                    "meta": "data/build/compare/compare_meta.json",
                    "lock": "external.lock"}),
    "epi_curve": (draw_epi_curve,
                  {"cases": "data/build/streams/cases_daily_national.tsv",
                   "deaths": "data/build/streams/deaths_daily_national.tsv"}),
    "ascertainment": (draw_ascertainment,
                      {"split": "data/build/streams/"
                                "community_deaths_daily_national.tsv",
                       "deaths": "data/build/streams/deaths_daily_national.tsv",
                       "zone_status":
                           "data/build/series/zone_table_status.csv"}),
    "release_grid": (draw_release_grid,
                     {**{f"stream_{n}": f"data/build/streams/{n}.tsv"
                         for n, _ in RELEASE_ROWS},
                      "zone_table": "data/build/series/zone_table.csv",
                      "exceptions": "registers/reconciliation_exceptions.tsv",
                      "summary": "data/build/series/province_summary.csv",
                      "prose": "data/build/series/prose_provinces.csv"}),
    "residuals": (draw_residuals,
                  {"province_series": "data/build/series/province_series.csv"}),
    "streams_detail": (draw_streams_detail,
                       {"zone_table": "data/build/series/zone_table.csv",
                        "caveat": "data/build/series/provisional_caveat.csv",
                        "lab": "data/build/series/lab_prose.csv"}),
    "national_detail": (draw_national_detail,
                        {"zone_table": "data/build/series/zone_table.csv",
                         "caveat": "data/build/series/provisional_caveat.csv",
                         "summary": "data/build/series/province_summary.csv",
                         "prose": "data/build/series/prose_provinces.csv",
                         "banner": "data/build/series/banner.csv"}),
    "outcomes": (draw_outcomes,
                 {"zone_table": "data/build/series/zone_table.csv",
                  "banner": "data/build/series/banner.csv",
                  "zone_status": "data/build/series/zone_table_status.csv"}),
    "care_ledger": (draw_care_ledger,
                    {"care": "data/build/series/care_prose.csv",
                     "banner": "data/build/series/banner.csv",
                     "caveat": "data/build/series/provisional_caveat.csv"}),
    "availability": (draw_availability,
                     {"zone_table": "data/build/series/zone_table.csv",
                      "zone_status": "data/build/series/zone_table_status.csv",
                      "summary": "data/build/series/province_summary.csv",
                      "prose": "data/build/series/prose_provinces.csv"}),
    "province_series": (draw_province_series,
                        {"province_series": "data/build/series/province_series.csv",
                         "summary": "data/build/series/province_summary.csv",
                         "prose": "data/build/series/prose_provinces.csv"}),
}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--figure", required=True, choices=sorted(FIGURES))
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args()

    draw, inputs = FIGURES[args.figure]
    paths = {k: Path(v) for k, v in inputs.items()}
    missing = [str(p) for p in paths.values() if not p.exists()]
    if missing:
        sys.exit(f"inputs not built: {missing}\nRun `make build` first.")
    draw(paths, args.out)
    print(f"  {args.out}")


if __name__ == "__main__":
    main()
