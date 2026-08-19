// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { fireEvent, render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import {
  DATATABLE_COMPACT_ROW_HEIGHT_PX,
  DATATABLE_DEFAULT_ROW_HEIGHT_PX,
  DATATABLE_VIRTUALIZE_THRESHOLD,
  DATATABLE_VIRTUAL_VIEWPORT_PX,
} from '../../../performance/runtimeBudgets';
import { DataTable, type DataTableColumn, type DataTableSortState } from '../DataTable';

type Row = {
  id: number;
  symbol: string;
};

const COLUMNS: DataTableColumn<Row>[] = [
  {
    id: 'symbol',
    header: 'Symbol',
    rowHeader: true,
    nowrap: true,
    sortControl: { ariaLabel: 'Sort by symbol' },
    cell: (row) => row.symbol,
  },
];

const EMPTY_STATE = { title: 'No positions' };

function buildRows(count: number): Row[] {
  return Array.from({ length: count }, (_, index) => ({
    id: index + 1,
    symbol: `SYM${String(index + 1).padStart(3, '0')}`,
  }));
}

function renderTable(
  rows: readonly Row[],
  extra?: {
    sort?: DataTableSortState;
    virtualization?: false;
    density?: 'compact' | 'default';
  },
) {
  return render(
    <DataTable
      caption="Portfolio positions"
      scrollAreaLabel="Scrollable portfolio positions"
      columns={COLUMNS}
      rows={rows}
      getRowKey={(row) => row.id}
      getRowTestId={(row) => `position-${row.id}`}
      emptyState={EMPTY_STATE}
      sort={extra?.sort}
      density={extra?.density}
      virtualization={extra?.virtualization}
    />,
  );
}

function scrollRegion(): HTMLElement {
  return screen.getByRole('region', { name: 'Scrollable portfolio positions' });
}

function bodyRowCount(): number {
  return document.querySelectorAll('[data-testid^="position-"]').length;
}

