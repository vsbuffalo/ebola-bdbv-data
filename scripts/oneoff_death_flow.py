"""ONE-OFF: where a death goes, from the event to the model's likelihood.

DISPOSABLE BY DESIGN. Delete this file and `make oneoff-death-flow`
together once the question is settled.

Draws the death pathway as a flow: an Ebola death occurs, may or may not be
confirmed, may or may not be classified into the community/care split, and
lands in one, both or neither of the two emitted streams. Every count is
read from the built streams at draw time -- nothing here is typed -- and
the two lossy edges are drawn as prominently as the surviving ones, because
they are what a reader most needs to see.

The national window is the one the split exists for (13 July onward); the
`deaths_*` stream itself runs from 29 May, which the caption states.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import polars as pl
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

COMM, CARE = "#D55E00", "#0072B2"
LOST = "#9a9a9a"
INK, MUTED = "#222222", "#666666"


def box(ax, x, y, w, h, text, *, fc="#ffffff", ec=INK, tc=INK, lw=1.4,
        style="round,pad=0.012", fs=9.5, weight="normal", ls="solid"):
    ax.add_patch(FancyBboxPatch((x - w / 2, y - h / 2), w, h,
                                boxstyle=style, facecolor=fc, edgecolor=ec,
                                linewidth=lw, linestyle=ls, zorder=2))
    ax.text(x, y, text, ha="center", va="center", fontsize=fs, color=tc,
            zorder=3, linespacing=1.45, fontweight=weight)


def arrow(ax, xy_from, xy_to, *, color=INK, lw=1.6, ls="solid", label=None,
          lx=0.0, ly=0.0, fs=9, tc=None):
    ax.add_patch(FancyArrowPatch(xy_from, xy_to, arrowstyle="-|>",
                                 mutation_scale=14, color=color, lw=lw,
                                 linestyle=ls, shrinkA=2, shrinkB=3, zorder=1))
    if label:
        mx = (xy_from[0] + xy_to[0]) / 2 + lx
        my = (xy_from[1] + xy_to[1]) / 2 + ly
        ax.text(mx, my, label, ha="center", va="center", fontsize=fs,
                color=tc or color, zorder=3, linespacing=1.4)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--streams", type=Path, default=Path("data/build/streams"))
    ap.add_argument("--scope", default="national")
    ap.add_argument("--out", type=Path,
                    default=Path("data/build/figures/oneoff_death_flow.png"))
    args = ap.parse_args()

    s = args.scope
    c = pl.read_csv(args.streams / f"community_deaths_{s}.tsv", separator="\t")
    d = pl.read_csv(args.streams / f"deaths_{s}.tsv", separator="\t")
    j = c.join(d, on="time", how="left")
    comm = int(c[f"community_deaths_{s}"].sum())
    split = int(c[f"deaths_split_{s}"].sum())
    inwin = int(j[f"deaths_{s}"].sum())
    unclassified = inwin - split
    care = split - comm
    total_stream = int(d[f"deaths_{s}"].sum())
    w0, w1 = c["time"].min(), c["time"].max()

    fig, ax = plt.subplots(figsize=(12.6, 9.4))
    ax.set_xlim(0, 12.6); ax.set_ylim(0, 9.4); ax.axis("off")
    ax.text(0.1, 9.25, "Where a death goes", ha="left", va="top", fontsize=16,
            fontweight="bold", color=INK)
    ax.text(0.1, 8.82, "and which of it reaches the model",
            ha="left", va="top", fontsize=10.5, color=MUTED)

    # ---- the event, and the first loss -------------------------------------
    box(ax, 4.0, 7.85, 3.4, 0.7, "A person dies of Ebola",
        fc="#f4f4f4", ec=MUTED, tc=INK, fs=11.5, weight="bold")

    box(ax, 9.6, 7.85, 4.6, 1.5,
        "Body never swabbed\nrefusal · burial before the team · failure\n\n"
        "NEVER CONFIRMED — in no stream\ncount unknown, anywhere in the source",
        fc="#f7f7f7", ec=LOST, tc=MUTED, ls=(0, (4, 3)), fs=9.5)
    arrow(ax, (5.75, 7.85), (7.2, 7.85), color=LOST, ls=(0, (4, 3)))

    # ---- confirmed --------------------------------------------------------
    box(ax, 4.0, 6.1, 3.4, 0.8, f"Confirmed death\n{inwin:,} in this window",
        fc="#eef3f8", ec=INK, fs=10.5, weight="bold")
    arrow(ax, (4.0, 7.48), (4.0, 6.53), label="swab+, or\ndied a known case",
          lx=-1.5, fs=9, tc=MUTED)

    # every confirmed death reaches the death stream
    box(ax, 1.5, 4.3, 2.7, 0.9,
        f"deaths_{s}.tsv\n{total_stream:,} deaths, all weeks",
        fc="#ffffff", ec=INK, fs=10, weight="bold")
    arrow(ax, (2.9, 5.78), (1.8, 4.8), label="all\nof them", lx=-0.5, ly=0.25,
          fs=9, tc=MUTED)

    # ---- classified or not ------------------------------------------------
    box(ax, 5.3, 4.3, 3.2, 0.9,
        f"Classified that day\n{split:,} — the denominator",
        fc="#ffffff", ec=INK, fs=10, weight="bold")
    arrow(ax, (4.4, 5.68), (5.1, 4.79))

    box(ax, 9.6, 4.3, 4.6, 1.2,
        f"Never classified — {unclassified:,}\n"
        "silent days · batch consolidations\n"
        "in the death stream, not in the split",
        fc="#f7f7f7", ec=LOST, tc=MUTED, ls=(0, (4, 3)), fs=9.5)
    arrow(ax, (5.4, 5.7), (7.9, 4.75), color=LOST, ls=(0, (4, 3)))

    # ---- the two classes --------------------------------------------------
    box(ax, 3.5, 2.5, 3.1, 0.95,
        f"Never under care\n{comm:,}  ·  post-mortem Swab+",
        fc="#fdece2", ec=COMM, tc=INK, fs=10, weight="bold")
    box(ax, 7.2, 2.5, 3.1, 0.95,
        f"Died under care\n{care:,}  ·  CTE / CT / hospital",
        fc="#e6f0f7", ec=CARE, tc=INK, fs=10, weight="bold")
    arrow(ax, (4.9, 3.83), (3.8, 3.0), color=COMM)
    arrow(ax, (5.7, 3.83), (6.9, 3.0), color=CARE)

    # ---- the emitted stream ------------------------------------------------
    box(ax, 5.3, 0.95, 5.6, 1.1,
        f"community_deaths_{s}.tsv\n"
        f"numerator {comm:,}   ·   denominator {split:,}\n"
        f"two counts, never a ratio",
        fc="#ffffff", ec=INK, fs=10.5, weight="bold")
    arrow(ax, (3.5, 2.01), (4.3, 1.53), color=COMM)
    arrow(ax, (7.2, 2.01), (6.3, 1.53), color=CARE)

    ax.text(10.6, 0.95, "model infers\n"
            + r"$P(\mathrm{never\ isolated}\mid\mathrm{confirmed\ death})$"
            + "\nbeta-binomial", ha="center", va="center", fontsize=10,
            color=INK, linespacing=1.7)
    arrow(ax, (8.15, 0.95), (9.05, 0.95))

    ax.text(0.1, 0.02,
            f"Counts: {args.scope.replace('_', '-')}, {w0} to {w1} — the "
            f"window in which the source prints the split.   "
            f"Dashed = lost to the observation process.",
            ha="left", va="bottom", fontsize=9, color=MUTED)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.out, dpi=160, bbox_inches="tight")
    print(f"  {args.out}")


if __name__ == "__main__":
    main()
