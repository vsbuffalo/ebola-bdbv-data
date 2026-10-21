"""Daily testing volume and positives, read from the laboratory prose.

SOURCE       The INSP situation reports' laboratory section. PRIMARY. Unlike
             every other series in this repository, this one has NO numeric
             cross-check lineage: INRB-UMIE transcribes the laboratory block
             as free-text sentences, so what licenses each number here must
             come from the page itself.
PRODUCES     One row per (report, province) with the day's samples analysed,
             positives, and (where the source printed one) the positivity —
             daily FLOWS, not stocks. A boolean column `rate_printed` records
             which of the two licences below admitted the row.
FITTED       Intended for the national model class: testing volume is the
             scale anchor that lets the data constrain the reporting
             probability instead of a prior.
VALIDATED BY the sentence itself, three ways at once, when the source prints
             a percentage. The reports print the positivity rate beside the
             counts, so a sentence is accepted only when it contains a UNIQUE
             pair of integers (k, N), k <= N, whose ratio reproduces the
             printed percentage to rounding tolerance. A wording variant the
             patterns have not seen cannot produce a wrong number -- it
             produces a REFUSAL, counted and printed. Downstream, the
             positives cross-check against the day's printed new confirmed
             cases. These rows carry `rate_printed = True` and `printed_pct`
             holds the page's own percentage.

             WHEN NO PERCENTAGE IS PRINTED, a weaker licence applies: the
             sample count is the integer standing next to "échantillons",
             and the positive count is the integer standing next to
             "positifs" / "résultats positifs" / "cas confirmés" / "nouveaux
             cas", tried in that priority order -- the first of these
             phrases present in the segment decides the count, so a
             subordinate clause such as "dont 85 nouveaux cas" cannot
             outrank "93 résultats positifs" earlier in the same sentence.
             Both nouns must be found and each must be the unique integer
             beside its noun in the segment, and the positive count must not
             exceed the sample count; failing either still refuses. These
             rows carry `rate_printed = False` and `printed_pct = null` --
             nothing is invented for the number the source did not print.

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
from lib.archive import held_pdfs, report_skipped  # noqa: E402

PROVINCES = {
    "ituri": "Ituri", "nord kivu": "Nord-Kivu", "sud kivu": "Sud-Kivu",
    "haut uele": "Haut-Uélé", "bas uele": "Bas-Uélé", "tshopo": "Tshopo",
    "sud ubangi": "Sud-Ubangi", "nord ubangi": "Nord-Ubangi",
}
PROV_RE = re.compile(r"\b(Ituri|Nord[-\s]Kivu|Sud[-\s]Kivu|Haut[-\s]U[ée]l[ée]"
                     r"|Bas[-\s]U[ée]l[ée]|Tshopo|Sud[-\s]Ubangi|Nord[-\s]Ubangi)\b",
                     re.I)
LAB_WORD = re.compile(r"[ée]chantillons?|pr[ée]l[èe]vements?", re.I)

# A DEATH SPLIT HAS THE SAME ARITHMETIC SHAPE AS A POSITIVITY, so the
# licence-or-refuse rule cannot tell them apart: "23 décès dont 14
# communautaires (60,9 %)" offers the pair (14, 23) reproducing 60,9 %
# exactly, and it was licensed as 14 positives out of 23 samples on
# 2026-08-02 Ituri -- a day whose real testing figures are elsewhere. The
# guard is arithmetic and the ambiguity is semantic, so no tolerance change
# fixes it; the clause has to leave the pool before the pair is chosen.
# Deaths and their community share are already extracted from the tables,
# which is where they belong.
DEATH_SPLIT = re.compile(
    r"\d+\s+d[ée]c[èe]s\s+dont\s+\d+\s+communautaires?\s*"
    r"(?:\(\s*[\d,.]+\s*%\s*\))?", re.I)
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


# WHEN NO PERCENTAGE IS PRINTED, licensed_pair has nothing to license
# against and every such sentence used to refuse as "no_printed_rate" --
# 33 of the archive's 44 refusals, 13 report-days left with no laboratory
# row at all. Some of these sentences do carry both counts in the clear,
# e.g. sitrep 092: "93 résultats positifs (336 échantillons analysés)". What
# licenses the pair here is not arithmetic but the NOUN each integer sits
# beside -- the same idiom the NEG branch below already uses for "tous
# négatifs" ("(\d+)\s+(?:nouveaux\s+)?[ée]chantillons"). SAMPLE_NOUN finds
# the sample count; POSITIVE_NOUN_TIERS finds the positive count by trying
# each phrase in priority order and stopping at the first that appears at
# all -- a lower-priority synonym is a DIFFERENT clause, not a second vote
# on the same quantity: "93 résultats positifs (...), dont 85 nouveaux cas"
# states the day's total positives and, separately, how many of them are
# newly confirmed, and the tiering is what keeps 85 from outranking 93.
# Either noun missing, or matched more than once, is not a licence -- the
# sentence still refuses, just under a name that says which check failed.
SAMPLE_NOUN = re.compile(r"(\d{1,4})\s+(?:nouveaux\s+)?[ée]chantillons?", re.I)
POSITIVE_NOUN_TIERS = (
    re.compile(r"(\d{1,4})\s+(?:r[ée]sultats\s+)?positifs?", re.I),
    re.compile(r"(\d{1,4})\s+cas\s+confirm[ée]s?", re.I),
    re.compile(r"(\d{1,4})\s+nouveaux?\s+cas\b", re.I),
)


def _noun_anchor(tiers: tuple[re.Pattern, ...], text: str) -> tuple[int | None, str]:
    """The integer beside a noun phrase, tried tier by tier. The first tier
    with any hit decides the outcome -- a unique hit licenses the count, more
    than one hit is ambiguity -- without falling through to a lower-priority
    synonym that might happen to be unique on its own. No tier matching at
    all is "missing", distinguished from "ambiguous" so the refusal names
    which failure occurred."""
    for pat in tiers:
        hits = [int(m.group(1)) for m in pat.finditer(text)]
        if not hits:
            continue
        return (hits[0], "ok") if len(hits) == 1 else (None, "ambiguous")
    return None, "missing"


def noun_adjacent_pair(text: str) -> tuple[tuple[int, int] | None, str]:
    """(samples, positives) licensed by noun adjacency alone, for a segment
    that prints no percentage. Returns (None, why) on any refusal, where why
    is one of "no_noun_anchor" (either noun missing or matched more than
    once) or "positives_exceed_samples" (both nouns found, but the reading
    is not arithmetically possible, so it is not a readable sentence)."""
    n, n_status = _noun_anchor((SAMPLE_NOUN,), text)
    k, k_status = _noun_anchor(POSITIVE_NOUN_TIERS, text)
    if n_status != "ok" or k_status != "ok":
        return None, "no_noun_anchor"
    if k > n:
        return None, "positives_exceed_samples"
    return (n, k), "ok"


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
        # Harvest from the segment with death-split clauses removed; the
        # stored sentence stays whole so the refusal is auditable.
        pool = DEATH_SPLIT.sub(" ", seg)
        pcts = [float(p.replace(",", ".")) for p in PCT.findall(pool)]
        ints = [int(x) for x in INT.findall(pool)]
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
                # "tous négatifs" is the source stating the rate in words --
                # zero -- so this row is as validated as a printed number.
                rows.append({"province": prov, "samples": int(ns[0]),
                             "positives": 0, "printed_pct": 0.0,
                             "rate_printed": True,
                             "sentence": seg.strip()[:220]})
                continue
        if not pcts:
            # No percentage anywhere in the segment: licensed_pair has
            # nothing to check a pair against, so the weaker noun-adjacency
            # licence is the only route left. It needs at least two integers
            # to have anything to try, same threshold the old
            # "no_printed_rate" refusal used.
            if len(ints) >= 2:
                got, why = noun_adjacent_pair(pool)
                if got is not None:
                    n, k = got
                    rows.append({"province": prov, "samples": n,
                                 "positives": k, "printed_pct": None,
                                 "rate_printed": False,
                                 "sentence": seg.strip()[:220]})
                elif why == "positives_exceed_samples":
                    refused.append({"why": "fallback_positives_exceed_samples",
                                    "prov": prov, "sent": seg[:160]})
                else:
                    refused.append({"why": "no_noun_anchor", "prov": prov,
                                    "sent": seg[:160]})
            continue
        if len(ints) < 2:
            continue
        got = licensed_pair(ints, pcts)
        if got is None:
            refused.append({"why": "no_unique_licensed_pair", "prov": prov,
                            "sent": seg[:160]})
            continue
        k, n, p = got
        rows.append({"province": prov, "samples": n, "positives": k,
                     "printed_pct": p, "rate_printed": True,
                     "sentence": seg.strip()[:220]})
    out, conflicts = dedupe_by_province(rows)
    refused.extend(conflicts)
    return out, refused


def dedupe_by_province(rows: list[dict]) -> tuple[list[dict], list[dict]]:
    """One row per province per report: if the section states a province
    twice with different licensed pairs, that is a conflict, not a choice --
    UNLESS one reading carries a printed rate and the other does not, in
    which case the validated reading wins outright. Two sentences about the
    same province-day disagreeing on the numbers is a genuine conflict only
    when both (or neither) are backed by the source's own percentage; a
    percentage-backed reading beating a noun-adjacency guess is the licence
    hierarchy working as designed, not an ambiguity to flag. Returns (kept
    rows, conflict refusals)."""
    seen: dict[str, int] = {}
    out: list[dict] = []
    refused: list[dict] = []
    for r in rows:
        idx = seen.get(r["province"])
        if idx is None:
            seen[r["province"]] = len(out)
            out.append(r)
            continue
        prev = out[idx]
        if (prev["samples"], prev["positives"]) == (r["samples"], r["positives"]):
            continue
        if prev["rate_printed"] and not r["rate_printed"]:
            continue  # the validated row already kept wins
        if r["rate_printed"] and not prev["rate_printed"]:
            out[idx] = r  # a validated reading supersedes the earlier guess
            continue
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
    pdfs, extra = held_pdfs(args.pdfs)
    report_skipped(extra)
    for pdf in pdfs:
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
              "printed_pct": pl.Float64, "rate_printed": pl.Boolean,
              "sentence": pl.Utf8}
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
