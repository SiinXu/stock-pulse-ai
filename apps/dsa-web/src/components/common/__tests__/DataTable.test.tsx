// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { fireEvent, render, screen, within } from '@testing-library/react';
import { createRef } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { DataTable, type DataTableColumn } from '../DataTable';

type Row = {
  id: number;
  symbol: string;
  price: number;
  disabled?: boolean;
};

const ROWS: Row[] = [
  { id: 1, symbol: 'AAPL', price: 212.48 },
  { id: 2, symbol: 'MSFT', price: 516.12 },
];

const COLUMNS: DataTableColumn<Row>[] = [
  {
    id: 'symbol',
    header: 'Symbol',
    rowHeader: true,
    nowrap: true,
    sortControl: { ariaLabel: 'Sort by symbol' },
    cell: (row) => <span>{row.symbol}</span>,
  },
  {
    id: 'price',
    header: 'Last price',
    align: 'end',
    cell: (row) => row.price.toFixed(2),
  },
];

const EMPTY_STATE = {
  title: 'No positions',
  description: 'Add a position to populate this table.',
};

function renderStaticTable(rows: readonly Row[] = ROWS) {
  return render(
    <DataTable
      caption="Portfolio positions"
      scrollAreaLabel="Scrollable portfolio positions"
      columns={COLUMNS}
      rows={rows}
      getRowKey={(row) => row.id}
      emptyState={EMPTY_STATE}
    />,
  );
}

