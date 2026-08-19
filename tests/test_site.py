"""The search index handed to the browser."""

from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path
from typing import Any

from psmf_cal.models import Pitch, Team
from psmf_cal.parsing.text import normalize_search
from psmf_cal.site import INDEX_FILENAME, INDEX_GLOBAL, build_index, write_site

WHEN = dt.datetime(2026, 8, 18, 12, 30, tzinfo=dt.UTC)


def _build(teams: list[Team], pitches: dict[str, Pitch]) -> dict[str, Any]:
    """build_index() is declared as dict[str, object]; the tests want to index into it."""
    payload: dict[str, Any] = build_index(teams, pitches, WHEN)
    return payload


def _index(kktnc: Team, pitches: dict[str, Pitch]) -> dict[str, Any]:
    return _build([kktnc], pitches)


class TestIndex:
    def test_carries_the_scrape_timestamp(self, kktnc: Team, pitches: dict[str, Pitch]) -> None:
        assert _index(kktnc, pitches)["generated"] == "2026-08-18T12:30:00+00:00"

    def test_team_entry_shape(self, kktnc: Team, pitches: dict[str, Pitch]) -> None:
        team = _index(kktnc, pitches)["teams"][0]
        assert team["s"] == "kktnc-on-tour"
        assert team["n"] == "KKTNC On Tour"
        assert team["g"] == "7.H"
        assert team["gs"] == "7-h"
        assert team["l"] == "hl"
        assert team["ics"] == "ics/hl/7-h/kktnc-on-tour.ics"
        assert team["c"] == "bílá, černá"
        assert len(team["m"]) == 11

    def test_only_leagues_that_produced_teams_are_listed(
        self, kktnc: Team, pitches: dict[str, Pitch]
    ) -> None:
        """A chip for a league a partial build skipped could never match anything."""
        assert [entry["k"] for entry in _index(kktnc, pitches)["leagues"]] == ["hl"]

    def test_league_entry_carries_its_folded_search_terms(
        self, kktnc: Team, dynamo: Team, pitches: dict[str, Pitch]
    ) -> None:
        """Same contract as a team's "q": folded here, matched verbatim in the browser."""
        entries = {e["k"]: e for e in _build([kktnc, dynamo], pitches)["leagues"]}
        assert entries["vet"]["n"] == "Veteránská liga"
        assert entries["vet"]["s"] == "VET"
        for term in ("veteranska liga", "vet", "veterani"):
            assert term in entries["vet"]["q"]
        assert normalize_search(entries["vet"]["q"]) == entries["vet"]["q"]

    def test_teams_are_grouped_by_league_in_index_order(
        self, kktnc: Team, dynamo: Team, pitches: dict[str, Pitch]
    ) -> None:
        """Search results keep this order, so the Hanspaulska comes before the veterans."""
        payload = _build([dynamo, kktnc], pitches)
        assert [team["l"] for team in payload["teams"]] == ["hl", "vet"]

    def test_normalised_name_is_precomputed_for_the_browser(
        self, kktnc: Team, pitches: dict[str, Pitch]
    ) -> None:
        """The browser folds only the query; the index side is done here and tested."""
        team = _index(kktnc, pitches)["teams"][0]
        assert team["q"] == normalize_search("KKTNC On Tour") == "kktnc on tour"

    def test_fixture_entry_shape(self, kktnc: Team, pitches: dict[str, Pitch]) -> None:
        first = _index(kktnc, pitches)["teams"][0]["m"][0]
        assert first == {
            "r": 1,
            "d": "2026-09-03",
            "t": "20:30",
            "w": "Čt",
            "o": "Patespool",
            "h": False,
            "p": "TEMPO",
        }

    def test_home_flag_matches_perspective(self, kktnc: Team, pitches: dict[str, Pitch]) -> None:
        fixtures = _index(kktnc, pitches)["teams"][0]["m"]
        assert fixtures[1]["h"] is True  # round 2, at home
        assert fixtures[1]["o"] == "Měcholupská střeva"

    def test_only_referenced_pitches_are_emitted(
        self, kktnc: Team, pitches: dict[str, Pitch]
    ) -> None:
        """Pitches are deduplicated into a shared map, not repeated per fixture."""
        emitted = _index(kktnc, pitches)["pitches"]
        used = {m.pitch.code for m in kktnc.matches}
        assert set(emitted) == used
        assert len(emitted) < len(kktnc.matches)

    def test_pitch_entry_has_name_address_and_coordinates(
        self, kktnc: Team, pitches: dict[str, Pitch]
    ) -> None:
        emitted = _index(kktnc, pitches)["pitches"]["PODV2"]
        assert emitted["n"] == "Podvinný mlýn"
        assert emitted["a"] == "Kovanecká, Praha 9"
        assert emitted["lat"] and emitted["lon"]

    def test_pitch_notes_stay_out_of_the_index(
        self, kktnc: Team, pitches: dict[str, Pitch]
    ) -> None:
        """The long Czech notes belong in the .ics; shipping them twice would bloat the page."""
        emitted = _index(kktnc, pitches)["pitches"]["PODV2"]
        assert set(emitted) == {"n", "a", "lat", "lon"}


