# Registers — the hand-authored record

Everything else in this repository is fetched or derived. These files are
neither: each row is a judgement someone made after reading a page, and no
pipeline can regenerate one. Deleting a register loses knowledge; deleting
anything under `data/build/` costs a rebuild.

That is why they live here rather than under `data/raw/`, which holds what the
source published and what our own fetchers wrote.

| File | What each row asserts |
| --- | --- |
| `reconciliation_exceptions.tsv` | *I opened this page, added the printed rows, and the source does not agree with itself.* A claim about one document, keyed on its SHA-256. |
| `sitrep_number_overrides.tsv` | *This upload's filename does not state its report number or data date correctly; the page says otherwise.* |

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
