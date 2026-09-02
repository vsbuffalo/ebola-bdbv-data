"""One-off: where a death goes, from the event to the model's likelihood.

Disposable by design. Delete this file and `make oneoff-death-flow`
together once the question is settled.

Draws the death pathway as a flow: an Ebola death occurs, may or may not be
confirmed, may or may not be classified into the community/care split, and
lands in one, both or neither of the two emitted streams. Every count is
read from the built streams at draw time -- nothing here is typed.

Three states, three encodings, because two of them were once drawn alike
and that was a claim about the data that is not true:

  extracted and emitted     solid border, coloured  -- in a stream the model
                                                       reads
  extracted, not classified solid grey              -- *in* the death stream,
                                                       counted, fed to the
                                                       model; only its
                                                       community/care status
                                                       is unknown. Missing
                                                       covariate, not a
                                                       missing death.
  never observed            dashed, hollow          -- no count exists in the
                                                       source at all

The middle state is measurable and measured (it is the difference between
the two streams); the outer one is not. Drawing them the same way implied
the outbreak loses deaths where in fact it loses only their classification.

The national window is the one the split exists for (13 July onward); the
`deaths_*` stream itself runs from 29 May, which the caption states.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import polars as pl
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

COMM, CARE = "#D55E00", "#0072B2"
#: The three states a death can be in, and the encoding each gets. KEPT
#: SEPARATE ON PURPOSE: `UNCLASS` is observed and counted, `UNOBS` is not.
KEPT = "#222222"          # extracted and emitted
UNCLASS = "#7a7a7a"       # extracted, counted, but carrying no classification
UNOBS = "#b0b0b0"         # never observed; no count exists
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
    # The *daily* files, not the weekly ones. Both families are published at
    # both resolutions, and the weekly bins are not the same bins: the
    # community family's first bin opens on 13 July, when the source first
    # printed the split, while the deaths family's bin covering that date
    # opened on 8 July. Joining the two weekly files on `time` therefore
    # matched a 2-day community bin against a 7-day death bin and counted the
    # five days in between as deaths the source declined to classify. That put
    # 118 deaths into the unclassified box that were never in the window at
    # all. The daily files share the report-day grid, so their spans agree by
    # construction -- and the assertion below says so rather than assuming it.
    c = pl.read_csv(args.streams / f"community_deaths_daily_{s}.tsv",
                    separator="\t", null_values="NA")
    d = pl.read_csv(args.streams / f"deaths_daily_{s}.tsv", separator="\t",
                    null_values="NA")
    lo, hi = c["time"].min(), c["time"].max()
    j = (d.filter((pl.col("time") >= lo) & (pl.col("time") <= hi))
           .select(["time", f"deaths_{s}", "days_covered"])
           .join(c.select(["time", f"deaths_split_{s}", f"community_deaths_{s}",
                           pl.col("days_covered").alias("_dc_c")]),
                 on="time", how="left"))
    bad = j.filter(pl.col("days_covered") != pl.col("_dc_c"))
    if bad.height > 1:
        sys.exit(f"{bad.height} report day(s) where the death and community "
                 "spans disagree; the difference below would not be a count "
                 f"of anything:\n{bad}")
    comm = int(j[f"community_deaths_{s}"].sum())
    split = int(j[f"deaths_split_{s}"].sum())
    inwin = int(j[f"deaths_{s}"].sum())
    unclassified = inwin - split
    care = split - comm
    total_stream = int(d[f"deaths_{s}"].sum())
    w0, w1 = lo, hi

    fig, ax = plt.subplots(figsize=(14.2, 9.4))
    ax.set_xlim(0, 14.2); ax.set_ylim(0, 9.4); ax.axis("off")
    ax.text(0.1, 9.25, "Where a death goes", ha="left", va="top", fontsize=16,
            fontweight="bold", color=INK)
    ax.text(0.1, 8.82, "and which of it reaches the model",
            ha="left", va="top", fontsize=10.5, color=MUTED)

    # ---- the event, and the first loss -------------------------------------
    box(ax, 5.6, 7.85, 3.4, 0.7, "A person dies of Ebola",
        fc="#f4f4f4", ec=MUTED, tc=INK, fs=11.5, weight="bold")

    box(ax, 11.2, 7.85, 4.6, 1.5,
        "Body never swabbed\nrefusal · burial before the team · failure\n\n"
        "Never confirmed — in no stream\ncount unknown, anywhere in the source",
        fc="#ffffff", ec=UNOBS, tc=MUTED, ls=(0, (4, 3)), fs=9.5)
    arrow(ax, (7.35, 7.85), (8.8, 7.85), color=UNOBS, ls=(0, (4, 3)))

    # ---- confirmed --------------------------------------------------------
    box(ax, 5.6, 6.1, 3.4, 0.8, f"Confirmed death\n{inwin:,} in this window",
        fc="#eef3f8", ec=INK, fs=10.5, weight="bold")
    arrow(ax, (5.6, 7.48), (5.6, 6.53), label="swab+, or\ndied a known case",
          lx=-1.5, fs=9, tc=MUTED)

    # EVERY confirmed death reaches the death stream, classified or not --
    # the fact the old drawing obscured by dashing the unclassified edge.
    box(ax, 3.1, 4.3, 2.7, 0.9,
        f"deaths_{s}.tsv\n{total_stream:,} deaths, all weeks",
        fc="#ffffff", ec=INK, fs=10, weight="bold")
    arrow(ax, (4.5, 5.78), (3.4, 4.8), label="all\nof them", lx=-0.5, ly=0.25,
          fs=9, tc=MUTED)

    # ---- classified or not ------------------------------------------------
    box(ax, 6.9, 4.3, 3.2, 0.9,
        f"Classified that day\n{split:,} — the denominator",
        fc="#ffffff", ec=INK, fs=10, weight="bold")
    arrow(ax, (6.0, 5.68), (6.7, 4.79))

    box(ax, 11.2, 4.3, 4.6, 1.2,
        f"Not classified — {unclassified:,}\n"
        "report days printing no split · batch consolidations\n"
        "counted in the death stream; only the\ncommunity/care status is unknown",
        fc="#efefef", ec=UNCLASS, tc=INK, fs=9.5)
    arrow(ax, (7.0, 5.7), (9.5, 4.75), color=UNCLASS)

    # ---- the two classes --------------------------------------------------
    box(ax, 5.1, 2.5, 3.1, 0.95,
        f"First confirmed at death\n{comm:,}  ·  post-mortem swab+",
        fc="#fdece2", ec=COMM, tc=INK, fs=10, weight="bold")
    box(ax, 8.8, 2.5, 3.1, 0.95,
        f"Already a known case\n{care:,}  ·  died in CTE / CT",
        fc="#e6f0f7", ec=CARE, tc=INK, fs=10, weight="bold")
    arrow(ax, (6.5, 3.83), (5.4, 3.0), color=COMM)
    arrow(ax, (7.3, 3.83), (8.5, 3.0), color=CARE)

    # ---- the emitted stream ------------------------------------------------
    box(ax, 6.9, 0.95, 5.6, 1.1,
        f"community_deaths_{s}.tsv\n"
        f"numerator {comm:,}   ·   denominator {split:,}\n"
        f"two counts, never a ratio",
        fc="#ffffff", ec=INK, fs=10.5, weight="bold")
    arrow(ax, (5.1, 2.01), (5.9, 1.53), color=COMM)
    arrow(ax, (8.8, 2.01), (7.9, 1.53), color=CARE)

    ax.text(12.45, 0.95,
            "model infers\n"
            "P(first confirmed at death\n"
            "  |  confirmed death)\n"
            "beta-binomial", ha="center", va="center", fontsize=10,
            color=INK, linespacing=1.7)
    arrow(ax, (9.75, 0.95), (10.55, 0.95))

    # ---- legend: the three states, stated once -----------------------------
    lx, ly0, dy = 0.35, 7.9, 0.62
    ax.text(lx, ly0 + 0.5, "each box is one of three states",
            ha="left", va="center", fontsize=9, color=MUTED, style="italic")
    for i, (ec, fc, ls, lab) in enumerate([
            (KEPT, "#ffffff", "solid", "extracted and emitted\nthe model reads it"),
            (UNCLASS, "#efefef", "solid",
             "extracted, counted, unclassified\nin the death stream only"),
            (UNOBS, "#ffffff", (0, (4, 3)),
             "never observed\nno count exists")]):
        y = ly0 - i * dy
        ax.add_patch(FancyBboxPatch((lx, y - 0.11), 0.42, 0.22,
                                    boxstyle="round,pad=0.01", facecolor=fc,
                                    edgecolor=ec, linewidth=1.4, linestyle=ls))
        ax.text(lx + 0.55, y, lab, ha="left", va="center", fontsize=8.5,
                color=MUTED, linespacing=1.35)

    ax.text(0.1, 0.02,
            f"Counts: {args.scope.replace('_', '-')}, {w0} to {w1} — the "
            f"window in which the source prints the split.   "
            f"The grey state is a missing classification, not a missing "
            f"death: those {unclassified:,} are in the fitted death stream.",
            ha="left", va="bottom", fontsize=9, color=MUTED)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.out, dpi=160, bbox_inches="tight")
    print(f"  {args.out}")


if __name__ == "__main__":
    main()
