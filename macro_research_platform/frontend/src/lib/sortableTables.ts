// Every plain data table sorts by its column headers — app-wide, without touching each table. One delegated
// listener: hovering a header marks its table sortable (if it is a simple grid and does not already sort itself);
// a click (or Enter) cycles that column descending → ascending → original order for numbers, ascending first for
// text. Numbers are read the way the tables print them ($1.2B, -3.4%, (12), 25bp, 8.5×); blanks and dashes sort
// last. The sort is re-applied when React re-renders or live values tick, so the order holds while data updates.

const BLANK = /^(|—|–|-|n\/?a|na|null|none|…|\.\.\.)$/i;
const MULT: Record<string, number> = { k: 1e3, m: 1e6, b: 1e9, bn: 1e9, t: 1e12, tn: 1e12 };

/** A table cell's text as a number, or null when it is not one. */
export function cellNumber(raw: string): number | null {
  let s = raw.replace(/\s+/g, '').replace(/[,$€£¥₩]/g, '').replace(/[−–]/g, '-');
  if (!s || BLANK.test(s)) return null;
  let sign = 1;
  if (/^\(.*\)$/.test(s)) { sign = -1; s = s.slice(1, -1); }
  const m = s.match(/^([+-]?\d*\.?\d+(?:e[+-]?\d+)?)(k|m|bn|b|tn|t)?(%|bp|bps|x|×|pp|pts?)?$/i);
  if (!m) return null;
  const v = parseFloat(m[1]) * (m[2] ? MULT[m[2].toLowerCase()] : 1);
  return Number.isFinite(v) ? sign * v : null;
}

/** Sort comparator over cell texts: numeric when most of the column is numeric, else natural text order. */
export function columnKind(texts: string[]): 'num' | 'text' {
  const filled = texts.filter((t) => !BLANK.test(t.replace(/\s+/g, '')));
  if (!filled.length) return 'text';
  return filled.filter((t) => cellNumber(t) !== null).length / filled.length >= 0.6 ? 'num' : 'text';
}

type Dir = 'desc' | 'asc';
interface State { col: number; dir: Dir; kind: 'num' | 'text' }
const states = new WeakMap<HTMLTableElement, State>();
const observers = new WeakMap<HTMLTableElement, MutationObserver>();

const headerRow = (t: HTMLTableElement) => t.tHead?.rows[t.tHead.rows.length - 1] ?? null;
const bodyRows = (t: HTMLTableElement) => Array.from(t.tBodies[0]?.rows ?? []);
const cellText = (r: HTMLTableRowElement, i: number) => (r.cells[i]?.textContent ?? '').trim();

/** A plain grid we can sort: one body, at least 3 rows, every row as wide as the header, no own sort controls. */
function eligible(t: HTMLTableElement): boolean {
  if (t.dataset.autosort === 'on') return true;      // 'off' is re-checked: a table still loading may qualify later
  const hr = headerRow(t);
  const rows = bodyRows(t);
  let ok = !!hr && t.tBodies.length === 1 && rows.length >= 3 && !t.closest('[data-sort="off"]');
  if (ok && hr) {
    const n = hr.cells.length;
    ok = Array.from(hr.cells).every((c) => c.colSpan === 1 && !c.querySelector('button, a, input, select')
      && !c.hasAttribute('aria-sort') && getComputedStyle(c).cursor !== 'pointer')
      && rows.every((r) => r.cells.length === n && Array.from(r.cells).every((c) => c.colSpan === 1));
  }
  t.dataset.autosort = ok ? 'on' : 'off';
  if (ok && hr) for (const c of Array.from(hr.cells)) { c.tabIndex = 0; c.title ||= 'Sort by this column'; }
  return ok;
}

