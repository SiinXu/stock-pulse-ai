// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { ArrowDown, ArrowUp, ArrowUpDown } from 'lucide-react';
import {
  Fragment,
  forwardRef,
  useLayoutEffect,
  useRef,
  useState,
  type ForwardedRef,
  type Key,
  type KeyboardEvent,
  type MouseEvent,
  type ReactElement,
  type ReactNode,
  type RefAttributes,
} from 'react';
import { useVirtualWindow } from '../../hooks/useVirtualWindow';
import { cn } from '../../utils/cn';
import { StatePanel } from './StatePanel';
import { Surface } from './Surface';
import {
  findBoundedVerticalScrollParent,
  resolveDataTableViewportCap,
  resolveDataTableVirtualization,
  type DataTableVirtualizationProp,
} from './dataTableVirtualization';

export type {
  DataTableVirtualizationConfig,
  DataTableVirtualizationProp,
  DataTableVirtualizationReason,
  ResolvedDataTableVirtualization,
} from './dataTableVirtualization';

export type DataTableAlign = 'start' | 'center' | 'end';
export type DataTableDensity = 'compact' | 'default';
export type DataTableFrame = 'embedded' | 'surface';
export type DataTableLayout = 'auto' | 'fixed';
export type DataTableMinWidth = 'container' | 'narrow' | 'content' | 'wide' | 'extra-wide';
export type DataTableSeparatorTone = 'default' | 'subtle' | 'inherit';
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
  widthPercent?: number;
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
  frame?: DataTableFrame;
  layout?: DataTableLayout;
  minWidth?: DataTableMinWidth;
  separatorTone?: DataTableSeparatorTone;
  sort?: DataTableSortState | null;
  onSortChange?: (nextSort: DataTableSortState) => void;
  isRowSelected?: (row: T, index: number) => boolean;
  getRowTestId?: (row: T, index: number) => string;
  /**
   * Auto-window body rows once `rows.length` meets the measured threshold.
   * Pass `false` for variable-height, rowspan, or other incompatible tables.
   * Controlled detail rows disable windowing automatically.
   */
  virtualization?: DataTableVirtualizationProp;
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
  container: 'min-w-full',
  narrow: 'min-w-140',
  content: 'min-w-[40rem]',
  wide: 'min-w-[56rem]',
  'extra-wide': 'min-w-[64rem]',
};

const CELL_PADDING_STYLES: Record<DataTableDensity, string> = {
  compact: 'px-3 py-2',
  default: 'px-4 py-3',
};

const TABLE_TEXT_STYLES: Record<DataTableDensity, string> = {
  compact: 'text-xs',
  default: 'text-sm',
};

const HEADER_SEPARATOR_STYLES: Record<DataTableSeparatorTone, string> = {
  default: 'border-border',
  subtle: 'border-subtle',
  inherit: 'border-inherit',
};

