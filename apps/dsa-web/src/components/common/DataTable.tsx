// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { ArrowDown, ArrowUp, ArrowUpDown } from 'lucide-react';
import {
  Fragment,
  forwardRef,
  type ForwardedRef,
  type Key,
  type KeyboardEvent,
  type MouseEvent,
  type ReactElement,
  type ReactNode,
  type RefAttributes,
} from 'react';
import { cn } from '../../utils/cn';
import { StatePanel } from './StatePanel';
import { Surface } from './Surface';

export type DataTableAlign = 'start' | 'center' | 'end';
export type DataTableDensity = 'compact' | 'default';
export type DataTableMinWidth = 'content' | 'wide' | 'extra-wide';
export type DataTableSortDirection = 'ascending' | 'descending';

export interface DataTableSortState {
  columnId: string;
  direction: DataTableSortDirection;
}

export interface DataTableColumn<T> {
  id: string;
  header: ReactNode;
  cell: (row: T, index: number) => ReactNode;
  align?: DataTableAlign;
  width?: 'compact' | 'default' | 'wide';
  nowrap?: boolean;
  rowHeader?: boolean;
  sortControl?: {
    ariaLabel: string;
  };
}

export interface DataTableStateContent {
  title: ReactNode;
  description?: ReactNode;
  icon?: ReactNode;
  action?: ReactNode;
}

export interface DataTableStatus extends DataTableStateContent {
  state: 'loading' | 'error' | 'retrying';
}

interface DataTableBaseProps<T> {
  caption: string;
  captionMode?: 'hidden' | 'visible';
  scrollAreaLabel?: string;
  columns: readonly DataTableColumn<T>[];
  rows: readonly T[];
  getRowKey: (row: T, index: number) => Key;
  emptyState: DataTableStateContent;
  status?: DataTableStatus;
  density?: DataTableDensity;
  minWidth?: DataTableMinWidth;
  sort?: DataTableSortState | null;
  onSortChange?: (nextSort: DataTableSortState) => void;
}

interface DataTableStaticRows {
  onRowActivate?: never;
  getRowAriaLabel?: never;
  isRowDisabled?: never;
}

interface DataTableInteractiveRows<T> {
  onRowActivate: (row: T, index: number) => void;
  getRowAriaLabel: (row: T, index: number) => string;
  isRowDisabled?: (row: T, index: number) => boolean;
}

interface DataTableWithoutRowDetails {
  isRowDetailVisible?: never;
  renderRowDetail?: never;
  getRowDetailId?: never;
  getRowDetailAriaLabel?: never;
}

interface DataTableWithRowDetails<T> {
  isRowDetailVisible: (row: T, index: number) => boolean;
  renderRowDetail: (row: T, index: number) => ReactNode;
  getRowDetailId?: (row: T, index: number) => string;
  getRowDetailAriaLabel?: (row: T, index: number) => string;
}

export type DataTableProps<T> = DataTableBaseProps<T> & (
  DataTableStaticRows | DataTableInteractiveRows<T>
) & (
  DataTableWithoutRowDetails | DataTableWithRowDetails<T>
);

const ALIGN_STYLES: Record<DataTableAlign, string> = {
  start: 'text-left',
  center: 'text-center',
  end: 'text-right',
};

const ALIGN_CONTENT_STYLES: Record<DataTableAlign, string> = {
  start: 'justify-start',
  center: 'justify-center',
  end: 'justify-end',
};

const WIDTH_STYLES = {
  compact: 'w-24',
  default: 'w-40',
  wide: 'w-64',
} as const;

const MIN_WIDTH_STYLES: Record<DataTableMinWidth, string> = {
  content: 'min-w-[40rem]',
  wide: 'min-w-[56rem]',
  'extra-wide': 'min-w-[64rem]',
};

const CELL_PADDING_STYLES: Record<DataTableDensity, string> = {
  compact: 'px-3 py-2',
  default: 'px-4 py-3',
};

