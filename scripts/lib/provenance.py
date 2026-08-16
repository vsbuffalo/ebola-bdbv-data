"""Shared fetch + provenance helpers.

Every networked download in this project goes through `fetch()`, which records
the source URL, a sha256 of the payload, its size and the fetch date in
raw/PROVENANCE.tsv. That file is committed, so any raw artefact can be traced
to where it came from and checked for drift without re-fetching.

Paths are always derived at runtime from this file's location -- never
hardcoded (see CLAUDE.md).
"""

from __future__ import annotations

import datetime as dt
import hashlib
import urllib.parse
import urllib.request
from pathlib import Path

# scripts/lib/provenance.py -> parents[0] is lib/, [1] is scripts/, [2] is the
# repo root. Derived from this file's own location rather than the working
# directory, so a rule can be invoked from anywhere.
REPO_ROOT = Path(__file__).resolve().parents[2]
PROVENANCE = REPO_ROOT / "data" / "raw" / "PROVENANCE.tsv"

# INSP blocks default user agents with HTTP 403; a browser UA returns 200.
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15"

_HEADER = "path\tsource_url\tsha256\tbytes\tfetched_utc\n"


def _encode(url: str) -> str:
    """Percent-encode non-ASCII path characters.

    Many INSP filenames contain a literal degree sign (SitRep_..._N°_73...pdf),
    which urllib cannot put on the wire as-is. `safe="/%"` leaves any already
    percent-encoded sequence untouched.
    """
    p = urllib.parse.urlsplit(url)
    return urllib.parse.urlunsplit(
        (p.scheme, p.netloc, urllib.parse.quote(p.path, safe="/%"), p.query, p.fragment)
    )


def fetch(url: str, dest: Path, *, timeout: int = 60) -> bytes:
    """Download `url` to `dest`, returning the payload and logging provenance."""
    req = urllib.request.Request(_encode(url), headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        payload = resp.read()
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(payload)
    _record(dest, url, payload)
    return payload


def record(dest: Path, url: str) -> None:
    """Log provenance for a file this project WROTE from `url`.

    Used where the payload is assembled from several requests (e.g. a paginated
    API), so the bytes worth hashing are the emitted artefact rather than any
    single response.
    """
    _record(dest, url, dest.read_bytes())


def _record(dest: Path, url: str, payload: bytes) -> None:
    rel = dest.resolve().relative_to(REPO_ROOT).as_posix()
    row = "\t".join(
        [
            rel,
            url,
            hashlib.sha256(payload).hexdigest(),
            str(len(payload)),
            dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d"),
        ]
    )
    PROVENANCE.parent.mkdir(parents=True, exist_ok=True)
    existing = {}
    if PROVENANCE.exists():
        lines = PROVENANCE.read_text().splitlines()
        for line in lines[1:]:
            if line.strip():
                existing[line.split("\t", 1)[0]] = line
    existing[rel] = row
    PROVENANCE.write_text(_HEADER + "\n".join(existing[k] for k in sorted(existing)) + "\n")
