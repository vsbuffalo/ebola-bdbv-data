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
        for prov, color in PROVINCE_COLOR.items():
            line = (series.filter((pl.col("province") == prov)
                                  & pl.col(col).is_not_null())
                    .sort("date"))
            if line.height:
                x, y = _dates(line["date"]), line[col].to_list()
                ax.plot(x, y, color=color, linewidth=1.8, zorder=3)
                ax.annotate(prov, (x[-1], y[-1]), xytext=(4, 0),
                            textcoords="offset points", va="center",
                            fontsize=8, color=color)
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


FIGURES = {
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
