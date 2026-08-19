"""Emit the static site: the search index plus the hand-written assets.

Fixture data is inlined into one index rather than split per team or per
league. Pitch descriptions are the bulky part and they repeat heavily, so they
are deduplicated into a shared map keyed by code and referenced from each
fixture; what remains is roughly 130 bytes per fixture, i.e. not much over a
megabyte for all four leagues together. That is small enough to ship in one
request, which keeps the front end free of per-team fetch plumbing and means
that switching league or selecting a team never waits on the network.

The index is emitted as ``teams.js`` -- a single assignment to a global --
rather than as ``teams.json`` loaded with fetch(). A page opened straight from
disk is same-origin-restricted and fetch() of a sibling file fails there, so a
plain <script> tag is the one form that works both from ``file://`` and from a
static server. The payload is identical JSON either way.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
import shutil
from collections.abc import Sequence
from pathlib import Path

from psmf_cal.models import LEAGUES, SEASON_LABEL, League, Pitch, Team
from psmf_cal.parsing.text import normalize_search

ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"
ASSET_FILES = ("index.html", "style.css", "app.js")

#: Global the emitted index assigns itself to, read by assets/app.js.
INDEX_GLOBAL = "PSMF_DATA"
INDEX_FILENAME = "teams.js"

#: Files index.html references and which therefore get a content fingerprint.
#: A visitor who has the page cached from last week must not be served last
#: week's team list against this week's script, so the query string changes
#: whenever -- and only whenever -- the file behind it does.
VERSIONED = ("style.css", "app.js", INDEX_FILENAME)


def _league_json(league: League) -> dict[str, object]:
    """One entry of the league switcher, plus everything search needs about it.

    ``q`` is the folded haystack the browser matches a query against: the full
    name, the badge, and the aliases people actually type ("vet", "veterani").
    Folding it here rather than in the browser keeps the JS side to one
    indexOf() and puts the transform under the Python tests.
    """
    terms = (league.name, league.short, league.key, *league.aliases)
    return {
        "k": league.key,
        "n": league.name,
        "s": league.short,
        "q": " ".join(dict.fromkeys(normalize_search(term) for term in terms)),
    }


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
        "l": team.league.key,
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
    order = {league.key: index for index, league in enumerate(LEAGUES)}
    ordered = sorted(
        teams, key=lambda t: (order[t.league.key], t.group.level, t.group.group, t.name)
    )
    present = {team.league.key for team in teams}
    return {
        "generated": generated_at.isoformat(timespec="seconds"),
        "season": SEASON_LABEL,
        # Only leagues that actually produced teams, so a partial build (--league
        # or --only) does not render a filter chip that can never match anything.
        "leagues": [_league_json(league) for league in LEAGUES if league.key in present],
        "pitches": {code: _pitch_json(pitches[code]) for code in sorted(used)},
        "teams": [_team_json(team) for team in ordered],
    }


def _fingerprint(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:10]


def add_cache_busters(html: str, dist: Path) -> str:
    """Stamp each referenced asset in ``html`` with a hash of its contents.

    Rewriting the markup here rather than hand-maintaining version numbers in
    index.html means the fingerprints cannot drift out of step with the files.
    """
    for name in VERSIONED:
        target = dist / name
        if not target.exists():
            raise FileNotFoundError(f"cannot fingerprint a file that was not written: {target}")
        pattern = re.compile(rf'(["\'])({re.escape(name)})(\?[^"\']*)?\1')
        html = pattern.sub(rf"\g<1>{name}?v={_fingerprint(target)}\g<1>", html)
    return html


def write_site(
    dist: Path,
    teams: Sequence[Team],
    pitches: dict[str, Pitch],
    generated_at: dt.datetime,
) -> Path:
    """Write the search index and copy the static assets into ``dist``."""
    dist.mkdir(parents=True, exist_ok=True)

    index_path = dist / INDEX_FILENAME
    payload = build_index(teams, pitches, generated_at)
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    index_path.write_text(f"window.{INDEX_GLOBAL}={encoded};\n", encoding="utf-8")

    for name in ASSET_FILES:
        source = ASSETS_DIR / name
        if not source.exists():
            raise FileNotFoundError(f"missing site asset: {source}")
        shutil.copyfile(source, dist / name)

    # After the copy, so the hashes describe what actually landed in dist/.
    page = dist / "index.html"
    page.write_text(add_cache_busters(page.read_text(encoding="utf-8"), dist), encoding="utf-8")

    return index_path
