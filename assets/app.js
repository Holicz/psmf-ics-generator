/* Kalendář zápasů PSMF — vanilla JS, no dependencies.
 *
 * Everything is pre-generated: this file searches an index and renders a panel.
 * It never builds an .ics; the download links point at files written at build time.
 */
(function () {
  'use strict';

  var MAX_RESULTS = 40;

  var input = document.getElementById('q');
  var results = document.getElementById('results');
  var detail = document.getElementById('detail');
  var status = document.getElementById('status');
  var generated = document.getElementById('generated');

  var data = null;
  var matches = [];
  var cursor = -1;

  /* Fold text for diacritics- and case-insensitive matching.
   *
   * Mirrored exactly by normalize_search() in psmf_cal/parsing/text.py, which
   * precomputes this for every team name; here it is applied to the query.
   * Verify the two agree with:
   *   node -e "console.log('Měcholupská'.normalize('NFD').replace(/\p{M}/gu,'').toLowerCase())"
   *   python3 -c "from psmf_cal.parsing.text import normalize_search as n; print(n('Měcholupská'))"
   */
  function normalize(text) {
    return text.normalize('NFD').replace(/\p{M}/gu, '').toLowerCase();
  }

  function haystack(team) {
    /* Name plus both spellings of the group, so "7.H" and "7h" both work. */
    return team.q + ' ' + normalize(team.g) + ' ' + normalize(team.g).replace('.', '');
  }

  function search(query) {
    var needle = normalize(query).trim();
    if (!needle) return [];
    var terms = needle.split(/\s+/);
    return data.teams.filter(function (team) {
      var hay = haystack(team);
      return terms.every(function (term) { return hay.indexOf(term) !== -1; });
    });
  }

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function renderResults() {
    results.textContent = '';
    var shown = matches.slice(0, MAX_RESULTS);

    shown.forEach(function (team, index) {
      var li = el('li', null);
      li.id = 'opt-' + index;
      li.setAttribute('role', 'option');
      li.setAttribute('aria-selected', index === cursor ? 'true' : 'false');
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

    if (!input.value.trim()) {
      status.textContent = '';
    } else if (!matches.length) {
      status.textContent = 'Žádný tým neodpovídá.';
    } else if (matches.length > MAX_RESULTS) {
      status.textContent = 'Nalezeno ' + matches.length + ' týmů, zobrazeno prvních ' +
        MAX_RESULTS + '. Zkus být konkrétnější.';
    } else {
      status.textContent = 'Nalezeno ' + matches.length +
        (matches.length === 1 ? ' tým.' : ' týmů.');
    }
  }

  function plural(count, one, few, many) {
    if (count === 1) return one;
    if (count >= 2 && count <= 4) return few;
    return many;
  }

  function renderDetail(team) {
    detail.textContent = '';
    detail.hidden = false;

    detail.appendChild(el('h2', null, team.n));

    var sub = el('p', 'detail-sub');
    sub.textContent = 'Skupina ' + team.g + ' · ' + team.m.length + ' ' +
      plural(team.m.length, 'zápas', 'zápasy', 'zápasů') +
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
    detail.hidden = true;
    detail.textContent = '';
    renderResults();
  }

  function onInput() {
    matches = search(input.value);
    cursor = matches.length ? 0 : -1;
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

  function start(payload) {
    data = payload;
    var when = new Date(payload.generated);
    generated.dateTime = payload.generated;
    generated.textContent = isNaN(when.getTime())
      ? payload.generated
      : when.toLocaleString('cs-CZ', {
          day: 'numeric', month: 'numeric', year: 'numeric',
          hour: '2-digit', minute: '2-digit'
        });

    input.disabled = false;
    input.addEventListener('input', onInput);
    input.addEventListener('keydown', onKeydown);

    var initial = new URLSearchParams(location.search).get('q');
    if (initial) { input.value = initial; onInput(); }
    input.focus();
  }

  input.disabled = true;
  fetch('teams.json')
    .then(function (response) {
      if (!response.ok) throw new Error('HTTP ' + response.status);
      return response.json();
    })
    .then(start)
    .catch(function (error) {
      status.textContent = 'Nepodařilo se načíst seznam týmů (' + error.message + ').';
    });
})();
