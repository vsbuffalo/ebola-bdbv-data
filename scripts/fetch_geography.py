"""The health-zone geography and population for the provinces this outbreak
has reached, cut from the nationwide reference to the reports' own frame.

WHY A FRAME AND NOT THE WHOLE COUNTRY. `build_streams.populations` uses this
as a DENOMINATOR, and the reports state their own: sitrep 108 reads «60 des
151 (39,7%) zones de santé *des six provinces* restent affectées», and sitrep
119 widens it -- «Avec l'ajout de la zone de santé de Bulu dans la province de
Sud Ubangi nouvellement touchée, la RDC compte actuellement 62 zones de santé
sur 167 (37,1%) affectées et 7 provinces touchées». So the affected-zone
fraction those sentences quote is a fraction of THIS set, and taking all 519
zones in the upstream file instead would silently re-scale every per-capita
quantity to the whole country.

WHY THIS SCRIPT EXISTS AT ALL. Both reference files were fetched once, by
hand, on 2026-08-16 and committed with a provenance row but no rule that
regenerates them -- so when the source's frame moved from 151 zones to 167
there was nothing to re-run, and the choice of frame lived only in whatever
command someone typed that day. `AFFECTED` below is now that choice, written
down, and re-running this reproduces both files from it.

THE FRAME IS DECLARED, NOT DISCOVERED. It would be easy to derive `AFFECTED`
from the provinces the extraction has seen cases in, and that would be wrong
in a specific way: the denominator would then move every time a case appeared
somewhere new, so a per-capita rate would change for two unrelated reasons at
once and neither would be visible in the number. A province is added here when
a human reads the sentence that adds it, and the sitrep that said so is cited
on the line.

THE COUNT IS CHECKED AGAINST THE SOURCE'S OWN. `--expect-zones` fails the run
if the cut does not come out at the number the reports print, which is the one
external check available on a frame assembled from a third-party file.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.provenance import REPO_ROOT, fetch, record

#: Upstream nationwide references, both from INRB-UMIE's repository. Pinned by
#: URL here and by sha256 in `data/raw/PROVENANCE.tsv` on every run.
GEOJSON_URL = ("https://raw.githubusercontent.com/INRB-UMIE/BDBV2026-Data/"
               "main/build/drc_health_zones.geojson")
POPULATION_URL = ("https://raw.githubusercontent.com/INRB-UMIE/BDBV2026-Data/"
                  "main/data/worldpop/processed/worldpop__pop_count__static.csv")

#: The provinces the reports say this outbreak has reached, each with the
#: report that said so. Spellings are the UPSTREAM GEOJSON's, which differ from
#: the reports' own (`Haut-Uele` against `Haut-Uélé`); `aggregate_provinces`
#: owns the mapping between the two and is not duplicated here.
AFFECTED = {
    "Ituri": "sitrep 005, the first report of this epidemic",
    "Nord-Kivu": "sitrep 005",
    "Sud-Kivu": "sitrep 011",
    "Haut-Uele": "sitrep 062",
    "Tshopo": "sitrep 062",
    "Bas-Uele": "sitrep 100",
    # «la province de Sud Ubangi nouvellement touchée ... 62 zones de sante
    # sur 167 (37,1%) affectees et 7 provinces touchees»
    "Sud-Ubangi": "sitrep 119 (2026-09-10), one case in Bulu",
}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--geojson-out", type=Path,
                    default=REPO_ROOT / "data/raw/health_zones.geojson")
    ap.add_argument("--population-out", type=Path,
                    default=REPO_ROOT / "data/raw/zone_population.csv")
    ap.add_argument("--expect-zones", type=int, default=167,
                    help="the health-zone count the reports themselves print "
                         "for the affected frame; the run fails if the cut "
                         "does not come out at it.")
    args = ap.parse_args()

    scratch = args.geojson_out.parent / ".upstream"
    scratch.mkdir(parents=True, exist_ok=True)
    geo_raw = scratch / "drc_health_zones.geojson"
    pop_raw = scratch / "worldpop_pop_count_static.csv"
    fetch(GEOJSON_URL, geo_raw, timeout=180)
    fetch(POPULATION_URL, pop_raw, timeout=180)

    geo = json.loads(geo_raw.read_text())
    unknown = sorted(set(AFFECTED) - {f["properties"].get("province")
                                      for f in geo["features"]})
    if unknown:
        raise SystemExit(
            f"{unknown} named in AFFECTED but absent from the upstream "
            "geography: either the upstream spelling changed or the province "
            "does not exist there. Refusing to cut a frame around a province "
            "that contributes no zones and so no population.")

    kept = [f for f in geo["features"]
            if f["properties"].get("province") in AFFECTED]
    if len(kept) != args.expect_zones:
        by_prov = {}
        for f in kept:
            by_prov[f["properties"]["province"]] = \
                by_prov.get(f["properties"]["province"], 0) + 1
        raise SystemExit(
            f"the affected frame cut to {len(kept)} health zones but the "
            f"reports print {args.expect_zones}. Per province: {by_prov}. "
            "Either a province joined and AFFECTED has not been told, or the "
            "upstream file re-drew a boundary -- both want a human.")

    # Upstream names the column `pop_count`; the committed reference has always
    # called it `population`, and `build_streams` reads that name. The rename
    # was done by hand in the original fetch and is written down here so it is
    # part of the rule rather than part of whatever someone typed once.
    names = {f["properties"]["nom"] for f in kept}
    rows = list(csv.DictReader(io.StringIO(pop_raw.read_text())))
    if rows and "pop_count" not in rows[0]:
        raise SystemExit(
            f"upstream population file has columns {list(rows[0])}, with no "
            "`pop_count` to read: the column this depends on was renamed.")
    pop = [{"nom": r["nom"], "population": r["pop_count"]}
           for r in rows if r["nom"] in names]
    if missing := sorted(names - {r["nom"] for r in pop}):
        raise SystemExit(
            f"{len(missing)} zone(s) in the frame carry no population "
            f"upstream, and a zone with no people is not a denominator: "
            f"{', '.join(missing[:5])}")

    # Sorted so the committed files are a stable diff: an upstream reordering
    # must not look like a change of content.
    kept.sort(key=lambda f: (f["properties"]["province"], f["properties"]["nom"]))
    args.geojson_out.write_text(
        json.dumps({"type": "FeatureCollection", "features": kept},
                   ensure_ascii=False, separators=(",", ":")))
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=["nom", "population"],
                       lineterminator="\n")
    w.writeheader()
    for r in sorted(pop, key=lambda r: r["nom"]):
        w.writerow({"nom": r["nom"], "population": r["population"]})
    args.population_out.write_text(buf.getvalue())

    record(args.geojson_out, GEOJSON_URL)
    record(args.population_out, POPULATION_URL)
    geo_raw.unlink()
    pop_raw.unlink()
    scratch.rmdir()

    total = sum(float(r["population"]) for r in pop)
    print(f"  {len(kept)} health zones across {len(AFFECTED)} affected "
          f"provinces, {total:,.0f} people")
    print(f"  {args.geojson_out.relative_to(REPO_ROOT)}")
    print(f"  {args.population_out.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
