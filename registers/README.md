# Registers — the hand-authored record

Everything else in this repository is fetched or derived. These files are
neither: each row is a judgement someone made after reading a page, and no
pipeline can regenerate one. Deleting a register loses knowledge; deleting
anything under `data/build/` costs a rebuild.

That is why they live here rather than under `data/raw/`, which holds what the
source published and what our own fetchers wrote.

| File                            | What each row asserts                                                                                                                                                                                                                                                           |
| ------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `reconciliation_exceptions.tsv` | _I opened this page, added the printed rows, and the source does not agree with itself._ A claim about one document, keyed on its SHA-256.                                                                                                                                      |
| `sitrep_number_overrides.tsv`   | _This upload's filename does not state its report number or data date correctly; the page says otherwise._                                                                                                                                                                      |
| `external_sitreps.tsv`          | _INSP does not serve this report; we hold it from a secondary archive, its PDF is committed because nothing can fetch it again, and here is where it came from._ Also carries the one place this project files a report against its own printed date, with the argument for it. |
| `rejected_routes.tsv`           | _This extraction route reads this document's values as something they are not, in a way no identity can catch from inside._                                                                                                                                                     |
| `zone_province_overrides.tsv`   | _The page states which province this row belongs to, but the table's geometry does not carry it._                                                                                                                                                                               |
| `zone_aliases_local.csv`        | _This printed spelling and this shapefile name are the same health zone._                                                                                                                                                                                                       |
| `stream_families.tsv`           | _This is what the streams of this observation family measure, in one sentence._ Keyed on the family, never on the file, so four province variants of one quantity cannot drift apart.                                                                                           |

The last one is the only register that is not a judgement about a page: it is a
judgement about a **quantity**, and it exists because the generated data
dictionary at `data/build/streams/README.md` can measure a stream's span, its
row count and its columns off the file itself, but cannot say what the numbers
mean. A stream this pipeline publishes whose family has no row there stops the
build, so a new stream cannot ship undocumented.

## Rules that apply to every register here

- **Keyed on the document, not on the report number.** INSP revises reports and
  republishes them under the same number. An entry names a file hash so a
  corrected report returns to the failing set instead of inheriting a judgement
  made about its predecessor.
- **Exact, not permissive.** An entry licenses one specific value — a residual
  of exactly +5, a specific report number — and nothing else. If our reading
  changes, the entry stops matching and the report fails again. That is the
  difference between a record and a mute button.
- **Every row carries who checked and against what.** An entry without
  provenance cannot be re-examined, and these are exactly the claims that will
  need re-examining when a report is revised.
- **Inference is labelled as inference.** Where an entry generalises from what a
  page states to a neighbouring case the page does not mention, it says so in
  the note.
