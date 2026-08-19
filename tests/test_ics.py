"""ICS rendering: escaping, folding on byte length, timezone handling."""

from __future__ import annotations

import datetime as dt

import pytest
from icalendar import Calendar

from psmf_cal.ics import MATCH_DURATION, escape_text, event_uid, fold_line, render_calendar
from psmf_cal.models import Team
from psmf_cal.validate import (
    ValidationError,
    assert_dst_boundary_is_sane,
    validate_calendar,
)

KITS = {"kktnc-on-tour": "bílá, černá", "patespool": "zlatá", "real-oranjes": "oranžová, modrá"}
VET_KITS = {"dynamo-uk-vet": "černá, bílá", "santa-dominica-vet": "černo-bílá"}


class TestEscaping:
    def test_backslash_is_escaped_first(self) -> None:
        """Escaping ';' before the backslash would double-escape what we introduced."""
        assert escape_text("a\\b") == r"a\\b"
        assert escape_text(r"a\;b") == r"a\\\;b"

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("a;b", r"a\;b"),
            ("a,b", r"a\,b"),
            ("a\nb", r"a\nb"),
            ("a\r\nb", r"a\nb"),
            ("Kovanecká, Praha 9", r"Kovanecká\, Praha 9"),
        ],
    )
    def test_special_characters(self, raw: str, expected: str) -> None:
        assert escape_text(raw) == expected

    def test_colon_is_not_escaped(self) -> None:
        """RFC 5545 requires escaping only backslash, semicolon, comma and newline."""
        assert escape_text("Výkop: 20:30") == "Výkop: 20:30"

    def test_diacritics_pass_through_untouched(self) -> None:
        assert escape_text("Měcholupská střeva") == "Měcholupská střeva"


class TestFolding:
    def test_short_lines_are_untouched(self) -> None:
        assert fold_line("SUMMARY:krátké") == "SUMMARY:krátké"

    def test_exactly_75_octets_is_not_folded(self) -> None:
        line = "X" * 75
        assert fold_line(line) == line

    def test_76_octets_folds(self) -> None:
        assert fold_line("X" * 76) == "X" * 75 + "\r\n X"

    def test_every_folded_segment_fits_in_75_octets(self) -> None:
        """The limit is octets, and Czech text is mostly two-byte characters."""
        line = "DESCRIPTION:" + "Měcholupská střeva a Houbařův Ráj, ěščřžýáíé. " * 12
        for segment in fold_line(line).split("\r\n"):
            assert len(segment.encode("utf-8")) <= 75

    def test_folding_never_splits_a_multibyte_character(self) -> None:
        """A naive 75-character split would tear 'ř' in half and corrupt the file."""
        line = "DESCRIPTION:" + "ř" * 200
        folded = fold_line(line)
        assert folded.replace("\r\n ", "") == line  # decodes cleanly, nothing lost
        folded.encode("utf-8").decode("utf-8")

    def test_unfolding_restores_the_original(self) -> None:
        line = "DESCRIPTION:" + "Hřiště č. 1 je nejblíže hale, č. 3 nejdále. " * 6
        assert fold_line(line).replace("\r\n ", "") == line

    def test_continuation_lines_begin_with_one_space(self) -> None:
        segments = fold_line("SUMMARY:" + "á" * 120).split("\r\n")
        assert len(segments) > 1
        assert all(segment.startswith(" ") for segment in segments[1:])

    def test_emoji_outside_the_bmp_survives(self) -> None:
        """The ⚽ prefix plus a long name must not be torn apart."""
        line = "SUMMARY:⚽ " + "Slavoj Dětská obrna TJ – Měcholupská střeva (venku) " * 3
        assert fold_line(line).replace("\r\n ", "") == line


class TestUid:
    def test_is_deterministic(self, kktnc: Team) -> None:
        first = kktnc.matches[0]
        assert event_uid(kktnc, first) == event_uid(kktnc, first)

    def test_includes_the_league_and_the_group(self, kktnc: Team) -> None:
        """Slugs are unique only within a group, and group slugs repeat across
        leagues, so a UID needs both to identify a fixture."""
        assert event_uid(kktnc, kktnc.matches[0]) == "hl-7-h-kktnc-on-tour-2026p-1@psmf.cz"

    def test_does_not_collide_across_leagues(self, kktnc: Team, dynamo: Team) -> None:
        """The failure this guards against is silent: two calendars sharing a UID
        overwrite each other inside the visitor's client, not here."""
        assert event_uid(dynamo, dynamo.matches[0]) == "vet-1-a-dynamo-uk-vet-2026p-1@psmf.cz"
        mine = {event_uid(kktnc, m) for m in kktnc.matches}
        theirs = {event_uid(dynamo, m) for m in dynamo.matches}
        assert not mine & theirs

    def test_is_unique_per_round(self, kktnc: Team) -> None:
        uids = {event_uid(kktnc, m) for m in kktnc.matches}
        assert len(uids) == len(kktnc.matches)


