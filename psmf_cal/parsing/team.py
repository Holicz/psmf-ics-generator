"""Parse a team page into its list of fixtures.

A team page carries four tables: the group standings, the fixture list
(``games-new-table``), an empty unofficial-result widget, and the refereeing
roster (``referees-table``). Only the fixture list is read here -- it is
selected by class and then confirmed by its header row, so a layout change is a
loud failure rather than a silently empty calendar.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag

from psmf_cal.models import SEASON_SLUG, GroupRef, Match, Pitch, TeamRef
from psmf_cal.parsing.text import ParseError, clean, parse_time, split_date_cell, to_prague

_FIXTURE_TABLE_CLASS = "games-new-table"
_EXPECTED_HEADERS = ("Datum", "Čas", "Hřiště", "Domácí - Hosté", "Kolo")
_TEAM_HREF_RE = re.compile(rf"/souteze/{re.escape(SEASON_SLUG)}/[^/]+/tymy/([^/]+)/?$")
_PITCH_HREF_RE = re.compile(r"/hriste/#([A-Za-z0-9]+)$")
_ROUND_RE = re.compile(r"^(\d+)\.?$")


def _fixture_table(soup: BeautifulSoup, url: str) -> Tag:
    table = soup.find("table", class_=_FIXTURE_TABLE_CLASS)
    if not isinstance(table, Tag):
        raise ParseError(url, f"no table.{_FIXTURE_TABLE_CLASS} on team page")

    rows = table.find_all("tr")
    if not rows:
        raise ParseError(url, "fixture table has no rows")
    headers = tuple(clean(cell.get_text()) for cell in rows[0].find_all(["th", "td"]))
    if headers != _EXPECTED_HEADERS:
        raise ParseError(url, f"unexpected fixture headers {headers!r}")
    return table


def _team_refs(cell: Tag, url: str, base_url: str) -> tuple[TeamRef, TeamRef]:
    """Home and away, taken from the two team links in document order.

    Reading identity from the hrefs rather than the visible text means a team
    whose name contains a dash, or two teams with the same name, still resolve
    correctly.
    """
    refs: list[TeamRef] = []
    for anchor in cell.find_all("a", href=True):
        match = _TEAM_HREF_RE.search(str(anchor["href"]).split("?")[0])
        if match is None:
            continue  # the shirt-colour toggles link to "#"
        refs.append(
            TeamRef(
                slug=match.group(1),
                name=clean(str(anchor.get("title") or anchor.get_text())),
                url=urljoin(base_url, match.group(0)),
            )
        )
    if len(refs) != 2:
        raise ParseError(url, f"fixture row names {len(refs)} teams, expected 2")
    return refs[0], refs[1]


def _own_colors(table: Tag, own_name: str) -> str | None:
    """The kit this page's team is published as wearing.

    Every fixture row carries a colour swatch per team; on a team's own page the
    swatch labelled with its own name is the authoritative record of its kit.
    Opponent swatches appearing in these rows are deliberately ignored -- each
    opponent's colours are read from that opponent's own page instead, so kits
    are resolved by slug and never by matching display names.
    """
    for anchor in table.find_all("a", attrs={"data-dccolor": True}):
        if clean(str(anchor.get("data-dctitle", ""))) == own_name:
            color = clean(str(anchor["data-dccolor"]))
            if color:
                return color
    return None


@dataclass(frozen=True, slots=True)
class ParsedTeamPage:
    """Everything one team page contributes to the build."""

    matches: tuple[Match, ...]
    colors: str | None


def parse_team_page(
    html: str,
    url: str,
    group: GroupRef,
    team_slug: str,
    pitches: dict[str, Pitch],
) -> ParsedTeamPage:
    soup = BeautifulSoup(html, "lxml")
    table = _fixture_table(soup, url)

    matches: list[Match] = []
    for row in table.find_all("tr")[1:]:
        cells = row.find_all("td")
        if len(cells) != 5:
            raise ParseError(url, f"fixture row has {len(cells)} cells, expected 5")

        weekday, date = split_date_cell(cells[0].get_text(), url=url)
        kickoff_time = parse_time(clean(cells[1].get_text()), url=url)

        pitch_anchor = cells[2].find("a", href=_PITCH_HREF_RE)
        if not isinstance(pitch_anchor, Tag):
            raise ParseError(url, f"round {clean(cells[4].get_text())}: no pitch link")
        pitch_match = _PITCH_HREF_RE.search(str(pitch_anchor["href"]))
        assert pitch_match is not None  # guaranteed by the find() predicate
        code = pitch_match.group(1)
        if code not in pitches:
            raise ParseError(url, f"pitch code {code!r} is absent from the pitch directory")

        home, away = _team_refs(cells[3], url, base_url=url)
        if team_slug not in (home.slug, away.slug):
            raise ParseError(
                url, f"fixture {home.slug} v {away.slug} does not involve {team_slug!r}"
            )

        round_text = clean(cells[4].get_text())
        round_match = _ROUND_RE.match(round_text)
        if round_match is None:
            raise ParseError(url, f"unrecognised round {round_text!r}")

        matches.append(
            Match(
                round_no=int(round_match.group(1)),
                kickoff=to_prague(date, kickoff_time),
                weekday=weekday,
                home=home,
                away=away,
                pitch=pitches[code],
            )
        )

    if not matches:
        raise ParseError(url, "fixture table lists no matches")

    rounds = [m.round_no for m in matches]
    if len(set(rounds)) != len(rounds):
        raise ParseError(url, f"duplicate round numbers {sorted(rounds)}")

    own_name = next(m.home.name if m.home.slug == team_slug else m.away.name for m in matches)
    return ParsedTeamPage(
        matches=tuple(sorted(matches, key=lambda m: (m.kickoff, m.round_no))),
        colors=_own_colors(table, own_name),
    )
