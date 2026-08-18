"""ONE-OFF: what the community-death streams actually contain.

DISPOSABLE BY DESIGN. Delete this file and `make oneoff-death-split`
together once the question is settled. It reads only built stream files.

WHAT THE FILE IS. `community_deaths_<scope>.tsv` carries TWO COUNTS per
row and no percentage:

    time        community_deaths_ituri   deaths_split_ituri
    2026-08-15  75                       136

the numerator (confirmed deaths of people never under case management,
confirmed post-mortem by swab) and the denominator (all confirmed deaths
the report split that week). The ratio is never stored, because storing it
would throw away the sample size the likelihood needs: 3/6 and 300/600 are
the same percentage and very different evidence. The model reads the pair
as a beta-binomial and infers the probability; this figure draws the pair,
and shows the ratio only with the uncertainty that the counts imply.

LEFT: the two counts, stacked -- community below, under-care above. The
column height is the week's split deaths.
RIGHT: the implied fraction with a 95% Jeffreys interval, so a week resting
on few deaths visibly says less than one resting on many.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import polars as pl
from scipy.stats import beta

COMM, CARE = "#D55E00", "#0072B2"     # Okabe-Ito, CVD-validated pair
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
        d = pl.read_csv(args.streams / f"community_deaths_{scope}.tsv",
                        separator="\t")
        num, den = f"community_deaths_{scope}", f"deaths_split_{scope}"
        xs = [mdates.datestr2num(t) for t in d["time"]]
        k = d[num].to_list()
        tot = d[den].to_list()
        care = [t - c for c, t in zip(k, tot)]

        ax = axes[0][ci]
        ax.bar(xs, k, width=4.6, color=COMM, label="never under care (Swab+)")
        ax.bar(xs, care, width=4.6, bottom=k, color=CARE,
               label="died under care (CTE/CT)")
        for x, c, t in zip(xs, k, tot):
            ax.annotate(f"{c}/{t}", (x, t), ha="center", va="bottom",
                        fontsize=7.5, color="#444444")
        ax.set_title(f"{scope.replace('_', '-').title()} — confirmed deaths "
                     f"per week,\nsplit as the source prints it",
                     loc="left", fontsize=10, fontweight="bold")
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
        "What `community_deaths_*.tsv` holds: two COUNTS per week,\n"
        "not a percentage — numerator = confirmed deaths never under case\n"
        "management (post-mortem Swab+), denominator = all deaths split",
        x=0.01, ha="left", fontsize=11.5, fontweight="bold")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.out, dpi=160)
    print(f"  {args.out}")


if __name__ == "__main__":
    main()