class TestRenderedCalendar:
    def test_render_is_byte_reproducible(self, kktnc: Team, stamp: dt.datetime) -> None:
        """A fixed DTSTAMP means re-importing updates events instead of duplicating."""
        assert render_calendar(kktnc, KITS, stamp) == render_calendar(kktnc, KITS, stamp)

    def test_uses_crlf_endings(self, kktnc: Team, stamp: dt.datetime) -> None:
        data = render_calendar(kktnc, KITS, stamp)
        assert data.endswith(b"\r\n")
        assert b"\n" not in data.replace(b"\r\n", b"")

    def test_is_valid_utf8(self, kktnc: Team, stamp: dt.datetime) -> None:
        render_calendar(kktnc, KITS, stamp).decode("utf-8")

    def test_no_line_exceeds_75_octets(self, kktnc: Team, stamp: dt.datetime) -> None:
        data = render_calendar(kktnc, KITS, stamp)
        assert max(len(line) for line in data.split(b"\r\n")) <= 75

    def test_required_calendar_properties(self, kktnc: Team, stamp: dt.datetime) -> None:
        text = render_calendar(kktnc, KITS, stamp).decode("utf-8")
        for required in (
            "VERSION:2.0",
            "CALSCALE:GREGORIAN",
            "METHOD:PUBLISH",
            "PRODID:",
            "X-WR-TIMEZONE:Europe/Prague",
            "BEGIN:VTIMEZONE",
            "TZID:Europe/Prague",
            "RRULE:FREQ=YEARLY;BYMONTH=10;BYDAY=-1SU",
            "RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=-1SU",
        ):
            assert required in text

    def test_calendar_name(self, kktnc: Team, stamp: dt.datetime) -> None:
        text = render_calendar(kktnc, KITS, stamp).decode("utf-8")
        assert "X-WR-CALNAME:KKTNC On Tour – HL podzim 2026 (7.H)" in text

    def test_calendar_name_names_the_league(self, dynamo: Team, stamp: dt.datetime) -> None:
        """Two calendars called "Dynamo 1.A" in one client would be unusable."""
        text = render_calendar(dynamo, VET_KITS, stamp).decode("utf-8")
        assert "X-WR-CALNAME:Dynamo UK VET – VET podzim 2026 (1.A)" in text

    def test_description_leaves_the_league_out(self, dynamo: Team, stamp: dt.datetime) -> None:
        """The calendar name carries it once; every event repeating it is noise."""
        calendar = Calendar.from_ical(render_calendar(dynamo, VET_KITS, stamp))
        first = next(iter(calendar.walk("VEVENT")))
        description = str(first["DESCRIPTION"])
        assert "kolo – 1.A (podzim 2026)" in description
        assert "Veteránská liga" not in description

    def test_output_path_is_league_scoped(self, kktnc: Team, dynamo: Team) -> None:
        assert kktnc.ics_path == "ics/hl/7-h/kktnc-on-tour.ics"
        assert dynamo.ics_path == "ics/vet/1-a/dynamo-uk-vet.ics"

    def test_every_event_carries_a_three_hour_alarm(self, kktnc: Team, stamp: dt.datetime) -> None:
        calendar = Calendar.from_ical(render_calendar(kktnc, KITS, stamp))
        events = calendar.walk("VEVENT")
        assert len(events) == 11
        for event in events:
            alarms = event.walk("VALARM")
            assert len(alarms) == 1
            assert alarms[0]["TRIGGER"].to_ical() == b"-PT3H"

    def test_events_last_75_minutes(self, kktnc: Team, stamp: dt.datetime) -> None:
        calendar = Calendar.from_ical(render_calendar(kktnc, KITS, stamp))
        for event in calendar.walk("VEVENT"):
            assert event.decoded("DTEND") - event.decoded("DTSTART") == MATCH_DURATION

    def test_summary_states_the_perspective(self, kktnc: Team, stamp: dt.datetime) -> None:
        calendar = Calendar.from_ical(render_calendar(kktnc, KITS, stamp))
        summaries = {str(e["SUMMARY"]) for e in calendar.walk("VEVENT")}
        assert "⚽ Patespool – KKTNC On Tour (venku)" in summaries
        assert "⚽ KKTNC On Tour – Měcholupská střeva (doma)" in summaries

    def test_location_names_the_exact_surface(self, kktnc: Team, stamp: dt.datetime) -> None:
        calendar = Calendar.from_ical(render_calendar(kktnc, KITS, stamp))
        locations = {str(e["LOCATION"]) for e in calendar.walk("VEVENT")}
        assert "Podvinný mlýn (PODV2), Kovanecká, Praha 9" in locations

    def test_description_survives_a_round_trip_with_notes_intact(
        self, kktnc: Team, stamp: dt.datetime
    ) -> None:
        """Folding plus escaping must not corrupt the verbatim Czech pitch notes."""
        calendar = Calendar.from_ical(render_calendar(kktnc, KITS, stamp))
        eighth = next(e for e in calendar.walk("VEVENT") if "PODV2" in str(e["LOCATION"]))
        description = str(eighth["DESCRIPTION"])
        assert "Hřiště č.1 je blíže buňkám se sociálním zařízením." in description
        assert "Soupeř: Real Oranjes" in description
        assert "Kde hrajete: venku" in description
        assert "Výkop: středa 4. 11. 2026 v 20:30" in description
        assert "https://www.psmf.cz/hriste/" in description
        assert kktnc.url in description

    def test_description_names_both_kits(self, kktnc: Team, stamp: dt.datetime) -> None:
        calendar = Calendar.from_ical(render_calendar(kktnc, KITS, stamp))
        first = next(e for e in calendar.walk("VEVENT") if "Patespool" in str(e["SUMMARY"]))
        assert "Dresy: bílá, černá (soupeř: zlatá)" in str(first["DESCRIPTION"])

    def test_geo_is_present_for_located_pitches(self, kktnc: Team, stamp: dt.datetime) -> None:
        text = render_calendar(kktnc, KITS, stamp).decode("utf-8")
        assert "GEO:50.10945;14.4919236" in text


