"""Daily testing volume and positives, read from the laboratory prose.

SOURCE       The INSP situation reports' laboratory section. PRIMARY. Unlike
             every other series in this repository, this one has NO numeric
             cross-check lineage: INRB-UMIE transcribes the laboratory block
             as free-text sentences, so what licenses each number here must
             come from the page itself.
PRODUCES     One row per (report, province) with the day's samples analysed,
             positives, and the printed positivity — daily FLOWS, not stocks.
FITTED       Intended for the national model class: testing volume is the
             scale anchor that lets the data constrain the reporting
             probability instead of a prior.
VALIDATED BY the sentence itself, three ways at once. The reports print the
             positivity rate beside the counts, so a sentence is accepted
             only when it contains a UNIQUE pair of integers (k, N), k <= N,
             whose ratio reproduces the printed percentage to rounding
             tolerance. A wording variant the patterns have not seen cannot
             produce a wrong number -- it produces a REFUSAL, counted and
             printed. Downstream, the positives cross-check against the
             day's printed new confirmed cases.

WHY COMBINATORIC RATHER THAN PATTERNED. The wording varies enormously --
"115 nouveaux échantillons collectés et analysés (positivité 39,1% ; n=45)",
"89 nouveaux résultats positifs (59 vivants et 30 décès) parmi les 288
nouveaux échantillons reçus et analysés (Taux de positivité : 30,9%)",
"le Nord-Kivu a confirmé 8 nouveaux cas dont 3 décès parmi 133 échantillons
analysés (6,0%)" -- and a per-wording regex would be a museum of one-off
patterns, each a silent failure when the source rephrases. The percentage is
the invariant: whatever the sentence's shape, the two numbers that matter
are the ones that reproduce it. Extra integers in the sentence (the
living/dead split, a zone count) cannot collide unless they happen to form
the same ratio, in which case the sentence is AMBIGUOUS and refused.

FLOWS ONLY. A sentence is admitted only if it marks the day's new activity
("nouveaux", "dernières 24", "du jour"). The early vintage also prints
cumulative sample counts ("Au total, 109 échantillons..."); those are a
stock, and mixing them into a flow series is the exact defect the
stock-vs-flow rule exists to prevent. Cumulative-looking lab sentences are
counted separately, not parsed.
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

PROVINCES = {
    "ituri": "Ituri", "nord kivu": "Nord-Kivu", "sud kivu": "Sud-Kivu",
    "haut uele": "Haut-Uélé", "bas uele": "Bas-Uélé", "tshopo": "Tshopo",
}
PROV_RE = re.compile(r"\b(Ituri|Nord[-\s]Kivu|Sud[-\s]Kivu|Haut[-\s]U[ée]l[ée]"
                     r"|Bas[-\s]U[ée]l[ée]|Tshopo)\b", re.I)
LAB_WORD = re.compile(r"[ée]chantillons?|pr[ée]l[èe]vements?", re.I)
FLOW_WORD = re.compile(r"nouveaux?|nouvelles?|derni[èe]res?\s+24|du\s+jour", re.I)
PCT = re.compile(r"(\d{1,2}(?:[.,]\d{1,2})?)\s*%")
#: The lookahead also refuses `,\d` and `.\d`: a decimal percentage's integer
#: part ("2,6%" -> 2) otherwise joins the pool, and on sitrep 040 the phantom
#: pair (2, 76) -> 2.63% collided with the true (1, 39) -> 2.56%, turning a
#: perfectly licensed sentence into an ambiguity refusal.
INT = re.compile(r"(?<![\d,.%])(\d{1,4})(?!\d|[.,]\d|\s*%)")


def _norm_prov(s: str) -> str:
    import unicodedata
    t = unicodedata.normalize("NFKD", s)
    t = "".join(c for c in t if not unicodedata.combining(c))
    return PROVINCES[re.sub(r"[\s-]+", " ", t.lower()).strip()]


def licensed_pair(ints: list[int], pcts: list[float]) -> tuple[int, int, float] | None:
    """The unique (positives, samples) pair whose ratio reproduces a printed
    percentage. The tolerance covers both rounding and the source's habit of
    TRUNCATING (1/6 prints as 16,6%): one decimal -> 0.15, integer percent
    -> 0.55. More than one satisfying pair is ambiguity, and ambiguity is
    refusal."""
    hits = []
    for p in pcts:
        tol = 0.55 if float(p).is_integer() else 0.15
        for i, k in enumerate(ints):
            for j, n in enumerate(ints):
                if i == j or n == 0 or k > n:
                    continue
                if abs(100.0 * k / n - p) <= tol:
                    hits.append((k, n, p))
    uniq = {(k, n) for k, n, _ in hits}
    if len(uniq) != 1:
        return None
    return hits[0]


def extract(pdf: Path) -> tuple[list[dict], list[dict]]:
    text = subprocess.run(["pdftotext", "-q", "-layout", str(pdf), "-"],
                          capture_output=True, text=True).stdout
    flat = re.sub(r"\s+", " ", text)
    rows, refused = [], []
    # PROVINCE-ANCHORED SEGMENTS, not sentences. The lab prose defeats every
    # sentence heuristic in some vintage: bullet lists lose their full stops
    # when flattened, the parentheticals contain semicolons ("39,1% ; n=45"),
    # and the modern vintage chains four provinces through one sentence with
    # "tandis que". What is stable is that each province's figures FOLLOW its
    # name and precede the next province's. So each mention of a province
    # opens a segment that runs to the next province mention (or a hard
    # sentence break, or 260 characters), and the licence is applied per
    # segment.
    STOCK = re.compile(r"\bcumul|au\s+total|depuis\s+le\s+d[ée]but"
                       r"|au\s+\d{1,2}\s+\w+\s+20\d\d", re.I)
    # THE LABORATOIRE SECTION IS DAILY BY CONSTRUCTION -- it reports the
    # day's actions -- and its bullet vintage states no flow word at all:
    # "Ituri : 82 échantillons collectés et analysés (18 positifs...)".
    # Proof it is a flow: the positives equal the day's printed new confirmed
    # cases (sitrep 020: 18 = 18; sitrep 070: 51 = 51). Segments inside the
    # section therefore default to flow, with a stock marker still
    # overriding; segments elsewhere in the document keep the strict rule.
    lab_lo, lab_hi = -1, -1
    mlab = re.search(r"(?:\d[\d.]*\.?\s*)?Laboratoire\b", flat)
    if mlab:
        lab_lo = mlab.start()
        mnext = re.search(r"Pr[ée]vention\s+et\s+Contr[ôo]le|PCI\b"
                          r"|Points?\s+d.[Ee]ntr[ée]e|Vaccination"
                          r"|Communication|Prise\s+en\s+charge",
                          flat[lab_lo:])
        lab_hi = lab_lo + (mnext.start() if mnext else 2500)
    mentions = [m for m in PROV_RE.finditer(flat)]
    for idx, m in enumerate(mentions):
        end = mentions[idx + 1].start() if idx + 1 < len(mentions) \
            else m.end() + 260
        end = min(end, m.end() + 260)
        # A bullet ends a segment as surely as the next province does: the
        # figures after "● Le taux de positivité..." belong to the bullet,
        # not to the province list that happened to close just before it --
        # sitrep 007's national 17/37 was briefly Sud-Kivu's (a province
        # with three cases) through exactly that leak.
        stop = re.search(r"\.\s+[A-Z0-9]|[●•▪]", flat[m.end():end])
        if stop:
            end = m.end() + stop.start() + 1
        seg = flat[m.start():end]
        if not LAB_WORD.search(seg):
            continue
        prov = _norm_prov(m.group(1))
        pcts = [float(p.replace(",", ".")) for p in PCT.findall(seg)]
        ints = [int(x) for x in INT.findall(seg)]
        # Flow-ness may be stated once for the whole passage ("Au cours des
        # dernières 24 heures..." heading a chain of provinces), so a little
        # preceding context votes too -- but a stock marker INSIDE the
        # segment overrides: "le cumul des échantillons" is a stock however
        # the passage opened.
        ctx = flat[max(0, m.start() - 160):m.start()]
        in_lab = lab_lo <= m.start() < lab_hi
        if STOCK.search(seg):
            if pcts and ints:
                refused.append({"why": "not_a_flow", "prov": prov,
                                "sent": seg[:160]})
            continue
        if not (in_lab or FLOW_WORD.search(seg) or FLOW_WORD.search(ctx)):
            if pcts and len(ints) >= 2:
                refused.append({"why": "no_flow_marker", "prov": prov,
                                "sent": seg[:160]})
            continue
        # "tous revenus négatifs" / "aucun résultat positif" is zero positives
        # stated in words -- a licence as explicit as a printed rate. The
        # sample count must sit adjacent to its noun, uniquely.
        NEG = re.compile(r"tous\s+(?:sont\s+)?(?:revenus\s+)?n[ée]gatifs?"
                         r"|aucun\s+(?:nouveau\s+)?(?:r[ée]sultat\s+)?positif",
                         re.I)
        if not pcts and NEG.search(seg):
            ns = re.findall(r"(\d{1,4})\s+(?:nouveaux\s+)?[ée]chantillons", seg)
            if len(ns) == 1:
                rows.append({"province": prov, "samples": int(ns[0]),
                             "positives": 0, "printed_pct": 0.0,
                             "sentence": seg.strip()[:220]})
                continue
        if not pcts or len(ints) < 2:
            if len(ints) >= 2:
                refused.append({"why": "no_printed_rate", "prov": prov,
                                "sent": seg[:160]})
            continue
        got = licensed_pair(ints, pcts)
        if got is None:
            refused.append({"why": "no_unique_licensed_pair", "prov": prov,
                            "sent": seg[:160]})
            continue
        k, n, p = got
        rows.append({"province": prov, "samples": n, "positives": k,
                     "printed_pct": p, "sentence": seg.strip()[:220]})
    # One row per province per report: if the section states a province twice
    # with different licensed pairs, that is a conflict, not a choice.
    seen: dict[str, dict] = {}
    out = []
    for r in rows:
        prev = seen.get(r["province"])
        if prev is None:
            seen[r["province"]] = r
            out.append(r)
        elif (prev["samples"], prev["positives"]) != (r["samples"], r["positives"]):
            refused.append({"why": "conflicting_sentences", "prov": r["province"],
                            "sent": r["sentence"][:160]})
    return out, refused


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pdfs", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()
    args.out.parent.mkdir(parents=True, exist_ok=True)

    rows, status = [], []
    for pdf in sorted(args.pdfs.glob("*.pdf")):
        if not FILENAME.search(pdf.stem):
            continue
        num, date = report_key(pdf)
        got, refused = extract(pdf)
        for r in got:
            rows.append({"sitrep": num, "date": date, **r})
        status.append({"sitrep": num, "date": date, "n_parsed": len(got),
                       "n_refused": len(refused),
                       "refused": "; ".join(f"{r['why']}({r['prov']})"
                                            for r in refused[:4])})
        if not args.quiet and (got or refused):
            print(f"  {pdf.stem}  parsed {len(got)} province(s)"
                  + (f", refused {len(refused)}" if refused else ""))

    schema = {"sitrep": pl.Int64, "date": pl.Utf8, "province": pl.Utf8,
              "samples": pl.Int64, "positives": pl.Int64,
              "printed_pct": pl.Float64, "sentence": pl.Utf8}
    pl.DataFrame(rows, schema=schema).write_csv(args.out)
    st = pl.DataFrame(status)
    st.write_csv(args.out.with_name(args.out.stem + "_status.csv"))

    n_any = st.filter(pl.col("n_parsed") > 0).height
    n_ref = st.filter(pl.col("n_refused") > 0).height
    print(f"\n{st.height} reports scanned; {n_any} yield licensed lab rows "
          f"({len(rows)} province-days); {n_ref} carry refused lab sentences "
          "(see the status file -- a refusal is a wording the licence has "
          "not seen, never a guessed number)")


if __name__ == "__main__":
    main()
