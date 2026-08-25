"""Fail-closed access to pipeline artefacts, for the data document.

Two failures occur in every analysis repository, and this module exists to turn
both into loud render errors instead of stale documents:

  * The document embeds a figure or table that no rule produces -- so it can
    never be regenerated, and drifts silently from the inputs.
  * The document reads an artefact that a rule produces but a refactor moved --
    so the render works from a stale file until someone notices.

Every read the document makes therefore goes through here: `figure()` and
`load()` require the path to be DECLARED by the pipeline and PRESENT on disk;
`source()` requires the path to be a committed input under `data/raw/` or
`registers/`, tracked by git. Anything else raises, and the render stops.

Deliberately standalone -- it knows about Make, polars and git, and nothing
about Ebola -- because the same two failures occur everywhere and this may
become a shared package.

ADAPTED FROM THE REFERENCE PROJECT'S SNAKEMAKE VERSION, with its three recorded
defects fixed here: `source()` now infers the separator from the suffix instead
of hardcoding tab (a `.csv` register was being read as one column and passing
by luck); a failed subprocess is an error rather than an empty declared-set
that blames the document; and the pipeline definition is a parameter rather
than a hardcoded tuple.

WHAT "DECLARED" MEANS UNDER MAKE. The reference introspected
`snakemake --summary` for the workflow's output list. This pipeline is a
Makefile, which has no equivalent query, so the declared set is every
`data/build/...` path that appears literally in the Makefile's text. That is an
approximation with a known edge: a path built by wildcard expansion would not
appear literally. This pipeline names every output in full, and the check below
fails closed -- an undeclared path is refused even if present on disk.
"""

from __future__ import annotations

import functools
import json
import re
import subprocess
import sys
from pathlib import Path

import polars as pl

ROOT = Path(__file__).resolve().parents[1]
PIPELINE = ROOT / "Makefile"

_SOURCE_DIRS = ("data/raw/", "registers/")


@functools.lru_cache(maxsize=None)
def _declared() -> frozenset[str]:
    text = PIPELINE.read_text()
    return frozenset(re.findall(r"data/build/[\w./\-]+", text))


def _require_declared(rel: str) -> Path:
    if rel not in _declared():
        raise SystemExit(
            f"_guard: `{rel}` is read by the document but appears in no rule "
            f"of {PIPELINE.name}. Either the artefact moved, or it was never "
            "given a rule -- both are exactly what this check exists to catch.")
    path = ROOT / rel
    if not path.exists():
        raise SystemExit(
            f"_guard: `{rel}` is declared by the pipeline but has not been "
            "built. Run `make build` (and `make figures` / `make compare`).")
    return path


def _sep(path: Path) -> str:
    return "\t" if path.suffix == ".tsv" else ","


def figure(rel: str) -> str:
    """Assert the figure is pipeline-built and present; returns the path."""
    _require_declared(rel)
    return rel


def load(rel: str) -> pl.DataFrame:
    # `NA` IS DECLARED AS THE NULL TOKEN. A published flow stream carries a row
    # on every report day it spans and writes `NA` where the source said
    # nothing, so that a model accumulating between observations closes its
    # interval on schedule. polars does not read `NA` as null by default: one
    # hole would turn a count column into a string column, and a plot of that
    # column draws the strings at the axis baseline -- a hole rendered as an
    # observed zero, in a figure that looks entirely plausible.
    path = _require_declared(rel)
    return pl.read_csv(path, separator=_sep(path), infer_schema_length=None,
                       null_values="NA")


def load_json(rel: str) -> dict:
    return json.loads(_require_declared(rel).read_text())


def source(rel: str) -> pl.DataFrame:
    """A committed input: raw reference data or a hand-authored register.

    No pipeline can regenerate a claim about what a printed page says, so these
    are not declared outputs -- what stands in for the declaration is that git
    tracks them. An untracked source is refused: the document must not cite
    evidence that is not in the record.
    """
    if not rel.startswith(_SOURCE_DIRS):
        raise SystemExit(
            f"_guard: source() is for committed inputs under "
            f"{' or '.join(_SOURCE_DIRS)}; got `{rel}`.")
    r = subprocess.run(["git", "ls-files", "--error-unmatch", rel],
                       capture_output=True, text=True, cwd=ROOT)
    if r.returncode != 0:
        raise SystemExit(
            f"_guard: `{rel}` is not tracked by git ({r.stderr.strip()}). "
            "A source the record does not hold cannot be cited.")
    path = ROOT / rel
    return pl.read_csv(path, separator=_sep(path), comment_prefix="#",
                       infer_schema_length=None)


def stat(value) -> str:
    """Format a number for prose. Exists so a typed literal is visible in a diff."""
    if isinstance(value, int):
        return f"{value:,}"
    return f"{value:,.3g}"
