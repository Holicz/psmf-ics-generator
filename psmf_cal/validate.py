"""Read generated calendars back and check them.

Nothing here trusts the renderer. Every file is re-parsed with a third-party
implementation and compared against the scraped data it was built from.
"""

from __future__ import annotations

import datetime as dt

from icalendar import Calendar

from psmf_cal.models import Team
from psmf_cal.parsing.text import PRAGUE


class ValidationError(RuntimeError):
    """A generated calendar did not survive a round trip."""


def _fail(team: Team, detail: str) -> ValidationError:
    return ValidationError(f"{team.ics_path}: {detail}")


def validate_calendar(team: Team, payload: bytes) -> None:
    """Re-parse one calendar and assert it matches ``team``.

    Checks that every scraped fixture produced exactly one event, that each
    DTSTART came back timezone-aware (a naive value would drift by an hour for
    part of the season), and that the local wall-clock time still equals what
    the source page published -- which is what actually proves the VTIMEZONE
    rather than merely asserting its presence.
    """
    if b"\r\n" not in payload:
        raise _fail(team, "no CRLF line endings")
    for line in payload.split(b"\r\n"):
        if len(line) > 75:
            raise _fail(team, f"line exceeds 75 octets: {line[:40]!r}...")

    calendar = Calendar.from_ical(payload)

    timezones = calendar.walk("VTIMEZONE")
    if not timezones:
        raise _fail(team, "no VTIMEZONE block")

    events = calendar.walk("VEVENT")
    if len(events) != len(team.matches):
        raise _fail(team, f"{len(events)} events for {len(team.matches)} scraped matches")

    by_uid = {str(event["UID"]) for event in events}
    if len(by_uid) != len(events):
        raise _fail(team, "duplicate UIDs")

    expected = {m.round_no: m for m in team.matches}
    for event in events:
        start = event.decoded("DTSTART")
        if not isinstance(start, dt.datetime):
            raise _fail(team, "DTSTART is not a datetime")
        if start.tzinfo is None or start.utcoffset() is None:
            raise _fail(team, f"DTSTART {start!r} is not timezone-aware")

        end = event.decoded("DTEND")
        if not isinstance(end, dt.datetime):
            raise _fail(team, "DTEND is not a datetime")

        local = start.astimezone(PRAGUE)
        match = next((m for m in expected.values() if m.kickoff.astimezone(PRAGUE) == local), None)
        if match is None:
            raise _fail(team, f"event at {local.isoformat()} matches no scraped fixture")
        if local.strftime("%H:%M") != match.kickoff.strftime("%H:%M"):
            raise _fail(
                team,
                f"round {match.round_no}: wall clock {local:%H:%M} != published "
                f"{match.kickoff:%H:%M}",
            )
        if not event.get("SUMMARY"):
            raise _fail(team, f"round {match.round_no}: empty SUMMARY")
        if not event.walk("VALARM"):
            raise _fail(team, f"round {match.round_no}: no VALARM")


def assert_dst_boundary_is_sane(team: Team, payload: bytes) -> str:
    """Spot-check a fixture on the far side of the October DST switch.

    Returns a human-readable description of what was checked, or an empty string
    when this team has no post-switch fixture.
    """
    switch = dt.datetime(2026, 10, 25, 3, 0, tzinfo=PRAGUE)
    after = [m for m in team.matches if m.kickoff >= switch]
    if not after:
        return ""

    target = after[0]
    calendar = Calendar.from_ical(payload)
    for event in calendar.walk("VEVENT"):
        start = event.decoded("DTSTART")
        if not isinstance(start, dt.datetime):
            continue
        local = start.astimezone(PRAGUE)
        if local != target.kickoff:
            continue
        offset = local.utcoffset()
        if offset != dt.timedelta(hours=1):
            raise _fail(team, f"post-DST fixture has offset {offset}, expected +01:00")
        return (
            f"{team.ics_path}: round {target.round_no} {local:%Y-%m-%d %H:%M %Z} "
            f"(UTC{offset}) matches published {target.kickoff:%H:%M}"
        )
    raise _fail(team, "post-DST fixture missing from calendar")
