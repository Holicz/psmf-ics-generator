"""Typed structures shared by every layer.

These are the only vocabulary the parsing, ICS and site layers have in common.
Everything is frozen: the crawl builds these once and later stages only read them.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Mapping
from dataclasses import dataclass

#: Half of the season every competition below is crawled for. The four leagues
#: run in lockstep, so one label covers all of them.
SEASON_LABEL = "podzim 2026"
#: Suffix used inside every UID; identifies the season so a future spring run cannot collide.
SEASON_UID_TAG = "2026p"

BASE_URL = "https://www.psmf.cz"
PITCHES_URL = f"{BASE_URL}/hriste/"


@dataclass(frozen=True, slots=True)
class League:
    """One PSMF competition, e.g. the Hanspaulská or the veterans' league.

    ``key`` is ours, not psmf.cz's: it is the segment that separates leagues in
    the output tree and in every UID. Group slugs such as ``1-a`` exist in all
    four leagues, so without it two different teams would collide.
    """

    key: str  # "hl", "vet", "svet", "uvet"
    season_slug: str  # path segment on psmf.cz
    name: str  # "Veteránská liga"
    short: str  # "VET" -- the badge in the UI and the calendar-name prefix
    #: Extra search terms folded into the index so "veterani" finds this league.
    aliases: tuple[str, ...] = ()

    @property
    def url(self) -> str:
        return f"{BASE_URL}/souteze/{self.season_slug}/"


#: Every league the site covers, in the order psmf.cz itself lists them.
#: Futsal is deliberately absent: it runs on a cross-year season slug
#: (``2025-2026-futsal-podzim``) and is a different sport with its own page
#: layout, so it is not a one-line addition here.
LEAGUES: tuple[League, ...] = (
    League(
        key="hl",
        season_slug="2026-hanspaulska-liga-podzim",
        name="Hanspaulská liga",
        short="HL",
        aliases=("hanspaulka", "hl"),
    ),
    League(
        key="vet",
        season_slug="2026-veteranska-liga-podzim",
        name="Veteránská liga",
        short="VET",
        aliases=("veterani", "vet"),
    ),
    League(
        key="svet",
        season_slug="2026-superveteranska-liga-podzim",
        name="Superveteránská liga",
        short="SVET",
        aliases=("superveterani", "svet"),
    ),
    League(
        key="uvet",
        season_slug="2026-ultraveteranska-liga-podzim",
        name="Ultraveteránská liga",
        short="UVET",
        aliases=("ultraveterani", "uvet"),
    ),
)

LEAGUES_BY_KEY: Mapping[str, League] = {league.key: league for league in LEAGUES}


@dataclass(frozen=True, slots=True)
class GroupRef:
    """One group (skupina) within a league, e.g. level 7 group H."""

    league: League
    level: int
    group: str  # single upper-case letter, "A".."N"
    url: str

    @property
    def slug(self) -> str:
        """Path segment used by psmf.cz, e.g. ``7-h``. Unique only within a league."""
        return f"{self.level}-{self.group.lower()}"

    @property
    def key(self) -> str:
        """Globally unique identity of this group, e.g. ``vet/1-a``."""
        return f"{self.league.key}/{self.slug}"

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

    Slugs are unique only *within* a group, so a full identity is (league, group, slug).
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
    def league(self) -> League:
        return self.group.league

    @property
    def calendar_name(self) -> str:
        return f"{self.name} – {self.league.short} {SEASON_LABEL} ({self.group.label})"

    @property
    def ics_path(self) -> str:
        """Path of the generated file relative to the site root.

        The league segment is what keeps ``1-a`` in the veterans' league from
        overwriting ``1-a`` in the Hanspaulská.
        """
        return f"ics/{self.league.key}/{self.group.slug}/{self.slug}.ics"


#: Kits of every team in one group, keyed by team slug. Fixtures are always
#: intra-group, so this is enough to resolve any opponent's colours.
GroupKits = Mapping[str, "str | None"]