const NESTED_INTERACTIVE_SELECTOR = [
  'a[href]',
  'button',
  'input',
  'label',
  'select',
  'textarea',
  'summary',
  '[contenteditable]:not([contenteditable="false"])',
  '[role="button"]',
  '[role="link"]',
  '[role="checkbox"]',
  '[role="menuitem"]',
  '[role="option"]',
  '[role="switch"]',
  '[role="tab"]',
  '[role="textbox"]',
  '[tabindex]:not([tabindex="-1"])',
].join(',');

function isNestedInteractiveTarget(target: EventTarget | null, row: HTMLTableRowElement): boolean {
  if (!(target instanceof Element)) return false;
  const nestedControl = target.closest(NESTED_INTERACTIVE_SELECTOR);
  return nestedControl !== null && nestedControl !== row && row.contains(nestedControl);
}

function nextSortDirection(
  columnId: string,
  current: DataTableSortState | null | undefined,
): DataTableSortDirection {
  return current?.columnId === columnId && current.direction === 'ascending'
    ? 'descending'
    : 'ascending';
}

function SortIcon({ direction }: { direction?: DataTableSortDirection }) {
  if (direction === 'ascending') return <ArrowUp aria-hidden="true" />;
  if (direction === 'descending') return <ArrowDown aria-hidden="true" />;
  return <ArrowUpDown aria-hidden="true" />;
}

