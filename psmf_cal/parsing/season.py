"""Discover every group of one league's season from its index page.

The index also links per-level summary pages (``/7/``) alongside the real
groups (``/7-h/``); only the latter are groups. All four leagues publish the
same shape, so one parser serves them all -- the league only decides which
season slug the hrefs must carry.
"""

from __future__ import annotations

import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from psmf_cal.models import GroupRef, League
from psmf_cal.parsing.text import ParseError


def _group_href_re(league: League) -> re.Pattern[str]:
    return re.compile(rf"/souteze/{re.escape(league.season_slug)}/(\d+)-([a-z])/?$")


def parse_season_index(html: str, url: str, league: League) -> list[GroupRef]:
    soup = BeautifulSoup(html, "lxml")
    pattern = _group_href_re(league)

    groups: dict[str, GroupRef] = {}
    for anchor in soup.find_all("a", href=True):
        match = pattern.search(str(anchor["href"]).split("?")[0])
        if match is None:
            continue
        level, letter = int(match.group(1)), match.group(2).upper()
        ref = GroupRef(league=league, level=level, group=letter, url=urljoin(url, match.group(0)))
        groups.setdefault(ref.slug, ref)

    if not groups:
        raise ParseError(url, f"{league.name} season index linked no groups")
    return sorted(groups.values(), key=lambda g: (g.level, g.group))
