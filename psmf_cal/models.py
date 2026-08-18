"""Typed structures shared by every layer.

These are the only vocabulary the parsing, ICS and site layers have in common.
Everything is frozen: the crawl builds these once and later stages only read them.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Mapping
from dataclasses import dataclass

SEASON_SLUG = "2026-hanspaulska-liga-podzim"
SEASON_LABEL = "HL podzim 2026"
#: Suffix used inside every UID; identifies the season so a future spring run cannot collide.
SEASON_UID_TAG = "2026p"

BASE_URL = "https://www.psmf.cz"
SEASON_URL = f"{BASE_URL}/souteze/{SEASON_SLUG}/"
PITCHES_URL = f"{BASE_URL}/hriste/"


@dataclass(frozen=True, slots=True)
class GroupRef:
    """One group (skupina) within the season, e.g. level 7 group H."""

    level: int
    group: str  # single upper-case letter, "A".."N"
    url: str

    @property
    def slug(self) -> str:
        """Path segment used by psmf.cz and by our output tree, e.g. ``7-h``."""
        return f"{self.level}-{self.group.lower()}"

    @property
    def label(self) -> str:
        """Human-facing label shown in the UI and calendar name, e.g. ``7.H``."""
        return f"{self.level}.{self.group}"


@dataclass(frozen=True, slots=True)
class Pitch:
    """A single playing surface.

    One directory row can list several codes (STER1/STER2/STER3) that share a
    complex, address, coordinates and description; each code becomes its own
    Pitch so LOCATION can name the exact surface. ``notes`` stays verbatim Czech
    because it is the practical "how do I find this pitch" text.
    """

    code: str
    name: str
    address: str
    notes: str
    latitude: float | None
    longitude: float | None

    @property
    def maps_url(self) -> str:
        """Google Maps link: coordinates when known, address search otherwise."""
        from urllib.parse import quote

        if self.latitude is not None and self.longitude is not None:
            return (
                f"https://www.google.com/maps/search/?api=1&query={self.latitude},{self.longitude}"
            )
        return f"https://www.google.com/maps/search/?api=1&query={quote(self.address)}"

    @property
    def mapy_url(self) -> str:
        """Link to mapy.cz, the map the league's own pitch directory points at."""
        if self.latitude is None or self.longitude is None:
            from urllib.parse import quote

            return f"https://mapy.cz/?q={quote(self.address)}"
        return f"https://mapy.cz/?q=GPS:%20{self.latitude}%20{self.longitude}"


@dataclass(frozen=True, slots=True)
class TeamRef:
    """A team as referenced from a group listing or a fixture row.

    Slugs are unique only *within* a group, so a full identity is (group, slug).
    """

    slug: str
    name: str
    url: str


@dataclass(frozen=True, slots=True)
class Match:
    """One fixture from a team's schedule table."""

    round_no: int
    kickoff: dt.datetime  # timezone-aware, Europe/Prague
    weekday: str  # Czech abbreviation as published, e.g. "Ct"
    home: TeamRef
    away: TeamRef
    pitch: Pitch

    def is_home_for(self, slug: str) -> bool:
        return self.home.slug == slug

    def opponent_of(self, slug: str) -> TeamRef:
        return self.away if self.home.slug == slug else self.home


@dataclass(frozen=True, slots=True)
class Team:
    """A team plus its parsed schedule -- the unit one .ics file is built from.

    ``colors`` is the kit as published on this team's *own* page, which is the
    authoritative source for it. Opponent kits are never read out of our own
    fixture rows; they are looked up from the opponent's Team entry via
    :class:`GroupKits`, keyed by slug rather than by display name.
    """

    slug: str
    name: str
    url: str
    group: GroupRef
    matches: tuple[Match, ...]
    colors: str | None

    @property
    def calendar_name(self) -> str:
        return f"{self.name} – {SEASON_LABEL} ({self.group.label})"

    @property
    def ics_path(self) -> str:
        """Path of the generated file relative to the site root."""
        return f"ics/{self.group.slug}/{self.slug}.ics"


#: Kits of every team in one group, keyed by team slug. Fixtures are always
#: intra-group, so this is enough to resolve any opponent's colours.
GroupKits = Mapping[str, "str | None"]
