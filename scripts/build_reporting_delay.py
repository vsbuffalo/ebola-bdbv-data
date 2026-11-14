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

What counts as an arrival, and what is set aside. A bar that reads higher
than it ever has before is cases arriving, at the delay of the chart that
shows them. Everything else a bar does is recorded and not counted:

- *A dip.* The bar reads lower than in the previous chart. Most dips are one
  case and are regained in a later chart: the reader places a bar's top a
  case low in the small renders, on different bars in different charts. A
  dip is not subtracted from anything; it is summed into `n_dip_ignored` at
  its delay.
- *A regain.* The bar rises but only back towards a height it has already
  reached. Counting it would report a case arriving late that the curve
  already held, so it goes to `n_regain_ignored`.
- *A redraw by the source.* Where `registers/onset_redraws.tsv` names the
  pair of charts, a fall is the source withdrawing cases from that onset
  date. It goes to `n_withdrawn_by_source`, and the bar's highest reading is
  reset to the new height so that later growth counts as arrivals again. The
  cases withdrawn stay in `n` at the delay they first appeared with: they
  were reported, and later taken back.

Every triangle cell that moved is written to the `--cells` file with which
of the four it was, so each total in the published table can be traced to
the charts behind it.

TWO THINGS THAT MAKE A SINGLE NUMBER WRONG, both visible in the output.

*The early cohorts are not a reporting delay.* May and June onsets carry mean
delays several times those of the later cohorts. Those cases were not slow to
be reported; the epidemic's early history was reconstructed retrospectively,
months after the fact. Pooling them with recent cohorts produces an overall
mean that describes no case in particular and overstates the routine delay.

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


#: What a cell of the triangle that moved is taken to be. Exactly one applies
#: to a fall; a rise is split between `arrived` and `regain_ignored`.
ACCOUNTS = ("arrived", "dip_ignored", "regain_ignored", "withdrawn_by_source")
PUBLISHED_COUNTS = {"arrived": "n", "dip_ignored": "n_dip_ignored",
                    "regain_ignored": "n_regain_ignored",
                    "withdrawn_by_source": "n_withdrawn_by_source"}


def load_redraws(path: Path, triangle: pl.DataFrame) -> set[tuple[str, str]]:
    """The chart pairs between which the source redrew bars lower.

    An entry must name two consecutive charts of this triangle. One whose
    later chart this build does not hold is skipped, because a build of an
    earlier release has not reached it; one whose charts are both held but
    are not consecutive stops the build, because the falls it was written
    for now sit in a different pair.
    """
    held = set(triangle["sha12_from"].to_list()) | set(triangle["sha12_to"].to_list())
    pairs = set(zip(triangle["sha12_from"].to_list(), triangle["sha12_to"].to_list()))
    out: set[tuple[str, str]] = set()
    with path.open(newline="") as fh:
        rows = csv.DictReader((ln for ln in fh if not ln.startswith("#")),
                              delimiter="\t")
        for r in rows:
            pair = (r["sha12_from"], r["sha12_to"])
            if pair[1] not in held:
                continue
            if pair not in pairs:
                raise SystemExit(
                    f"{path}: sitrep {r['sitrep_from']} -> {r['sitrep_to']} "
                    f"({pair[0]} -> {pair[1]}) is not a pair of consecutive "
                    "accepted charts in this build -- the entry no longer "
                    "describes the triangle")
            out.add(pair)
    return out


def account(triangle: pl.DataFrame,
            redraws: set[tuple[str, str]]) -> pl.DataFrame:
    """Each cell that moved, with what its movement is taken to be.

    Per onset date the charts are walked in order, carrying the bar's height
    relative to the first chart (`level`) and the highest it has reached
    (`prior_high`, as it stood before the cell). A rise counts as arrivals
    only for the part above `prior_high`.
    """
    out: list[dict] = []
    moved = triangle.filter(pl.col("d_total") != 0).sort(
        "onset_date", "report_date_to")
    for (_onset,), cells in moved.group_by("onset_date", maintain_order=True):
        level = high = 0
        for c in cells.iter_rows(named=True):
            d = c["d_total"]
            row = {**c, "level_before": level, "prior_high": high,
                   **{a: 0 for a in ACCOUNTS}}
            level += d
            if d > 0:
                row["arrived"] = max(0, level - high)
                row["regain_ignored"] = d - row["arrived"]
                high = max(high, level)
            elif (c["sha12_from"], c["sha12_to"]) in redraws:
                row["withdrawn_by_source"] = -d
                high = min(high, level)
            else:
                row["dip_ignored"] = -d
            out.append(row)
    return pl.DataFrame(out, schema={**moved.schema, "level_before": pl.Int64,
                                     "prior_high": pl.Int64,
                                     **{a: pl.Int64 for a in ACCOUNTS}})


