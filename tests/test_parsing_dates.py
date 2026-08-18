"""Date and time parsing, including the two-digit year the site publishes."""

from __future__ import annotations

import datetime as dt

import pytest

from psmf_cal.parsing.text import (
    ParseError,
    normalize_search,
    parse_czech_date,
    parse_time,
    split_date_cell,
    to_prague,
)


class TestTwoDigitYear:
    def test_two_digit_year_is_read_as_this_century(self) -> None:
        assert parse_czech_date("3.9.26", url="u") == dt.date(2026, 9, 3)

    def test_single_digit_day_and_month(self) -> None:
        assert parse_czech_date("1.1.27", url="u") == dt.date(2027, 1, 1)

    def test_four_digit_year_still_works(self) -> None:
        assert parse_czech_date("15.10.2026", url="u") == dt.date(2026, 10, 15)

    @pytest.mark.parametrize("value", ["", "3/9/26", "3.9.", "32.9.26", "3.13.26", "abc"])
    def test_rubbish_raises_rather_than_guessing(self, value: str) -> None:
        with pytest.raises(ParseError):
            parse_czech_date(value, url="https://example/x")

    def test_error_carries_the_offending_url(self) -> None:
        with pytest.raises(ParseError) as excinfo:
            parse_czech_date("nope", url="https://example/team/")
        assert excinfo.value.url == "https://example/team/"


class TestTime:
    def test_parses_kickoff(self) -> None:
        assert parse_time("20:30", url="u") == dt.time(20, 30)

    def test_accepts_single_digit_hour(self) -> None:
        assert parse_time("9:15", url="u") == dt.time(9, 15)

    @pytest.mark.parametrize("value", ["24:00", "20:61", "2030", ""])
    def test_impossible_time_raises(self, value: str) -> None:
        with pytest.raises(ParseError):
            parse_time(value, url="u")


class TestDateCell:
    def test_splits_weekday_from_date_across_nbsp(self) -> None:
        assert split_date_cell("Čt\xa03.9.26", url="u") == ("Čt", dt.date(2026, 9, 3))

    def test_weekday_disagreeing_with_date_is_an_error(self) -> None:
        """A published weekday that contradicts the date means we misread it."""
        with pytest.raises(ParseError, match="is a"):
            split_date_cell("Po 3.9.26", url="u")

    def test_all_czech_weekdays_round_trip(self) -> None:
        # 31.8.2026 is a Monday; seven consecutive days cover every abbreviation.
        cells = [
            "Po 31.8.26",
            "Út 1.9.26",
            "St 2.9.26",
            "Čt 3.9.26",
            "Pá 4.9.26",
            "So 5.9.26",
            "Ne 6.9.26",
        ]
        for cell in cells:
            split_date_cell(cell, url="u")


class TestTimezone:
    def test_september_kickoff_is_summer_time(self) -> None:
        moment = to_prague(dt.date(2026, 9, 3), dt.time(20, 30))
        assert moment.utcoffset() == dt.timedelta(hours=2)
        assert moment.tzname() == "CEST"

    def test_november_kickoff_is_winter_time(self) -> None:
        """The season crosses the last-Sunday-of-October switch."""
        moment = to_prague(dt.date(2026, 11, 4), dt.time(20, 30))
        assert moment.utcoffset() == dt.timedelta(hours=1)
        assert moment.tzname() == "CET"

    def test_wall_clock_survives_the_switch(self) -> None:
        before = to_prague(dt.date(2026, 10, 20), dt.time(19, 15))
        after = to_prague(dt.date(2026, 11, 4), dt.time(19, 15))
        assert before.strftime("%H:%M") == after.strftime("%H:%M") == "19:15"
        assert before.utcoffset() != after.utcoffset()


class TestSearchNormalisation:
    def test_strips_czech_diacritics(self) -> None:
        assert normalize_search("Měcholupská střeva") == "mecholupska streva"

    def test_is_case_insensitive(self) -> None:
        assert normalize_search("KKTNC On Tour") == "kktnc on tour"

    def test_matches_in_both_directions(self) -> None:
        """Typing without diacritics finds the accented name and vice versa."""
        assert normalize_search("mecholupska") in normalize_search("Měcholupská střeva")
        assert normalize_search("Měcholupská") in normalize_search("Mecholupska streva")

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("Bröndby codein IF", "brondby codein if"),
            ("Houbařův Ráj", "houbaruv raj"),
            ("Slavoj Dětská obrna TJ", "slavoj detska obrna tj"),
            ("Žižkov", "zizkov"),
            ("Ďáblice", "dablice"),
            ("F.C.K.", "f.c.k."),
        ],
    )
    def test_real_team_names(self, raw: str, expected: str) -> None:
        assert normalize_search(raw) == expected

    def test_already_decomposed_input_is_stable(self) -> None:
        """NFD input must fold to the same result as NFC input."""
        import unicodedata

        name = "Měcholupská"
        assert normalize_search(unicodedata.normalize("NFD", name)) == normalize_search(name)
