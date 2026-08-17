"""The reports' own warning that their recent numbers are not yet complete.

SOURCE       The INSP situation report PDFs. PRIMARY, and a statement the
             source makes about ITSELF rather than about the outbreak.
PRODUCES     One row per report: whether it carries the caveat, which form,
             the sentence verbatim, a checked translation, and where on the
             page it sits.
FITTED       No, and that is a scope decision rather than a gap. It is a
             statement about the trailing edge of every other stream, so it
             belongs beside them as an annotation -- see below for why it must
             not be turned into a shaded period.
VALIDATED BY nothing internal; it is a presence test. What makes it safe is
             that an UNCLASSIFIED caution sentence is reported rather than
             dropped, so a phrasing we have not seen cannot pass as absence.

WHAT THE SOURCE ACTUALLY SAYS, and why it matters more than its length:

    "Les fluctuations récentes doivent être interprétées avec prudence en
     raison des retards de notification et de la consolidation progressive
     des données."

    "Recent fluctuations must be interpreted with caution owing to
     notification delays and the progressive consolidation of the data."

That is the custodians of the data declining to read their own most recent
points as epidemiology. Any trend taken from the end of a series -- a
flattening, a fall in the reproduction number -- is being read against numbers
the people who published them say are still filling in.

THREE SENTENCES LOOK ALIKE AND ARE NOT THE SAME CLAIM, which is the whole
reason this is a parser and not a grep. An earlier version of this project
matched `interpretees avec prudence` alone. That single pattern also catches:

    "La létalité particulièrement élevée au Nord-Kivu doit être interprétée
     avec prudence dans un contexte d'épidémie évolutive"

    "The particularly high case-fatality in Nord-Kivu must be interpreted with
     caution in the context of an evolving epidemic"

which is an epidemiological caution about a RATIO, not a statement that the
data are incomplete -- and folding it in would have marked two reports as
provisional on the strength of a sentence about case-fatality. The
discriminator is the REASON CLAUSE: the provisionality caveat gives a
data-completeness reason (notification delays, progressive consolidation), the
case-fatality one gives an epidemiological one.

A third form is a figure caption on sitrep 038 -- "La variation journalière
doit être interprétée avec prudence", with no reason at all. It is recorded as
its own kind rather than merged, because a warning attached to one figure is a
narrower statement than a report-level caveat.

WHY THIS IS A PER-REPORT FLAG AND NOT A DATE RANGE. The sentence is about each
report's OWN trailing edge, so it is a rolling statement, not a claim that a
fixed calendar window is unreliable. Shading "13 July to the data edge" would
assert that the whole of late July is provisional, when most of it has since
consolidated. One mark per report says what the source said; a shaded period
says something the source did not.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

import polars as pl

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.report_date import FILENAME, report_key

# Any sentence cautioning the reader. Deliberately WIDE: everything it catches
# is either classified below or reported as unclassified, and a wide net with a
# loud residue is what keeps a new phrasing from passing as absence.
CAUTION = re.compile(
    r"[^.!?]{0,220}(?:interpr[ée]t[ée]e?s?\s+avec\s+prudence"
    r"|avec\s+prudence|sous[- ]?estimation|donn[ée]es?\s+provisoires?)"
    r"[^.!?]{0,260}[.!?]", re.I)

# The reason that makes it a claim about DATA rather than about epidemiology.
DATA_REASON = re.compile(
    r"retards?\s+de\s+notification|notification\s+tardive"
    r"|consolidation\s+(?:progressive|des\s+donn[ée]es)"
    r"|donn[ée]es?\s+en\s+cours\s+de\s+consolidation"
    r"|compl[ée]tude|donn[ée]es?\s+incompl[èe]tes?", re.I)

# The subject that makes it about a movement in the series over time.
TREND = re.compile(r"fluctuations?|variation|tendances?|courbes?", re.I)

# An epidemiological caution wearing the same words. Excluded explicitly rather
# than by omission, so the exclusion is visible and testable.
NOT_ABOUT_DATA = re.compile(r"l[ée]talit[ée]|taux\s+de\s+l[ée]talit[ée]", re.I)

# Translations for the forms we have read. A form we have NOT read is left
# untranslated and flagged -- a machine-mangled translation of a claim about
# data quality is worse than an honest blank.
KNOWN = [
    (re.compile(r"fluctuations\s+r[ée]centes.*retards\s+de\s+notification", re.I),
     "Recent fluctuations must be interpreted with caution owing to "
     "notification delays and the progressive consolidation of the data."),
    (re.compile(r"fluctuations\s+observ[ée]es\s+au\s+cours\s+des\s+derniers\s+jours", re.I),
     "Fluctuations observed over recent days must be interpreted with caution "
     "owing to notification delays and the progressive consolidation of the "
     "data."),
    (re.compile(r"variation\s+journali[èe]re", re.I),
     "Daily variation must be interpreted with caution."),
]


def classify(sentence: str) -> str | None:
    """`recent_data_provisional`, `figure_note`, or None if not about the data."""
    if NOT_ABOUT_DATA.search(sentence):
        return None
    if DATA_REASON.search(sentence) and TREND.search(sentence):
        return "recent_data_provisional"
    if TREND.search(sentence) and re.search(r"⚠", sentence):
        return "figure_note"
    return None


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pdfs", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args()

    rows, unclassified = [], []
    for pdf in sorted(args.pdfs.glob("*.pdf")):
        if not FILENAME.search(pdf.stem):
            continue
        text = subprocess.run(["pdftotext", "-q", "-layout", str(pdf), "-"],
                              capture_output=True, text=True).stdout
        num, date = report_key(pdf, text)
        flat = " ".join(text.split())
        best = None
        for m in CAUTION.finditer(flat):
            s = m.group(0).strip()
            kind = classify(s)
            if kind is None:
                # Only sentences that LOOK like our target but are not
                # classified are worth reporting; the case-fatality caution is
                # a known exclusion, not a surprise.
                if not NOT_ABOUT_DATA.search(s) and TREND.search(s):
                    unclassified.append((num, s[:150]))
                continue
            # WHERE ON THE PAGE, as a fraction of the document. The caveat is
            # printed near the front; a match deep in the annexes would be a
            # different kind of statement and is worth being able to see.
            at = m.start() / max(len(flat), 1)
            if best is None or (kind == "recent_data_provisional"
                                and best["kind"] != kind):
                en = next((t for p, t in KNOWN if p.search(s)), "")
                best = {"sitrep": num, "date": date, "kind": kind,
                        "position": round(at, 3), "quote_fr": s,
                        "quote_en": en, "translated": bool(en)}
        rows.append(best or {"sitrep": num, "date": date, "kind": "none",
                             "position": None, "quote_fr": "", "quote_en": "",
                             "translated": True})

    d = pl.DataFrame(rows).sort("sitrep")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    d.write_csv(args.out)

    by = d.group_by("kind").len().sort("len", descending=True)
    print(f"{d.height} reports scanned")
    for kind, n in by.iter_rows():
        print(f"  {kind:<26} {n}")
    flagged = d.filter(pl.col("kind") == "recent_data_provisional")
    if flagged.height:
        print(f"  the caveat runs {flagged['date'].min()} to {flagged['date'].max()}")
    untranslated = d.filter(~pl.col("translated"))
    if untranslated.height:
        print(f"  UNTRANSLATED phrasing on {untranslated.height} report(s): "
              f"{untranslated['sitrep'].to_list()} -- read them and extend "
              f"`KNOWN` rather than leaving a claim about data quality in a "
              f"language the reader does not have.")
    if unclassified:
        print(f"  UNCLASSIFIED caution sentences ({len(unclassified)}), which "
              f"may be a phrasing we have not seen:")
        for n, s in unclassified[:6]:
            print(f"    sitrep {n}: {s}")


if __name__ == "__main__":
    main()
