// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
/* eslint-disable react-refresh/only-export-components -- this Vite-only fixture defines and mounts its test harness in one entry file */
import { StrictMode, useMemo, useState } from 'react';
import { createRoot } from 'react-dom/client';
import '@fontsource-variable/geist/index.css';
import '../src/index.css';
import '../src/App.css';
import {
  Badge,
  Button,
  DataTable,
  type DataTableColumn,
  type DataTableSortState,
  type DataTableStatus,
} from '../src/components/common';
import { ThemeProvider } from '../src/components/theme/ThemeProvider';
import { UiLanguageProvider } from '../src/contexts/UiLanguageContext';

type FixtureView = 'ready' | 'loading' | 'empty' | 'error' | 'retrying';

type SignalRow = {
  id: string;
  symbol: string;
  company: string;
  market: string;
  price: number;
  change: number;
  status: 'active' | 'watch';
  updated: string;
};

const SIGNALS: readonly SignalRow[] = [
  {
    id: 'aapl',
    symbol: 'AAPL',
    company: 'Apple',
    market: 'NASDAQ',
    price: 212.48,
    change: 1.82,
    status: 'active',
    updated: '09:41',
  },
  {
    id: 'msft',
    symbol: 'MSFT',
    company: 'Microsoft',
    market: 'NASDAQ',
    price: 516.12,
    change: -0.64,
    status: 'watch',
    updated: '09:38',
  },
  {
    id: 'nvda',
    symbol: 'NVDA',
    company: 'NVIDIA',
    market: 'NASDAQ',
    price: 177.02,
    change: 2.14,
    status: 'active',
    updated: '09:35',
  },
  {
    id: 'tsm',
    symbol: 'TSM',
    company: 'TSMC',
    market: 'NYSE',
    price: 245.71,
    change: 0.37,
    status: 'watch',
    updated: '09:31',
  },
];

function initialView(): FixtureView {
  const value = new URLSearchParams(window.location.search).get('state');
  return value === 'loading' || value === 'empty' || value === 'error' || value === 'retrying'
    ? value
    : 'ready';
}

