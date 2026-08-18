"""The search index handed to the browser."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any

from psmf_cal.models import Pitch, Team
from psmf_cal.parsing.text import normalize_search
from psmf_cal.site import build_index, write_site


def _index(kktnc: Team, pitches: dict[str, Pitch]) -> dict[str, Any]:
    when = dt.datetime(2026, 8, 18, 12, 30, tzinfo=dt.UTC)
    return build_index([kktnc], pitches, when)


class TestIndex:
    def test_carries_the_scrape_timestamp(self, kktnc: Team, pitches: dict[str, Pitch]) -> None:
        assert _index(kktnc, pitches)["generated"] == "2026-08-18T12:30:00+00:00"

    def test_team_entry_shape(self, kktnc: Team, pitches: dict[str, Pitch]) -> None:
        team = _index(kktnc, pitches)["teams"][0]
        assert team["s"] == "kktnc-on-tour"
        assert team["n"] == "KKTNC On Tour"
        assert team["g"] == "7.H"
        assert team["gs"] == "7-h"
        assert team["ics"] == "ics/7-h/kktnc-on-tour.ics"
        assert team["c"] == "bílá, černá"
        assert len(team["m"]) == 11

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
        when = dt.datetime(2026, 8, 18, 12, 30, tzinfo=dt.UTC)
        write_site(tmp_path, [kktnc], pitches, when)
        for name in ("teams.json", "index.html", "style.css", "app.js"):
            assert (tmp_path / name).exists()

    def test_index_is_valid_utf8_json(
        self, kktnc: Team, pitches: dict[str, Pitch], tmp_path: Path
    ) -> None:
        when = dt.datetime(2026, 8, 18, 12, 30, tzinfo=dt.UTC)
        path = write_site(tmp_path, [kktnc], pitches, when)
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload["teams"][0]["n"] == "KKTNC On Tour"

    def test_index_keeps_diacritics_unescaped(
        self, kktnc: Team, pitches: dict[str, Pitch], tmp_path: Path
    ) -> None:
        when = dt.datetime(2026, 8, 18, 12, 30, tzinfo=dt.UTC)
        path = write_site(tmp_path, [kktnc], pitches, when)
        assert "Měcholupská střeva" in path.read_text(encoding="utf-8")