const BODY_SEPARATOR_STYLES: Record<DataTableSeparatorTone, string> = {
  default: 'divide-border',
  subtle: 'divide-subtle',
  inherit: 'divide-inherit border-inherit',
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

function getFixedColumnWidths<T>(
  columns: readonly DataTableColumn<T>[],
  layout: DataTableLayout,
): number[] | null {
  if (layout !== 'fixed') return null;
  const widths: number[] = [];
  for (const column of columns) {
    if (
      typeof column.widthPercent !== 'number'
      || !Number.isFinite(column.widthPercent)
      || column.widthPercent <= 0
    ) {
      return null;
    }
    widths.push(column.widthPercent);
  }
  const total = widths.reduce((sum, width) => sum + width, 0);
  return total > 0 ? widths.map((width) => (width / total) * 100) : null;
}

function VirtualSpacerRow({
  position,
  height,
  columnCount,
}: {
  position: 'top' | 'bottom';
  height: number;
  columnCount: number;
}) {
  if (height <= 0 || columnCount <= 0) return null;
  return (
    <tr
      aria-hidden="true"
      data-data-table-spacer={position}
      className="border-0"
      style={{ height }}
    >
      <td
        colSpan={columnCount}
        className="border-0 p-0"
        style={{ height, padding: 0, lineHeight: 0, fontSize: 0 }}
      />
    </tr>
  );
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
  frame = 'surface',
  layout = 'auto',
  minWidth = 'wide',
  separatorTone = 'default',
  sort,
  onSortChange,
  isRowSelected,
  getRowTestId,
  virtualization,
  onRowActivate,
  getRowAriaLabel,
  isRowDisabled,
  isRowDetailVisible,
  renderRowDetail,
  getRowDetailId,
  getRowDetailAriaLabel,
}: DataTableProps<T>, ref: ForwardedRef<HTMLTableElement>) {
  const scrollAreaRef = useRef<HTMLDivElement>(null);
  const resolvedVirtualization = resolveDataTableVirtualization({
    rowCount: rows.length,
    hasRowDetails: Boolean(renderRowDetail),
    density,
    virtualization,
  });
  const virtualize = resolvedVirtualization.enabled;
  const defaultViewport = resolvedVirtualization.viewportMaxHeight;
  const [viewportCap, setViewportCap] = useState(defaultViewport);
  const {
    range,
    onScroll: onVirtualScroll,
    setViewportHeight,
  } = useVirtualWindow({
    itemCount: rows.length,
    estimatedItemHeight: resolvedVirtualization.rowHeight,
    overscan: resolvedVirtualization.overscan,
    enabled: virtualize,
  });

  useLayoutEffect(() => {
    if (!virtualize) {
      return;
    }
    const container = scrollAreaRef.current;
    if (!container) {
      return;
    }
    const updateHeight = () => {
      const cap = resolveDataTableViewportCap(container, defaultViewport);
      setViewportCap(cap);
      const measured = container.clientHeight;
      setViewportHeight(measured > 0 ? measured : cap);
    };
    updateHeight();
    if (typeof ResizeObserver === 'undefined') {
      return;
    }
    const observer = new ResizeObserver(updateHeight);
    observer.observe(container);
    const scrollParent = findBoundedVerticalScrollParent(container, defaultViewport);
    if (scrollParent) {
      observer.observe(scrollParent);
    }
    return () => observer.disconnect();
  }, [defaultViewport, setViewportHeight, virtualize, rows.length]);

  useLayoutEffect(() => {
    if (!virtualize) {
      return;
    }
    const container = scrollAreaRef.current;
    if (!container) {
      return;
    }
    const measuredViewport = container.clientHeight > 0 ? container.clientHeight : viewportCap;
    const maxScroll = Math.max(
      0,
      rows.length * resolvedVirtualization.rowHeight - measuredViewport,
    );
    if (container.scrollTop > maxScroll) {
      container.scrollTop = maxScroll;
    }
  }, [resolvedVirtualization.rowHeight, rows.length, viewportCap, virtualize]);

  const effectiveState = status ?? (rows.length === 0
    ? { state: 'empty' as const, ...emptyState }
    : null);

  if (effectiveState) {
    const statePanel = (
      <StatePanel
        state={effectiveState.state}
        title={effectiveState.title}
        description={effectiveState.description}
        icon={effectiveState.icon}
        action={effectiveState.action}
        titleAs="p"
        surfaceLevel="canvas"
        data-data-table={frame === 'embedded' ? 'state' : undefined}
        className="min-h-44"
      />
    );
    if (frame === 'embedded') return statePanel;
    return (
      <Surface
        level="interactive"
        padding="none"
        data-data-table="state"
        className="overflow-hidden"
      >
        {statePanel}
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

  const fixedColumnWidths = getFixedColumnWidths(columns, layout);
  const windowStart = virtualize ? range.startIndex : 0;
  const windowEnd = virtualize ? range.endIndex : rows.length - 1;
  const tableContent = (
      <div
        ref={scrollAreaRef}
        role="region"
        aria-label={scrollAreaLabel ?? caption}
        tabIndex={0}
        data-data-table-scroll="true"
        data-data-table={frame === 'embedded' ? 'ready' : undefined}
        data-data-table-virtualized={virtualize ? 'true' : 'false'}
        data-data-table-virtual-reason={resolvedVirtualization.reason}
        data-mounted-count={virtualize ? Math.max(0, windowEnd - windowStart + 1) : rows.length}
        data-total-count={rows.length}
        onScroll={virtualize ? onVirtualScroll : undefined}
        style={virtualize ? { maxHeight: viewportCap } : undefined}
        className={cn(
          'max-w-full overflow-x-auto overscroll-x-contain focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-primary/55',
          virtualize && 'overflow-y-auto overscroll-y-contain',
          separatorTone === 'inherit' && 'border-inherit',
        )}
      >
        <table
          ref={ref}
          data-density={density}
          data-layout={layout}
          aria-rowcount={virtualize ? rows.length + 1 : undefined}
          className={cn(
            'w-full border-collapse',
            TABLE_TEXT_STYLES[density],
            layout === 'fixed' ? 'table-fixed' : 'table-auto',
            MIN_WIDTH_STYLES[minWidth],
            separatorTone === 'inherit' && 'border-inherit',
          )}
        >
          <caption className={cn(
            captionMode === 'visible'
              ? 'border-b px-4 py-3 text-left text-sm font-semibold text-foreground'
              : 'sr-only',
            captionMode === 'visible' && HEADER_SEPARATOR_STYLES[separatorTone],
          )}
          >
            {caption}
          </caption>
          {fixedColumnWidths ? (
            <colgroup>
              {fixedColumnWidths.map((width, index) => (
                <col key={columns[index].id} style={{ width: `${width}%` }} />
              ))}
            </colgroup>
          ) : null}
          <thead className={cn(
            'border-b text-xs text-secondary-text',
            HEADER_SEPARATOR_STYLES[separatorTone],
            virtualize ? 'sticky top-0 z-10 bg-card' : 'bg-subtle-soft',
          )}
          >
            <tr aria-rowindex={virtualize ? 1 : undefined}>
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
          <tbody className={cn(
            'divide-y',
            BODY_SEPARATOR_STYLES[separatorTone],
            virtualize && '[&>[data-data-table-spacer]]:border-0',
          )}
          >
            {virtualize ? (
              <VirtualSpacerRow
                position="top"
                height={range.offsetTop}
                columnCount={columns.length}
              />
            ) : null}
            {rows.slice(windowStart, windowEnd + 1).map((row, offset) => {
              const index = windowStart + offset;
              const rowKey = getRowKey(row, index);
              const disabled = Boolean(isRowDisabled?.(row, index));
              const interactive = Boolean(onRowActivate);
              const selected = Boolean(isRowSelected?.(row, index));
              const detailVisible = Boolean(isRowDetailVisible?.(row, index));
              return (
                <Fragment key={rowKey}>
                  <tr
                    aria-label={getRowAriaLabel?.(row, index)}
                    aria-rowindex={virtualize ? index + 2 : undefined}
                    aria-disabled={interactive && disabled ? true : undefined}
                    aria-selected={isRowSelected ? selected : undefined}
                    aria-keyshortcuts={interactive && !disabled ? 'Enter Space' : undefined}
                    tabIndex={interactive && !disabled ? 0 : undefined}
                    data-row-activatable={interactive || undefined}
                    data-row-disabled={disabled || undefined}
                    data-row-selected={selected || undefined}
                    data-testid={getRowTestId?.(row, index)}
                    className={cn(
                      'align-top transition-[background-color] duration-150 motion-reduce:transition-none',
                      interactive && !disabled && 'cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-primary/55',
                      interactive && !disabled && !selected && 'hover:bg-hover/60',
                      selected && 'bg-primary/10 ring-1 ring-inset ring-primary/35',
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
            {virtualize ? (
              <VirtualSpacerRow
                position="bottom"
                height={range.offsetBottom}
                columnCount={columns.length}
              />
            ) : null}
          </tbody>
        </table>
      </div>
  );

  if (frame === 'embedded') return tableContent;

  return (
    <Surface
      level="interactive"
      padding="none"
      data-data-table="ready"
      className="overflow-hidden"
    >
      {tableContent}
    </Surface>
  );
}

type DataTableComponent = <T>(
  props: DataTableProps<T> & RefAttributes<HTMLTableElement>,
) => ReactElement;

export const DataTable = forwardRef(DataTableInner) as DataTableComponent;

(DataTable as { displayName?: string }).displayName = 'DataTable';
