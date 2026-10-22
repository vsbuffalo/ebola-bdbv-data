"""What a situation report says that the reports before it did not.

    python scripts/sitrep_digest.py 159            # -> data/build/summaries/sitrep_159/

Input to the daily summary agent (`scripts/daily_summary.py`), and the one
part of it that is deterministic. INSP copies much of each report forward from
the last -- challenge rows, boilerplate, sometimes numbers that should have
moved -- and some sentences run unchanged for weeks (a strike sentence sits in
every report from 063 to 081). A reader comparing only with yesterday calls
those new whenever they skip a day, so each sentence of report N is classed
against the previous LOOKBACK reports we hold:

  new        like nothing in any of them
  updated    a sentence of report N-1 with different numbers or light
             rewording (INSP rephrases its daily summary lines from report
             to report, so exact matching would call them all new)
  returning  absent from N-1 but present in an earlier report of the window
  repeated   word for word in N-1 (counted, not listed)

Sentences come from `pdftotext` in reading order, joined within a paragraph
and split at sentence punctuation; table cells mostly fail the five-word
filter, which is intended -- the tables are read by the extraction, and the
full layout text is written alongside for the agent to check them.

Writes, per report: `text.txt` (layout text of N), `previous.txt` (of N-1),
and `digest.md` (the classified sentences).
"""

from __future__ import annotations

import argparse
import difflib
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PDFS = ROOT / "data/raw/sitrep_pdfs"
OUT = ROOT / "data/build/summaries"
LOOKBACK = 5
MIN_WORDS = 5
SIMILAR = 0.75     # masked-text similarity at which a sentence is a rewording


def pdf_of(n: int) -> Path | None:
    hits = sorted(PDFS.glob(f"sitrep_{n:03d}_*.pdf"))
    return hits[0] if hits else None


def held_before(n: int, k: int) -> list[int]:
    """The k highest report numbers we hold below n, newest first."""
    nums = sorted({int(m.group(1)) for p in PDFS.glob("sitrep_*.pdf")
                   if (m := re.match(r"sitrep_(\d{3})_", p.name))})
    return [x for x in reversed(nums) if x < n][:k]


def pdftext(pdf: Path, layout: bool) -> str:
    cmd = ["pdftotext", *(["-layout"] if layout else []), str(pdf), "-"]
    return subprocess.run(cmd, capture_output=True, text=True, check=True).stdout


def sentences(text: str) -> list[str]:
    out: list[str] = []
    for para in re.split(r"\n\s*\n", text):
        flat = re.sub(r"\s+", " ", para.replace("-\n", "")).strip()
        for s in re.split(r"(?<=[.;!?])\s+(?=[A-ZÀ-Ý«(•\d])", flat):
            s = s.strip(" •-–")
            if len(re.findall(r"[A-Za-zÀ-ÿ]{2,}", s)) >= MIN_WORDS:
                out.append(s)
    return list(dict.fromkeys(out))          # keep order, drop repeats


def mask(s: str) -> str:
    return re.sub(r"\d[\d\s.,]*", "#", s.lower())


def closest(s: str, pool: dict[str, str]) -> str | None:
    """The sentence in `pool` (masked -> original) that `s` rewords, if any."""
    m = mask(s)
    if m in pool:
        return pool[m]
    best, score = None, SIMILAR
    for pm, orig in pool.items():
        sm = difflib.SequenceMatcher(None, m, pm, autojunk=False)
        if sm.real_quick_ratio() >= score and sm.quick_ratio() >= score \
                and (r := sm.ratio()) >= score:
            best, score = orig, r
    return best


def classify(today: list[str], prev: list[str], older: list[list[str]]):
    prev_exact = set(prev)
    prev_masked = {mask(s): s for s in prev}
    older_masked = {mask(s): s for ss in older for s in ss}
    new, updated, returning, repeated = [], [], [], 0
    for s in today:
        if s in prev_exact:
            repeated += 1
        elif (before := closest(s, prev_masked)) is not None:
            updated.append((before, s))
        elif closest(s, older_masked) is not None:
            returning.append(s)
        else:
            new.append(s)
    return new, updated, returning, repeated


def digest(n: int, lookback: int = LOOKBACK) -> Path:
    pdf = pdf_of(n)
    if pdf is None:
        raise SystemExit(f"sitrep {n:03d} is not in {PDFS.relative_to(ROOT)}")
    window = held_before(n, lookback)
    out = OUT / f"sitrep_{n:03d}"
    out.mkdir(parents=True, exist_ok=True)
    (out / "text.txt").write_text(pdftext(pdf, layout=True))
    texts = {k: sentences(pdftext(pdf_of(k), layout=False)) for k in window}
    if window:
        (out / "previous.txt").write_text(pdftext(pdf_of(window[0]), layout=True))
    today = sentences(pdftext(pdf, layout=False))
    new, updated, returning, repeated = classify(
        today, texts[window[0]] if window else [], [texts[k] for k in window[1:]])
    prev = f"{window[0]:03d}" if window else "none"
    lines = [f"# Sitrep {n:03d} against the reports before it", "",
             f"Compared with {prev} (the previous report held) and, for "
             f"returning text, {', '.join(f'{k:03d}' for k in window[1:]) or 'nothing older'}. "
             f"{len(today)} sentences: {len(new)} new, {len(updated)} updated, "
             f"{len(returning)} returning, {repeated} repeated word for word "
             f"from {prev} (not listed).", "",
             "## New: like nothing in the previous reports", ""]
    lines += [f"- {s}" for s in new] or ["- (none)"]
    lines += ["", f"## Updated: a sentence of {prev} with new numbers or rewording", ""]
    lines += [f"- before: {a}\n  after:  {b}" for a, b in updated] or ["- (none)"]
    lines += ["", f"## Returning: absent from {prev}, present in an earlier report", ""]
    lines += [f"- {s}" for s in returning] or ["- (none)"]
    (out / "digest.md").write_text("\n".join(lines) + "\n")
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("sitreps", type=int, nargs="+")
    ap.add_argument("--lookback", type=int, default=LOOKBACK)
    args = ap.parse_args()
    for n in args.sitreps:
        print(digest(n, args.lookback).relative_to(ROOT))


if __name__ == "__main__":
    main()
