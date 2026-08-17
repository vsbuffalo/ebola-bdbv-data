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

    provinces = ["Ituri", "Nord-Kivu"]
    rows = [
        ("cases_diff", "Confirmed cases / day\ndifferenced cumulative"),
        ("new_cases", "New confirmed cases / day\nthe source's own 24 h figure"),
        ("deaths_diff", "Confirmed deaths / day\ndifferenced cumulative"),
        ("deaths_community", "Community deaths / day\npost-mortem swab"),
        ("deaths_treatment_centre",
         "Treatment-centre deaths / day\nthe other half of the split"),
    ]

    fig = plt.figure(figsize=(11, 3.1 * len(rows) + 3.7),
                     constrained_layout=True)
    fig.get_layout_engine().set(rect=(0, 0, 1, 0.965))
    all_axes: list = []
    gs = fig.add_gridspec(len(rows) + 1, 2,
                          height_ratios=[1.0] * len(rows) + [1.25])

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

    # ONE CALENDAR FOR EVERY PANEL. A stream that starts on 13 July must show
    # ten empty weeks before it, or its late start reads as a full history.
    xlim = (min(a.get_xlim()[0] for a in all_axes + [axn]),
            max(a.get_xlim()[1] for a in all_axes + [axn]))
    for a in all_axes + [axn, axs2]:
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
    "residuals": (draw_residuals,
                  {"province_series": "data/build/series/province_series.csv"}),
    "streams_detail": (draw_streams_detail,
                       {"zone_table": "data/build/series/zone_table.csv",
                        "caveat": "data/build/series/provisional_caveat.csv",
                        "summary": "data/build/series/province_summary.csv",
                        "prose": "data/build/series/prose_provinces.csv"}),
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
