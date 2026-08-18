/* Optional front-end check: runs the real assets/app.js under a DOM stub
 * against a built dist/teams.json, so the search, keyboard handling and
 * download links are exercised without a browser.
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
for (const id of ['q','results','detail','status','generated']) { nodes[id] = mkNode('div'); nodes[id].id = id; }
global.document = {
  getElementById: id => nodes[id],
  createElement: mkNode,
  createTextNode: t => { const n = mkNode('#text'); n.textContent = t; return n; },
};
global.location = { search: '' };
global.window = global;

// --- load the generated index exactly as the page does ----------------
eval(fs.readFileSync('dist/teams.js', 'utf8'));
if (!global.PSMF_DATA) { console.error('dist/teams.js did not define PSMF_DATA'); process.exit(1); }

// --- run the real app.js ---------------------------------------------
eval(fs.readFileSync('assets/app.js', 'utf8'));
await new Promise(r => setTimeout(r, 30));

const q = nodes.q, results = nodes.results, detail = nodes.detail, status = nodes.status;
const names = () => results.children.map(li => li.children[1].textContent);
const badges = () => results.children.map(li => li.children[0].textContent);
function type(text) { q.value = text; q.fire('input'); }
function key(k) { q.fire('keydown', { key: k, preventDefault(){} }); }

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
type('7.h');
check('"7.h" lists that group', badges().every(b => b === '7.H') && results.children.length === 12, badges().join(','));
type('7h');
check('"7h" works without the dot', badges().every(b => b === '7.H') && results.children.length === 12);

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
check('href points at the pre-generated file', link && link.href === 'ics/7-h/kktnc-on-tour.ics', link && link.href);
check('download attribute is set', link && link.getAttribute('download') === 'kktnc-on-tour.ics');
check('detail lists all 11 fixtures', detail.textContent.match(/doma|venku/g)?.length >= 11);
check('detail shows pitch name and address', detail.textContent.includes('Podvinný mlýn (PODV2)') && detail.textContent.includes('Kovanecká, Praha 9'));
check('detail shows opponent', detail.textContent.includes('Real Oranjes'));

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
