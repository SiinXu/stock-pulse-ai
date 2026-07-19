// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type React from 'react';
import { Fragment } from 'react';
import { ArrowDown, ArrowUp, ArrowUpDown } from 'lucide-react';
import { cn } from '../../utils/cn';
import { StatePanel } from './StatePanel';

export type DataTableColumnPriority = 'primary' | 'secondary' | 'tertiary';
export type DataTableSortDirection = 'asc' | 'desc';

export interface DataTableSort {
  columnId: string;
  direction: DataTableSortDirection;
}

export interface DataTableColumn<Row> {
  id: string;
  header: React.ReactNode;
  cell: (row: Row, index: number) => React.ReactNode;
  priority?: DataTableColumnPriority;
  align?: 'left' | 'center' | 'right';
  sortable?: boolean;
  headerClassName?: string;
  cellClassName?: string | ((row: Row, index: number) => string | undefined);
}

export interface DataTableProps<Row> {
  ariaLabel: string;
  columns: readonly DataTableColumn<Row>[];
  rows: readonly Row[];
  getRowKey: (row: Row, index: number) => React.Key;
  emptyState: React.ReactNode;
  loadingLabel: React.ReactNode;
  isLoading?: boolean;
  sort?: DataTableSort;
  onSortChange?: (sort: DataTableSort) => void;
  caption?: React.ReactNode;
  className?: string;
  scrollClassName?: string;
  tableClassName?: string;
  headClassName?: string;
  bodyClassName?: string;
  rowClassName?: string | ((row: Row, index: number) => string | undefined);
  onRowClick?: (row: Row, index: number) => void;
  getRowAriaLabel?: (row: Row, index: number) => string;
  isRowSelected?: (row: Row, index: number) => boolean;
  renderAfterRow?: (row: Row, index: number) => React.ReactNode;
  afterRowCellClassName?: string;
  minWidthClassName?: string;
}

const PRIORITY_STYLES: Record<DataTableColumnPriority, string> = {
  primary: 'table-cell',
  secondary: 'hidden md:table-cell',
  tertiary: 'hidden lg:table-cell',
};

const ALIGN_STYLES = {
  left: 'text-left',
  center: 'text-center',
  right: 'text-right',
} as const;

export function DataTable<Row>({
  ariaLabel,
  columns,
  rows,
  getRowKey,
  emptyState,
  loadingLabel,
  isLoading = false,
  sort,
  onSortChange,
  caption,
  className,
  scrollClassName,
  tableClassName,
  headClassName,
  bodyClassName,
  rowClassName,
  onRowClick,
  getRowAriaLabel,
  isRowSelected,
  renderAfterRow,
  afterRowCellClassName,
  minWidthClassName = 'min-w-full',
}: DataTableProps<Row>) {
  if (isLoading) {
    return (
      <div className={className}>
        <StatePanel status="loading" title={loadingLabel} compact />
      </div>
    );
  }

  if (rows.length === 0) {
    return <div className={className}>{emptyState}</div>;
  }

  return (
    <div className={cn('min-w-0', className)}>
      <div className={cn('overflow-x-auto', scrollClassName)}>
        <table
          aria-label={ariaLabel}
          className={cn('w-full border-collapse text-sm', minWidthClassName, tableClassName)}
        >
          {caption ? <caption className="sr-only">{caption}</caption> : null}
          <thead className={cn('border-b border-border/60 text-xs text-muted-text', headClassName)}>
            <tr>
              {columns.map((column) => {
                const priority = column.priority ?? 'primary';
                const align = column.align ?? 'left';
                const isSorted = sort?.columnId === column.id;
                const ariaSort = column.sortable
                  ? isSorted
                    ? sort.direction === 'asc' ? 'ascending' : 'descending'
                    : 'none'
                  : undefined;

                return (
                  <th
                    key={column.id}
                    scope="col"
                    aria-sort={ariaSort}
                    data-column-priority={priority}
                    className={cn(
                      'px-3 py-2 font-medium',
                      PRIORITY_STYLES[priority],
                      ALIGN_STYLES[align],
                      column.headerClassName,
                    )}
                  >
                    {column.sortable && onSortChange ? (
                      <button
                        type="button"
                        className={cn(
                          'inline-flex min-h-11 min-w-11 items-center gap-1.5 text-current focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-foreground/15',
                          align === 'right' && 'ml-auto',
                          align === 'center' && 'mx-auto',
                        )}
                        onClick={() => onSortChange({
                          columnId: column.id,
                          direction: isSorted && sort.direction === 'asc' ? 'desc' : 'asc',
                        })}
                      >
                        <span>{column.header}</span>
                        {isSorted ? (
                          sort.direction === 'asc'
                            ? <ArrowUp className="h-3.5 w-3.5" aria-hidden="true" />
                            : <ArrowDown className="h-3.5 w-3.5" aria-hidden="true" />
                        ) : <ArrowUpDown className="h-3.5 w-3.5" aria-hidden="true" />}
                      </button>
                    ) : column.header}
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody className={cn('divide-y divide-border/40', bodyClassName)}>
            {rows.map((row, rowIndex) => {
              const afterRow = renderAfterRow?.(row, rowIndex);
              return (
                <Fragment key={getRowKey(row, rowIndex)}>
                  <tr
                    aria-label={onRowClick ? getRowAriaLabel?.(row, rowIndex) : undefined}
                    aria-selected={isRowSelected?.(row, rowIndex)}
                    tabIndex={onRowClick ? 0 : undefined}
                    onClick={onRowClick ? () => onRowClick(row, rowIndex) : undefined}
                    onKeyDown={onRowClick ? (event) => {
                      if (event.key === 'Enter' || event.key === ' ') {
                        event.preventDefault();
                        onRowClick(row, rowIndex);
                      }
                    } : undefined}
                    className={cn(
                      'transition-colors hover:bg-hover/60',
                      onRowClick && 'cursor-pointer focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-inset focus-visible:ring-foreground/15',
                      typeof rowClassName === 'function' ? rowClassName(row, rowIndex) : rowClassName,
                    )}
                  >
                    {columns.map((column) => {
                      const priority = column.priority ?? 'primary';
                      const align = column.align ?? 'left';
                      return (
                        <td
                          key={column.id}
                          data-column-priority={priority}
                          className={cn(
                            'px-3 py-3',
                            PRIORITY_STYLES[priority],
                            ALIGN_STYLES[align],
                            typeof column.cellClassName === 'function'
                              ? column.cellClassName(row, rowIndex)
                              : column.cellClassName,
                          )}
                        >
                          {column.cell(row, rowIndex)}
                        </td>
                      );
                    })}
                  </tr>
                  {afterRow ? (
                    <tr data-table-after-row="true">
                      <td colSpan={columns.length} className={cn('p-0', afterRowCellClassName)}>
                        {afterRow}
                      </td>
                    </tr>
                  ) : null}
                </Fragment>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
