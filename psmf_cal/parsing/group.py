"""Extract the team list from a group page."""

from __future__ import annotations

import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from psmf_cal.models import SEASON_SLUG, GroupRef, TeamRef
from psmf_cal.parsing.text import ParseError, clean


def _team_href_re(group: GroupRef) -> re.Pattern[str]:
    return re.compile(rf"/souteze/{re.escape(SEASON_SLUG)}/{re.escape(group.slug)}/tymy/([^/]+)/?$")


def parse_group(html: str, url: str, group: GroupRef) -> list[TeamRef]:
    soup = BeautifulSoup(html, "lxml")
    pattern = _team_href_re(group)

    teams: dict[str, TeamRef] = {}
    for anchor in soup.find_all("a", href=True):
        match = pattern.search(str(anchor["href"]).split("?")[0])
        if match is None:
            continue
        name = clean(str(anchor.get("title") or anchor.get_text()))
        if not name:
            continue
        slug = match.group(1)
        teams.setdefault(slug, TeamRef(slug=slug, name=name, url=urljoin(url, match.group(0))))

    if not teams:
        raise ParseError(url, f"group {group.label} linked no teams")
    return sorted(teams.values(), key=lambda t: t.slug)
