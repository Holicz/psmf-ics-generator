"""Command line entry point: crawl, generate, validate, report.

This is the only module aware of both the network and the filesystem. Parsing,
ICS rendering and site rendering are all pure functions it calls.
"""

from __future__ import annotations

import argparse
import datetime as dt
import logging
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

from psmf_cal.http import CachedFetcher, FetchError
from psmf_cal.ics import render_calendar
from psmf_cal.models import PITCHES_URL, SEASON_URL, GroupRef, Pitch, Team
from psmf_cal.parsing.group import parse_group
from psmf_cal.parsing.pitches import parse_pitches
from psmf_cal.parsing.season import parse_season_index
from psmf_cal.parsing.team import parse_team_page
from psmf_cal.parsing.text import ParseError
from psmf_cal.site import write_site
from psmf_cal.validate import ValidationError, assert_dst_boundary_is_sane, validate_calendar

log = logging.getLogger("psmf_cal")


@dataclass(frozen=True, slots=True)
class Failure:
    """One team or group we could not process, kept for the closing summary."""

    url: str
    detail: str


def _collect_group(
    fetcher: CachedFetcher,
    group: GroupRef,
    pitches: dict[str, Pitch],
    failures: list[Failure],
) -> list[Team]:
    """Crawl one group. A team that fails is recorded and skipped, not fatal."""
    try:
        listing = parse_group(fetcher.get(group.url), group.url, group)
    except (FetchError, ParseError) as exc:
        failures.append(Failure(group.url, str(exc)))
        log.error("group %s: FAILED (%s)", group.label, exc)
        return []

    teams: list[Team] = []
    for ref in listing:
        try:
            page = parse_team_page(fetcher.get(ref.url), ref.url, group, ref.slug, pitches)
        except (FetchError, ParseError) as exc:
            failures.append(Failure(ref.url, str(exc)))
            log.error("  team %s: FAILED (%s)", ref.slug, exc)
            continue
        teams.append(
            Team(
                slug=ref.slug,
                name=ref.name,
                url=ref.url,
                group=group,
                matches=page.matches,
                colors=page.colors,
            )
        )

    total = sum(len(t.matches) for t in teams)
    log.info(
        "group %s: %d teams, %d matches%s",
        group.label,
        len(teams),
        total,
        "" if len(teams) == len(listing) else f" ({len(listing) - len(teams)} failed)",
    )
    return teams


def _write_calendars(
    dist: Path, teams: list[Team], stamp: dt.datetime, failures: list[Failure]
) -> tuple[int, str]:
    """Render, validate and write one .ics per team. Returns (count, dst_note)."""
    by_group: dict[str, dict[str, str | None]] = {}
    for team in teams:
        by_group.setdefault(team.group.slug, {})[team.slug] = team.colors

    written = 0
    dst_note = ""
    for team in teams:
        payload = render_calendar(team, by_group[team.group.slug], stamp)
        try:
            validate_calendar(team, payload)
            note = assert_dst_boundary_is_sane(team, payload)
        except ValidationError as exc:
            failures.append(Failure(team.url, f"validation: {exc}"))
            log.error("  %s: VALIDATION FAILED (%s)", team.ics_path, exc)
            continue
        if note and not dst_note:
            dst_note = note

        path = dist / team.ics_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        written += 1
    return written, dst_note


def _directory_size(path: Path) -> int:
    return sum(p.stat().st_size for p in path.rglob("*") if p.is_file())


def _human(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    return f"{value:.1f} GB"


def build(args: argparse.Namespace) -> int:
    started = dt.datetime.now(dt.UTC)
    fetcher = CachedFetcher(args.cache, use_cache=not args.no_cache)

    log.info("pitch directory %s", PITCHES_URL)
    pitches = parse_pitches(fetcher.get(PITCHES_URL), PITCHES_URL)
    log.info("  %d pitch codes", len(pitches))

    log.info("season index %s", SEASON_URL)
    groups = parse_season_index(fetcher.get(SEASON_URL), SEASON_URL)
    if args.only:
        wanted = set(args.only)
        groups = [g for g in groups if g.slug in wanted]
        if not groups:
            log.error("no group matched --only %s", ", ".join(sorted(wanted)))
            return 2
    log.info("  %d groups", len(groups))

    failures: list[Failure] = []
    teams: list[Team] = []
    for group in groups:
        teams.extend(_collect_group(fetcher, group, pitches, failures))

    if not teams:
        log.error("no teams were parsed; refusing to write an empty site")
        return 1

    dist: Path = args.dist
    if dist.exists():
        shutil.rmtree(dist)
    written, dst_note = _write_calendars(dist, teams, started, failures)
    index_path = write_site(dist, teams, pitches, started.astimezone())

    log.info("")
    log.info("=" * 62)
    log.info("teams parsed      %d", len(teams))
    log.info("matches           %d", sum(len(t.matches) for t in teams))
    log.info("ics files written %d", written)
    log.info("teams.json        %s", _human(index_path.stat().st_size))
    log.info("dist/             %s", _human(_directory_size(dist)))
    log.info("http              %d cached, %d fetched", fetcher.hits, fetcher.misses)
    if dst_note:
        log.info("DST spot-check    %s", dst_note)

    if failures:
        log.error("")
        log.error("%d FAILURE(S):", len(failures))
        for failure in failures:
            log.error("  %s", failure.url)
            log.error("      %s", failure.detail)
        return 1

    log.info("no failures")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="psmf-cal",
        description="Generate a static site of .ics calendars for Hanspaulska liga teams.",
    )
    parser.add_argument("--dist", type=Path, default=Path("dist"), help="output directory")
    parser.add_argument("--cache", type=Path, default=Path(".cache"), help="HTML cache directory")
    parser.add_argument(
        "--no-cache", action="store_true", help="ignore cached HTML and refetch every page"
    )
    parser.add_argument(
        "--only",
        nargs="+",
        metavar="GROUP",
        help="restrict the crawl to these group slugs, e.g. 7-h 1-a",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout)
    try:
        return build(args)
    except (FetchError, ParseError) as exc:
        log.error("fatal: %s", exc)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
