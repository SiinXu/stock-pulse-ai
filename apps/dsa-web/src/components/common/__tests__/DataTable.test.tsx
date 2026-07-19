import { fireEvent, render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { DataTable, type DataTableColumn } from '../DataTable';

type Row = {
  id: number;
  name: string;
  status: string;
  detail: string;
};

const columns: DataTableColumn<Row>[] = [
  { id: 'name', header: 'Name', cell: (row) => row.name, sortable: true },
  {
    id: 'status',
    header: 'Status',
    cell: (row) => row.status,
    priority: 'secondary',
    cellClassName: (row) => row.status === 'Ready' ? 'text-success' : 'text-warning',
  },
  { id: 'detail', header: 'Detail', cell: (row) => row.detail, priority: 'tertiary' },
];

const rows: Row[] = [
  { id: 1, name: 'Alpha', status: 'Ready', detail: 'First row' },
  { id: 2, name: 'Beta', status: 'Pending', detail: 'Second row' },
];

const baseProps = {
  ariaLabel: 'Accounts',
  columns,
  rows,
  getRowKey: (row: Row) => row.id,
  loadingLabel: 'Loading accounts',
  emptyState: <p>No accounts</p>,
};

describe('DataTable', () => {
  it('renders accessible headers, rows, and responsive column priorities', () => {
    render(<DataTable {...baseProps} />);

    const table = screen.getByRole('table', { name: 'Accounts' });
    expect(within(table).getAllByRole('row')).toHaveLength(3);
    expect(within(table).getByText('Alpha')).toBeInTheDocument();
    expect(within(table).getByText('Ready').closest('td')).toHaveClass('text-success');
    expect(within(table).getByRole('columnheader', { name: 'Status' })).toHaveClass('hidden', 'md:table-cell');
    expect(within(table).getByRole('columnheader', { name: 'Detail' })).toHaveClass('hidden', 'lg:table-cell');
  });

  it('emits controlled sort changes and exposes aria-sort', () => {
    const onSortChange = vi.fn();
    const { rerender } = render(
      <DataTable
        {...baseProps}
        sort={{ columnId: 'name', direction: 'asc' }}
        onSortChange={onSortChange}
      />,
    );

    const nameHeader = screen.getByRole('columnheader', { name: 'Name' });
    expect(nameHeader).toHaveAttribute('aria-sort', 'ascending');
    fireEvent.click(within(nameHeader).getByRole('button', { name: 'Name' }));
    expect(onSortChange).toHaveBeenCalledWith({ columnId: 'name', direction: 'desc' });

    rerender(
      <DataTable
        {...baseProps}
        sort={{ columnId: 'status', direction: 'desc' }}
        onSortChange={onSortChange}
      />,
    );
    expect(screen.getByRole('columnheader', { name: 'Name' })).toHaveAttribute('aria-sort', 'none');
  });

  it('renders shared loading and caller-owned empty states', () => {
    const { rerender } = render(<DataTable {...baseProps} isLoading />);
    expect(screen.getByRole('status')).toHaveTextContent('Loading accounts');
    expect(screen.queryByRole('table')).not.toBeInTheDocument();

    rerender(<DataTable {...baseProps} rows={[]} />);
    expect(screen.getByText('No accounts')).toBeInTheDocument();
    expect(screen.queryByRole('table')).not.toBeInTheDocument();
  });

  it('renders an optional full-width detail row after its owner row', () => {
    render(
      <DataTable
        {...baseProps}
        renderAfterRow={(row) => row.id === 1 ? <p>Expanded first row</p> : null}
      />,
    );

    const detail = screen.getByText('Expanded first row');
    const detailRow = detail.closest('tr');
    expect(detailRow).toHaveAttribute('data-table-after-row', 'true');
    expect(detail.closest('td')).toHaveAttribute('colspan', String(columns.length));
    expect(screen.getAllByRole('row')).toHaveLength(4);
  });

  it('supports accessible pointer and keyboard row selection', () => {
    const onRowClick = vi.fn();
    render(
      <DataTable
        {...baseProps}
        onRowClick={onRowClick}
        getRowAriaLabel={(row) => `Open ${row.name}`}
        isRowSelected={(row) => row.id === 1}
      />,
    );

    const firstRow = screen.getByRole('row', { name: 'Open Alpha' });
    const secondRow = screen.getByRole('row', { name: 'Open Beta' });
    expect(firstRow).toHaveAttribute('aria-selected', 'true');
    expect(secondRow).toHaveAttribute('tabindex', '0');

    fireEvent.click(firstRow);
    fireEvent.keyDown(secondRow, { key: 'Enter' });
    fireEvent.keyDown(secondRow, { key: ' ' });
    expect(onRowClick).toHaveBeenNthCalledWith(1, rows[0], 0);
    expect(onRowClick).toHaveBeenNthCalledWith(2, rows[1], 1);
    expect(onRowClick).toHaveBeenNthCalledWith(3, rows[1], 1);
  });
});