function apply(t: HTMLTableElement) {
  const st = states.get(t);
  const body = t.tBodies[0];
  if (!st || !body) return;
  const rows = bodyRows(t);
  rows.forEach((r, i) => { if (r.dataset.origIndex === undefined) r.dataset.origIndex = String(1e6 + i); });
  const key = (r: HTMLTableRowElement) => (st.kind === 'num' ? cellNumber(cellText(r, st.col)) : cellText(r, st.col) || null);
  const sorted = [...rows].sort((a, b) => {
    const x = key(a), y = key(b);
    if (x === null || y === null) return x === y ? 0 : x === null ? 1 : -1;   // blanks last either way
    const c = typeof x === 'number' ? x - (y as number) : String(x).localeCompare(String(y), undefined, { numeric: true, sensitivity: 'base' });
    return st.dir === 'asc' ? c : -c;
  });
  if (sorted.every((r, i) => r === rows[i])) return;
  for (const r of sorted) body.appendChild(r);
}

function restore(t: HTMLTableElement) {
  const body = t.tBodies[0];
  if (!body) return;
  const rows = bodyRows(t).sort((a, b) => Number(a.dataset.origIndex ?? 2e6) - Number(b.dataset.origIndex ?? 2e6));
  for (const r of rows) body.appendChild(r);
}

function watch(t: HTMLTableElement) {
  if (observers.has(t)) return;
  let queued = false;
  const mo = new MutationObserver(() => {
    if (queued) return;
    if (!t.isConnected) { mo.disconnect(); observers.delete(t); return; }
    queued = true;
    requestAnimationFrame(() => {
      queued = false;
      if (states.has(t)) apply(t);   // React re-rendered or a value ticked; our own moves settle as a no-op
    });
  });
  mo.observe(t.tBodies[0], { childList: true, subtree: true, characterData: true });
  observers.set(t, mo);
}

function paint(t: HTMLTableElement) {
  const st = states.get(t);
  const hr = headerRow(t);
  if (!hr) return;
  Array.from(hr.cells).forEach((c, i) => {
    if (st && st.col === i) { c.setAttribute('aria-sort', st.dir === 'asc' ? 'ascending' : 'descending'); c.dataset.sortDir = st.dir; }
    else { c.removeAttribute('aria-sort'); delete c.dataset.sortDir; }
  });
}

export function sortByHeader(th: HTMLTableCellElement) {
  const t = th.closest('table');
  if (!t || !eligible(t) || th.parentElement !== headerRow(t)) return;
  const col = th.cellIndex;
  const prev = states.get(t);
  const kind = columnKind(bodyRows(t).map((r) => cellText(r, col)));
  const first: Dir = kind === 'num' ? 'desc' : 'asc';
  let next: State | null;
  if (!prev || prev.col !== col) next = { col, dir: first, kind };
  else if (prev.dir === first) next = { col, dir: first === 'desc' ? 'asc' : 'desc', kind };
  else next = null;                                                            // third click: original order
  if (next) { states.set(t, next); watch(t); apply(t); }
  else { states.delete(t); restore(t); }
  paint(t);
}

let installed = false;

export function installSortableTables(): void {
  if (installed || typeof document === 'undefined') return;
  installed = true;
  const headerOf = (e: Event) => {
    const th = (e.target as HTMLElement | null)?.closest?.('thead th') as HTMLTableCellElement | null;
    return th && !(e.target as HTMLElement).closest('button, a, input, select') ? th : null;
  };
  document.addEventListener('mouseover', (e) => {
    const th = headerOf(e);
    const t = th?.closest('table');
    if (t) eligible(t);
  }, { passive: true });
  document.addEventListener('click', (e) => {
    const th = headerOf(e);
    if (th && th.closest('table')?.dataset.autosort === 'on') sortByHeader(th);
  });
  document.addEventListener('keydown', (e) => {
    if (e.key !== 'Enter' && e.key !== ' ') return;
    const th = headerOf(e);
    if (th && th.closest('table')?.dataset.autosort === 'on') { e.preventDefault(); sortByHeader(th); }
  });
  document.addEventListener('focusin', (e) => { const th = headerOf(e); const t = th?.closest('table'); if (t) eligible(t); });
}
