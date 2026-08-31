"""Rebuild a past release's figures, so two releases can be looked at side by
side.

What it reconstructs, and what it does not. This runs TODAY's extraction over
THAT RELEASE's inputs. It answers "how did the data change between these two
releases", which is the question you ask when comparing figures — differences
you see are differences in the reports read, not in the code that read them.

It does not answer "what did release X publish at the time", because that
needs X's code as well, and the two questions want different things. Holding
the code fixed is what makes the comparison legible: otherwise a figure that
moved between r1 and r3 could have moved because a report landed or because an
extractor was fixed, and the picture cannot tell you which.

How a release's inputs are recovered. The PDF archive is not committed, but
`data/raw/sitrep_pdfs.manifest.tsv` is, one row per report the release read.
So a release's input set is recoverable from its tag even though its bytes are
not: stage that manifest beside a directory of symlinks into the real archive,
and `lib.archive.held_pdfs` reads exactly the reports the tag pinned and passes
over everything fetched since.

That only works because every extractor reads the manifest rather than globbing
the archive directory. Before that changed, a checkout of an old tag read
whatever was on disk, so no past release could be rebuilt at all.

Where the output goes. `data/build/figures/releases/<tag>/`, which is
gitignored like the rest of `data/build`. Nothing here is committed: 3.4 MB per
figure set against a repository that has already published thirty releases is
not a thing to put in git when the manifests make it reconstructible on demand.
`docs/figures/` continues to hold the current release's figures and nothing
else, so every link into it keeps working.

Reports that a release could not have read are skipped and counted, not
silently dropped — see `lib.archive`.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = "data/raw/sitrep_pdfs.manifest.tsv"
ARCHIVE = ROOT / "data/raw/sitrep_pdfs"

#: The figures worth reconstructing per release: the ones whose content is a
#: reading of the data. `availability`, `release_grid` and `response_timeline`
#: describe the archive's shape rather than the outbreak, and `validation` and
#: the two `comparison` figures need `make compare`, which needs the external
#: checkout. Kept short on purpose -- this is a comparison aid, not a mirror of
#: `make figures`.
FIGURES = ("epi_curve", "ascertainment", "ascertainment_provinces",
           "outcomes", "care_ledger",
           "national_detail", "streams_detail", "test_positivity",
           "lab_effort", "positivity_provinces")


def run(cmd: list[str], **kw) -> None:
    r = subprocess.run(cmd, cwd=ROOT, **kw)
    if r.returncode not in (0, 1):        # 1 = a reported gap, not a failure
        sys.exit(f"failed ({r.returncode}): {' '.join(cmd)}")


def slug(tag: str) -> str:
    return tag.replace("/", "-")


def stage_archive(tag: str, into: Path) -> int:
    """A PDF directory holding this release's manifest and links to the real
    bytes. Returns how many reports the release read."""
    pdfs = into / "sitrep_pdfs"
    if into.exists():
        shutil.rmtree(into)
    pdfs.mkdir(parents=True)
    manifest = into / "sitrep_pdfs.manifest.tsv"
    text = subprocess.run(["git", "show", f"{tag}:{MANIFEST}"], cwd=ROOT,
                          capture_output=True, text=True)
    if text.returncode != 0:
        sys.exit(f"{tag} has no {MANIFEST}: {text.stderr.strip()}")
    manifest.write_text(text.stdout)
    n = 0
    for line in text.stdout.splitlines()[1:]:
        name = line.split("\t")[0].strip()
        if not name:
            continue
        src = ARCHIVE / name
        if not src.exists():
            sys.exit(
                f"{tag} read {name}, which the archive no longer holds. Its "
                "figures cannot be rebuilt from this checkout; run "
                "`make fetch` or recover the report.")
        (pdfs / name).symlink_to(src.resolve())
        n += 1
    return n


def input_sets() -> dict[str, list[str]]:
    """`manifest digest -> the release tags that read that set`, oldest first.

    Thirty tags, nine sets. A revision usually fixes an extraction rather than
    adding a report, so most consecutive releases read exactly the same
    reports and their figures cannot differ under a fixed extraction. Grouping
    on the manifest is what makes a per-release archive nine directories that
    each differ from the next, rather than thirty of which twenty-one are
    copies.
    """
    import hashlib
    tags = subprocess.run(
        ["git", "tag", "-l", "data/*", "--sort=creatordate"],
        cwd=ROOT, capture_output=True, text=True).stdout.split()
    groups: dict[str, list[str]] = {}
    for t in tags:
        blob = subprocess.run(["git", "show", f"{t}:{MANIFEST}"], cwd=ROOT,
                              capture_output=True)
        if blob.returncode != 0:
            continue
        groups.setdefault(hashlib.sha256(blob.stdout).hexdigest(),
                          []).append(t)
    return groups


def build_distinct(args) -> int:
    groups = input_sets()
    print(f"{sum(len(v) for v in groups.values())} published tag(s) share "
          f"{len(groups)} distinct input set(s); building the earliest of each")
    index = []
    for tags in groups.values():
        first = tags[0]
        one = argparse.Namespace(tag=first, keep_build=args.keep_build,
                                 distinct=False)
        print(f"\n=== {first}" + (f"  (same reports as: {', '.join(tags[1:])})"
                                   if len(tags) > 1 else ""))
        build_one(one)
        index.append((first, tags))
    idx = ROOT / "data/build/figures/releases/INDEX.md"
    idx.parent.mkdir(parents=True, exist_ok=True)
    idx.write_text(
        "# Figure sets by input set\n\n"
        "Today's extraction over each release's own manifest, so a difference "
        "between two directories is a difference in the reports read and never "
        "in the code that read them.\n\n"
        "Built from the earliest tag carrying each manifest; the tags listed "
        "beside it read exactly the same reports and cannot differ.\n\n"
        + "".join(f"- `{slug(f)}/` — {f}"
                  + (f" (also {', '.join(rest[1:])})" if len(rest) > 1 else "")
                  + "\n" for f, rest in index))
    print(f"\nindex -> {idx.relative_to(ROOT)}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tag", help="a published release tag, e.g. "
                                  "data/2026-08-29-r2")
    ap.add_argument("--distinct", action="store_true",
                    help="build one figure set per DISTINCT input set rather "
                         "than per tag. Thirty published tags share nine "
                         "manifests -- most revisions were extraction fixes "
                         "over the same reports -- so building per tag would "
                         "produce twenty-one figure sets identical to their "
                         "neighbour. The earliest tag carrying each manifest "
                         "is built, and the others are listed beside it.")
    ap.add_argument("--keep-build", action="store_true",
                    help="leave the intermediate series and streams in place "
                         "for inspection rather than only the figures")
    args = ap.parse_args()

    if args.distinct:
        return build_distinct(args)
    if not args.tag:
        sys.exit("give --tag <release>, or --distinct to build one set per "
                 "distinct input set")
    tag = args.tag
    tags = subprocess.run(["git", "tag", "-l", tag], cwd=ROOT,
                          capture_output=True, text=True).stdout.split()
    if tag not in tags:
        sys.exit(f"no such release tag: {tag}")

    work = ROOT / "data/build/releases" / slug(tag)
    out = ROOT / "data/build/figures/releases" / slug(tag)
    out.mkdir(parents=True, exist_ok=True)

    return build_one(args)


def build_one(args) -> int:
    tag = args.tag
    work = ROOT / "data/build/releases" / slug(tag)
    out = ROOT / "data/build/figures/releases" / slug(tag)
    out.mkdir(parents=True, exist_ok=True)
    n = stage_archive(tag, work / "raw")
    pdfs = str(work / "raw/sitrep_pdfs")
    series, streams = work / "series", work / "streams"
    series.mkdir(parents=True, exist_ok=True)
    streams.mkdir(parents=True, exist_ok=True)
    print(f"{tag}: {n} report(s) pinned by its manifest")

    py = ["uv", "run", "python"]
    run([*py, "scripts/extract_zone_table.py", "--pdfs", pdfs,
         "--out", str(series / "zone_table.csv")])
    run([*py, "scripts/extract_zone_table.py", "--pdfs", pdfs, "--spec",
         "provincial_summary", "--out", str(series / "province_summary.csv"),
         "--quiet"])
    run([*py, "scripts/parse_provisional_caveat.py", "--pdfs", pdfs,
         "--out", str(series / "provisional_caveat.csv")])
    run([*py, "scripts/extract_prose_provinces.py", "--pdfs", pdfs,
         "--only", "12", "14", "16",
         "--out", str(series / "prose_provinces.csv")])
    run([*py, "scripts/extract_lab_prose.py", "--pdfs", pdfs, "--quiet",
         "--out", str(series / "lab_prose.csv")])
    run([*py, "scripts/extract_care_prose.py", "--pdfs", pdfs, "--quiet",
         "--out", str(series / "care_prose.csv")])
    run([*py, "scripts/extract_banner.py", "--pdfs", pdfs, "--quiet",
         "--out", str(series / "banner.csv")])
    run([*py, "scripts/extract_daily_notified.py", "--pdfs", pdfs, "--quiet",
         "--out", str(series / "daily_notified.csv")])
    run([*py, "scripts/aggregate_provinces.py",
         "--panel", str(series / "zone_table.csv"), "--pdfs", pdfs,
         "--exceptions", "registers/reconciliation_exceptions.tsv",
         "--out", str(series / "province_series.csv")])
    run([*py, "scripts/build_uganda_stream.py",
         "--uganda", "data/raw/uganda_cases.toml",
         "--out", str(streams / "uganda_exports.tsv")])
    run([*py, "scripts/build_streams.py",
         "--panel", str(series / "zone_table.csv"),
         "--summary", str(series / "province_summary.csv"),
         "--prose", str(series / "prose_provinces.csv"),
         "--lab", str(series / "lab_prose.csv"),
         "--caveat", str(series / "provisional_caveat.csv"),
         "--banner", str(series / "banner.csv"),
         "--notified", str(series / "daily_notified.csv"),
         "--care", str(series / "care_prose.csv"),
         "--geojson", "data/raw/health_zones.geojson",
         "--population", "data/raw/zone_population.csv",
         "--uganda-stream", str(streams / "uganda_exports.tsv"),
         "--out-dir", str(streams)])

    drawn = []
    for name in FIGURES:
        target = out / f"{name}.png"
        r = subprocess.run(
            [*py, "scripts/plot_figures.py", "--figure", name,
             "--build-dir", str(work), "--out", str(target)],
            cwd=ROOT, capture_output=True, text=True)
        if r.returncode == 0:
            drawn.append(name)
        else:
            print(f"  {name}: not drawn — {r.stdout.strip() or r.stderr.strip()}",
                  file=sys.stderr)
    if not args.keep_build:
        shutil.rmtree(work / "raw", ignore_errors=True)
    print(f"{len(drawn)} figure(s) -> {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
