"""Parse https://www.psmf.cz/hriste/ into a code -> Pitch map.

The directory is one table: complex name, one or more pitch codes, then an
address followed by free-form Czech notes. Several codes routinely share a row
(STER1/STER2/STER3 are three surfaces in one complex); each becomes its own
Pitch entry pointing at the shared text, since the notes are what tell you
which numbered surface is which.
"""

from __future__ import annotations

import re
from urllib.parse import unquote

from bs4 import BeautifulSoup, Tag

from psmf_cal.models import Pitch
from psmf_cal.parsing.text import ParseError, clean

_EXPECTED_HEADERS = ("Název hřiště", "Zkratka hřiště")
_GPS_RE = re.compile(r"GPS:\s*(-?\d+\.\d+)\s+(-?\d+\.\d+)")


def _coordinates(href: str) -> tuple[float | None, float | None]:
    """Pull latitude/longitude out of the directory's mapy.cz link."""
    match = _GPS_RE.search(unquote(href))
    if match is None:
        return None, None
    return float(match.group(1)), float(match.group(2))


def _split_address_and_notes(cell: Tag) -> tuple[str, str]:
    """First <br>-delimited line is the address; everything after it is notes."""
    lines = [clean(line) for line in cell.get_text("\n").split("\n")]
    lines = [line for line in lines if line]
    if not lines:
        return "", ""
    return lines[0], "\n".join(lines[1:])


def parse_pitches(html: str, url: str) -> dict[str, Pitch]:
    soup = BeautifulSoup(html, "lxml")
    table = soup.find("table")
    if not isinstance(table, Tag):
        raise ParseError(url, "no pitch table found")

    rows = table.find_all("tr")
    if not rows:
        raise ParseError(url, "pitch table has no rows")

    headers = tuple(clean(cell.get_text()) for cell in rows[0].find_all(["th", "td"]))
    if len(headers) < 3 or headers[:2] != _EXPECTED_HEADERS:
        raise ParseError(url, f"unexpected pitch table headers {headers!r}")

    pitches: dict[str, Pitch] = {}
    for row in rows[1:]:
        cells = row.find_all("td")
        if len(cells) != 3:
            raise ParseError(url, f"pitch row has {len(cells)} cells, expected 3")

        name = clean(cells[0].get_text())
        anchors = [a for a in cells[1].find_all("a") if a.get("name")]
        if not anchors:
            raise ParseError(url, f"pitch row {name!r} lists no codes")
        address, notes = _split_address_and_notes(cells[2])
        if not address:
            raise ParseError(url, f"pitch row {name!r} has no address")

        for anchor in anchors:
            code = clean(str(anchor["name"]))
            latitude, longitude = _coordinates(str(anchor.get("href", "")))
            if code in pitches:
                raise ParseError(url, f"duplicate pitch code {code!r}")
            pitches[code] = Pitch(
                code=code,
                name=name,
                address=address,
                notes=notes,
                latitude=latitude,
                longitude=longitude,
            )

    if not pitches:
        raise ParseError(url, "pitch directory produced no entries")
    return pitches
