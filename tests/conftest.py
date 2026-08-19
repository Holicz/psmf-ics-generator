"""Shared fixtures. Every test reads saved HTML from disk; none touch the network."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from psmf_cal.models import LEAGUES_BY_KEY, GroupRef, League, Pitch, Team
from psmf_cal.parsing.pitches import parse_pitches
from psmf_cal.parsing.team import parse_team_page

FIXTURES = Path(__file__).parent / "fixtures"

HL: League = LEAGUES_BY_KEY["hl"]
VET: League = LEAGUES_BY_KEY["vet"]
UVET: League = LEAGUES_BY_KEY["uvet"]

GROUP_7H = GroupRef(
    league=HL,
    level=7,
    group="H",
    url="https://www.psmf.cz/souteze/2026-hanspaulska-liga-podzim/7-h/",
)
#: The veterans' 1.A. Its slug collides with the Hanspaulska 1.A, which is the
#: whole reason the league is part of every path and every UID.
GROUP_VET_1A = GroupRef(
    league=VET,
    level=1,
    group="A",
    url="https://www.psmf.cz/souteze/2026-veteranska-liga-podzim/1-a/",
)
#: An ultraveterans' group with an odd number of teams, so every team's
#: schedule carries one round off among the fixtures.
GROUP_UVET_2A = GroupRef(
    league=UVET,
    level=2,
    group="A",
    url="https://www.psmf.cz/souteze/2026-ultraveteranska-liga-podzim/2-a/",
)
KKTNC_URL = GROUP_7H.url + "tymy/kktnc-on-tour/"
DYNAMO_URL = GROUP_VET_1A.url + "tymy/dynamo-uk-vet/"
ZVAHOV_URL = GROUP_UVET_2A.url + "tymy/zvahov-uvl/"
PITCHES_URL = "https://www.psmf.cz/hriste/"


def load(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


@pytest.fixture(scope="session")
def pitches() -> dict[str, Pitch]:
    return parse_pitches(load("pitches.html"), PITCHES_URL)


@pytest.fixture(scope="session")
def kktnc(pitches: dict[str, Pitch]) -> Team:
    page = parse_team_page(
        load("team-kktnc-on-tour.html"), KKTNC_URL, GROUP_7H, "kktnc-on-tour", pitches
    )
    return Team(
        slug="kktnc-on-tour",
        name="KKTNC On Tour",
        url=KKTNC_URL,
        group=GROUP_7H,
        matches=page.matches,
        colors=page.colors,
    )


@pytest.fixture(scope="session")
def dynamo(pitches: dict[str, Pitch]) -> Team:
    """A veterans' team, so the league-aware paths are exercised on real markup."""
    page = parse_team_page(
        load("vet-team-dynamo-uk-vet.html"), DYNAMO_URL, GROUP_VET_1A, "dynamo-uk-vet", pitches
    )
    return Team(
        slug="dynamo-uk-vet",
        name="Dynamo UK VET",
        url=DYNAMO_URL,
        group=GROUP_VET_1A,
        matches=page.matches,
        colors=page.colors,
    )


@pytest.fixture(scope="session")
def stamp() -> dt.datetime:
    """A fixed DTSTAMP, so rendered output is byte-for-byte reproducible."""
    return dt.datetime(2026, 8, 18, 10, 30, 0, tzinfo=dt.UTC)
