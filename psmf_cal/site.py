"""Emit the static site: the search index plus the hand-written assets.

Fixture data is inlined into ``teams.json`` rather than split into per-team
files. Pitch descriptions are the bulky part and they repeat heavily, so they
are deduplicated into a shared map keyed by code and referenced from each
fixture; what remains is roughly 130 bytes per fixture, i.e. about 1 MB for the
whole league. That is small enough to ship in one request, which keeps the
front end free of per-team fetch plumbing and means selecting a team never
waits on the network.
"""

from __future__ import annotations

import datetime as dt
import json
import shutil
from collections.abc import Sequence
from pathlib import Path

from psmf_cal.models import SEASON_LABEL, Pitch, Team
from psmf_cal.parsing.text import normalize_search

ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"
ASSET_FILES = ("index.html", "style.css", "app.js")


def _pitch_json(pitch: Pitch) -> dict[str, object]:
    entry: dict[str, object] = {"n": pitch.name, "a": pitch.address}
    if pitch.latitude is not None and pitch.longitude is not None:
        entry["lat"] = pitch.latitude
        entry["lon"] = pitch.longitude
    return entry


def _team_json(team: Team) -> dict[str, object]:
    return {
        "s": team.slug,
        "n": team.name,
        # Precomputed fold of the name. The browser applies the identical
        # transform to the query only, so the expensive half of diacritics-
        # insensitive search is done here and is covered by the Python tests.
        "q": normalize_search(team.name),
        "g": team.group.label,
        "gs": team.group.slug,
        "u": team.url,
        "ics": team.ics_path,
        "c": team.colors,
        "m": [
            {
                "r": match.round_no,
                "d": match.kickoff.strftime("%Y-%m-%d"),
                "t": match.kickoff.strftime("%H:%M"),
                "w": match.weekday,
                "o": match.opponent_of(team.slug).name,
                "h": match.is_home_for(team.slug),
                "p": match.pitch.code,
            }
            for match in team.matches
        ],
    }


def build_index(
    teams: Sequence[Team], pitches: dict[str, Pitch], generated_at: dt.datetime
) -> dict[str, object]:
    """Assemble the JSON payload the front end loads."""
    used = {match.pitch.code for team in teams for match in team.matches}
    ordered = sorted(teams, key=lambda t: (t.group.level, t.group.group, t.name))
    return {
        "generated": generated_at.isoformat(timespec="seconds"),
        "season": SEASON_LABEL,
        "pitches": {code: _pitch_json(pitches[code]) for code in sorted(used)},
        "teams": [_team_json(team) for team in ordered],
    }


def write_site(
    dist: Path,
    teams: Sequence[Team],
    pitches: dict[str, Pitch],
    generated_at: dt.datetime,
) -> Path:
    """Write ``teams.json`` and copy the static assets into ``dist``."""
    dist.mkdir(parents=True, exist_ok=True)

    index_path = dist / "teams.json"
    payload = build_index(teams, pitches, generated_at)
    index_path.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )

    for name in ASSET_FILES:
        source = ASSETS_DIR / name
        if not source.exists():
            raise FileNotFoundError(f"missing site asset: {source}")
        shutil.copyfile(source, dist / name)

    return index_path
