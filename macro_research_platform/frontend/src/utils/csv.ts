/**
 * CSV export helpers (data-trust / reporting).
 *
 * Institutional users paste panel data into IC memos and risk reports, so every data
 * table needs a clean, correctly-escaped CSV export driven by the real underlying
 * values (not scraped, formatted DOM text).
 */

type Cell = string | number | null | undefined;

/** RFC-4180 field escaping: quote fields containing comma, quote, or newline. */
function escapeCell(v: Cell): string {
  if (v === null || v === undefined) return '';
  const s = String(v);
  if (/[",\n]/.test(s)) {
    return `"${s.replace(/"/g, '""')}"`;
  }
  return s;
}

/** Build a CSV string from column headers and row arrays. */
export function toCsv(columns: string[], rows: Cell[][]): string {
  const head = columns.map(escapeCell).join(',');
  const body = rows.map((r) => r.map(escapeCell).join(',')).join('\n');
  return body ? `${head}\n${body}\n` : `${head}\n`;
}

/** Trigger a browser download of the given rows as a timestamped CSV file. */
export function downloadCsv(baseName: string, columns: string[], rows: Cell[][]): void {
  const csv = toCsv(columns, rows);
  const stamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
  const safe = baseName.replace(/[^a-z0-9-_]+/gi, '-').toLowerCase();
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = `${safe}-${stamp}.csv`;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  setTimeout(() => URL.revokeObjectURL(url), 0);
}
