# Nord-Kivu's isolation census: from sitrep 124 the reports print two counts

## Decision: option B, implemented

Both counts are published. `care_census_nord_kivu.tsv` is unchanged in meaning:
the total, every patient hospitalised. `care_census_dedicated_nord_kivu.tsv` is
new: the part in dedicated structures, 26 rows from sitrep 124 (15 September).
No flag column was added to the total file. The new file's rows already mark the
days the split was printed, and adding a column to a file consumers vendor would
change its schema for no new information.

What changed in the extraction (`scripts/extract_care_prose.py`):

- `census_dedicated` is read only from wording that names a subset («dont N dans
  les structures normées/dédiées», «dont N dans les CTE», «: N dans les CTE/CT»,
  «(N patients aux lits des CTE/CT sur B lits)»), or from a printed occupancy
  fraction whose rate names the CTE/CT. It is kept only when smaller than the
  total.
- `beds_occupied` is the numerator of any printed occupancy fraction («84,2 %
  (315/374)»). Haut-Uélé, Tshopo and Ituri print these too, sometimes below
  their total (Haut-Uélé on sitrep 149: 45 occupied beds against 68 in
  isolation), without saying where the remainder are. So an occupied-bed count
  is not treated as a claim about structures.
- The occupancy rate is tested against the part where one is printed, under its
  own name, `occupancy_occupied`. That check licenses the part and not the
  total, which it never tested.

