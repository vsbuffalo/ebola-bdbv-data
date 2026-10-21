# Refreshing the comparison sources: five disagreements, none ours

Date: 2026-10-20 Project: ebola-bdbv-data Tags: validation, inrb-umie,
epiforecasts-scan, source-defects

## Context / question

The two renderings this pipeline is only *checked against* — INRB-UMIE's manual
transcription and the epiforecasts scan — had been pinned since mid-August, so
four fifths of our zone-days had nothing to be compared with. Both pins were
moved to their current heads, and the comparison re-run. Every new disagreement
was then settled against the page: for each, which reading does the PDF print?

## Setup

- INRB-UMIE BDBV2026-Data: `df7d1c5` (13 Aug, ends 11 Aug) → `db4aee1` (20 Oct,
  through SitRep 157). The comparison reads
  `data/insp_sitrep/processed/insp_sitrep__cumulative_confirmed_{cases,deaths}__daily.csv`,
  joined on data date.
- epiforecasts/BVDOutbreakSize scan: a local-copy snapshot of 72 reports →
  `924c0aa`, 135 reports, now pinned in `external.lock` and fetched by
  `make scan-refresh` at that commit.
- Each disagreement read against the zone table (Tableau 2), the printed
  province subtotals, the narrative sentence and the neighbouring reports, by
  two read-only agents, with page text quoted.

## Measurements

| Comparison                                             | Old pins      | New pins      |
| ------------------------------------------------------ | ------------- | ------------- |
| INRB-UMIE, zone-day cases equal                        | 2,142 / 2,151 | 5,592 / 5,609 |
| INRB-UMIE, zone-day deaths equal                       | 2,036 / 2,041 | 5,490 / 5,499 |
| INRB-UMIE, rows disagreeing                            | 14            | 23            |
| Scan, national cumulative cases equal                  | 71 / 71       | 133 / 134     |
| Scan, front-page tiles (deaths, recoveries, isolation) | 1 differs     | 2 differ      |

The nine new INRB-UMIE rows are sitrep 095 (eight zones) and sitrep 102 (one).
Sitrep 070 Rimba, which looked new, is one of the original fourteen: re-running
the comparison functions against the old pin reproduces it.

## Observations, item by item

| # | Report, field                              | Ours             | Theirs | What the page prints                                                                                                                        | Verdict                                                     |
| - | ------------------------------------------ | ---------------- | ------ | ------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------- |
| 1 | 095 (17 Aug), 8 zones, cases/deaths        | e.g. Isiro 47/22 | 42/19  | «Isiro 47 22 46,8%»; every province subtotal closes on our rows (Haut-Uélé 145, Tshopo 14), and INRB's values would break them (140, 13)    | INRB transcription: values carried forward from 15 August   |
| 2 | 102 (24 Aug), Boga deaths                  | 2                | 1      | «Boga 2 2 100,0% 1 1 … 1»: 2 cases, 2 deaths, one new death that day; the Ituri subtotal closes only with 2                                 | INRB transcription: the new death applied a day late        |
| 3 | 070 (23 Jul), Rimba cases                  | 8                | 7      | «Rimba 8 4 50,0% 1 0 0 0», and the narrative lists «Rimba (1)» among the day's new cases; 069 prints 7, 071 prints 8                        | INRB transcription: the day's increment missed              |
| 4 | 089 (11 Aug), national cases               | 4,566            | 4,567  | The banner, the prose and the Total row all print 4 566; the five province rows sum to 4 567, as does 4 449 (088) + 118 new                 | Source self-disagreement; the scan chose the sum, by design |
| 5 | 136 (27 Sep), patients in isolation (tile) | 817              | 803    | The page-1 tile prints 817; the care prose prints «Ainsi, 803 patients demeuraient en isolement», and its five province censuses sum to 803 | Source self-disagreement; the scan used the prose census    |

## Interpretation

**No extraction bug of ours.** In all five, our value is the number the page
prints in the place our reader reads.

**Items 1–3 are INRB-UMIE transcription errors**, and the mechanism of item 1 is
worth recording because it is general. The copy of the 17 August report
INRB-UMIE holds is a different printing from ours: headed «SitRep N°094 … 17
août», where ours is N°095, and its zone table lists only the zones with new
cases in the past 24 hours. Their protocol carries forward the last value for a
zone absent from the table. They never transcribed our 094 (16 August), where
the increments for Damas, Nyankunde, Kalunguta and the rest appear, so the
carried value was 15 August's. Isiro, which *is* printed in their copy as 47/22,
was missed outright.

**A source finding: INSP issued alternately numbered printings between 094 and
102.** By header and hash, INRB-UMIE's 094 is dated 17 August (ours: 16), their
096 is 19 August (ours: 18), their "101" is 24 August (ours: 23, with 102 for
24), their "102" is byte-identical to our 103, and they hold no 095. Both
lineages date rows by the printed «Date de rapportage», so the comparison joins
correctly; anyone matching the two by report number in that stretch is off by
one. Our index lists one upload each for those numbers, and the alternate
printings do not appear in it; whether INSP ever posted them or sent them to
INRB-UMIE directly is not known.

**Items 4–5 are the source printing two different numbers**, and the scan's own
notes say it chose the other one deliberately. They are not transcription
differences, and the comparison currently counts them as if they were.

## Next

- Decide what the comparison does with a source self-disagreement: compare like
  with like (our parts sum for 089, a separate column for the 136 prose census),
  or keep the printed values and mark the rows as known source disagreements.
  Recommendation: mark them, because what the comparison is for is
  transcription, and both lineages transcribed correctly.
- Sitrep 089's national case residual of 1 (printed Total 4 566 against rows
  summing to 4 567) is reported as failing on every build and excused nowhere;
  `registers/reconciliation_exceptions.tsv` holds only 089's Ituri deaths entry.
  It needs a register row stating what the page prints.
- Consider reporting items 1–3 to INRB-UMIE, with the page text, as issues on
  their repository.
