# Data pipeline entry points. Networked steps are separate from ordinary builds
# by design: `build` and `doc` never touch the network, so a rebuild can never
# silently change what the source says.

.PHONY: check fetch verify build test

## check   -- is the archive current, and does the source still look the same?
##            Exit 0 current, 1 behind, 2 the source moved, 3 unreachable.
##            The ONLY check here that looks outward: everything else asks
##            whether the reports we hold are consistent, not whether we hold
##            the reports that exist.
check:
	@uv run python scripts/check_upstream.py

## fetch   -- NETWORKED. Re-read the index and fetch any PDF we do not hold.
##            Run `check` first: when it reports CHANGED, this may do the wrong
##            thing quietly, because the predicate that decides what a report
##            IS is the thing that moved.
fetch:
	uv run python scripts/fetch_sitrep_index.py --out data/raw/insp_sitrep_index.tsv
	uv run python scripts/fetch_sitrep_pdfs.py --index data/raw/insp_sitrep_index.tsv \
		--out data/raw/sitrep_pdfs --manifest data/raw/sitrep_pdfs.manifest.tsv

## verify  -- OFFLINE. Every held PDF hashes to what the manifest records.
verify:
	uv run python scripts/verify_archive.py --pdfs data/raw/sitrep_pdfs \
		--manifest data/raw/sitrep_pdfs.manifest.tsv

## build   -- OFFLINE. PDFs -> health-zone extraction -> province aggregation.
##            Stops with exit 2 if a province total disagrees with the sum of
##            its parts; that is a finding, not a nuisance.
build:
	uv run python scripts/extract_zone_table.py \
		--pdfs data/raw/sitrep_pdfs --out data/build/series/zone_table.csv
	uv run python scripts/extract_zone_table.py \
		--pdfs data/raw/sitrep_pdfs --spec provincial_summary \
		--out data/build/series/province_summary.csv --quiet
	uv run python scripts/extract_prose_provinces.py \
		--pdfs data/raw/sitrep_pdfs --only 12 14 16 \
		--out data/build/series/prose_provinces.csv
	uv run python scripts/aggregate_provinces.py \
		--panel data/build/series/zone_table.csv \
		--pdfs data/raw/sitrep_pdfs \
		--exceptions registers/reconciliation_exceptions.tsv \
		--out data/build/series/province_series.csv

## test    -- the pure-function tests.
test:
	uv run pytest tests/ -q
