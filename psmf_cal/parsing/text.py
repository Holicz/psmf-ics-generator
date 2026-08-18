"""Small shared primitives for the parsers: errors, whitespace, dates, folding keys."""

from __future__ import annotations

import datetime as dt
import re
import unicodedata
from zoneinfo import ZoneInfo

PRAGUE = ZoneInfo("Europe/Prague")

#: Czech weekday abbreviations as published, indexed by ``date.weekday()``.
CZECH_WEEKDAYS = ("Po", "Út", "St", "Čt", "Pá", "So", "Ne")

#: Spelled-out Czech weekdays, for calendar descriptions.
CZECH_WEEKDAYS_FULL = (
    "pondělí",
    "úterý",
    "středa",
    "čtvrtek",
    "pátek",
    "sobota",
    "neděle",
)

_DATE_RE = re.compile(r"^(\d{1,2})\.(\d{1,2})\.(\d{2}|\d{4})$")
_TIME_RE = re.compile(r"^(\d{1,2}):(\d{2})$")


class ParseError(ValueError):
    """Markup did not match expectations.

    Always carries the offending URL so a failure summary can point at the page
    to go and look at.
    """

    def __init__(self, url: str, detail: str) -> None:
        super().__init__(f"{url}: {detail}")
        self.url = url
        self.detail = detail


def clean(text: str) -> str:
    """Collapse whitespace, including the non-breaking spaces psmf.cz is full of."""
    return " ".join(text.replace("\xa0", " ").split())


def parse_czech_date(value: str, *, url: str) -> dt.date:
    """Parse ``3.9.26`` (and the occasional ``3.9.2026``) into a date.

    Two-digit years are the norm on psmf.cz. They are read as 2000+yy: the site
    has no pre-2000 content, so no pivot heuristic is needed or wanted.
    """
    match = _DATE_RE.match(value.strip())
    if match is None:
        raise ParseError(url, f"unrecognised date {value!r}")
    day, month, year = (int(part) for part in match.groups())
    if len(match.group(3)) == 2:
        year += 2000
    try:
        return dt.date(year, month, day)
    except ValueError as exc:
        raise ParseError(url, f"impossible date {value!r}: {exc}") from exc


def parse_time(value: str, *, url: str) -> dt.time:
    match = _TIME_RE.match(value.strip())
    if match is None:
        raise ParseError(url, f"unrecognised time {value!r}")
    hour, minute = int(match.group(1)), int(match.group(2))
    if hour > 23 or minute > 59:
        raise ParseError(url, f"impossible time {value!r}")
    return dt.time(hour, minute)


def split_date_cell(value: str, *, url: str) -> tuple[str, dt.date]:
    """Split ``Čt 3.9.26`` into its weekday abbreviation and date.

    The published weekday is cross-checked against the parsed date. A mismatch
    means we misread the date -- a silent off-by-one here would put every
    affected fixture in a calendar on the wrong day, so it is a hard error.
    """
    parts = clean(value).split()
    if len(parts) != 2:
        raise ParseError(url, f"unrecognised date cell {value!r}")
    weekday, raw_date = parts
    date = parse_czech_date(raw_date, url=url)
    expected = CZECH_WEEKDAYS[date.weekday()]
    if weekday != expected:
        raise ParseError(
            url, f"date cell {value!r} says {weekday} but {date.isoformat()} is a {expected}"
        )
    return weekday, date


def to_prague(date: dt.date, time: dt.time) -> dt.datetime:
    """Attach the Europe/Prague zone to a published wall-clock kick-off."""
    return dt.datetime.combine(date, time, tzinfo=PRAGUE)


def normalize_search(text: str) -> str:
    """Fold text for diacritics- and case-insensitive matching.

    Mirrors the browser exactly::

        s.normalize('NFD').replace(/\\p{M}/gu, '').toLowerCase()

    so that ``mecholupska`` matches ``Měcholupská střeva`` and vice versa.
    ``str.lower`` is used rather than ``str.casefold`` precisely because
    JavaScript's ``toLowerCase`` is the thing being mirrored -- casefold would
    diverge on inputs such as "ß".
    """
    decomposed = unicodedata.normalize("NFD", text)
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return stripped.lower()
