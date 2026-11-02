// Hover any data table to copy it (pastes into Excel as columns) or download it as CSV. One floating control lives on
// <body>, positioned at the hovered table's corner, so React-rendered tables are never modified.
import { tableCSV, tableSnapshot, tableTSV } from './tableData';

let installed = false;

function eligible(t: HTMLTableElement): boolean {
  return t.tBodies.length > 0 && t.rows.length >= 3 && !t.closest('[data-no-table-actions], dialog');
}

export function installTableActions(): void {
  if (installed || typeof document === 'undefined') return;
  installed = true;
  const bar = document.createElement('div');
  bar.className = 'tbl-actions';
  bar.setAttribute('role', 'toolbar');
  bar.setAttribute('aria-label', 'Table actions');
  const copy = document.createElement('button');
  const csv = document.createElement('button');
  copy.type = csv.type = 'button';
  copy.textContent = 'Copy';
  copy.title = 'Copy this table — pastes into Excel as columns';
  csv.textContent = 'CSV';
  csv.title = 'Download this table as CSV';
  bar.append(copy, csv);
  bar.hidden = true;
  document.body.append(bar);
  let current: HTMLTableElement | null = null;
  let hideTimer: ReturnType<typeof setTimeout> | undefined;

  const place = () => {
    if (!current || !current.isConnected) { bar.hidden = true; return; }
    const r = current.getBoundingClientRect();
    if (r.height < 40 || r.bottom < 0 || r.top > window.innerHeight) { bar.hidden = true; return; }
    bar.hidden = false;
    // just below the table's bottom-right corner (usually empty space), or just above it when the bottom is off-screen
    const h = bar.offsetHeight || 24;
    const top = r.bottom + h + 4 <= window.innerHeight ? r.bottom + 2 : Math.max(4, r.top - h - 2);
    bar.style.top = `${top + window.scrollY}px`;
    bar.style.left = `${Math.min(r.right, window.innerWidth - 8) + window.scrollX - bar.offsetWidth}px`;
  };
  const flash = (b: HTMLButtonElement, text: string) => {
    const old = b.dataset.label ?? b.textContent ?? '';
    b.dataset.label = old;
    b.textContent = text;
    setTimeout(() => { b.textContent = old; }, 1400);
  };
  document.addEventListener('mouseover', (e) => {
    const el = e.target as HTMLElement | null;
    if (!el?.closest) return;
    if (el.closest('.tbl-actions')) { clearTimeout(hideTimer); return; }
    const t = el.closest('table') as HTMLTableElement | null;
    if (t && eligible(t)) {
      clearTimeout(hideTimer);
      current = t;
      place();
    } else if (current) {
      clearTimeout(hideTimer);
      hideTimer = setTimeout(() => { bar.hidden = true; current = null; }, 400);
    }
  }, { passive: true });
  window.addEventListener('scroll', () => { if (!bar.hidden) place(); }, { passive: true, capture: true });
  copy.addEventListener('click', async () => {
    if (!current) return;
    const s = tableSnapshot(current);
    try {
      await navigator.clipboard.writeText(tableTSV(s.headers, s.rows));
      flash(copy, `Copied ${s.rows.length} rows`);
    } catch {
      flash(copy, 'Clipboard blocked');
    }
  });
  csv.addEventListener('click', () => {
    if (!current) return;
    const s = tableSnapshot(current);
    const url = URL.createObjectURL(new Blob(['﻿' + tableCSV(s.headers, s.rows)], { type: 'text/csv;charset=utf-8' }));
    const a = document.createElement('a');
    a.href = url;
    a.download = `${s.title.replace(/[^\w -]/g, '').slice(0, 70) || 'table'}.csv`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    flash(csv, 'Saved');
  });
}