def cohorts(triangle: pl.DataFrame) -> list[dict]:
    last = dt.date.fromisoformat(triangle["report_date_to"].max())
    t = triangle.with_columns(pl.col("onset_date").str.slice(0, 7).alias("month"))
    out = []
    for m in sorted(set(t["month"].to_list())):
        s = t.filter(pl.col("month") == m)
        ignored = {PUBLISHED_COUNTS[a]: int(s[a].sum()) for a in ACCOUNTS[1:]}
        arrivals = s.filter(pl.col("arrived") > 0)
        d, w = arrivals["delay_days"].to_list(), arrivals["arrived"].to_list()
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
            "onset_month": m, "n": n, **ignored,
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
    ap.add_argument("--redraws", required=True, type=Path,
                    help="register of chart pairs the source redrew lower")
    ap.add_argument("--cells", required=True, type=Path,
                    help="every triangle cell that moved, and how it was counted")
    args = ap.parse_args()

    raw = pl.read_csv(args.triangle, infer_schema_length=20000)
    tri = account(raw, load_redraws(args.redraws, raw))
    assert int(tri.select(pl.sum_horizontal(
        pl.col("arrived") + pl.col("regain_ignored")
        - pl.col("dip_ignored") - pl.col("withdrawn_by_source")).sum()).item()) \
        == int(raw["d_total"].sum()), "the four accounts must sum to the triangle"
    cells = args.cells if args.cells.is_absolute() else REPO_ROOT / args.cells
    cells.parent.mkdir(parents=True, exist_ok=True)
    tri.write_csv(cells)

    # The full distribution, which is what a convolution needs. A summary
    # statistic cannot be convolved and the delay is too skewed for a mean to
    # stand in for it.
    rows = []
    t = tri.with_columns(pl.col("onset_date").str.slice(0, 7).alias("onset_month"))
    for m in sorted(set(t["onset_month"].to_list())):
        s = t.filter(pl.col("onset_month") == m)
        tot = s["arrived"].sum()
        if not tot:
            continue
        agg = (s.group_by("delay_days")
                .agg([pl.col(a).sum().alias(PUBLISHED_COUNTS[a]) for a in ACCOUNTS])
                .sort("delay_days"))
        acc = 0
        for r in agg.iter_rows(named=True):
            acc += r["n"]
            rows.append({"onset_month": m, "delay_days": r["delay_days"],
                         "n": r["n"], "share": round(r["n"] / tot, 6),
                         "cumulative_share": round(acc / tot, 6),
                         **{k: r[k] for k in list(PUBLISHED_COUNTS.values())[1:]}})
    out = args.out if args.out.is_absolute() else REPO_ROOT / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["onset_month", "delay_days", "n",
                                           "share", "cumulative_share",
                                           *list(PUBLISHED_COUNTS.values())[1:]])
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
            "published onset curve, per onset-month cohort. A case is counted "
            "when its onset date's bar rises above the highest it has been "
            "read; falls, and rises back to an earlier height, are not counted "
            "and are totalled per cohort and per delay in n_dip_ignored, "
            "n_regain_ignored and n_withdrawn_by_source. The distribution "
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
        print(f"    {c['onset_month']}  n={c['n']:5d}  "
              f"(dips {c['n_dip_ignored']}, regains {c['n_regain_ignored']}, "
              f"withdrawn {c['n_withdrawn_by_source']})  mean {c['mean_delay_days']:5.1f} d  "
              f"median {c['median_delay_days']:3d}  p90 {c['p90_delay_days']:3d}  {flag}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
