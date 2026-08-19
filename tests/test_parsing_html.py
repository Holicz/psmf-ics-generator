"""Parsing saved pages into structures: season index, group, team, pitches."""

from __future__ import annotations

import datetime as dt

import pytest

from psmf_cal.models import Pitch
from psmf_cal.parsing.group import parse_group
from psmf_cal.parsing.pitches import parse_pitches
from psmf_cal.parsing.season import parse_season_index
from psmf_cal.parsing.team import parse_team_page
from psmf_cal.parsing.text import ParseError
from tests.conftest import (
    GROUP_7H,
    GROUP_UVET_2A,
    GROUP_VET_1A,
    HL,
    KKTNC_URL,
    PITCHES_URL,
    VET,
    ZVAHOV_URL,
    load,
)


class TestSeasonIndex:
    def test_discovers_every_group(self) -> None:
        groups = parse_season_index(load("season-index.html"), "https://www.psmf.cz/x/", HL)
        assert len(groups) == 60

    def test_ignores_per_level_summary_pages(self) -> None:
        """/7/ is a level overview; only /7-h/ style links are groups."""
        groups = parse_season_index(load("season-index.html"), "https://www.psmf.cz/x/", HL)
        assert all(g.group.isalpha() and len(g.group) == 1 for g in groups)

    def test_levels_span_one_to_eight(self) -> None:
        groups = parse_season_index(load("season-index.html"), "https://www.psmf.cz/x/", HL)
        assert {g.level for g in groups} == set(range(1, 9))

    def test_urls_are_absolute(self) -> None:
        groups = parse_season_index(load("season-index.html"), "https://www.psmf.cz/x/", HL)
        assert all(g.url.startswith("https://www.psmf.cz/souteze/") for g in groups)

    def test_a_page_without_groups_raises(self) -> None:
        with pytest.raises(ParseError, match="linked no groups"):
            parse_season_index("<html><body>nic</body></html>", "https://example/", HL)

    def test_the_veterans_index_is_read_by_the_same_parser(self) -> None:
        """All four leagues publish the same shape; only the season slug differs."""
        groups = parse_season_index(load("vet-season-index.html"), "https://www.psmf.cz/x/", VET)
        assert [g.slug for g in groups] == [
            "1-a",
            "2-a",
            "2-b",
            "3-a",
            "3-b",
            "3-c",
            "3-d",
            "4-a",
            "4-b",
            "4-c",
        ]
        assert all(g.league is VET for g in groups)

    def test_a_league_only_claims_its_own_groups(self) -> None:
        """Every psmf.cz page links all four leagues in its navigation, so the
        season slug in the href is the only thing keeping them apart."""
        with pytest.raises(ParseError, match="linked no groups"):
            parse_season_index(load("vet-season-index.html"), "https://www.psmf.cz/x/", HL)

    def test_group_keys_are_unique_across_leagues(self) -> None:
        hl = parse_season_index(load("season-index.html"), "https://www.psmf.cz/x/", HL)
        vet = parse_season_index(load("vet-season-index.html"), "https://www.psmf.cz/x/", VET)
        shared = {g.slug for g in hl} & {g.slug for g in vet}
        assert shared, "the leagues do reuse group slugs, which is the whole problem"
        assert not {g.key for g in hl} & {g.key for g in vet}


class TestGroupPage:
    def test_lists_all_twelve_teams(self) -> None:
        teams = parse_group(load("group-7-h.html"), GROUP_7H.url, GROUP_7H)
        assert len(teams) == 12

    def test_keeps_diacritics_in_names(self) -> None:
        teams = parse_group(load("group-7-h.html"), GROUP_7H.url, GROUP_7H)
        by_slug = {t.slug: t.name for t in teams}
        assert by_slug["mecholupska-streva"] == "Měcholupská střeva"
        assert by_slug["brondby-codein-if"] == "Bröndby codein IF"

    def test_an_empty_group_raises_rather_than_returning_nothing(self) -> None:
        with pytest.raises(ParseError, match="linked no teams"):
            parse_group("<html><body></body></html>", GROUP_7H.url, GROUP_7H)

    def test_a_veterans_group_lists_its_teams(self) -> None:
        teams = parse_group(load("vet-group-1-a.html"), GROUP_VET_1A.url, GROUP_VET_1A)
        assert len(teams) == 12
        assert "dynamo-uk-vet" in {t.slug for t in teams}

    def test_a_group_page_of_another_league_yields_nothing(self) -> None:
        """1-a exists in both leagues; the season slug is what tells them apart."""
        with pytest.raises(ParseError, match="linked no teams"):
            parse_group(load("vet-group-1-a.html"), GROUP_7H.url, GROUP_7H)


