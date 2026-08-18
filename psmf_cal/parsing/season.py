"""Discover every group of the season from its index page.

The index also links per-level summary pages (``/7/``) alongside the real
groups (``/7-h/``); only the latter are groups.
"""

from __future__ import annotations

import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from psmf_cal.models import SEASON_SLUG, GroupRef
from psmf_cal.parsing.text import ParseError

_GROUP_HREF_RE = re.compile(rf"/souteze/{re.escape(SEASON_SLUG)}/(\d+)-([a-z])/?$")


def parse_season_index(html: str, url: str) -> list[GroupRef]:
    soup = BeautifulSoup(html, "lxml")

    groups: dict[str, GroupRef] = {}
    for anchor in soup.find_all("a", href=True):
        match = _GROUP_HREF_RE.search(str(anchor["href"]).split("?")[0])
        if match is None:
            continue
        level, letter = int(match.group(1)), match.group(2).upper()
        ref = GroupRef(level=level, group=letter, url=urljoin(url, match.group(0)))
        groups.setdefault(ref.slug, ref)

    if not groups:
        raise ParseError(url, "season index linked no groups")
    return sorted(groups.values(), key=lambda g: (g.level, g.group))
