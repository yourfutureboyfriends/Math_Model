/**
 * CsvButton — compact "export this table to CSV" action for a panel header.
 *
 * Pass a getData() that returns the table's real columns + rows; the CSV is built
 * from the underlying values at click time (not scraped DOM text). Renders as a small
 * icon button that fits next to a SourceTag / ComputedTag in a section header.
 */
import React from 'react';
import { Download } from 'lucide-react';
import { downloadCsv } from '@/utils/csv';

type Cell = string | number | null | undefined;

interface CsvButtonProps {
  /** File base name (a timestamp is appended). */
  filename: string;
  /** Returns the table data at click time. */
  getData: () => { columns: string[]; rows: Cell[][] };
  className?: string;
  label?: string;
}

export function CsvButton({ filename, getData, className = '', label = 'CSV' }: CsvButtonProps): React.ReactElement {
  const onClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      const { columns, rows } = getData();
      if (!rows || rows.length === 0) return;
      downloadCsv(filename, columns, rows);
    } catch {
      /* no-op: never let an export throw into the UI */
    }
  };
  return (
    <button
      type="button"
      onClick={onClick}
      title="Export table to CSV"
      className={`inline-flex items-center gap-1 text-2xs font-mono px-1.5 py-0.5 rounded-sm border border-border text-text-tertiary hover:text-bloomberg hover:border-bloomberg-border transition-colors ${className}`}
    >
      <Download className="w-3 h-3" />
      <span className="uppercase tracking-wider">{label}</span>
    </button>
  );
}
