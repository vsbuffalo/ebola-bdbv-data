"""The EDA figures, each a pure function of declared inputs.

ONE DRAWING FUNCTION PER FIGURE, and a registry mapping name -> function, so the
Makefile and any document share one source of truth about which figures exist.
Every figure is a build target; nothing here is run ad hoc.

WHAT THE TWO FIGURES ARGUE
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
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import polars as pl

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


def _dates(col: pl.Series) -> list:
    return [mdates.datestr2num(d) for d in col.to_list()]


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
    cal.xaxis.set_major_formatter(mdates.DateFormatter("%d %b"))

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

    Three annotation layers, all drawn from artefacts rather than typed in:
      * cell colour   -- the row's own `flags`, so backlog and harmonisation
                         days are visible rather than averaged away;
      * era bands     -- the extraction route from `zone_table.table`, which
                         changes exactly when the bulletin is reformatted;
      * event ticks   -- the reconciliation exception register, i.e. the days
                         the page's own arithmetic does not close.
    """
    streams = {name: pl.read_csv(p, separator="\t", infer_schema_length=None)
               for name, p in inputs.items() if name.startswith("stream_")}
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
    ax.set_facecolor("#f7f7f7")            # the ground IS "no observation"
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
    ax.set_ylim(0, ny)
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
    fig.get_layout_engine().set(rect=(0, 0.105, 1, 0.872))
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

    fig.suptitle("What the release contains, report by report",
                 x=0.008, ha="left", fontsize=14, fontweight="bold")
    ax.set_title(f"{nx} report-days carrying at least one observation · "
                 f"{ny} published streams · {all_dates[0]} to {all_dates[-1]}",
                 loc="left", fontsize=9.5, color="#555555", pad=8)
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
    d = pl.read_csv(inputs["split"], separator="\t", try_parse_dates=True)
    deaths = pl.read_csv(inputs["deaths"], separator="\t", try_parse_dates=True)
    d = (d.drop_nulls(["community_deaths_national", "deaths_split_national"])
         .filter(pl.col("deaths_split_national") > 0)
         .join(deaths.select("time", "deaths_national"), on="time", how="left")
         .sort("time"))

    # DO NOT DIVIDE THESE BY days_covered. The column means two different
    # things across this repo's streams, and here it is the WRONG one. The
    # split is flow-summed -- it is the report's own 24-hour figure -- so
    # `days_covered` records the gap since the previous observation, not the
    # span the count covers. Sitrep 089 (9 Aug) carries 51 classified deaths
    # with days_covered = 4 while its neighbours run 50 to 67 in a single day;
    # dividing by 4 would draw 13 and invent a collapse that did not happen.
    # The national total below IS cumulative-differenced, so it divides. The
    # asymmetry is real and it is the reason this comment exists.
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
    published = {r["date"]: r["status"] for r in status.iter_rows(named=True)}
    have = {str(v) for v in d["time"].to_list()}
    day = dt.timedelta(days=1)
    cur, runs = None, []
    span_lo, span_hi = d["time"].min(), d["time"].max()
    probe = span_lo
    while probe <= span_hi:
        key = str(probe)
        missing = key not in have
        why = ("no report published" if key not in published
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
    leg = ax.legend(loc="lower right", bbox_to_anchor=(1.0, 1.045),
                    fontsize=9.5, frameon=True, framealpha=0.95,
                    facecolor="white", edgecolor="#8a8a8a", borderpad=0.6,
                    ncol=2, columnspacing=1.6, handlelength=1.3)
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
    sh.xaxis.set_major_formatter(mdates.DateFormatter("%d %b"))

    for a in (ax, sh):
        for s in ("top", "right"):
            a.spines[s].set_visible(False)
        a.spines["left"].set_color("#999999")
        a.spines["bottom"].set_color("#999999")

    bold_span = (f"{d['time'].min():%d\\ %b}\\ to\\ "
                 f"{d['time'].max():%d\\ %b\\ %Y}")
    fig.suptitle("Confirmed deaths found in the community, not in care",
                 x=0.006, ha="left", fontsize=15, fontweight="bold")
    ax.set_title("Every confirmed death the reports classify, by where it was "
                 f"found · $\\bf{{{bold_span}}}$",
                 loc="left", fontsize=11, color="#333333")
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
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%d %b"))
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


def draw_streams_detail(inputs: dict[str, Path], out: Path) -> None:
    """Every flow we extract, by province -- and the national-only series,
    separated. Grey points are observations as published, one per report at its
    own reporting date; the line is a centred seven-day rolling geometric mean.
    The pink strip marks reports whose source cautions its own recent data are
    still consolidating; a gap in the strip is a report that did not say it.
    """
    import sys as _sys
    _sys.path.insert(0, str(Path(__file__).resolve().parent))
    from aggregate_provinces import carry_province
    from build_streams import daily_cumulative, ALIASES, load_aliases

    ALIASES.update(load_aliases(Path("data/raw/zone_aliases.csv"),
                                Path("registers/zone_aliases_local.csv")))
    panel = carry_province(pl.read_csv(inputs["zone_table"],
                                       infer_schema_length=None))
    caveat = pl.read_csv(inputs["caveat"], infer_schema_length=None)
    summary = pl.read_csv(inputs["summary"], infer_schema_length=None)
    prose = pl.read_csv(inputs["prose"], infer_schema_length=None)
    lab = pl.read_csv(inputs["lab"], infer_schema_length=None)

    provinces = ["Ituri", "Nord-Kivu"]
    rows = [
        ("cases_diff", "Confirmed cases / day\ndifferenced cumulative"),
        ("new_cases", "New confirmed cases / day\nthe source's own 24 h figure"),
        ("deaths_diff", "Confirmed deaths / day\ndifferenced cumulative"),
        ("deaths_community", "Community deaths / day\npost-mortem swab"),
        ("deaths_treatment_centre",
         "Treatment-centre deaths / day\nthe other half of the split"),
        ("lab_tests", "Samples analysed / day\nlaboratory prose, licensed by "
         "its own printed positivity"),
    ]

    fig = plt.figure(figsize=(11, 3.1 * len(rows) + 7.0),
                     constrained_layout=True)
    fig.get_layout_engine().set(rect=(0, 0, 1, 0.965))
    all_axes: list = []
    gs = fig.add_gridspec(len(rows) + 2, 2,
                          height_ratios=[1.0] * len(rows) + [1.25, 1.25])

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
            ax.xaxis.set_major_formatter(mdates.DateFormatter("%d %b"))
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

    # ---- The national-only section, deliberately separated. --------------
    axn = fig.add_subplot(gs[len(rows), 0])
    axs2 = fig.add_subplot(gs[len(rows), 1])

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
    axn.set_title("NATIONAL ONLY — cumulative confirmed",
                  loc="left", fontsize=10, fontweight="bold")
    _caveat_rug(axn, caveat)

    susp = (panel.filter((pl.col("level") == "national")
                         & pl.col("suspected").is_not_null())
            .group_by("date").agg(pl.col("suspected").last()).sort("date"))
    if susp.height:
        axs2.plot(_dates(susp["date"]), susp["suspected"].to_list(),
                  color="#333333", linewidth=1.7, marker="o", markersize=3)
    axs2.set_title("NATIONAL ONLY — cumulative suspected, a stock\n"
                   "(printed to 1 June only; not comparable to any flow)",
                   loc="left", fontsize=9.5, fontweight="bold")
    axs2.margins(x=0.05)
    axs2.set_xlim(axn.get_xlim())
    _caveat_rug(axs2, caveat)
    for a in (axn, axs2):
        a.grid(True, **GRID)
        for sp in ("top", "right"):
            a.spines[sp].set_visible(False)
        a.xaxis.set_major_formatter(mdates.DateFormatter("%d %b"))

    # THE NATIONAL STOCKS, on their own row. These are readings at an
    # instant, not flows, so they are drawn as levels rather than smoothed
    # rates -- and the isolation census is split, because the banner's
    # headline counts SUSPECTS TOO (a median 61% of it), so only the
    # confirmed part observes a confirmed-case compartment.
    axi = fig.add_subplot(gs[len(rows) + 1, 0])
    axr = fig.add_subplot(gs[len(rows) + 1, 1])
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
    axi.set_title("NATIONAL ONLY — patients in isolation, a stock\n"
                  "the headline census counts suspects too",
                  loc="left", fontsize=9.5, fontweight="bold")
    rec = bn.filter(pl.col("cumul_recovered").is_not_null()).sort("date")
    if rec.height:
        axr.plot(_dates(rec["date"]), rec["cumul_recovered"].to_list(),
                 color="#009E73", linewidth=1.9, marker="o", markersize=3)
    axr.set_title("NATIONAL ONLY — cumulative recoveries\n"
                  "a running total, printed from 12 July",
                  loc="left", fontsize=9.5, fontweight="bold")
    for a in (axi, axr):
        a.grid(True, **GRID)
        a.margins(x=0.05)
        for sp in ("top", "right"):
            a.spines[sp].set_visible(False)
        a.xaxis.set_major_formatter(mdates.DateFormatter("%d %b"))
        _caveat_rug(a, caveat)

    # ONE CALENDAR FOR EVERY PANEL. A stream that starts on 13 July must show
    # ten empty weeks before it, or its late start reads as a full history.
    xlim = (min(a.get_xlim()[0] for a in all_axes + [axn]),
            max(a.get_xlim()[1] for a in all_axes + [axn]))
    for a in all_axes + [axn, axs2, axi, axr]:
        a.set_xlim(xlim)

    fig.suptitle(
        "Every extracted flow by province, and the national-only series",
        x=0.01, y=0.997, ha="left", fontsize=12, fontweight="bold")
    fig.text(0.01, 0.985,
             "Grey points: one observation per report, at its reporting date. "
             "Line: centred 7-day rolling geometric mean, broken across "
             "reporting gaps.\nPink strip: reports whose source cautions its "
             "recent data are still consolidating — one bar per report, so a "
             "gap is a report that did not say it.",
             ha="left", va="top", fontsize=8.5, color="#444444")
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
                        "summary": "data/build/series/province_summary.csv",
                        "prose": "data/build/series/prose_provinces.csv",
                        "lab": "data/build/series/lab_prose.csv",
                        "banner": "data/build/series/banner.csv"}),
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