class TestPitchDirectory:
    def test_parses_every_code(self, pitches: dict[str, Pitch]) -> None:
        assert len(pitches) == 42

    def test_codes_sharing_a_row_become_separate_pitches(self, pitches: dict[str, Pitch]) -> None:
        """STER1/2/3 are one complex but three surfaces; the notes disambiguate."""
        for code in ("STER1", "STER2", "STER3"):
            assert pitches[code].name == "Štěrboholy"
            assert pitches[code].address == "U Školy 430, Praha 10"
        assert "Hřiště č. 1 je nejblíže hale" in pitches["STER1"].notes

    def test_notes_stay_verbatim_czech(self, pitches: dict[str, Pitch]) -> None:
        notes = pitches["TEMPO"].notes
        assert "V areálu FC Tempo" in notes
        assert "UMT 3. generace, osvětlení." in notes
        assert "Obuv: kopačky povoleny i s lisovanými kolíky." in notes

    def test_coordinates_are_extracted(self, pitches: dict[str, Pitch]) -> None:
        tempo = pitches["TEMPO"]
        assert tempo.latitude == pytest.approx(50.0207742)
        assert tempo.longitude == pytest.approx(14.4326447)

    def test_every_pitch_has_an_address(self, pitches: dict[str, Pitch]) -> None:
        assert all(p.address for p in pitches.values())

    def test_maps_url_prefers_coordinates(self, pitches: dict[str, Pitch]) -> None:
        assert "query=50.0207742,14.4326447" in pitches["TEMPO"].maps_url

    def test_maps_url_falls_back_to_address(self) -> None:
        pitch = Pitch("X", "Hřiště X", "Ulice 1, Praha 1", "", None, None)
        assert "Ulice%201" in pitch.maps_url

    def test_wrong_table_shape_raises(self) -> None:
        html = "<table><tr><th>Něco</th><th>Jiného</th><th>Třetí</th></tr></table>"
        with pytest.raises(ParseError, match="unexpected pitch table headers"):
            parse_pitches(html, PITCHES_URL)