describe('DataTable', () => {
  it('renders a named native table, typed columns, row headers, and a focusable scroll region', () => {
    const ref = createRef<HTMLTableElement>();
    render(
      <DataTable
        ref={ref}
        caption="Portfolio positions"
        captionMode="visible"
        scrollAreaLabel="Scrollable portfolio positions"
        columns={COLUMNS}
        rows={ROWS}
        getRowKey={(row) => row.id}
        emptyState={EMPTY_STATE}
      />,
    );

    expect(screen.getByRole('table', { name: 'Portfolio positions' })).toBe(ref.current);
    expect(screen.getByRole('region', { name: 'Scrollable portfolio positions' })).toHaveAttribute('tabindex', '0');
    expect(screen.getByRole('columnheader', { name: /Symbol/ })).toBeVisible();
    expect(screen.getByRole('rowheader', { name: 'AAPL' })).toBeVisible();
    expect(screen.getByText('212.48')).toBeVisible();
    expect(screen.getByRole('table')).toHaveClass('table-auto', 'min-w-[56rem]', 'text-sm');
    expect(screen.getByRole('table').closest('[data-surface-level="interactive"]')).toBeInTheDocument();
  });

  it('embeds ready and state content without adding an interactive surface', () => {
    const { rerender } = render(
      <DataTable
        caption="Portfolio positions"
        columns={COLUMNS}
        rows={ROWS}
        getRowKey={(row) => row.id}
        emptyState={EMPTY_STATE}
        frame="embedded"
        density="compact"
        minWidth="container"
        separatorTone="inherit"
      />,
    );

    const table = screen.getByRole('table', { name: 'Portfolio positions' }) as HTMLTableElement;
    expect(table).toHaveClass('min-w-full', 'text-xs', 'border-inherit');
    expect(table.closest('[data-data-table="ready"]')).toHaveAttribute('role', 'region');
    expect(table.closest('[data-surface-level]')).toBeNull();
    expect(table.tHead).toHaveClass('border-inherit');
    expect(table.tBodies[0]).toHaveClass('divide-inherit', 'border-inherit');

    rerender(
      <DataTable
        caption="Portfolio positions"
        columns={COLUMNS}
        rows={[]}
        getRowKey={(row) => row.id}
        emptyState={EMPTY_STATE}
        frame="embedded"
      />,
    );

    const state = screen.getByText('No positions').closest('[data-data-table="state"]');
    expect(state).toHaveAttribute('data-surface-level', 'canvas');
    expect(state?.closest('[data-surface-level="interactive"]')).toBeNull();
  });

  it('owns fixed proportional columns, selected-row presentation, and stable row test IDs', () => {
    const fixedColumns: DataTableColumn<Row>[] = [
      { ...COLUMNS[0], widthPercent: 3 },
      { ...COLUMNS[1], widthPercent: 1 },
    ];
    render(
      <DataTable
        caption="Portfolio positions"
        columns={fixedColumns}
        rows={ROWS}
        getRowKey={(row) => row.id}
        emptyState={EMPTY_STATE}
        layout="fixed"
        isRowSelected={(row) => row.id === 1}
        getRowTestId={(row) => `position-${row.id}`}
      />,
    );

    const table = screen.getByRole('table', { name: 'Portfolio positions' });
    const columns = table.querySelectorAll('colgroup col');
    expect(table).toHaveClass('table-fixed');
    expect(columns).toHaveLength(2);
    expect(columns[0]).toHaveStyle({ width: '75%' });
    expect(columns[1]).toHaveStyle({ width: '25%' });
    expect(screen.getByTestId('position-1')).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByTestId('position-1')).toHaveAttribute('data-row-selected', 'true');
    expect(screen.getByTestId('position-1')).toHaveClass('bg-primary/10', 'ring-primary/35');
    expect(screen.getByTestId('position-2')).toHaveAttribute('aria-selected', 'false');
    expect(screen.getByTestId('position-2')).not.toHaveAttribute('data-row-selected');
  });

  it('owns controlled detail-row geometry, identity, and accessible labels', () => {
    const { rerender } = render(
      <DataTable
        caption="Portfolio positions"
        columns={COLUMNS}
        rows={ROWS}
        getRowKey={(row) => row.id}
        emptyState={EMPTY_STATE}
        isRowDetailVisible={(row) => row.id === 1}
        renderRowDetail={(row) => <button type="button">Inspect {row.symbol}</button>}
        getRowDetailId={(row) => `position-${row.id}-details`}
        getRowDetailAriaLabel={(row) => `${row.symbol} position details`}
      />,
    );

    const detailRow = screen.getByRole('row', { name: 'AAPL position details' });
    expect(detailRow).toHaveAttribute('id', 'position-1-details');
    expect(detailRow).toHaveAttribute('data-data-table-detail-row', 'true');
    expect(detailRow).toHaveClass('bg-subtle-soft');
    expect(within(detailRow).getByRole('cell')).toHaveAttribute('colspan', '2');
    expect(within(detailRow).getByRole('button', { name: 'Inspect AAPL' })).toBeVisible();
    expect(screen.queryByRole('row', { name: 'MSFT position details' })).not.toBeInTheDocument();

    rerender(
      <DataTable
        caption="Portfolio positions"
        columns={COLUMNS}
        rows={ROWS}
        getRowKey={(row) => row.id}
        emptyState={EMPTY_STATE}
        isRowDetailVisible={() => false}
        renderRowDetail={(row) => <span>{row.symbol} detail</span>}
        getRowDetailId={(row) => `position-${row.id}-details`}
        getRowDetailAriaLabel={(row) => `${row.symbol} position details`}
      />,
    );

    expect(document.querySelector('[data-data-table-detail-row="true"]')).not.toBeInTheDocument();
  });

  it('owns empty, loading, error, and retrying state surfaces without rendering a second table', () => {
    const { rerender } = render(
      <DataTable
        caption="Portfolio positions"
        columns={COLUMNS}
        rows={[]}
        getRowKey={(row) => row.id}
        emptyState={EMPTY_STATE}
      />,
    );
    expect(screen.getByText('No positions')).toBeVisible();
    expect(screen.queryByRole('table')).not.toBeInTheDocument();
    expect(document.querySelector('[data-state-panel="empty"]')).toBeInTheDocument();

    rerender(
      <DataTable
        caption="Portfolio positions"
        columns={COLUMNS}
        rows={ROWS}
        getRowKey={(row) => row.id}
        emptyState={EMPTY_STATE}
        status={{ state: 'loading', title: 'Loading positions' }}
      />,
    );
    expect(screen.getByRole('status')).toHaveAttribute('aria-busy', 'true');
    expect(screen.queryByRole('table')).not.toBeInTheDocument();

    rerender(
      <DataTable
        caption="Portfolio positions"
        columns={COLUMNS}
        rows={ROWS}
        getRowKey={(row) => row.id}
        emptyState={EMPTY_STATE}
        status={{
          state: 'error',
          title: 'Positions unavailable',
          action: <button type="button">Retry positions</button>,
        }}
      />,
    );
    expect(screen.getByRole('alert')).toHaveTextContent('Positions unavailable');
    expect(screen.getByRole('button', { name: 'Retry positions' })).toBeVisible();

    rerender(
      <DataTable
        caption="Portfolio positions"
        columns={COLUMNS}
        rows={ROWS}
        getRowKey={(row) => row.id}
        emptyState={EMPTY_STATE}
        status={{ state: 'retrying', title: 'Retrying positions' }}
      />,
    );
    expect(screen.getByRole('status')).toHaveAttribute('aria-busy', 'true');
    expect(screen.getByText('Retrying positions')).toBeVisible();
  });

  it('keeps sorting controlled and exposes native aria-sort state', () => {
    const onSortChange = vi.fn();
    const { rerender } = render(
      <DataTable
        caption="Portfolio positions"
        columns={COLUMNS}
        rows={ROWS}
        getRowKey={(row) => row.id}
        emptyState={EMPTY_STATE}
        sort={{ columnId: 'symbol', direction: 'ascending' }}
        onSortChange={onSortChange}
      />,
    );

    expect(screen.getByRole('columnheader', { name: /Symbol/ })).toHaveAttribute('aria-sort', 'ascending');
    fireEvent.click(screen.getByRole('button', { name: 'Sort by symbol' }));
    expect(onSortChange).toHaveBeenLastCalledWith({ columnId: 'symbol', direction: 'descending' });

    rerender(
      <DataTable
        caption="Portfolio positions"
        columns={COLUMNS}
        rows={ROWS}
        getRowKey={(row) => row.id}
        emptyState={EMPTY_STATE}
        sort={{ columnId: 'price', direction: 'descending' }}
        onSortChange={onSortChange}
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: 'Sort by symbol' }));
    expect(onSortChange).toHaveBeenLastCalledWith({ columnId: 'symbol', direction: 'ascending' });
  });

  it('activates rows with click, Enter, or Space and ignores nested interactive controls', () => {
    const onRowActivate = vi.fn();
    const onNestedAction = vi.fn();
    const interactiveColumns: DataTableColumn<Row>[] = [
      ...COLUMNS,
      {
        id: 'actions',
        header: 'Actions',
        align: 'end',
        cell: (row) => (
          <div>
            <button type="button" onClick={onNestedAction}>Inspect {row.symbol}</button>
            <a href={`#${row.symbol}`}>Open link</a>
            <label>
              Note label
              <input aria-label={`Note ${row.symbol}`} />
            </label>
            <span role="button" tabIndex={0}>Custom action</span>
          </div>
        ),
      },
    ];
    render(
      <DataTable
        caption="Portfolio positions"
        columns={interactiveColumns}
        rows={ROWS}
        getRowKey={(row) => row.id}
        emptyState={EMPTY_STATE}
        onRowActivate={onRowActivate}
        getRowAriaLabel={(row) => `Open ${row.symbol} position`}
      />,
    );

    const row = screen.getByRole('row', { name: 'Open AAPL position' });
    expect(row).toHaveAttribute('aria-keyshortcuts', 'Enter Space');
    fireEvent.click(within(row).getByRole('rowheader', { name: 'AAPL' }));
    fireEvent.keyDown(row, { key: 'Enter' });
    fireEvent.keyDown(row, { key: ' ' });
    expect(onRowActivate).toHaveBeenCalledTimes(3);

    const nestedButton = within(row).getByRole('button', { name: 'Inspect AAPL' });
    fireEvent.click(nestedButton);
    fireEvent.keyDown(nestedButton, { key: 'Enter' });
    fireEvent.click(within(row).getByRole('link', { name: 'Open link' }));
    fireEvent.click(within(row).getByRole('textbox', { name: 'Note AAPL' }));
    fireEvent.click(within(row).getByText('Note label'));
    fireEvent.click(within(row).getByRole('button', { name: 'Custom action' }));
    expect(onNestedAction).toHaveBeenCalledTimes(1);
    expect(onRowActivate).toHaveBeenCalledTimes(3);
  });

  it('removes disabled rows from the row-activation tab sequence', () => {
    const onRowActivate = vi.fn();
    render(
      <DataTable
        caption="Portfolio positions"
        columns={COLUMNS}
        rows={[{ ...ROWS[0], disabled: true }]}
        getRowKey={(row) => row.id}
        emptyState={EMPTY_STATE}
        onRowActivate={onRowActivate}
        getRowAriaLabel={(row) => `Open ${row.symbol} position`}
        isRowDisabled={(row) => Boolean(row.disabled)}
      />,
    );

    const row = screen.getByRole('row', { name: 'Open AAPL position' });
    expect(row).toHaveAttribute('aria-disabled', 'true');
    expect(row).not.toHaveAttribute('aria-keyshortcuts');
    expect(row).not.toHaveAttribute('tabindex');
    fireEvent.click(row);
    fireEvent.keyDown(row, { key: 'Enter' });
    expect(onRowActivate).not.toHaveBeenCalled();
  });

  it('keeps a hidden caption available as the table accessible name', () => {
    renderStaticTable();
    expect(screen.getByRole('table', { name: 'Portfolio positions' })).toBeVisible();
  });
});
