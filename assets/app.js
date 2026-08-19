/* Kalendář zápasů PSMF — vanilla JS, no dependencies.
 *
 * Everything is pre-generated: this file searches an index and renders a panel.
 * It never builds an .ics; the download links point at files written at build time.
 *
 * The index spans four leagues, so a team's identity is (league, group, slug).
 * Group labels such as "1.A" exist in every league, which is why the league is
 * both a filter above the box and a badge on every row.
 */
(function () {
  'use strict';

  var MAX_RESULTS = 40;
  var ALL = '';                     /* the "Vše" filter: no league restriction */

  var input = document.getElementById('q');
  var results = document.getElementById('results');
  var detail = document.getElementById('detail');
  var status = document.getElementById('status');
  var generated = document.getElementById('generated');
  var chipHost = document.getElementById('league-chips');

  var data = null;
  var leagues = {};                 /* key -> league entry from the index */
  var league = ALL;
  var chips = [];                   /* [{key, radio}] in display order */
  var matches = [];
  var cursor = -1;
  var opened = null;                /* the team whose schedule is on screen */

  /* Fold text for diacritics- and case-insensitive matching.
   *
   * Mirrored exactly by normalize_search() in psmf_cal/parsing/text.py, which
   * precomputes this for every team name and every league's search terms; here
   * it is applied to the query. Verify the two agree with:
   *   node -e "console.log('Měcholupská'.normalize('NFD').replace(/\p{M}/gu,'').toLowerCase())"
   *   python3 -c "from psmf_cal.parsing.text import normalize_search as n; print(n('Měcholupská'))"
   */
  function normalize(text) {
    return text.normalize('NFD').replace(/\p{M}/gu, '').toLowerCase();
  }

  /* Everything one team can be found by, folded once at start-up rather than
   * per keystroke: the name, the league (name, badge and aliases such as
   * "vet"), and both spellings of the group so "7.H" and "7h" both work. */
  function buildHaystacks() {
    data.teams.forEach(function (team) {
      var group = normalize(team.g);
      var entry = leagues[team.l];
      team.hay = team.q + ' ' + (entry ? entry.q : team.l) + ' ' +
        group + ' ' + group.replace('.', '');
    });
  }

  function search(query, restrictTo) {
    var needle = normalize(query).trim();
    if (!needle) return [];
    var terms = needle.split(/\s+/);
    return data.teams.filter(function (team) {
      if (restrictTo !== ALL && team.l !== restrictTo) return false;
      return terms.every(function (term) { return team.hay.indexOf(term) !== -1; });
    });
  }

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  /* ---------- league filter ---------- */

  /* "Veteránská liga" -> "Veteránská": the chips sit under a "Liga" legend, so
   * repeating the word in every one of them is noise. */
  function chipLabel(name) {
    return name.replace(/\s+liga$/i, '');
  }

  function addChip(key, label, count) {
    var wrap = el('label', 'chip' + (key ? ' chip-' + key : ' chip-all'));
    var radio = document.createElement('input');
    radio.type = 'radio';
    radio.name = 'liga';
    radio.value = key;
    radio.checked = key === league;
    radio.addEventListener('change', function () { setLeague(key); });
    wrap.appendChild(radio);
    wrap.appendChild(el('span', 'chip-text', label));
    wrap.appendChild(el('span', 'chip-count', String(count)));
    chipHost.appendChild(wrap);
    chips.push({ key: key, radio: radio });
  }

  function renderChips() {
    var counts = {};
    data.teams.forEach(function (t) { counts[t.l] = (counts[t.l] || 0) + 1; });

    addChip(ALL, 'Vše', data.teams.length);
    data.leagues.forEach(function (entry) {
      addChip(entry.k, chipLabel(entry.n), counts[entry.k] || 0);
    });
  }

  function setLeague(key) {
    if (league === key) return;
    league = key;
    chips.forEach(function (chip) { chip.radio.checked = chip.key === key; });
    onInput();   /* drops the open schedule too, if the filter excluded it */
    syncUrl();
  }

  /* ---------- results ---------- */

  function leagueName(key) {
    return leagues[key] ? leagues[key].n : key;
  }

  function leagueShort(key) {
    return leagues[key] ? leagues[key].s : key;
  }

  function renderResults() {
    results.textContent = '';
    var shown = matches.slice(0, MAX_RESULTS);
    /* Redundant once a single league is selected -- the chip above already says it. */
    var showLeague = league === ALL;

    shown.forEach(function (team, index) {
      var li = el('li', null);
      li.id = 'opt-' + index;
      li.setAttribute('role', 'option');
      li.setAttribute('aria-selected', index === cursor ? 'true' : 'false');
      if (showLeague) {
        li.appendChild(el('span', 'badge league lg-' + team.l, leagueShort(team.l)));
      }
      li.appendChild(el('span', 'badge', team.g));
      li.appendChild(el('span', 'result-name', team.n));
      li.appendChild(el('span', 'result-meta', team.m.length + ' zápasů'));
      li.addEventListener('mousedown', function (event) {
        event.preventDefault();       /* keep focus in the input */
        select(index);
      });
      results.appendChild(li);
    });

    input.setAttribute('aria-expanded', shown.length ? 'true' : 'false');
    if (cursor >= 0 && shown[cursor]) {
      input.setAttribute('aria-activedescendant', 'opt-' + cursor);
      var active = results.children[cursor];
      if (active.scrollIntoView) active.scrollIntoView({ block: 'nearest' });
    } else {
      input.removeAttribute('aria-activedescendant');
    }

    renderStatus();
  }

  function renderStatus() {
    status.textContent = '';
    if (!input.value.trim()) return;

    if (!matches.length) {
      /* A miss inside one league is usually the filter, not the query: say how
       * many teams the same words find everywhere and offer one tap out. */
      var elsewhere = league === ALL ? [] : search(input.value, ALL);
      if (elsewhere.length) {
        status.appendChild(document.createTextNode(
          'V lize ' + leagueName(league) + ' nic. Ve všech ligách: ' + elsewhere.length + '. '));
        var reset = el('button', 'link-button', 'Hledat ve všech ligách');
        reset.type = 'button';
        reset.addEventListener('click', function () { setLeague(ALL); });
        status.appendChild(reset);
      } else {
        status.textContent = 'Žádný tým neodpovídá.';
      }
      return;
    }

    var where = league === ALL ? '' : ' v lize ' + leagueName(league);
    if (matches.length > MAX_RESULTS) {
      status.textContent = 'Nalezeno ' + matches.length + ' týmů' + where +
        ', zobrazeno prvních ' + MAX_RESULTS + '. Zkus být konkrétnější.';
    } else {
      status.textContent = 'Nalezeno ' + matches.length +
        (matches.length === 1 ? ' tým' : ' týmů') + where + '.';
    }
  }

  function plural(count, one, few, many) {
    if (count === 1) return one;
    if (count >= 2 && count <= 4) return few;
    return many;
  }

  function closeDetail() {
    opened = null;
    detail.hidden = true;
    detail.textContent = '';
  }

  function renderDetail(team) {
    opened = team;
    detail.textContent = '';
    detail.hidden = false;

    detail.appendChild(el('h2', null, team.n));

    var sub = el('p', 'detail-sub');
    sub.textContent = leagueName(team.l) + ' · skupina ' + team.g + ' · ' +
      team.m.length + ' ' + plural(team.m.length, 'zápas', 'zápasy', 'zápasů') +
      (team.c ? ' · dresy: ' + team.c : '');
    detail.appendChild(sub);

    var link = el('a', 'download', '⬇ Stáhnout kalendář (.ics)');
    link.href = team.ics;
    link.setAttribute('download', team.s + '.ics');
    link.type = 'text/calendar';
    detail.appendChild(link);

    var note = el('p', 'download-note');
    note.textContent = 'Soubor otevři v Google Kalendáři, Apple Kalendáři nebo Outlooku. ' +
      'Časy jsou v pražském čase včetně přechodu na zimní čas. Upozornění 3 hodiny před výkopem.';
    detail.appendChild(note);

    var list = el('div', 'fixtures');
    team.m.forEach(function (match) {
      var pitch = data.pitches[match.p] || { n: match.p, a: '' };
      var row = el('div', 'fixture');

      var when = el('div', 'fixture-when');
      when.appendChild(el('strong', null, formatDate(match.d)));
      when.appendChild(document.createTextNode(match.w + ' ' + match.t));
      row.appendChild(when);

      var opponent = el('div', 'fixture-opponent');
      opponent.appendChild(document.createTextNode(match.o));
      opponent.appendChild(el('span', 'side ' + (match.h ? 'doma' : 'venku'),
        match.h ? 'doma' : 'venku'));
      row.appendChild(opponent);

      var place = el('div', 'fixture-place');
      place.appendChild(el('span', 'code', pitch.n + ' (' + match.p + ')'));
      if (pitch.a) place.appendChild(document.createTextNode(' · ' + pitch.a));
      row.appendChild(place);

      list.appendChild(row);
    });
    detail.appendChild(list);
  }

  function formatDate(iso) {
    var parts = iso.split('-');
    return Number(parts[2]) + '. ' + Number(parts[1]) + '.';
  }

  function select(index) {
    if (index < 0 || index >= matches.length) return;
    cursor = index;
    renderResults();
    renderDetail(matches[index]);
    detail.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
  }

  function clear() {
    input.value = '';
    matches = [];
    cursor = -1;
    closeDetail();
    renderResults();
    syncUrl();
  }

  function onInput() {
    matches = search(input.value, league);
    cursor = matches.length ? 0 : -1;
    /* A schedule left standing under a result list that no longer contains it
     * reads as the answer to the query being typed, which it is not. */
    if (opened && matches.indexOf(opened) === -1) closeDetail();
    renderResults();
  }

  function onKeydown(event) {
    if (event.key === 'Escape') {
      clear();
      event.preventDefault();
      return;
    }
    if (event.key === 'Enter') {
      if (cursor >= 0) { select(cursor); event.preventDefault(); }
      return;
    }
    if (event.key !== 'ArrowDown' && event.key !== 'ArrowUp') return;

    var limit = Math.min(matches.length, MAX_RESULTS);
    if (!limit) return;
    event.preventDefault();
    cursor = event.key === 'ArrowDown'
      ? (cursor + 1) % limit
      : (cursor <= 0 ? limit - 1 : cursor - 1);
    renderResults();
  }

  /* Keep the address bar in step with the query and the filter, so a search
   * worth sharing can simply be copied out of it. replaceState, not pushState:
   * typing must not bury the page under a hundred history entries. */
  function syncUrl() {
    if (!window.history || !history.replaceState) return;
    var parts = [];
    if (league !== ALL) parts.push('liga=' + encodeURIComponent(league));
    if (input.value.trim()) parts.push('q=' + encodeURIComponent(input.value.trim()));
    history.replaceState(null, '', parts.length ? '?' + parts.join('&') : location.pathname);
  }

  function onInputAndSync() {
    onInput();
    syncUrl();
  }

  function start(payload) {
    data = payload;
    data.leagues = data.leagues || [];
    data.leagues.forEach(function (entry) { leagues[entry.k] = entry; });
    buildHaystacks();

    var when = new Date(payload.generated);
    generated.dateTime = payload.generated;
    generated.textContent = isNaN(when.getTime())
      ? payload.generated
      : when.toLocaleString('cs-CZ', {
          day: 'numeric', month: 'numeric', year: 'numeric',
          hour: '2-digit', minute: '2-digit'
        });

    var params = new URLSearchParams(location.search);
    var wanted = params.get('liga');
    if (wanted && leagues[wanted]) league = wanted;

    renderChips();

    input.disabled = false;
    input.addEventListener('input', onInputAndSync);
    input.addEventListener('keydown', onKeydown);

    var initial = params.get('q');
    if (initial) { input.value = initial; onInput(); }
    input.focus();
  }

  /* teams.js is a plain <script> that assigns window.PSMF_DATA, rather than
   * JSON fetched at runtime: a page opened directly from disk cannot fetch a
   * sibling file, and this way the site works both from file:// and from any
   * static server. */
  if (window.PSMF_DATA && Array.isArray(window.PSMF_DATA.teams)) {
    start(window.PSMF_DATA);
  } else {
    input.disabled = true;
    status.textContent = 'Nepodařilo se načíst seznam týmů – chybí soubor teams.js.';
  }
})();
