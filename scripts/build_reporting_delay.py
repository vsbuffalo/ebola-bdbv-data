"""How long a case takes to appear in the published register, by onset cohort.

WHICH SOURCE: `data/build/onset/triangle.csv` (primary, ours), the
onset-by-report-vintage triangle built from successive readings of the source's
own published onset curve. A cell says how many cases with a given symptom-onset
date first appeared between two consecutive vintages.

WHAT IT PRODUCES: `data/build/series/reporting_delay.csv`, the delay
distribution per onset month, and a summary in `meta["reporting_delay"]`.

WHY IT MATTERS: `cases_*` is indexed by *report* date, so a model whose
projected quantity is a confirmation event is comparing two different instants.
The gap is this distribution. It is not a constant and it is not small in the
tail.

IS IT FITTED: no. Every number is a count of cases moving between two published
vintages.

WHAT VALIDATES IT: the cohort totals must reconcile with the onset curve's own
movement, which is how the triangle is built; nothing further is claimed here.

TWO THINGS THAT MAKE A SINGLE NUMBER WRONG, both visible in the output.

*The early cohorts are not a reporting delay.* May and June onsets carry mean
delays of 79 and 39 days. Those cases were not slow to be reported; the
epidemic's early history was reconstructed retrospectively, months after the
fact. Pooling them with recent cohorts produces an overall mean near 13 days
that describes no case in particular and overstates the routine delay by a
factor of two.

*The most recent cohort is right-truncated.* A case with onset last week and a
30-day delay has not been reported yet, so it is absent from its cohort and the
cohort's mean is biased downward. `settled` marks the cohorts whose follow-up
has outrun their own 90th percentile; the newest is always the least
trustworthy.

The consequence for a consumer is that the usable estimate is the most recent
*settled* cohort, and the honest uncertainty is the spread across cohorts
rather than the standard error within one.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
from pathlib import Path

import polars as pl

REPO_ROOT = Path(__file__).resolve().parents[1]

#: A cohort is called settled when its follow-up exceeds its own observed 90th
#: percentile -- most of its mass has had time to arrive. The test is partly
#: circular, because a truncated cohort underestimates its own p90, so it is
#: reported beside `followup_days` rather than in place of it and a consumer
#: can disagree. A fixed threshold was worse: set from the pooled delay it
#: picked June, a cohort that is retrospective reconstruction rather than
#: reporting.


def quantiles(delays: list[int], weights: list[int],
              ps=(0.5, 0.75, 0.9)) -> dict[float, int]:
    tot, acc, out = sum(weights), 0, {}
    for v, w in sorted(zip(delays, weights)):
        acc += w
        for p in ps:
            if p not in out and acc >= p * tot:
                out[p] = v
    return out


def cohorts(triangle: pl.DataFrame) -> list[dict]:
    last = dt.date.fromisoformat(triangle["report_date_to"].max())
    t = triangle.with_columns(pl.col("onset_date").str.slice(0, 7).alias("month"))
    out = []
    for m in sorted(set(t["month"].to_list())):
        s = t.filter(pl.col("month") == m)
        d, w = s["delay_days"].to_list(), s["d_total"].to_list()
        n = sum(w)
        if not n:
            continue
        # Follow-up measured from the *end* of the cohort's month, so a cohort
        # is called complete only when its youngest member has had the time.
        y, mo = (int(x) for x in m.split("-"))
        month_end = dt.date(y + mo // 12, mo % 12 + 1, 1) - dt.timedelta(days=1)
        followup = (last - month_end).days
        q = quantiles(d, w)
        out.append({
            "onset_month": m, "n": n,
            "mean_delay_days": round(sum(a * b for a, b in zip(d, w)) / n, 1),
            "median_delay_days": q.get(0.5), "p75_delay_days": q.get(0.75),
            "p90_delay_days": q.get(0.9),
            "followup_days": followup,
            "settled": followup >= (q.get(0.9) or 10**6),
        })
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--triangle", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--summary", required=True, type=Path)
    args = ap.parse_args()

    tri = pl.read_csv(args.triangle, infer_schema_length=20000).filter(
        pl.col("d_total") > 0)

    # The full distribution, which is what a convolution needs. A summary
    # statistic cannot be convolved and the delay is too skewed for a mean to
    # stand in for it.
    rows = []
    t = tri.with_columns(pl.col("onset_date").str.slice(0, 7).alias("onset_month"))
    for m in sorted(set(t["onset_month"].to_list())):
        s = t.filter(pl.col("onset_month") == m)
        tot = s["d_total"].sum()
        agg = (s.group_by("delay_days").agg(pl.col("d_total").sum().alias("n"))
                .sort("delay_days"))
        acc = 0
        for delay, n in agg.iter_rows():
            acc += n
            rows.append({"onset_month": m, "delay_days": delay, "n": n,
                         "share": round(n / tot, 6),
                         "cumulative_share": round(acc / tot, 6)})
    out = args.out if args.out.is_absolute() else REPO_ROOT / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["onset_month", "delay_days", "n",
                                           "share", "cumulative_share"])
        w.writeheader()
        w.writerows(rows)

    summary = cohorts(tri)
    # The routine delay, which is what a consumer wants, is the most recent
    # settled cohort that is not retrospective reconstruction. The early
    # cohorts are settled precisely because they are old, so recency is the
    # discriminator, not settledness alone.
    usable = [c for c in summary if c["settled"]]
    payload = {
        "by_onset_month": summary,
        "definition":
            "days from symptom onset to a case first appearing in the source's "
            "published onset curve, per onset-month cohort. The distribution "
            "itself is in data/build/series/reporting_delay.csv; convolve with "
            "that rather than shifting by a mean, because the delay is heavily "
            "right-skewed.",
        "usable_cohort":
            (usable[-1]["onset_month"] if usable else None),
        "caution":
            "not a constant and not stationary. The May and June cohorts are "
            "retrospective reconstruction of the epidemic's early history, not "
            "a reporting delay, and pooling them with recent cohorts doubles "
            "the apparent routine delay. The newest cohort is right-truncated "
            "and its mean is biased downward. Use the most recent settled "
            "cohort and take the spread across cohorts as the uncertainty.",
    }
    sm = args.summary if args.summary.is_absolute() else REPO_ROOT / args.summary
    sm.write_text(json.dumps(payload, indent=2) + "\n")

    print(f"  reporting delay: {len(rows)} (onset month, delay) cell(s) over "
          f"{len(summary)} cohort(s)")
    for c in summary:
        flag = ("settled" if c["settled"]
                else f"still arriving ({c['followup_days']} d follow-up)")
        print(f"    {c['onset_month']}  n={c['n']:5d}  mean {c['mean_delay_days']:5.1f} d  "
              f"median {c['median_delay_days']:3d}  p90 {c['p90_delay_days']:3d}  {flag}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