class TestTimezoneCorrectness:
    def test_all_starts_are_timezone_aware(self, kktnc: Team, stamp: dt.datetime) -> None:
        calendar = Calendar.from_ical(render_calendar(kktnc, KITS, stamp))
        for event in calendar.walk("VEVENT"):
            assert event.decoded("DTSTART").tzinfo is not None

    def test_pre_switch_fixture_stays_on_summer_time(self, kktnc: Team, stamp: dt.datetime) -> None:
        calendar = Calendar.from_ical(render_calendar(kktnc, KITS, stamp))
        event = next(e for e in calendar.walk("VEVENT") if "-2026p-7@" in str(e["UID"]))
        start = event.decoded("DTSTART")
        assert start.utcoffset() == dt.timedelta(hours=2)
        assert start.strftime("%H:%M") == "19:15"

    def test_post_switch_fixture_keeps_its_wall_clock_time(
        self, kktnc: Team, stamp: dt.datetime
    ) -> None:
        """Round 8 is 4 Nov, after the switch: 20:30 local must still be 20:30."""
        calendar = Calendar.from_ical(render_calendar(kktnc, KITS, stamp))
        event = next(e for e in calendar.walk("VEVENT") if "-2026p-8@" in str(e["UID"]))
        start = event.decoded("DTSTART")
        assert start.utcoffset() == dt.timedelta(hours=1)
        assert start.strftime("%Y-%m-%d %H:%M") == "2026-11-04 20:30"
        assert start.astimezone(dt.UTC).strftime("%H:%M") == "19:30"

    def test_a_veterans_calendar_also_survives_validation(
        self, dynamo: Team, stamp: dt.datetime
    ) -> None:
        validate_calendar(dynamo, render_calendar(dynamo, VET_KITS, stamp))

    def test_validation_accepts_our_own_output(self, kktnc: Team, stamp: dt.datetime) -> None:
        data = render_calendar(kktnc, KITS, stamp)
        validate_calendar(kktnc, data)
        assert "round 8" in assert_dst_boundary_is_sane(kktnc, data)

    def test_validation_rejects_a_truncated_calendar(self, kktnc: Team, stamp: dt.datetime) -> None:
        data = render_calendar(kktnc, KITS, stamp)
        broken = data.replace(b"BEGIN:VEVENT", b"BEGIN:VEVENT", 1)
        first = broken.index(b"BEGIN:VEVENT")
        second = broken.index(b"BEGIN:VEVENT", first + 1)
        with pytest.raises(ValidationError, match="events for"):
            validate_calendar(kktnc, broken[:first] + broken[second:])
