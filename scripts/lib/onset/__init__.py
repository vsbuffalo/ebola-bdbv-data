"""The onset-figure reader: sitrep PDFs -> the digitised symptom-onset curve.

The INSP situation reports embed, as a raster image, an epidemic curve by
symptom-onset date drawn from the DHIS2 line list -- the only epi-dated
observation in the source. This package reads it: locates the embedded
rasters, identifies the onset chart by its content (never its caption),
calibrates axes and palette from the figure's own furniture, measures each
bar twice by independent methods, and gates every vintage against the
figure's printed total and its temporal neighbours.

Design and requirements: notes/2026-08-28-onset-digitiser-design.md and
notes/2026-08-28-onset-digitiser-requirements.md. The failure modes this
package exists to avoid are documented there with measurements; the short
version is that a reader upstream let single pixels terminate measurements,
and re-reads of one identical chart moved a published reproduction number.

Modules, in pipeline order:
  pdfimg     PDF -> embedded chart-sized rasters, with decoded-pixel identity
  identify   raster -> what kind of chart it is, from content
  calibrate  raster -> axes, palette, dates (or a refusal)
  readers    raster + calibration -> per-bar (alive, dead) counts, twice
  gates      pure functions over the published tables
  assemble   snapshots -> dedup -> reporting triangle
"""
