"""Render a Team into an RFC 5545 calendar.

Written by hand rather than with a library because the three things most
calendar clients are unforgiving about -- a real VTIMEZONE, byte-exact line
folding, and TEXT escaping -- are precisely the things a library would hide.
The generated output is checked back with ``icalendar`` in psmf_cal.validate.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterable, Iterator

from psmf_cal.models import (
    PITCHES_URL,
    SEASON_LABEL,
    SEASON_UID_TAG,
    GroupKits,
    Match,
    Team,
)
from psmf_cal.parsing.text import CZECH_WEEKDAYS_FULL

PRODID = "-//psmf-cal//PSMF calendar generator//CS"

#: The source publishes a kick-off but never an end time, so every event is
#: given this fixed length. The 5+1 rules (Pravidlo 6) are identical in all
#: four leagues -- 2 x 30 minutes plus a break of at most five -- so one
#: duration covers them all. The 75 minutes kept here is deliberately
#: generous: it absorbs the referee's added time, and a block that runs a
#: little long is less disruptive in a diary than one that ends early.
MATCH_DURATION = dt.timedelta(minutes=75)

#: Reminder lead time, as required by the brief.
ALARM_TRIGGER = "-PT3H"

_MAX_OCTETS = 75


def escape_text(value: str) -> str:
    """Escape a TEXT value per RFC 5545 section 3.3.11.

    Backslash must be replaced first, otherwise the backslashes introduced by
    the later replacements would themselves be escaped.
    """
    return (
        value.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r\n", "\\n")
        .replace("\n", "\\n")
        .replace("\r", "\\n")
    )


def fold_line(line: str) -> str:
    """Fold one content line to 75 octets, continuing with a leading space.

    The limit is defined in octets, not characters, and these calendars are full
    of Czech diacritics -- so the split is computed on the UTF-8 encoding and
    then walked back off any continuation byte, which keeps multi-byte
    characters intact.
    """
    raw = line.encode("utf-8")
    if len(raw) <= _MAX_OCTETS:
        return line

    chunks: list[bytes] = []
    start = 0
    limit = _MAX_OCTETS
    while len(raw) - start > limit:
        end = start + limit
        while end > start and (raw[end] & 0xC0) == 0x80:
            end -= 1  # never split inside a multi-byte character
        chunks.append(raw[start:end])
        start = end
        limit = _MAX_OCTETS - 1  # a continuation line spends one octet on its space
    chunks.append(raw[start:])

    head, *rest = (chunk.decode("utf-8") for chunk in chunks)
    return "\r\n ".join([head, *rest])


def _dt_local(value: dt.datetime) -> str:
    return value.strftime("%Y%m%dT%H%M%S")


def _dt_utc(value: dt.datetime) -> str:
    return value.astimezone(dt.UTC).strftime("%Y%m%dT%H%M%SZ")


def _vtimezone() -> list[str]:
    """Europe/Prague under the EU rules: last Sunday of March and of October.

    The autumn season runs from September into December, so every calendar
    straddles the October transition and clients must be told the rule rather
    than handed floating or pre-converted times.
    """
    return [
        "BEGIN:VTIMEZONE",
        "TZID:Europe/Prague",
        "X-LIC-LOCATION:Europe/Prague",
        "BEGIN:DAYLIGHT",
        "TZOFFSETFROM:+0100",
        "TZOFFSETTO:+0200",
        "TZNAME:CEST",
        "DTSTART:19700329T020000",
        "RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=-1SU",
        "END:DAYLIGHT",
        "BEGIN:STANDARD",
        "TZOFFSETFROM:+0200",
        "TZOFFSETTO:+0100",
        "TZNAME:CET",
        "DTSTART:19701025T030000",
        "RRULE:FREQ=YEARLY;BYMONTH=10;BYDAY=-1SU",
        "END:STANDARD",
        "END:VTIMEZONE",
    ]


def event_uid(team: Team, match: Match) -> str:
    """Stable identity for one fixture.

    Includes the league and the group because team slugs repeat across both: a
    slug is unique only inside one group, and group slugs such as ``1-a`` exist
    in all four leagues. Without the full path, a visitor subscribed to two
    calendars that both contain a "sparta" would have one team's fixtures
    silently overwrite the other's.
    """
    return (
        f"{team.league.key}-{team.group.slug}-{team.slug}-{SEASON_UID_TAG}-{match.round_no}@psmf.cz"
    )


def _summary(team: Team, match: Match) -> str:
    side = "doma" if match.is_home_for(team.slug) else "venku"
    return f"⚽ {match.home.name} – {match.away.name} ({side})"


def _description(team: Team, match: Match, kits: GroupKits) -> str:
    opponent = match.opponent_of(team.slug)
    at_home = match.is_home_for(team.slug)
    pitch = match.pitch
    kickoff = match.kickoff
    weekday = CZECH_WEEKDAYS_FULL[kickoff.weekday()]

    lines = [
        # No league here: a player is in exactly one, and the calendar is named
        # after it -- repeating it on every fixture is noise week after week.
        f"{match.round_no}. kolo – {team.group.label} ({SEASON_LABEL})",
        f"Soupeř: {opponent.name}",
        f"Kde hrajete: {'doma' if at_home else 'venku'}",
        f"Výkop: {weekday} {kickoff.day}. {kickoff.month}. {kickoff.year} v {kickoff:%H:%M}",
    ]

    own_kit = team.colors
    opponent_kit = kits.get(opponent.slug)
    if own_kit or opponent_kit:
        lines.append(f"Dresy: {own_kit or 'neuvedeno'} (soupeř: {opponent_kit or 'neuvedeno'})")

    lines += ["", f"Hřiště: {pitch.name} ({pitch.code})", f"Adresa: {pitch.address}"]
    if pitch.notes:
        lines.append(pitch.notes)

    lines += [
        "",
        f"Mapa: {pitch.maps_url}",
        f"Mapy.cz: {pitch.mapy_url}",
        f"Tým na psmf.cz: {team.url}",
        f"Všechna hřiště: {PITCHES_URL}",
    ]
    return "\n".join(lines)


def _event(team: Team, match: Match, kits: GroupKits, dtstamp: dt.datetime) -> Iterator[str]:
    pitch = match.pitch
    yield "BEGIN:VEVENT"
    yield f"UID:{event_uid(team, match)}"
    # Fixed for the whole run so that re-importing a regenerated file updates
    # events in place instead of looking like a fresh set every time.
    yield f"DTSTAMP:{_dt_utc(dtstamp)}"
    yield f"DTSTART;TZID=Europe/Prague:{_dt_local(match.kickoff)}"
    yield f"DTEND;TZID=Europe/Prague:{_dt_local(match.kickoff + MATCH_DURATION)}"
    yield f"SUMMARY:{escape_text(_summary(team, match))}"
    yield f"LOCATION:{escape_text(f'{pitch.name} ({pitch.code}), {pitch.address}')}"
    yield f"DESCRIPTION:{escape_text(_description(team, match, kits))}"
    if pitch.latitude is not None and pitch.longitude is not None:
        # GEO takes a bare float pair and is not a TEXT value, so it is not escaped.
        yield f"GEO:{pitch.latitude};{pitch.longitude}"
    yield f"URL:{team.url}"
    yield "TRANSP:OPAQUE"
    yield "BEGIN:VALARM"
    yield "ACTION:DISPLAY"
    yield f"TRIGGER:{ALARM_TRIGGER}"
    yield f"DESCRIPTION:{escape_text(_summary(team, match))}"
    yield "END:VALARM"
    yield "END:VEVENT"


def _lines(team: Team, kits: GroupKits, dtstamp: dt.datetime) -> Iterator[str]:
    yield "BEGIN:VCALENDAR"
    yield "VERSION:2.0"
    yield f"PRODID:{PRODID}"
    yield "CALSCALE:GREGORIAN"
    yield "METHOD:PUBLISH"
    yield f"X-WR-CALNAME:{escape_text(team.calendar_name)}"
    yield "X-WR-TIMEZONE:Europe/Prague"
    yield (
        "X-WR-CALDESC:"
        + escape_text(f"Rozpis zápasů – {team.name} ({team.league.name} {team.group.label})")
    )
    yield from _vtimezone()
    for match in team.matches:
        yield from _event(team, match, kits, dtstamp)
    yield "END:VCALENDAR"


def render_calendar(team: Team, kits: GroupKits, dtstamp: dt.datetime) -> bytes:
    """Render ``team``'s schedule as a UTF-8 .ics payload with CRLF endings."""
    folded: Iterable[str] = (fold_line(line) for line in _lines(team, kits, dtstamp))
    return ("\r\n".join(folded) + "\r\n").encode("utf-8")
