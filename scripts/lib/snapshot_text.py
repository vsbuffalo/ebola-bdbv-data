"""The searchable text of a fetched document, for checking quotes against it.

HTML is reduced to its visible text; a PDF with a text layer goes through
`pdftotext`. Both are then normalised the same way -- typographic apostrophes
and quotes to ASCII, every run of whitespace (including the no-break and
narrow no-break spaces French typesetting uses) to one space, case folded -- so
a quote copied from a rendered page matches the bytes it was read from without
depending on how the page wrapped. Normalising more than that (dropping
punctuation, stemming) would let a misquote pass, so it stops there.
"""

from __future__ import annotations

import html
import re
import subprocess
from pathlib import Path

_SCRIPT = re.compile(r"<(script|style|noscript)\b.*?</\1>", re.I | re.S)
_TAG = re.compile(r"<[^>]+>")
_QUOTES = str.maketrans({"’": "'", "‘": "'", "“": '"',
                         "”": '"', "«": '"', "»": '"',
                         "–": "-", "—": "-"})


def normalise(text: str) -> str:
    return re.sub(r"\s+", " ", text.translate(_QUOTES)).strip().casefold()


def document_text(path: Path) -> str:
    raw = path.read_bytes()
    if raw.startswith(b"%PDF"):
        text = subprocess.run(["pdftotext", "-q", "-layout", str(path), "-"],
                              capture_output=True, text=True).stdout
    else:
        text = html.unescape(_TAG.sub(" ", _SCRIPT.sub(" ", raw.decode("utf-8", "replace"))))
    return normalise(text)
