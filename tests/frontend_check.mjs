/* Optional front-end check: runs the real assets/app.js under a DOM stub
 * against a built dist/teams.js, so the search, the league filter, keyboard
 * handling and the download links are exercised without a browser.
 *
 * Not part of the pytest suite -- it needs node and a completed build:
 *   python -m psmf_cal.cli && node tests/frontend_check.mjs
 */
import fs from 'fs';

// --- minimal DOM stub -------------------------------------------------
function mkNode(tag) {
  return {
    tagName: tag, className: '', id: '', hidden: false, disabled: false,
    value: '', href: '', type: '', dateTime: '', children: [], attrs: {},
    _text: '',
    get textContent() {
      return this.children.length
        ? this.children.map(c => c.textContent).join('')
        : this._text;
    },
    set textContent(v) { this._text = v; this.children = []; },
    appendChild(c) { this.children.push(c); return c; },
    setAttribute(k, v) { this.attrs[k] = v; },
    getAttribute(k) { return this.attrs[k]; },
    removeAttribute(k) { delete this.attrs[k]; },
    addEventListener(ev, fn) { (this._h ||= {})[ev] = fn; },
    fire(ev, arg) { this._h?.[ev]?.(arg); },
    createTextNode: null, scrollIntoView() {}, focus() {},
  };
}
const nodes = {};
for (const id of ['q','results','detail','status','generated','league-chips']) {
  nodes[id] = mkNode('div'); nodes[id].id = id;
}
global.document = {
  getElementById: id => nodes[id],
  createElement: mkNode,
  createTextNode: t => { const n = mkNode('#text'); n.textContent = t; return n; },
};
global.location = { search: '', pathname: '/' };
/* app.js keeps the address bar in step with the query; the stub only has to
 * record what it was asked to write, which the deep-link checks then read. */
let lastUrl = null;
global.history = { replaceState: (_s, _t, url) => { lastUrl = url; } };
global.window = global;

// --- load the generated index exactly as the page does ----------------
eval(fs.readFileSync('dist/teams.js', 'utf8'));
if (!global.PSMF_DATA) { console.error('dist/teams.js did not define PSMF_DATA'); process.exit(1); }

// --- run the real app.js ---------------------------------------------
eval(fs.readFileSync('assets/app.js', 'utf8'));
await new Promise(r => setTimeout(r, 30));

const q = nodes.q, results = nodes.results, detail = nodes.detail, status = nodes.status;
const chips = nodes['league-chips'];
/* A row is [league badge?, group badge, name, meta]; the league badge is dropped
 * once a single league is selected, so read the fields from the end. */
const names = () => results.children.map(li => li.children[li.children.length - 2].textContent);
const groups = () => results.children.map(li => li.children[li.children.length - 3].textContent);
const leagueBadges = () =>
  results.children.map(li => li.children.length === 4 ? li.children[0].textContent : null);
function type(text) { q.value = text; q.fire('input'); }
function key(k) { q.fire('keydown', { key: k, preventDefault(){} }); }
/* Chip label nodes wrap a radio; clicking one in a browser fires 'change'. */
function chipRadio(label) {
  return chips.children.find(c => c.children[1].textContent === label)?.children[0];
}
function pickLeague(label) { chipRadio(label).fire('change'); }

let fails = 0;
const check = (label, cond, extra='') => { console.log((cond?'  PASS  ':'  FAIL  ')+label+(cond?'':'  '+extra)); if(!cond) fails++; };

console.log('footer timestamp rendered:', JSON.stringify(nodes.generated.textContent));
console.log('\n--- diacritics-insensitive search, both directions ---');
type('mecholupska');
check('"mecholupska" finds the accented name', names().some(n => n.includes('Měcholupská')), names().join('|'));
type('Měcholupská');
check('"Měcholupská" finds it too', names().some(n => n.includes('Měcholupská')));
type('MECHOLUPSKA');
check('uppercase, unaccented works', names().some(n => n.includes('Měcholupská')));
type('houbaruv raj');
check('"houbaruv raj" finds Houbařův Ráj', names().some(n => n.includes('Houbařův Ráj')));
type('brondby');
check('"brondby" finds Bröndby (o-umlaut)', names().some(n => n.includes('Bröndby')));

