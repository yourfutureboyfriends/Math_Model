/**
 * Data grid on TanStack Table: sortable columns, a quick filter, column visibility, sticky header, dense rows,
 * right-aligned tabular numbers, optional row selection and row click.
 */
import { useMemo, useState } from 'react';
import {
  flexRender, getCoreRowModel, getFilteredRowModel, getSortedRowModel, useReactTable,
  type ColumnDef, type SortingState, type VisibilityState,
} from '@tanstack/react-table';
import { ArrowDown, ArrowUp, Columns, Search } from 'lucide-react';

export function DataGrid<T>({ data, columns, initialSort, onRowClick, rowClassName, maxHeight, filterPlaceholder, dense = true, toolbarRight }: {
  data: T[]; columns: ColumnDef<T, any>[]; initialSort?: SortingState; onRowClick?: (row: T) => void;
  rowClassName?: (row: T) => string; maxHeight?: number; filterPlaceholder?: string; dense?: boolean; toolbarRight?: React.ReactNode;
}) {
  const [sorting, setSorting] = useState<SortingState>(initialSort ?? []);
  const [filter, setFilter] = useState('');
  const [visibility, setVisibility] = useState<VisibilityState>({});
  const [showCols, setShowCols] = useState(false);
  const table = useReactTable({
    data, columns, state: { sorting, globalFilter: filter, columnVisibility: visibility },
    onSortingChange: setSorting, onGlobalFilterChange: setFilter, onColumnVisibilityChange: setVisibility,
    getCoreRowModel: getCoreRowModel(), getSortedRowModel: getSortedRowModel(), getFilteredRowModel: getFilteredRowModel(),
  });
  const pad = dense ? 'py-1 px-2' : 'py-2 px-3';
  const hideable = useMemo(() => table.getAllLeafColumns().filter((c) => c.getCanHide()), [table, columns]);
  return (
    <div className="ml-grid">
      <div className="flex items-center gap-2 mb-2">
        <label className="ml-grid-search"><Search className="w-3 h-3" /><input value={filter} onChange={(e) => setFilter(e.target.value)} placeholder={filterPlaceholder ?? 'Filter…'} aria-label="Filter rows" /></label>
        <span className="text-2xs text-text-tertiary">{table.getFilteredRowModel().rows.length} rows</span>
        <div className="ml-auto flex items-center gap-2">
          {toolbarRight}
          <div className="relative">
            <button className="ml-btn" onClick={() => setShowCols((v) => !v)} aria-expanded={showCols}><Columns className="w-3 h-3" />Columns</button>
            {showCols && <div className="ml-popover" role="menu">
              {hideable.map((c) => <label key={c.id} className="flex items-center gap-2 text-2xs py-0.5"><input type="checkbox" checked={c.getIsVisible()} onChange={c.getToggleVisibilityHandler()} />{String(c.columnDef.header ?? c.id)}</label>)}
            </div>}
          </div>
        </div>
      </div>
      <div className="overflow-auto border border-border-subtle rounded-md" style={{ maxHeight }}>
        <table className="w-full text-2xs border-collapse">
          <thead className="sticky top-0 z-10 bg-surface-2">
            {table.getHeaderGroups().map((hg) => (
              <tr key={hg.id}>{hg.headers.map((h) => { const s = h.column.getIsSorted(); const num = (h.column.columnDef.meta as any)?.numeric;
                return (
                  <th key={h.id} className={`${pad} font-medium text-text-tertiary uppercase tracking-wider text-[10px] border-b border-border whitespace-nowrap ${num ? 'text-right' : 'text-left'} ${h.column.getCanSort() ? 'cursor-pointer select-none hover:text-text-primary' : ''}`}
                    onClick={h.column.getToggleSortingHandler()} aria-sort={s === 'asc' ? 'ascending' : s === 'desc' ? 'descending' : undefined}
                    title={(h.column.columnDef.meta as any)?.title}>
                    <span className="inline-flex items-center gap-1">{flexRender(h.column.columnDef.header, h.getContext())}{s === 'asc' ? <ArrowUp className="w-3 h-3" /> : s === 'desc' ? <ArrowDown className="w-3 h-3" /> : null}</span>
                  </th>); })}</tr>))}
          </thead>
          <tbody>
            {table.getRowModel().rows.map((r) => (
              <tr key={r.id} onClick={onRowClick ? () => onRowClick(r.original) : undefined}
                className={`border-b border-border-subtle last:border-0 ${onRowClick ? 'cursor-pointer' : ''} hover:bg-surface-2 ${rowClassName?.(r.original) ?? ''}`}>
                {r.getVisibleCells().map((c) => <td key={c.id} className={`${pad} ${(c.column.columnDef.meta as any)?.numeric ? 'text-right font-mono tabular-nums' : ''}`}>{flexRender(c.column.columnDef.cell, c.getContext())}</td>)}
              </tr>))}
            {!table.getRowModel().rows.length && <tr><td colSpan={columns.length} className="py-4 text-center text-text-tertiary">No rows</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}