class TestTeamPage:
    def test_reads_the_fixture_table_only(self, kktnc) -> None:  # type: ignore[no-untyped-def]
        """The page also holds standings and a refereeing roster; neither is a fixture."""
        assert len(kktnc.matches) == 11
        assert [m.round_no for m in kktnc.matches] == list(range(1, 12))

    def test_home_and_away_come_from_link_order(self, kktnc) -> None:  # type: ignore[no-untyped-def]
        first = kktnc.matches[0]
        assert first.home.slug == "patespool"
        assert first.away.slug == "kktnc-on-tour"
        assert not first.is_home_for("kktnc-on-tour")
        assert first.opponent_of("kktnc-on-tour").name == "Patespool"

    def test_home_fixture_is_detected(self, kktnc) -> None:  # type: ignore[no-untyped-def]
        second = kktnc.matches[1]
        assert second.is_home_for("kktnc-on-tour")
        assert second.opponent_of("kktnc-on-tour").name == "Měcholupská střeva"

    def test_kickoffs_are_timezone_aware(self, kktnc) -> None:  # type: ignore[no-untyped-def]
        assert all(m.kickoff.tzinfo is not None for m in kktnc.matches)

    def test_the_season_crosses_the_dst_switch(self, kktnc) -> None:  # type: ignore[no-untyped-def]
        offsets = {m.kickoff.utcoffset() for m in kktnc.matches}
        assert offsets == {dt.timedelta(hours=1), dt.timedelta(hours=2)}

    def test_pitch_codes_resolve_to_the_directory(self, kktnc) -> None:  # type: ignore[no-untyped-def]
        eighth = kktnc.matches[7]
        assert eighth.pitch.code == "PODV2"
        assert eighth.pitch.name == "Podvinný mlýn"
        assert eighth.pitch.address == "Kovanecká, Praha 9"

    def test_own_kit_comes_from_this_teams_own_page(self, kktnc) -> None:  # type: ignore[no-untyped-def]
        assert kktnc.colors == "bílá, černá"

    def test_opponent_kit_comes_from_the_opponents_page(self, pitches: dict[str, Pitch]) -> None:
        """Kits are resolved per team from its own page, never from a peer's row."""
        patespool = parse_team_page(
            load("team-patespool.html"),
            GROUP_7H.url + "tymy/patespool/",
            GROUP_7H,
            "patespool",
            pitches,
        )
        assert patespool.colors == "zlatá"

    def test_unknown_pitch_code_is_an_error(self, pitches: dict[str, Pitch]) -> None:
        stripped = {k: v for k, v in pitches.items() if k != "TEMPO"}
        with pytest.raises(ParseError, match="absent from the pitch directory"):
            parse_team_page(
                load("team-kktnc-on-tour.html"), KKTNC_URL, GROUP_7H, "kktnc-on-tour", stripped
            )

    def test_page_for_a_different_team_is_rejected(self, pitches: dict[str, Pitch]) -> None:
        with pytest.raises(ParseError, match="does not involve"):
            parse_team_page(
                load("team-kktnc-on-tour.html"), KKTNC_URL, GROUP_7H, "someone-else", pitches
            )

    def test_a_veterans_page_parses_the_same_way(self, dynamo) -> None:  # type: ignore[no-untyped-def]
        assert len(dynamo.matches) == 11
        assert dynamo.colors == "černá, bílá"
        assert dynamo.matches[0].opponent_of("dynamo-uk-vet").name == "Santa Dominica VET"
        assert dynamo.matches[0].pitch.code == "MOTO4"

    def test_a_bye_round_is_skipped_not_fatal(self, pitches: dict[str, Pitch]) -> None:
        """An odd-sized group gives every team a round off, published as a row with
        the round number and nothing else. It is not a fixture and not an error."""
        page = parse_team_page(
            load("uvl-team-zvahov-uvl.html"), ZVAHOV_URL, GROUP_UVET_2A, "zvahov-uvl", pitches
        )
        rounds = [m.round_no for m in page.matches]
        assert rounds == [1, 2, 3, 4, 5, 6, 7, 8, 9, 11]
        assert 10 not in rounds

    def test_a_half_empty_row_still_raises(self, pitches: dict[str, Pitch]) -> None:
        """Only a wholly blank row is a bye; anything else is markup we misread."""
        html = (
            '<table class="games-new-table">'
            "<tr><th>Datum</th><th>Čas</th><th>Hřiště</th>"
            "<th>Domácí - Hosté</th><th>Kolo</th></tr>"
            "<tr><td></td><td>20:30</td><td></td><td>KKTNC On Tour</td><td>1.</td></tr>"
            "</table>"
        )
        with pytest.raises(ParseError, match="unrecognised date cell"):
            parse_team_page(html, KKTNC_URL, GROUP_7H, "kktnc-on-tour", pitches)

    def test_missing_fixture_table_raises(self, pitches: dict[str, Pitch]) -> None:
        with pytest.raises(ParseError, match="no table"):
            parse_team_page("<html></html>", KKTNC_URL, GROUP_7H, "kktnc-on-tour", pitches)

    def test_changed_headers_raise(self, pitches: dict[str, Pitch]) -> None:
        html = '<table class="games-new-table"><tr><th>Kdy</th><th>Kde</th></tr></table>'
        with pytest.raises(ParseError, match="unexpected fixture headers"):
            parse_team_page(html, KKTNC_URL, GROUP_7H, "kktnc-on-tour", pitches)