describe('DataTable virtualization', () => {
  it('keeps every row mounted below the measured threshold', () => {
    const rows = buildRows(DATATABLE_VIRTUALIZE_THRESHOLD - 1);
    renderTable(rows);
    const region = scrollRegion();
    expect(region).toHaveAttribute('data-data-table-virtualized', 'false');
    expect(region).toHaveAttribute('data-data-table-virtual-reason', 'below-threshold');
    expect(region).toHaveAttribute('data-mounted-count', String(rows.length));
    expect(region).toHaveAttribute('data-total-count', String(rows.length));
    expect(screen.getByTestId('position-1')).toBeVisible();
    expect(screen.getByTestId(`position-${rows.length}`)).toBeVisible();
    expect(bodyRowCount()).toBe(rows.length);
    expect(screen.getByRole('table')).not.toHaveAttribute('aria-rowcount');
    expect(document.querySelector('[data-data-table-spacer]')).not.toBeInTheDocument();
  });

  it('windows the first rows above the threshold and keeps last-row geometry', () => {
    const rows = buildRows(80);
    renderTable(rows);
    const region = scrollRegion();
    expect(region).toHaveAttribute('data-data-table-virtualized', 'true');
    expect(region).toHaveAttribute('data-data-table-virtual-reason', 'windowed');
    expect(region).toHaveStyle({ maxHeight: `${DATATABLE_VIRTUAL_VIEWPORT_PX}px` });
    expect(screen.getByRole('table')).toHaveAttribute('aria-rowcount', String(rows.length + 1));
    const tHead = (screen.getByRole('table') as HTMLTableElement).tHead;
    expect(tHead).toHaveClass('sticky', 'top-0', 'bg-card');
    expect(tHead).not.toHaveClass('bg-subtle-soft');
    expect(screen.getByTestId('position-1')).toHaveAttribute('aria-rowindex', '2');
    expect(screen.getByTestId('position-1')).toBeVisible();
    expect(screen.queryByTestId('position-80')).not.toBeInTheDocument();
    expect(bodyRowCount()).toBeLessThan(rows.length);
    expect(bodyRowCount()).toBeGreaterThan(0);

    const topSpacer = document.querySelector('[data-data-table-spacer="top"]');
    const bottomSpacer = document.querySelector('[data-data-table-spacer="bottom"]');
    expect(topSpacer).toBeNull();
    expect(bottomSpacer).toHaveAttribute('aria-hidden', 'true');
    const bottomHeight = Number.parseFloat((bottomSpacer as HTMLElement).style.height);
    const mounted = bodyRowCount();
    expect(bottomHeight).toBe((80 - mounted) * DATATABLE_DEFAULT_ROW_HEIGHT_PX);
  });

  it('scrolls to the last row without dropping the first-row identity', () => {
    const rows = buildRows(80);
    renderTable(rows);
    const region = scrollRegion();
    Object.defineProperty(region, 'scrollTop', {
      configurable: true,
      writable: true,
      value: 79 * DATATABLE_DEFAULT_ROW_HEIGHT_PX,
    });
    fireEvent.scroll(region);

    expect(screen.getByTestId('position-80')).toBeVisible();
    expect(screen.getByTestId('position-80')).toHaveAttribute('aria-rowindex', '81');
    expect(screen.queryByTestId('position-1')).not.toBeInTheDocument();
    const topSpacer = document.querySelector('[data-data-table-spacer="top"]') as HTMLElement;
    const bottomSpacer = document.querySelector('[data-data-table-spacer="bottom"]');
    expect(Number.parseFloat(topSpacer.style.height)).toBeGreaterThan(0);
    expect(bottomSpacer).toBeNull();
    expect(Number.parseFloat(topSpacer.style.height) + (bodyRowCount() * DATATABLE_DEFAULT_ROW_HEIGHT_PX))
      .toBe(80 * DATATABLE_DEFAULT_ROW_HEIGHT_PX);
  });

  it('preserves selection and activation after a windowed scroll', () => {
    const rows = buildRows(60);
    const onRowActivate = vi.fn();
    const { rerender } = render(
      <DataTable
        caption="Portfolio positions"
        scrollAreaLabel="Scrollable portfolio positions"
        columns={COLUMNS}
        rows={rows}
        getRowKey={(row) => row.id}
        getRowTestId={(row) => `position-${row.id}`}
        emptyState={EMPTY_STATE}
        onRowActivate={onRowActivate}
        getRowAriaLabel={(row) => `Open ${row.symbol}`}
        isRowSelected={(row) => row.id === 1}
      />,
    );

    fireEvent.click(screen.getByRole('row', { name: 'Open SYM001' }));
    expect(onRowActivate).toHaveBeenCalledTimes(1);
    expect(screen.getByTestId('position-1')).toHaveAttribute('aria-selected', 'true');

    const region = scrollRegion();
    Object.defineProperty(region, 'scrollTop', {
      configurable: true,
      writable: true,
      value: 50 * DATATABLE_DEFAULT_ROW_HEIGHT_PX,
    });
    fireEvent.scroll(region);
    expect(screen.queryByTestId('position-1')).not.toBeInTheDocument();
    fireEvent.click(screen.getByTestId('position-55'));
    expect(onRowActivate).toHaveBeenCalledWith(rows[54], 54);

    rerender(
      <DataTable
        caption="Portfolio positions"
        scrollAreaLabel="Scrollable portfolio positions"
        columns={COLUMNS}
        rows={rows}
        getRowKey={(row) => row.id}
        getRowTestId={(row) => `position-${row.id}`}
        emptyState={EMPTY_STATE}
        onRowActivate={onRowActivate}
        getRowAriaLabel={(row) => `Open ${row.symbol}`}
        isRowSelected={(row) => row.id === 55}
      />,
    );
    expect(screen.getByTestId('position-55')).toHaveAttribute('aria-selected', 'true');
  });

  it('re-windows after filter and sort without losing row identity', () => {
    const allRows = buildRows(40);
    const { rerender } = renderTable(allRows, {
      sort: { columnId: 'symbol', direction: 'ascending' },
    });
    expect(screen.getByTestId('position-1')).toHaveTextContent('SYM001');

    const filtered = allRows.filter((row) => row.id > 20);
    rerender(
      <DataTable
        caption="Portfolio positions"
        scrollAreaLabel="Scrollable portfolio positions"
        columns={COLUMNS}
        rows={filtered}
        getRowKey={(row) => row.id}
        getRowTestId={(row) => `position-${row.id}`}
        emptyState={EMPTY_STATE}
        sort={{ columnId: 'symbol', direction: 'descending' }}
      />,
    );
    expect(scrollRegion()).toHaveAttribute('data-total-count', '20');
    expect(scrollRegion()).toHaveAttribute('data-data-table-virtualized', 'false');
    expect(screen.getByTestId('position-21')).toHaveTextContent('SYM021');
    expect(screen.getByTestId('position-40')).toHaveTextContent('SYM040');
    expect(screen.queryByTestId('position-1')).not.toBeInTheDocument();
  });

  it('keeps empty and loading states on the state surface instead of a window', () => {
    const { rerender } = renderTable([]);
    expect(screen.queryByRole('table')).not.toBeInTheDocument();
    expect(document.querySelector('[data-data-table-virtualized]')).not.toBeInTheDocument();

    rerender(
      <DataTable
        caption="Portfolio positions"
        columns={COLUMNS}
        rows={buildRows(40)}
        getRowKey={(row) => row.id}
        emptyState={EMPTY_STATE}
        status={{ state: 'loading', title: 'Loading positions' }}
      />,
    );
    expect(screen.getByRole('status')).toHaveAttribute('aria-busy', 'true');
    expect(screen.queryByRole('table')).not.toBeInTheDocument();
  });

  it('fits the windowed viewport inside a tighter overflow parent', () => {
    const rows = buildRows(80);
    render(
      <div style={{ maxHeight: 240, overflowY: 'auto' }}>
        <DataTable
          caption="Portfolio positions"
          scrollAreaLabel="Scrollable portfolio positions"
          columns={COLUMNS}
          rows={rows}
          getRowKey={(row) => row.id}
          getRowTestId={(row) => `position-${row.id}`}
          emptyState={EMPTY_STATE}
          frame="embedded"
        />
      </div>,
    );

    const region = scrollRegion();
    expect(region).toHaveAttribute('data-data-table-virtualized', 'true');
    expect(region).toHaveStyle({ maxHeight: '240px' });
    expect(region).toHaveClass('overflow-y-auto');

    Object.defineProperty(region, 'scrollTop', {
      configurable: true,
      writable: true,
      value: 79 * DATATABLE_DEFAULT_ROW_HEIGHT_PX,
    });
    fireEvent.scroll(region);
    expect(screen.getByTestId('position-80')).toBeVisible();
  });

  it('walks past an overflow-hidden surface to a tighter scroll parent', () => {
    const rows = buildRows(80);
    render(
      <div style={{ maxHeight: 288, overflowY: 'auto' }}>
        <DataTable
          caption="Portfolio positions"
          scrollAreaLabel="Scrollable portfolio positions"
          columns={COLUMNS}
          rows={rows}
          getRowKey={(row) => row.id}
          getRowTestId={(row) => `position-${row.id}`}
          emptyState={EMPTY_STATE}
        />
      </div>,
    );

    const region = scrollRegion();
    expect(region).toHaveAttribute('data-data-table-virtualized', 'true');
    expect(region).toHaveStyle({ maxHeight: '288px' });
  });

  it('falls back to a full table for detail rows and explicit opt-out', () => {
    const rows = buildRows(40);
    const { rerender } = render(
      <DataTable
        caption="Portfolio positions"
        scrollAreaLabel="Scrollable portfolio positions"
        columns={COLUMNS}
        rows={rows}
        getRowKey={(row) => row.id}
        getRowTestId={(row) => `position-${row.id}`}
        emptyState={EMPTY_STATE}
        isRowDetailVisible={(row) => row.id === 1}
        renderRowDetail={(row) => <span>{row.symbol} detail</span>}
        getRowDetailAriaLabel={(row) => `${row.symbol} details`}
      />,
    );
    expect(scrollRegion()).toHaveAttribute('data-data-table-virtualized', 'false');
    expect(scrollRegion()).toHaveAttribute('data-data-table-virtual-reason', 'row-details');
    expect(bodyRowCount()).toBe(40);
    expect(screen.getByRole('row', { name: 'SYM001 details' })).toBeVisible();

    rerender(
      <DataTable
        caption="Portfolio positions"
        scrollAreaLabel="Scrollable portfolio positions"
        columns={COLUMNS}
        rows={rows}
        getRowKey={(row) => row.id}
        getRowTestId={(row) => `position-${row.id}`}
        emptyState={EMPTY_STATE}
        virtualization={false}
      />,
    );
    expect(scrollRegion()).toHaveAttribute('data-data-table-virtual-reason', 'disabled');
    expect(bodyRowCount()).toBe(40);
    expect(within(screen.getByRole('table')).getAllByRole('row')).toHaveLength(41);
  });

  it('keeps a translucent header wash only when the table is not windowed', () => {
    renderTable(buildRows(DATATABLE_VIRTUALIZE_THRESHOLD - 1));
    const tHead = (screen.getByRole('table') as HTMLTableElement).tHead;
    expect(tHead).toHaveClass('bg-subtle-soft');
    expect(tHead).not.toHaveClass('sticky');
    expect(tHead).not.toHaveClass('bg-card');
  });

  it('activates a windowed row with Enter and Space after scroll', () => {
    const rows = buildRows(60);
    const onRowActivate = vi.fn();
    render(
      <DataTable
        caption="Portfolio positions"
        scrollAreaLabel="Scrollable portfolio positions"
        columns={COLUMNS}
        rows={rows}
        getRowKey={(row) => row.id}
        getRowTestId={(row) => `position-${row.id}`}
        emptyState={EMPTY_STATE}
        onRowActivate={onRowActivate}
        getRowAriaLabel={(row) => `Open ${row.symbol}`}
      />,
    );

    const region = scrollRegion();
    Object.defineProperty(region, 'scrollTop', {
      configurable: true,
      writable: true,
      value: 50 * DATATABLE_DEFAULT_ROW_HEIGHT_PX,
    });
    fireEvent.scroll(region);

    const target = screen.getByTestId('position-55');
    fireEvent.keyDown(target, { key: 'Enter' });
    fireEvent.keyDown(target, { key: ' ' });
    expect(onRowActivate).toHaveBeenNthCalledWith(1, rows[54], 54);
    expect(onRowActivate).toHaveBeenNthCalledWith(2, rows[54], 54);
  });

  it('keeps error and retrying status on the state surface for large row sets', () => {
    const rows = buildRows(40);
    const { rerender } = render(
      <DataTable
        caption="Portfolio positions"
        columns={COLUMNS}
        rows={rows}
        getRowKey={(row) => row.id}
        emptyState={EMPTY_STATE}
        status={{ state: 'error', title: 'Positions unavailable' }}
      />,
    );
    expect(screen.getByRole('alert')).toHaveTextContent('Positions unavailable');
    expect(screen.queryByRole('table')).not.toBeInTheDocument();

    rerender(
      <DataTable
        caption="Portfolio positions"
        columns={COLUMNS}
        rows={rows}
        getRowKey={(row) => row.id}
        emptyState={EMPTY_STATE}
        status={{ state: 'retrying', title: 'Retrying positions' }}
      />,
    );
    expect(screen.getByRole('status')).toHaveTextContent('Retrying positions');
    expect(screen.queryByRole('table')).not.toBeInTheDocument();
  });

  it('windows compact nowrap rows with the compact estimate', () => {
    const rows = buildRows(80);
    renderTable(rows, { density: 'compact' });
    const region = scrollRegion();
    expect(region).toHaveAttribute('data-data-table-virtualized', 'true');
    expect(screen.getByRole('table')).toHaveAttribute('data-density', 'compact');
    expect(screen.queryByTestId('position-80')).not.toBeInTheDocument();

    Object.defineProperty(region, 'scrollTop', {
      configurable: true,
      writable: true,
      value: 79 * DATATABLE_COMPACT_ROW_HEIGHT_PX,
    });
    fireEvent.scroll(region);
    expect(screen.getByTestId('position-80')).toBeVisible();
    const topSpacer = document.querySelector('[data-data-table-spacer="top"]') as HTMLElement;
    expect(Number.parseFloat(topSpacer.style.height) % DATATABLE_COMPACT_ROW_HEIGHT_PX).toBe(0);
  });

  it('clamps a stale window after a filter that stays above the threshold', () => {
    const allRows = buildRows(80);
    const { rerender } = renderTable(allRows);
    const region = scrollRegion();
    Object.defineProperty(region, 'scrollTop', {
      configurable: true,
      writable: true,
      value: 79 * DATATABLE_DEFAULT_ROW_HEIGHT_PX,
    });
    fireEvent.scroll(region);
    expect(screen.getByTestId('position-80')).toBeVisible();

    const filtered = allRows.filter((row) => row.id <= 30);
    rerender(
      <DataTable
        caption="Portfolio positions"
        scrollAreaLabel="Scrollable portfolio positions"
        columns={COLUMNS}
        rows={filtered}
        getRowKey={(row) => row.id}
        getRowTestId={(row) => `position-${row.id}`}
        emptyState={EMPTY_STATE}
      />,
    );
    expect(scrollRegion()).toHaveAttribute('data-data-table-virtualized', 'true');
    expect(scrollRegion()).toHaveAttribute('data-total-count', '30');
    expect(screen.getByTestId('position-30')).toBeVisible();
    expect(screen.queryByTestId('position-80')).not.toBeInTheDocument();
  });
});