function DataTableInner<T>({
  caption,
  captionMode = 'hidden',
  scrollAreaLabel,
  columns,
  rows,
  getRowKey,
  emptyState,
  status,
  density = 'default',
  minWidth = 'wide',
  sort,
  onSortChange,
  onRowActivate,
  getRowAriaLabel,
  isRowDisabled,
  isRowDetailVisible,
  renderRowDetail,
  getRowDetailId,
  getRowDetailAriaLabel,
}: DataTableProps<T>, ref: ForwardedRef<HTMLTableElement>) {
  const effectiveState = status ?? (rows.length === 0
    ? { state: 'empty' as const, ...emptyState }
    : null);

  if (effectiveState) {
    return (
      <Surface
        level="interactive"
        padding="none"
        data-data-table="state"
        className="overflow-hidden"
      >
        <StatePanel
          state={effectiveState.state}
          title={effectiveState.title}
          description={effectiveState.description}
          icon={effectiveState.icon}
          action={effectiveState.action}
          titleAs="p"
          surfaceLevel="canvas"
          className="min-h-44"
        />
      </Surface>
    );
  }

  const activateFromMouse = (event: MouseEvent<HTMLTableRowElement>, row: T, index: number) => {
    if (!onRowActivate || event.defaultPrevented || isRowDisabled?.(row, index)) return;
    if (isNestedInteractiveTarget(event.target, event.currentTarget)) return;
    onRowActivate(row, index);
  };

  const activateFromKeyboard = (event: KeyboardEvent<HTMLTableRowElement>, row: T, index: number) => {
    if (!onRowActivate || event.defaultPrevented || event.repeat || isRowDisabled?.(row, index)) return;
    if (event.key !== 'Enter' && event.key !== ' ') return;
    if (isNestedInteractiveTarget(event.target, event.currentTarget)) return;
    event.preventDefault();
    onRowActivate(row, index);
  };

  return (
    <Surface
      level="interactive"
      padding="none"
      data-data-table="ready"
      className="overflow-hidden"
    >
      <div
        role="region"
        aria-label={scrollAreaLabel ?? caption}
        tabIndex={0}
        data-data-table-scroll="true"
        className="max-w-full overflow-x-auto overscroll-x-contain focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-primary/55"
      >
        <table
          ref={ref}
          data-density={density}
          className={cn('w-full border-collapse text-sm', MIN_WIDTH_STYLES[minWidth])}
        >
          <caption className={captionMode === 'visible'
            ? 'border-b border-border px-4 py-3 text-left text-sm font-semibold text-foreground'
            : 'sr-only'}
          >
            {caption}
          </caption>
          <thead className="border-b border-border bg-subtle-soft text-xs text-secondary-text">
            <tr>
              {columns.map((column) => {
                const align = column.align ?? 'start';
                const activeDirection = sort?.columnId === column.id ? sort.direction : undefined;
                const canSort = Boolean(column.sortControl && onSortChange);
                return (
                  <th
                    key={column.id}
                    scope="col"
                    aria-sort={canSort ? activeDirection ?? 'none' : undefined}
                    className={cn(
                      CELL_PADDING_STYLES[density],
                      ALIGN_STYLES[align],
                      column.width && WIDTH_STYLES[column.width],
                      column.nowrap && 'whitespace-nowrap',
                      'font-medium',
                    )}
                  >
                    {canSort ? (
                      <button
                        type="button"
                        data-control="data-table-sort"
                        aria-label={column.sortControl!.ariaLabel}
                        className={cn(
                          'control-hit-target relative inline-flex min-h-8 max-w-full items-center gap-1.5 rounded-lg text-inherit transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/55 motion-reduce:transition-none [&>svg]:h-3.5 [&>svg]:w-3.5',
                          ALIGN_CONTENT_STYLES[align],
                        )}
                        onClick={() => onSortChange?.({
                          columnId: column.id,
                          direction: nextSortDirection(column.id, sort),
                        })}
                      >
                        <span className="truncate">{column.header}</span>
                        <SortIcon direction={activeDirection} />
                      </button>
                    ) : column.header}
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {rows.map((row, index) => {
              const rowKey = getRowKey(row, index);
              const disabled = Boolean(isRowDisabled?.(row, index));
              const interactive = Boolean(onRowActivate);
              const detailVisible = Boolean(isRowDetailVisible?.(row, index));
              return (
                <Fragment key={rowKey}>
                  <tr
                    aria-label={getRowAriaLabel?.(row, index)}
                    aria-disabled={interactive && disabled ? true : undefined}
                    aria-keyshortcuts={interactive && !disabled ? 'Enter Space' : undefined}
                    tabIndex={interactive && !disabled ? 0 : undefined}
                    data-row-activatable={interactive || undefined}
                    data-row-disabled={disabled || undefined}
                    className={cn(
                      'align-top transition-[background-color] duration-150 motion-reduce:transition-none',
                      interactive && !disabled && 'cursor-pointer hover:bg-hover/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-primary/55',
                      disabled && 'opacity-55',
                    )}
                    onClick={(event) => activateFromMouse(event, row, index)}
                    onKeyDown={(event) => activateFromKeyboard(event, row, index)}
                  >
                    {columns.map((column) => {
                      const align = column.align ?? 'start';
                      const cellProps = {
                        className: cn(
                          CELL_PADDING_STYLES[density],
                          ALIGN_STYLES[align],
                          column.width && WIDTH_STYLES[column.width],
                          column.nowrap && 'whitespace-nowrap',
                          'text-secondary-text',
                        ),
                      };
                      return column.rowHeader ? (
                        <th key={column.id} scope="row" {...cellProps}>
                          {column.cell(row, index)}
                        </th>
                      ) : (
                        <td key={column.id} {...cellProps}>
                          {column.cell(row, index)}
                        </td>
                      );
                    })}
                  </tr>
                  {detailVisible && renderRowDetail ? (
                    <tr
                      id={getRowDetailId?.(row, index)}
                      aria-label={getRowDetailAriaLabel?.(row, index)}
                      data-data-table-detail-row="true"
                      className="align-top bg-subtle-soft"
                    >
                      <td colSpan={columns.length} className={CELL_PADDING_STYLES[density]}>
                        {renderRowDetail(row, index)}
                      </td>
                    </tr>
                  ) : null}
                </Fragment>
              );
            })}
          </tbody>
        </table>
      </div>
    </Surface>
  );
}

type DataTableComponent = <T>(
  props: DataTableProps<T> & RefAttributes<HTMLTableElement>,
) => ReactElement;

export const DataTable = forwardRef(DataTableInner) as DataTableComponent;

(DataTable as { displayName?: string }).displayName = 'DataTable';