class TestWriteSite:
    def test_writes_index_and_assets(
        self, kktnc: Team, pitches: dict[str, Pitch], tmp_path: Path
    ) -> None:
        write_site(tmp_path, [kktnc], pitches, WHEN)
        for name in (INDEX_FILENAME, "index.html", "style.css", "app.js"):
            assert (tmp_path / name).exists()

    def test_index_is_a_script_assigning_a_global(
        self, kktnc: Team, pitches: dict[str, Pitch], tmp_path: Path
    ) -> None:
        """A <script> tag, not fetched JSON, so the page also works from file://."""
        path = write_site(tmp_path, [kktnc], pitches, WHEN)
        text = path.read_text(encoding="utf-8")
        assert text.startswith(f"window.{INDEX_GLOBAL}=")
        assert text.endswith(";\n")

    def test_index_payload_is_valid_json(
        self, kktnc: Team, pitches: dict[str, Pitch], tmp_path: Path
    ) -> None:
        path = write_site(tmp_path, [kktnc], pitches, WHEN)
        text = path.read_text(encoding="utf-8")
        payload = json.loads(text[text.index("=") + 1 :].rstrip().rstrip(";"))
        assert payload["teams"][0]["n"] == "KKTNC On Tour"

    def test_assets_are_fingerprinted_in_the_markup(
        self, kktnc: Team, pitches: dict[str, Pitch], tmp_path: Path
    ) -> None:
        """A cached page from last week must not run against this week's team list."""
        write_site(tmp_path, [kktnc], pitches, WHEN)
        html = (tmp_path / "index.html").read_text(encoding="utf-8")
        for name in ("style.css", "app.js", INDEX_FILENAME):
            assert re.search(rf'["\']{re.escape(name)}\?v=[0-9a-f]{{10}}["\']', html), name

    def test_a_fingerprint_changes_only_when_the_file_does(
        self, kktnc: Team, pitches: dict[str, Pitch], tmp_path: Path
    ) -> None:
        first = tmp_path / "a"
        second = tmp_path / "b"
        write_site(first, [kktnc], pitches, WHEN)
        write_site(second, [kktnc], pitches, WHEN.replace(minute=45))
        stamps = [
            re.findall(r"app\.js\?v=([0-9a-f]+)", (path / "index.html").read_text("utf-8"))[0]
            for path in (first, second)
        ]
        assert stamps[0] == stamps[1], "app.js did not change, so its stamp must not either"
        teams = [
            re.findall(r"teams\.js\?v=([0-9a-f]+)", (path / "index.html").read_text("utf-8"))[0]
            for path in (first, second)
        ]
        assert teams[0] != teams[1], "the index did change, so its stamp must too"

    def test_index_keeps_diacritics_unescaped(
        self, kktnc: Team, pitches: dict[str, Pitch], tmp_path: Path
    ) -> None:
        path = write_site(tmp_path, [kktnc], pitches, WHEN)
        assert "Měcholupská střeva" in path.read_text(encoding="utf-8")