The consequences: the total file's post-124 rows no longer read as
contradictions (2 `contradicts` rows remain, both the source's own arithmetic).
The occupancy diagnostic divides the occupied count by the beds, so it no longer
shows Nord-Kivu above capacity from late September. The family sentence in
`registers/stream_families.tsv` says to fit one of the two, never both, and why.

Date: 2026-10-20 Project: ebola-bdbv-data Tags: care-ledger, census, nord-kivu,
stream-contract

## Context / question

`care_census_nord_kivu.tsv` publishes, per report day, the number of patients
the care pillar's Nord-Kivu bullet says are in care at the end of the day. It is
a *stock* (a reading at an instant), and a model can use it to observe an
isolation compartment directly. The question is whether that number means the
same thing across the archive. It does not obviously do so, because from
mid-September the bullet prints a second, smaller count beside it, and the
printed occupancy rate follows the smaller one.

## What the reports print, in four wordings

Every value below is read from the Nord-Kivu bullet of the care section ("Prise
en charge holistique"). *Total* is the headline count; *dedicated* is the count
the source places in treatment centres (CTE, centre de traitement Ebola; CT,
centre de transit; "structures normées" or "structures dédiées", the facilities
built to isolation standard); *ESS* (établissements de soins de santé) are
ordinary health facilities that are not CTE/CT.

| Sitreps (data dates)      | Wording                                                                                                                                           | Total   | Rate printed | What the rate is computed on                                                                    |
| ------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------- | ------- | ------------ | ----------------------------------------------------------------------------------------------- |
| ≤ 107 (≤ 29 Aug)          | «167 malades sont hospitalisés pour 206 lits, soit 81,1 % d'occupation» (100)                                                                     | 167–236 | 81–107 %     | the total: 214/206 = 103,9 % printed 103,9 % (104)                                              |
| 108–123 (30 Aug – 14 Sep) | «282 patients sont hospitalisés et le taux d'occupation global des lits en CTE/CT est en sursaturation (128,2 %)» (108)                           | 225–348 | 103–153 %    | the total, against unprinted beds: 311/220 = 141,4 % (119), 342/228 = 150,0 % (121)             |
| 124–145 (15 Sep – 6 Oct)  | «373 patients sont pris en charge en hospitalisation dont 216 dans les structures dédiées, soit un taux d'occupation global (94,7 %)» (124)       | 316–417 | 63–98 %      | the dedicated count: 216/228 = 94,7 % (124), 271/365 = 74,2 % printed «(271/365)» (144)         |
| 146–157 (7 Oct – 18 Oct)  | «468 patients (167 confirmés et 301 suspects …) sont hospitalisés : 328 dans les CTE/CT pour 374 lits, soit un taux d'occupation de 87,7 %» (152) | 445–523 | 84–95 %      | the dedicated count: «(325 patients aux lits des CTE/CT sur 354 lits)» (147), «(349/410)» (156) |

The remainder is sometimes printed outright. Sitrep 135 reads «328 patients …
dont 223 dans les CTE pour 354 lits … les 105 autres (32,0 %) étant pris en
charge dans les ESS»; 151 reads «445 patients … 333 dans les CTE/CT … et 112
(25,2 %) dans des ESS qui ne sont pas des CTE/CT». Those two close exactly
(223 + 105 = 328; 333 + 112 = 445), as do 153 and 154.

## Observations

**The total runs continuously across the change; the rate does not.** Sitrep 123
prints a total of 348 at 152,6 %; sitrep 124 prints 373 at 94,7 %. A total that
rises by 25 while the occupancy rate falls by 58 points is consistent with one
thing only: the rate's numerator changed from the total to the dedicated count.
No new beds are reported between the two days.

**Before sitrep 124 the reports do not say where the overflow was.** Through
sitrep 123 the rate is the total over the treatment-centre beds, and from sitrep
104 it exceeds 100 %, reaching 152,6 %. Patients beyond the bed count must have
been somewhere, and from sitrep 124 the reports say where: in ordinary
facilities (ESS). It is therefore likely, but not stated, that the earlier total
already included them. Nothing in the pre-124 wording settles this.

**Only Nord-Kivu prints the split.** No other province's bullet carries a "dont
N dans les structures …" clause or an ESS remainder; their totals are counted
against their own beds throughout.

**The dedicated count is bounded by capacity, and moves with it.** It runs
208–224 while Nord-Kivu has 228 dedicated beds (125–129), then 223–280 once
capacity reaches 308–365 (130–144), then 315–359 against 354–410 (146–157). Its
movements are largely the bed count's, not the epidemic's.

**The same wording problems recur in the newest vintage.** On sitreps 146–149
the total is stated as «demeuraient en isolement à la fin de la journée», and it
jumps from 417 (144) to 519 (146) before falling back to 445 (151); 523 is
printed on both 147 and 148. Sitrep 150's sentence has a missing parenthesis
(«471 patients dont 67 enfants de moins de 5 ans) sont hospitalisés») and its
parts do not close (330 + 107 = 437, not 471). Both are the source's.

## What this means for the published file today

`care_census_nord_kivu.tsv` carries the total throughout, which is the
continuous reading. From sitrep 124 its `checks` column reads `occupancy=fail`
(«contradicts»): the build tests the printed rate against total ÷ beds, and the
source now computes it on the dedicated count. That label is wrong in substance.
The source is not contradicting itself; it is computing a different ratio. The
occupancy diagnostic in `plot_figures.py` already excludes these rows for that
reason.

The interpretation stated in conversation on 2026-10-20, that the total "changed
meaning around sitrep 130 to include patients outside treatment centres", is not
supported by the full run. The evidence above points to the rate changing at
sitrep 124, with the total continuous.

## The decision, stated as two options

Both options leave `care_census_nord_kivu.tsv` meaning what it means now (the
total) and retarget the occupancy check on post-124 rows to the dedicated count,
so they stop reading as contradictions. They differ only in whether the
dedicated count is published.

- **Option A: one stream, flagged.** No new file. Rows from sitrep 124 carry a
  flag, `split_printed`, saying the source also printed a dedicated-structure
  count that day. The dedicated count stays in
  `data/build/series/care_prose.csv` as a reference column for anyone who wants
  it. *Consequence:* a model of an isolation compartment that means "in a
  treatment-centre bed" has nothing to fit after 15 September except the total,
  which includes ESS patients.
- **Option B: two streams.** Option A, plus a new stock file,
  `care_census_dedicated_nord_kivu.tsv`: the dedicated count, with rows only on
  the report days that print it (sitrep 124 onward, about 25 rows). It gets its
  own family sentence in `registers/stream_families.tsv`, saying that it is
  bounded by capacity. *Consequence:* the modelling side chooses which
  compartment to observe and can fit either, but never both against one
  compartment.

What neither option does: redefine `care_census_nord_kivu` to the dedicated
count from sitrep 124. That would splice two quantities into one column at a
date nothing in the file marks, which is the failure the stream contract exists
to prevent.

**Recommendation: Option B, leaning.** The two counts are different quantities
with different drivers: one tracks patients, the other mostly tracks beds.
Publishing both, under names that say which is which, makes the choice the
modelling side's, where it belongs. The case for A is that a 25-row, capacity-
bound series may not be worth a new file, and that is a fair call for whoever
fits it.

## Next

- Choose A or B; either way, change the occupancy check for split rows and add
  the family sentence.
- Sitreps 144 and 150 publish no total today (144: refused as ambiguous between
  417 and 271; 150: the unbalanced parenthesis). Decide whether 144's total
  should be licensed by the printed «(271/365)» closing on the dedicated count.
