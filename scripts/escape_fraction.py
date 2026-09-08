"""The share of confirmed cases first ascertained at death, and what it pins.

WHICH SOURCE: `community_deaths_daily_*` and `cases_daily_*` from our own
extraction (primary), not a third-party rendering.

WHAT IT PRODUCES: one number per exclusion rule -- the ratio

    e_obs = community deaths / new confirmed cases

reported on the same day, at national and province level, together with the
model quantity it constrains.

WHY IT IS NOT A ONE-LINER. The naive sum-ratio over every day the two series
overlap is wrong in two ways that both bias it DOWNWARD, and the size of the
bias is the difference between answering the modelling question and not:

  1. BACKLOG DUMPS INFLATE THE DENOMINATOR ALONE. 22 July publishes 369 new
     confirmations against a national daily norm near 80, with no
     corresponding surge in community deaths. Those are previously-infected
     people entering the register late, so they belong to earlier days'
     denominators. Same for the `consolidating` flag generally, which marks
     the period when the reports were working through a backlog.
  2. THE TWO SERIES DO NOT ALWAYS COVER THE SAME SPAN. On 9 August the
     community-death figure covers 4 days while the case figure covers 1.
     Dividing them compares a four-day numerator to a one-day denominator.

So the estimate is reported under four rules rather than as a point, and the
spread between them IS the uncertainty -- there is no basis in the source for
choosing one and hiding the others.

IS IT FITTED: no. This is a direct ratio of two published columns; nothing is
estimated. That is the point -- it constrains a direction in the fit that the
epidemic growth rate cannot.

WHAT VALIDATES IT: `community_deaths` is checked against the printed province
row by build_streams.ascertainment(); the numerator is a subset of the
denominator on every day, which is a necessary condition the source is not
obliged to satisfy and does.

THE MODEL QUANTITY. With `I` exiting by tau (confirmed alive), gamma*q
(community death, found and swabbed) and gamma*(1-q) (recovery or
unascertained death), the OBSERVABLE has confirmed cases in its denominator:

    e_obs   = gamma*q / (tau + gamma*q)        <- what we measure here
    e_model = gamma   / (tau + gamma)          <- P(never confirmed alive)

These are equal only when q = 1. Since e_obs excludes infections never
confirmed at all, e_obs <= e_model always. What the measurement pins exactly,
free of any assumption about the disease course, is

    gamma*q/tau = e_obs / (1 - e_obs)

after which e_model = (gamma*q/tau) / (q + gamma*q/tau) rides on q alone.
"""

from __future__ import annotations

import argparse
import datetime as dt
from pathlib import Path

import polars as pl

from lib import streams as streams_lib

# The one report-day whose case count is a backlog release rather than a day's
# incidence: 369 against a same-week national norm near 80.
BACKLOG_DUMPS = (dt.date(2026, 7, 22),)


def load(streams: Path, slug: str) -> pl.DataFrame:
    """Same-day community deaths beside new confirmed cases, with both spans."""
    # `null_values="NA"`: the daily flow files hole the report days the source
    # said nothing on, and the `drop_nulls` below removes them only if they
    # are read as nulls rather than as the string "NA".
    deaths = streams_lib.read(
        streams / f"community_deaths_daily_{slug}.tsv", dates=True)
    cases = streams_lib.read(streams / f"cases_daily_{slug}.tsv", dates=True)
    return (
        deaths.join(cases, on="time", how="inner", suffix="_cases")
        .drop_nulls([f"community_deaths_{slug}", f"cases_{slug}"])
    )


def ratio(df: pl.DataFrame, slug: str) -> tuple[int, int, float]:
    num = int(df[f"community_deaths_{slug}"].sum())
    den = int(df[f"cases_{slug}"].sum())
    return num, den, (num / den if den else float("nan"))


def rules(df: pl.DataFrame) -> dict[str, pl.DataFrame]:
    """The four exclusion rules, weakest assumption first."""
    matched = df.filter(pl.col("days_covered") == pl.col("days_covered_cases"))
    return {
        "all overlapping days": df,
        "span-matched": matched,
        "span-matched, no backlog dump": matched.filter(
            ~pl.col("time").is_in(list(BACKLOG_DUMPS))
        ),
        "no consolidation backlog": df.filter(pl.col("flags") == "-"),
    }


def report(streams: Path, slug: str, label: str) -> None:
    df = load(streams, slug)
    if df.is_empty():
        print(f"\n{label}: no overlapping days")
        return
    print(f"\n{label}  ({df['time'].min()} to {df['time'].max()})")
    print(f"  {'rule':<32} {'days':>5} {'ratio':>22} {'gamma*q/tau':>12}")
    for name, sub in rules(df).items():
        if sub.is_empty():
            continue
        num, den, e = ratio(sub, slug)
        odds = e / (1 - e) if e < 1 else float("inf")
        print(f"  {name:<32} {sub.height:>5} {f'{num}/{den} = {e:.4f}':>22} {odds:>12.3f}")


def implications(e_lo: float, e_hi: float) -> None:
    """What the pinned ridge leaves to the prior on q."""
    print("\nWhat q implies, given the pinned ridge")
    print(f"  (gamma*q/tau between {e_lo/(1-e_lo):.3f} and {e_hi/(1-e_hi):.3f})\n")
    print(f"  {'q':>6} {'e_model = P(never conf. alive)':>32} {'unascertained share':>22}")
    for q in (0.915, 0.810, 0.589, 0.45, 0.30):
        out = []
        for e in (e_lo, e_hi):
            x = e / (1 - e)
            em = x / (q + x)
            out.append((em, (1 - q) * em))
        print(
            f"  {q:>6.3f} {f'{out[0][0]:.3f} - {out[1][0]:.3f}':>32} "
            f"{f'{out[0][1]:.3f} - {out[1][1]:.3f}':>22}"
        )


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--streams", type=Path, default=Path("data/build/streams"))
    args = ap.parse_args()

    print("Share of confirmed cases first ascertained at death (e_obs)")
    print("=" * 78)
    report(args.streams, "national", "NATIONAL")
    for slug, label in (
        ("ituri", "Ituri"),
        ("nord_kivu", "Nord-Kivu"),
        ("haut_uele", "Haut-Uele"),
    ):
        if (args.streams / f"community_deaths_daily_{slug}.tsv").exists():
            report(args.streams, slug, label)

    nat = load(args.streams, "national")
    es = [ratio(sub, "national")[2] for sub in rules(nat).values() if not sub.is_empty()]
    implications(min(es), max(es))


if __name__ == "__main__":
    main()
