// Phase 2 — Terminal Table Component
// Clean monospace table with terminal aesthetic

import { cn } from '@/lib/utils';

interface TableColumn<T> {
  header: string;
  accessor: keyof T | ((item: T) => React.ReactNode);
  align?: 'left' | 'center' | 'right';
}

interface TableProps<T> {
  data?: T[];
  columns: TableColumn<T>[];
  keyExtractor: (item: T) => string;
  className?: string;
}

export function Table<T>({ data, columns, keyExtractor, className }: TableProps<T>) {
  if (!data?.length) return null;

  const getCellValue = (item: T, column: TableColumn<T>): React.ReactNode => {
    if (typeof column.accessor === 'function') {
      return column.accessor(item);
    }
    return item[column.accessor] as React.ReactNode;
  };

  return (
    <div className={cn('overflow-x-auto', className)}>
      <table className="w-full text-xs">
        <thead>
          <tr className="border-b border-border-subtle bg-surface-2">
            {columns.map((column, index) => (
              <th
                key={index}
                className={cn(
                  'text-left px-3 py-2 text-2xs font-medium text-text-tertiary',
                  'uppercase tracking-wider',
                  column.align === 'center' && 'text-center',
                  column.align === 'right' && 'text-right'
                )}
              >
                {column.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.map((item) => (
            <tr
              key={keyExtractor(item)}
              className="border-b border-border-subtle last:border-b-0 hover:bg-surface-2/50 transition-colors"
            >
              {columns.map((column, colIndex) => (
                <td
                  key={colIndex}
                  className={cn(
                    'px-3 py-2 text-text-primary',
                    column.align === 'center' && 'text-center',
                    column.align === 'right' && 'text-right'
                  )}
                >
                  {getCellValue(item, column)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
