"""Shared fixtures. Every test reads saved HTML from disk; none touch the network."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from psmf_cal.models import GroupRef, Pitch, Team
from psmf_cal.parsing.pitches import parse_pitches
from psmf_cal.parsing.team import parse_team_page

FIXTURES = Path(__file__).parent / "fixtures"

GROUP_7H = GroupRef(
    level=7, group="H", url="https://www.psmf.cz/souteze/2026-hanspaulska-liga-podzim/7-h/"
)
KKTNC_URL = GROUP_7H.url + "tymy/kktnc-on-tour/"
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
def stamp() -> dt.datetime:
    """A fixed DTSTAMP, so rendered output is byte-for-byte reproducible."""
    return dt.datetime(2026, 8, 18, 10, 30, 0, tzinfo=dt.UTC)