console.log('\n--- multi-term and group search ---');
type('kktnc tour');
check('two terms both required', names().some(n => n === 'KKTNC On Tour'));
type('hanspaulska 7.h');
check('"7.h" lists that group', groups().every(b => b === '7.H') && results.children.length === 12, groups().join(','));
type('hanspaulska 7h');
check('"7h" works without the dot', groups().every(b => b === '7.H') && results.children.length === 12);

console.log('\n--- leagues ---');
const leagueKeys = PSMF_DATA.leagues.map(l => l.k);
check('index carries every league', leagueKeys.length >= 1, leagueKeys.join(','));
check('a chip per league plus "Vše"', chips.children.length === leagueKeys.length + 1,
  chips.children.map(c => c.children[1].textContent).join(','));
/* Level 7 only exists in the Hanspaulska; 1.A exists in all four, which is
 * exactly why a bare group label cannot identify a team any more. */
type('1.a');
check('group 1.A alone spans several leagues',
  leagueKeys.length === 1 || new Set(leagueBadges()).size > 1, leagueBadges().join(','));
if (leagueKeys.includes('vet')) {
  type('vet');
  check('"vet" finds veterans by league name', leagueBadges().some(b => b === 'VET'));
  pickLeague('Veteránská');
  type('a');
  check('filtering to one league leaves only its teams',
    results.children.every(li => li.children.length === 3), 'league badge should be dropped');
  check('the filtered search says which league it searched',
    status.textContent.includes('Veteránská'), status.textContent);
  check('the filter reaches the address bar', /liga=vet/.test(lastUrl || ''), String(lastUrl));
  type('zzzz-neexistuje');
  check('a miss inside a filter reports it', status.textContent.includes('nic') ||
    status.textContent.includes('Žádný'), status.textContent);
  pickLeague('Vše');
  check('clearing the filter drops it from the address bar', !/liga=/.test(lastUrl || ''),
    String(lastUrl));
}

console.log('\n--- keyboard ---');
type('kktnc');
const before = results.children.findIndex(li => li.getAttribute('aria-selected') === 'true');
check('first result is preselected', before === 0);
key('ArrowDown');
check('ArrowDown moves the cursor', results.children.findIndex(li => li.getAttribute('aria-selected')==='true') === (results.children.length>1?1:0));
key('ArrowUp');
check('ArrowUp moves back', results.children.findIndex(li => li.getAttribute('aria-selected')==='true') === 0);
type('kktnc on tour');
key('Enter');
check('Enter opens the detail panel', detail.hidden === false);

const link = (function find(n){ if(n.className==='download') return n; for(const c of n.children){ const r=find(c); if(r) return r; } return null; })(detail);
check('download link exists', !!link);
check('href points at the pre-generated file', link && link.href === 'ics/hl/7-h/kktnc-on-tour.ics', link && link.href);
check('download attribute is set', link && link.getAttribute('download') === 'kktnc-on-tour.ics');
check('detail lists all 11 fixtures', detail.textContent.match(/doma|venku/g)?.length >= 11);
check('detail shows pitch name and address', detail.textContent.includes('Podvinný mlýn (PODV2)') && detail.textContent.includes('Kovanecká, Praha 9'));
check('detail shows opponent', detail.textContent.includes('Real Oranjes'));
check('detail names the league', detail.textContent.includes('Hanspaulská liga'), detail.textContent.slice(0, 120));
check('the query reaches the address bar', /q=kktnc/.test(lastUrl || ''), String(lastUrl));

type('kktnc on tour');
key('Enter');
type('mecholupska');
check('retyping past the open team closes its schedule', detail.hidden === true);
type('kktnc on tour');
key('Enter');
type('kktnc');
check('a team still in the results stays open', detail.hidden === false);

key('Escape');
check('Escape clears input', q.value === '');
check('Escape hides detail', detail.hidden === true);
check('Escape empties results', results.children.length === 0);

console.log('\n--- no-match and cap ---');
type('zzzzzz');
check('no match reports it', status.textContent.includes('Žádný'), status.textContent);
type('fc');
check('over-cap search is capped at 40', results.children.length <= 40);
check('over-cap search says so', /zobrazeno prvních 40|Nalezeno/.test(status.textContent), status.textContent);

console.log(fails === 0 ? '\nALL FRONT-END CHECKS PASSED' : `\n${fails} CHECK(S) FAILED`);
process.exit(fails === 0 ? 0 : 1);
