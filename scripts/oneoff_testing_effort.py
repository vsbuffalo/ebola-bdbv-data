"""ONE-OFF: did testing keep pace with incidence?

DISPOSABLE BY DESIGN. This is a question figure, not a pipeline artefact:
delete this file and `make oneoff-testing` together whenever the question
stops being live. It reads only committed build outputs and writes one PNG.

THE QUESTION. The laboratory prose gives testing volume; the zone tables
give confirmed cases. If testing effort grows more slowly than incidence,
then a rising case count is partly a rising *detection* count, positivity
climbs mechanically, and the reporting probability the models fit is not
constant over the window. That is a statement the two series can settle
between them.

WHAT IS PLOTTED, AND WHY WEEKLY. Both series are restricted to the report
days where the laboratory sentence licensed a count -- comparing testing on
days it was reported against cases on all days would confound effort with
coverage. Rates are then per licensed report-day within a week, and weeks
with fewer than three such days are dropped: a one-day week's rate is a
single report, not a rate.

READ THE SECOND ROW AS THE ANSWER. Tests per confirmed case is testing
effort per case detected; it is (100 / positivity) whenever the day's
positives equal the day's new confirmations, which they do on 44 of 53
checked province-days. Flat means testing scaled with the outbreak; falling
means it did not.
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

sys.path.insert(0, str(Path(__file__).resolve().parent))
from aggregate_provinces import carry_province

DAY0 = pl.date(2026, 5, 19)
TESTS, CASES = "#0072B2", "#D55E00"      # Okabe-Ito; validated for CVD
GRID = dict(color="#e8e8e8", linewidth=0.6)


def weekly(lab: pl.DataFrame, panel: pl.DataFrame, prov: str) -> pl.DataFrame:
    lb = (lab.filter(pl.col("province") == prov)
          .group_by("date").agg(pl.col("samples").sum(), pl.col("positives").sum())
          .with_columns(pl.col("date").str.to_date()).sort("date"))
    cs = (panel.filter((pl.col("province") == prov)
                       & pl.col("level").is_in(["zone", "unassigned"])
                       & pl.col("cum_cases").is_not_null())
          .group_by("date").agg(pl.col("cum_cases").sum())
          .with_columns(pl.col("date").str.to_date()).sort("date")
          .with_columns((pl.col("cum_cases") - pl.col("cum_cases").shift(1))
                        .alias("cases")))
    j = (lb.join(cs.select("date", "cases"), on="date", how="inner")
         .drop_nulls("cases")
         .with_columns(((pl.col("date") - DAY0).dt.total_days() // 7).alias("wk")))
    return (j.group_by("wk")
            .agg(pl.col("samples").sum(), pl.col("positives").sum(),
                 pl.col("cases").sum(), pl.len().alias("n"),
                 pl.col("date").max().alias("t"))
            .sort("wk").filter(pl.col("n") >= 3)
            .with_columns((pl.col("samples") / pl.col("n")).alias("tests_day"),
                          (pl.col("cases") / pl.col("n")).alias("cases_day"),
                          (pl.col("samples") / pl.col("cases")).alias("per_case")))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--lab", type=Path,
                    default=Path("data/build/series/lab_prose.csv"))
    ap.add_argument("--panel", type=Path,
                    default=Path("data/build/series/zone_table.csv"))
    ap.add_argument("--out", type=Path,
                    default=Path("data/build/figures/oneoff_testing_effort.png"))
    args = ap.parse_args()

    lab = pl.read_csv(args.lab, infer_schema_length=None)
    panel = carry_province(pl.read_csv(args.panel, infer_schema_length=None))
    provs = ["Ituri", "Nord-Kivu"]

    fig, axes = plt.subplots(2, 2, figsize=(11.5, 7.4), constrained_layout=True,
                             height_ratios=[1.35, 1])
    fig.get_layout_engine().set(rect=(0, 0, 1, 0.90))

    for ci, prov in enumerate(provs):
        w = weekly(lab, panel, prov)
        xs = [mdates.date2num(d) for d in w["t"].to_list()]

        ax = axes[0][ci]
        ax.plot(xs, w["tests_day"], color=TESTS, linewidth=2, marker="o",
                markersize=4.5)
        ax.plot(xs, w["cases_day"], color=CASES, linewidth=2, marker="o",
                markersize=4.5)
        ax.set_yscale("log")
        ax.annotate("samples analysed", (xs[-1], w["tests_day"][-1]),
                    xytext=(6, 0), textcoords="offset points", color=TESTS,
                    fontsize=9, va="center", fontweight="bold")
        ax.annotate("confirmed cases", (xs[-1], w["cases_day"][-1]),
                    xytext=(6, 0), textcoords="offset points", color=CASES,
                    fontsize=9, va="center", fontweight="bold")
        f, l = w.row(0, named=True), w.row(-1, named=True)
        ax.set_title(
            f"{prov} — per day\ntesting ×{l['tests_day']/f['tests_day']:.1f}"
            f"   ·   cases ×{l['cases_day']/max(f['cases_day'], 0.1):.1f}"
            f"   over the same weeks",
            loc="left", fontsize=10.5, fontweight="bold")
        ax.set_ylabel("per report-day (log)", fontsize=9)

        ad = axes[1][ci]
        ad.plot(xs, w["per_case"], color="#444444", linewidth=2, marker="o",
                markersize=4.5)
        ad.set_ylim(bottom=0)
        ad.set_ylabel("tests per confirmed case", fontsize=9)
        ad.set_title(f"effort per case detected: "
                     f"{f['per_case']:.1f} → {l['per_case']:.1f}",
                     loc="left", fontsize=9.5, color="#444444")

        for a in (ax, ad):
            a.grid(True, **GRID)
            a.xaxis.set_major_formatter(mdates.DateFormatter("%d %b"))
            for sp in ("top", "right"):
                a.spines[sp].set_visible(False)
        ax.set_xlim(min(xs) - 3, max(xs) + 14)
        ad.set_xlim(*ax.get_xlim())

    fig.suptitle(
        "Testing effort against incidence — did the laboratory keep pace?\n"
        "Weekly rates over report days whose laboratory sentence licensed a\n"
        "count (≥3/week); tests per case is 100/positivity.",
        x=0.01, ha="left", fontsize=11.5, fontweight="bold")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.out, dpi=160)
    print(f"  {args.out}")


if __name__ == "__main__":
    main()