function DataTableFixture() {
  const [view, setView] = useState<FixtureView>(initialView);
  const [sort, setSort] = useState<DataTableSortState>({
    columnId: 'symbol',
    direction: 'ascending',
  });
  const [openedRow, setOpenedRow] = useState('No row opened');
  const [nestedAction, setNestedAction] = useState('No nested action');
  const [selectedRow, setSelectedRow] = useState('aapl');

  const columns: readonly DataTableColumn<SignalRow>[] = [
    {
      id: 'symbol',
      header: 'Symbol',
      rowHeader: true,
      nowrap: true,
      width: 'default',
      sortControl: { ariaLabel: 'Sort by symbol' },
      cell: (row) => (
        <div>
          <div className="font-semibold text-foreground">{row.symbol}</div>
          <div className="text-xs text-secondary-text">{row.company}</div>
        </div>
      ),
    },
    {
      id: 'market',
      header: 'Market',
      nowrap: true,
      cell: (row) => row.market,
    },
    {
      id: 'price',
      header: 'Last price',
      align: 'end',
      nowrap: true,
      sortControl: { ariaLabel: 'Sort by last price' },
      cell: (row) => <span className="font-medium text-foreground">${row.price.toFixed(2)}</span>,
    },
    {
      id: 'change',
      header: 'Day change',
      align: 'end',
      nowrap: true,
      cell: (row) => (
        <span className={row.change >= 0 ? 'text-success' : 'text-danger'}>
          {row.change >= 0 ? '+' : ''}{row.change.toFixed(2)}%
        </span>
      ),
    },
    {
      id: 'status',
      header: 'Status',
      cell: (row) => (
        <Badge variant={row.status === 'active' ? 'success' : 'default'}>
          {row.status === 'active' ? 'Active' : 'Watch'}
        </Badge>
      ),
    },
    {
      id: 'updated',
      header: 'Updated',
      nowrap: true,
      cell: (row) => `${row.updated} UTC`,
    },
    {
      id: 'actions',
      header: 'Actions',
      align: 'end',
      nowrap: true,
      cell: (row) => (
        <Button
          type="button"
          variant="ghost"
          size="compact"
          onClick={() => setNestedAction(`Inspected ${row.symbol}`)}
        >
          Inspect
        </Button>
      ),
    },
  ];

  const sortedRows = useMemo(() => {
    const direction = sort.direction === 'ascending' ? 1 : -1;
    return [...SIGNALS].sort((left, right) => {
      if (sort.columnId === 'price') return (left.price - right.price) * direction;
      return left.symbol.localeCompare(right.symbol) * direction;
    });
  }, [sort]);
  const embeddedColumns: readonly DataTableColumn<SignalRow>[] = [
    {
      id: 'symbol',
      header: 'Symbol',
      rowHeader: true,
      widthPercent: 35,
      cell: (row) => <span className="font-semibold text-foreground">{row.symbol}</span>,
    },
    {
      id: 'company',
      header: 'Company',
      widthPercent: 65,
      cell: (row) => row.company,
    },
  ];

  const status: DataTableStatus | undefined = view === 'loading'
    ? { state: 'loading', title: 'Loading tracked signals' }
    : view === 'error'
      ? {
          state: 'error',
          title: 'Signals unavailable',
          description: 'The last request could not be completed.',
          action: (
            <Button type="button" variant="danger-subtle" size="compact" onClick={() => setView('ready')}>
              Retry table
            </Button>
          ),
        }
      : view === 'retrying'
        ? { state: 'retrying', title: 'Retrying tracked signals' }
        : undefined;

  return (
    <main className="min-h-dvh bg-background p-4 text-foreground sm:p-6">
      <div className="mx-auto max-w-6xl space-y-5">
        <header className="space-y-1">
          <p className="text-xs font-medium text-secondary-text">Signal operations</p>
          <h1 className="text-2xl font-semibold text-foreground">Tracked decision signals</h1>
          <p className="max-w-2xl text-sm text-secondary-text">
            Compare the latest tracked symbols and open one signal without coupling its row to nested commands.
          </p>
        </header>

        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border pb-3">
          <div>
            <h2 className="text-base font-semibold text-foreground">Current result set</h2>
            <p className="text-sm text-secondary-text">{view === 'empty' ? 0 : SIGNALS.length} tracked symbols</p>
          </div>
          <div className="text-right text-xs text-secondary-text">
            <p data-testid="row-result" aria-live="polite">{openedRow}</p>
            <p data-testid="nested-result" aria-live="polite">{nestedAction}</p>
          </div>
        </div>

        <DataTable
          caption="Tracked decision signals"
          scrollAreaLabel="Scrollable tracked decision signals"
          columns={columns}
          rows={view === 'empty' ? [] : sortedRows}
          getRowKey={(row) => row.id}
          emptyState={{
            title: 'No tracked signals',
            description: 'Run a signal screen to populate this result set.',
          }}
          status={status}
          sort={sort}
          onSortChange={setSort}
          onRowActivate={(row) => setOpenedRow(`Opened ${row.symbol}`)}
          getRowAriaLabel={(row) => `Open ${row.symbol} signal`}
        />

        {view === 'ready' ? (
          <section aria-labelledby="embedded-table-title" className="space-y-2">
            <h2 id="embedded-table-title" className="text-base font-semibold text-foreground">
              Embedded selection
            </h2>
            <p data-testid="selected-result" aria-live="polite" className="text-xs text-secondary-text">
              Selected {selectedRow.toUpperCase()}
            </p>
            <div
              data-testid="embedded-table-frame"
              className="overflow-hidden rounded-xl border border-[var(--settings-border)]"
            >
              <DataTable
                caption="Embedded selected signals"
                scrollAreaLabel="Scrollable embedded selected signals"
                columns={embeddedColumns}
                rows={SIGNALS}
                getRowKey={(row) => row.id}
                emptyState={{ title: 'No embedded signals' }}
                density="compact"
                frame="embedded"
                layout="fixed"
                minWidth="narrow"
                separatorTone="inherit"
                onRowActivate={(row) => setSelectedRow(row.id)}
                getRowAriaLabel={(row) => `Select ${row.symbol} signal`}
                isRowSelected={(row) => row.id === selectedRow}
                getRowTestId={(row) => `embedded-row-${row.id}`}
              />
            </div>
          </section>
        ) : null}
      </div>
    </main>
  );
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ThemeProvider>
      <UiLanguageProvider>
        <DataTableFixture />
      </UiLanguageProvider>
    </ThemeProvider>
  </StrictMode>,
);
