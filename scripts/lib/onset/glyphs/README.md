# The onset-figure glyph atlas

Exemplars of the digits and parentheses the onset figures print, cut from the
archive's own renders and matched against by `lib/onset/glyphs.py`. The readers
use them for exactly two numbers no PDF text layer carries: the y-axis tick
labels (the pixels-per-case rate and the gridline step) and the title's printed
total `(n = ...)`, the checksum every digitised vintage reconciles against.

Each subdirectory is one glyph class (`lparen`/`rparen` stand for the
parentheses); each file is one exemplar, 14x18 grayscale, ink bright, produced
by cropping a segmented component to its box, inverting, and Lanczos-resizing —
`glyphs.py:_normalise` is the reference implementation, and any new exemplar
must go through it.

Provenance: segmented from the y-axis margins and title strips of the distinct
onset renders of sitreps 059, 069, 083, 087, 088, 092, 098 and 102 (both
title-size and axis-size text, both document eras, JPEG and lossless), clustered
by correlation, and labelled by eye against the source images. Cross-checks
applied at labelling: a cluster harvested from the y margins can only be an axis
digit, and a title digit must occur in that vintage's printed n. Filenames carry
the bootstrap cluster number; it has no meaning beyond uniqueness.

If a future render defeats the atlas (a new font, a new size), the failure is
loud — calibration refuses the vintage with the unmatched glyphs named — and the
fix is to add labelled exemplars here, through `_normalise`, in a commit that
says which render they came from.
