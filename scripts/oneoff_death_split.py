"""ONE-OFF: what the community-death streams actually contain.

DISPOSABLE BY DESIGN. Delete this file and `make oneoff-death-split`
together once the question is settled. It reads only built stream files.

WHAT THE FILE IS. `community_deaths_<scope>.tsv` carries TWO COUNTS per
row and no percentage:

    time        community_deaths_ituri   deaths_split_ituri
    2026-08-15  75                       136

the numerator (confirmed deaths of people never under case management,
confirmed post-mortem by swab) and the denominator (all confirmed deaths
the report CLASSIFIED that week). The ratio is never stored, because
storing it would throw away the sample size the likelihood needs: 3/6 and
300/600 are the same percentage and very different evidence. The model
reads the pair as a beta-binomial and infers the probability; this figure
draws the pair, and shows the ratio only with the uncertainty the counts
imply.

THE DENOMINATOR IS NOT THE WEEK'S DEATHS. `deaths_split_*` sums the
reports' own 24-hour figures, so it counts only deaths a report classified
on a day it published. The death STREAM differences the cumulative and
therefore also carries deaths that accrued on silent days and in batch
consolidations. The grey band is that difference -- confirmed deaths the
source added to its cumulative but never split -- and over Ituri's window
it is 428 of 1,327 deaths, a third of them. It is drawn because a reader
comparing the coloured columns against the death stream would otherwise
wonder where the rest went, and because it is the honest picture of how
much of the mortality this classification actually covers.

WHAT IS NOT DRAWN, AND WHY. Community deaths whose swab was refused or
failed are NOT in any of these bands: an unswabbed body is never confirmed,
so it enters no column of the death table at all. Those events appear only
in the burial pillar's prose ("1 échec de swab à Butembo", "13 corps
restent en attente"), which counts DEATH ALERTS of any cause rather than
Ebola deaths -- a different universe, un-extracted, and not stackable on
these bars without inventing a subset relation the source does not state.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import polars as pl

from lib import streams as streams_lib
from scipy.stats import beta

COMM, CARE = "#D55E00", "#0072B2"     # Okabe-Ito, CVD-validated pair
UNCL = "#bdbdbd"                      # never classified: absence, not a class
GRID = dict(color="#e8e8e8", linewidth=0.6)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--streams", type=Path, default=Path("data/build/streams"))
    ap.add_argument("--scopes", nargs="+",
                    default=["national", "ituri", "nord_kivu"])
    ap.add_argument("--out", type=Path,
                    default=Path("data/build/figures/oneoff_death_split.png"))
    args = ap.parse_args()

    n = len(args.scopes)
    fig, axes = plt.subplots(2, n, figsize=(4.6 * n, 7.0),
                             constrained_layout=True, height_ratios=[1.3, 1])
    fig.get_layout_engine().set(rect=(0, 0, 1, 0.88))

    for ci, scope in enumerate(args.scopes):
        d = streams_lib.read(args.streams / f"community_deaths_{scope}.tsv")
        num, den = f"community_deaths_{scope}", f"deaths_split_{scope}"
        # The death stream over the same weeks, to expose what was never
        # classified. Absent for a scope with no death stream; then the band
        # is simply not drawn.
        dstream = args.streams / f"deaths_{scope}.tsv"
        unclassified = None
        if dstream.exists():
            w = streams_lib.read(dstream)
            j = d.join(w, on="time", how="left")
            unclassified = [max(int(a or 0) - int(b), 0) for a, b
                            in zip(j[f"deaths_{scope}"], j[den])]
        xs = [mdates.datestr2num(t) for t in d["time"]]
        k = d[num].to_list()
        tot = d[den].to_list()
        care = [t - c for c, t in zip(k, tot)]

        ax = axes[0][ci]
        ax.bar(xs, k, width=4.6, color=COMM, label="never under care (Swab+)")
        ax.bar(xs, care, width=4.6, bottom=k, color=CARE,
               label="died under care (CTE/CT)")
        if unclassified is not None:
            ax.bar(xs, unclassified, width=4.6, bottom=tot, color=UNCL,
                   label="in the death stream, never classified")
        for x, c, t in zip(xs, k, tot):
            ax.annotate(f"{c}/{t}", (x, t), ha="center", va="bottom",
                        fontsize=7.5, color="#444444")
        share = (f"\n{sum(tot)} of {sum(tot) + sum(unclassified)} deaths "
                 f"classified" if unclassified else "")
        ax.set_title(f"{scope.replace('_', '-').title()} — deaths per week"
                     f"{share}", loc="left", fontsize=9.5, fontweight="bold")
        ax.set_ylabel("confirmed deaths (count)", fontsize=9)
        if ci == 0:
            ax.legend(frameon=False, fontsize=8, loc="upper left")

        ad = axes[1][ci]
        frac = [c / t if t else None for c, t in zip(k, tot)]
        lo = [beta.ppf(0.025, c + 0.5, t - c + 0.5) for c, t in zip(k, tot)]
        hi = [beta.ppf(0.975, c + 0.5, t - c + 0.5) for c, t in zip(k, tot)]
        ad.vlines(xs, lo, hi, color="#888888", linewidth=1.4)
        ad.plot(xs, frac, color=COMM, linewidth=1.8, marker="o", markersize=5)
        ad.set_ylim(0, 1)
        ad.axhline(0.5, color="#cccccc", linewidth=0.8, linestyle=":")
        ad.set_ylabel("fraction never under care", fontsize=9)
        ad.set_title("the ratio the model infers, with 95% interval",
                     loc="left", fontsize=9, color="#444444")

        for a in (ax, ad):
            a.grid(True, axis="y", **GRID)
            a.xaxis.set_major_formatter(mdates.DateFormatter("%d %b"))
            for sp in ("top", "right"):
                a.spines[sp].set_visible(False)

    fig.suptitle(
        "What `community_deaths_*.tsv` holds: two COUNTS per week, not a "
        "percentage\n"
        "numerator = deaths never under case management (post-mortem Swab+) · "
        "denominator = deaths the report classified\n"
        "grey = in the death stream but never classified (silent days and "
        "batch consolidations); unswabbed deaths are in NO band",
        x=0.01, ha="left", fontsize=11.5, fontweight="bold")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.out, dpi=160)
    print(f"  {args.out}")


if __name__ == "__main__":
    main()
