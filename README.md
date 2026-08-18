# psmf-cal

Generates a static site where a visitor searches for a team in the Prague small-football
league (PSMF, Hanspaulská liga) and downloads a ready-made `.ics` calendar of that team's
fixtures.

Every calendar is written at build time. The site is plain HTML/CSS/JS with no backend and
no build tooling — nothing is generated when a visitor clicks.

Season covered: **Hanspaulská liga podzim 2026**.

## Usage

```sh
pip install -r requirements.txt
python -m psmf_cal.cli
```

That writes `dist/`. Serve it with any static file server:

```sh
python -m http.server -d dist 8000
```

### Options

| Flag | Meaning |
| --- | --- |
| `--dist PATH` | Output directory (default `dist`) |
| `--cache PATH` | HTML cache directory (default `.cache`) |
| `--no-cache` | Ignore cached HTML and refetch every page |
| `--only 7-h 1-a` | Restrict the crawl to specific groups — useful while developing |

The full crawl is ~760 pages at roughly 400 ms apiece, so budget about six minutes on a
cold cache. Responses are cached on disk by URL hash, so re-runs are near-instant.

Exit codes: `0` success, `1` finished with per-team failures (the site is still written
from everything that parsed), `2` a fatal error before the crawl could produce anything.

## Layout

```
psmf_cal/
  models.py      Pitch, TeamRef, Match, Team — frozen dataclasses
  http.py        caching, throttling, retry/backoff
  parsing/       HTML -> structures; never performs I/O
  ics.py         RFC 5545 rendering: escaping, folding, VTIMEZONE
  site.py        teams.json + asset emission
  validate.py    reads generated files back with `icalendar`
  cli.py         orchestration, failure reporting, exit code
assets/          index.html, style.css, app.js — copied verbatim
tests/fixtures/  saved HTML; the test suite never touches the network
```

## Development

```sh
ruff check . && ruff format --check .
mypy --strict .
pytest
```

The front end has its own optional check, which runs `assets/app.js` under a DOM stub
against a built index — search, keyboard navigation and the download links, without a
browser. It needs node and a completed build:

```sh
node tests/frontend_check.mjs
```

### Notes on a few decisions

**Fixtures are inlined into `teams.json`.** Pitch descriptions are the bulky part and they
repeat, so they are deduplicated into a shared map keyed by pitch code. What remains is
~130 bytes per fixture — under 1 MB for the whole league, which is worth one request to
avoid per-team fetch plumbing.

**Search normalisation lives in Python.** `normalize_search()` precomputes a folded form of
every team name into the index; the browser applies the identical transform to the query
only. The JS side is three lines, and the two can be compared directly:

```sh
node -e "console.log('Měcholupská'.normalize('NFD').replace(/\p{M}/gu,'').toLowerCase())"
python3 -c "from psmf_cal.parsing.text import normalize_search as n; print(n('Měcholupská'))"
```

**UIDs include the group** (`7-h-kktnc-on-tour-2026p-3@psmf.cz`). Team slugs are unique only
within a group, so without it a visitor subscribed to two groups that both contain a
"sparta" would have one team's fixtures silently overwrite the other's.

**Timezones are real.** The autumn season runs from September into December and therefore
crosses the October DST switch. Calendars carry a full `VTIMEZONE` for `Europe/Prague` with
the EU rules and use `DTSTART;TZID=`, never floating times or a pre-converted UTC. After
generating, every file is re-parsed with `icalendar` and a post-switch fixture is checked to
confirm its local wall-clock time still matches the source page.

**Refereeing duty is not included.** Team pages also publish a "Rozpis pískání" table; only
the fixture list is exported.

**Parsers fail loudly.** Unexpected markup raises `ParseError` carrying the offending URL
rather than returning an empty list — a team page that quietly parsed to zero matches would
produce a valid but empty calendar, which is worse than a crash. Per-team failures are
collected, printed as a summary, and turn the exit code non-zero without discarding the
teams that did parse.
