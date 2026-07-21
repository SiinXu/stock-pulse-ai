// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
/* eslint-disable react-refresh/only-export-components -- this Vite-only fixture defines and mounts its test harness in one entry file */
import { StrictMode, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { SlidersHorizontal } from 'lucide-react';
import '@fontsource-variable/geist/index.css';
import '../src/index.css';
import '../src/App.css';
import {
  Button,
  ConfirmDialog,
  Drawer,
  FilterSheet,
  Input,
  Modal,
  Popover,
  Select,
  ToastProvider,
  useToast,
} from '../src/components/common';
import { SettingsHelpButton } from '../src/components/settings/SettingsHelpButton';
import { ThemeProvider } from '../src/components/theme/ThemeProvider';
import { UiLanguageProvider } from '../src/contexts/UiLanguageContext';

type OuterOverlay = 'modal' | 'detail' | 'navigation' | null;

function HelpButton({ title }: { title: string }) {
  return (
    <SettingsHelpButton
      fieldKey="STOCK_LIST"
      title={title}
      helpKey="settings.base.STOCK_LIST"
    />
  );
}

function OverlayContents({
  title,
  onOpenConfirm,
  onShowToast,
}: {
  title: string;
  onOpenConfirm: () => void;
  onShowToast: () => void;
}) {
  return (
    <div className="flex flex-wrap items-center gap-3">
      <HelpButton title={title} />
      <Popover
        contentRole="menu"
        ariaLabel={`${title} actions`}
        placement="bottom"
        align="start"
        contentClassName="w-48 p-1"
        trigger={({ open, toggle }) => (
          <Button
            type="button"
            variant="secondary"
            size="comfortable"
            aria-haspopup="menu"
            aria-expanded={open}
            data-testid="open-nested-popover"
            onClick={toggle}
          >
            More actions
          </Button>
        )}
      >
        {({ close }) => (
          <>
            <button
              type="button"
              role="menuitem"
              className="flex min-h-11 w-full items-center rounded-lg px-3 text-left text-sm text-foreground hover:bg-hover"
              onClick={close}
            >
              Refresh context
            </button>
            <button
              type="button"
              role="menuitem"
              className="flex min-h-11 w-full items-center rounded-lg px-3 text-left text-sm text-foreground hover:bg-hover"
              onClick={() => {
                onShowToast();
                close();
              }}
            >
              Show status
            </button>
          </>
        )}
      </Popover>
      <Button
        type="button"
        variant="secondary"
        size="comfortable"
        data-testid="open-confirm"
        onClick={onOpenConfirm}
      >
        Open confirmation
      </Button>
      <Button
        type="button"
        variant="ghost"
        size="comfortable"
        onClick={onShowToast}
      >
        Show toast
      </Button>
    </div>
  );
}

function OverlayContractFixture() {
  const { showToast } = useToast();
  const [outerOverlay, setOuterOverlay] = useState<OuterOverlay>(null);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [filterOpen, setFilterOpen] = useState(false);
  const [market, setMarket] = useState('all');
  const [keyword, setKeyword] = useState('');
  const [appliedSummary, setAppliedSummary] = useState('No filters applied');

  const showStatus = () => showToast({
    title: 'Overlay status ready',
    message: 'The live region remains available above the active dialog.',
    tone: 'success',
    durationMs: 0,
  });

  return (
    <main className="min-h-dvh bg-background p-4 text-foreground sm:p-6">
      <div className="mx-auto max-w-4xl space-y-5">
        <header className="space-y-1">
          <h1 className="text-xl font-semibold text-foreground">Overlay contract fixture</h1>
          <p className="text-sm text-secondary-text" data-testid="applied-filter-summary">
            {appliedSummary}
          </p>
        </header>
        <div className="flex flex-wrap items-center gap-3">
          <HelpButton title="Standalone help" />
          <Popover
            contentRole="menu"
            ariaLabel="Fixture actions"
            trigger={({ open, toggle }) => (
              <Button
                type="button"
                variant="secondary"
                size="comfortable"
                aria-haspopup="menu"
                aria-expanded={open}
                data-testid="open-popover"
                onClick={toggle}
              >
                Open actions
              </Button>
            )}
          >
            <button type="button" role="menuitem">Fixture action</button>
            <Popover
              contentRole="menu"
              ariaLabel="Nested fixture actions"
              trigger={({ open, toggle }) => (
                <button
                  type="button"
                  role="menuitem"
                  aria-haspopup="menu"
                  aria-expanded={open}
                  onClick={toggle}
                >
                  Open nested actions
                </button>
              )}
            >
              <HelpButton title="Nested help" />
            </Popover>
          </Popover>
          <Button
            type="button"
            variant="secondary"
            size="comfortable"
            data-testid="open-modal"
            onClick={() => setOuterOverlay('modal')}
          >
            Open outer modal
          </Button>
          <Button
            type="button"
            variant="secondary"
            size="comfortable"
            data-testid="open-drawer"
            onClick={() => setOuterOverlay('detail')}
          >
            Open outer drawer
          </Button>
          <Button
            type="button"
            variant="secondary"
            size="comfortable"
            data-testid="open-navigation"
            onClick={() => setOuterOverlay('navigation')}
          >
            Open navigation
          </Button>
          <Button
            type="button"
            variant="primary"
            size="primary"
            data-testid="open-filter-sheet"
            onClick={() => setFilterOpen(true)}
          >
            <SlidersHorizontal aria-hidden="true" className="h-4 w-4" />
            More filters
          </Button>
        </div>
      </div>

      <Modal
        isOpen={outerOverlay === 'modal'}
        onClose={() => setOuterOverlay(null)}
        title="Outer modal"
        description="A form dialog with fixed actions"
        footer={(
          <>
            <Button variant="ghost" size="comfortable" onClick={() => setOuterOverlay(null)}>Cancel</Button>
            <Button variant="primary" size="comfortable" onClick={() => setOuterOverlay(null)}>Save changes</Button>
          </>
        )}
      >
        <OverlayContents
          title="Modal help"
          onOpenConfirm={() => setConfirmOpen(true)}
          onShowToast={showStatus}
        />
      </Modal>

      <Drawer
        isOpen={outerOverlay === 'detail'}
        onClose={() => setOuterOverlay(null)}
        title="Outer drawer"
        description="Supplemental report details"
        variant="detail"
      >
        <OverlayContents
          title="Drawer help"
          onOpenConfirm={() => setConfirmOpen(true)}
          onShowToast={showStatus}
        />
      </Drawer>

      <Drawer
        isOpen={outerOverlay === 'navigation'}
        onClose={() => setOuterOverlay(null)}
        title="StockPulse navigation"
        variant="navigation"
      >
        <nav className="space-y-1 p-3" aria-label="Fixture routes">
          {['Home', 'Reports', 'Settings'].map((route) => (
            <button
              key={route}
              type="button"
              className="flex min-h-11 w-full items-center rounded-lg px-3 text-left text-sm text-foreground hover:bg-hover"
            >
              {route}
            </button>
          ))}
        </nav>
      </Drawer>

      <FilterSheet
        isOpen={filterOpen}
        onClose={() => setFilterOpen(false)}
        title="More filters"
        description="Refine the visible signal set"
        resetLabel="Reset"
        applyLabel="View 12 results"
        onReset={() => {
          setMarket('all');
          setKeyword('');
        }}
        onApply={() => {
          setAppliedSummary(`Applied: ${market} / ${keyword || 'any keyword'}`);
          setFilterOpen(false);
        }}
      >
        <Select
          label="Market"
          value={market}
          onChange={setMarket}
          options={[
            { value: 'all', label: 'All markets' },
            { value: 'cn', label: 'China A-shares' },
            { value: 'us', label: 'United States' },
          ]}
        />
        <Input
          label="Keyword"
          value={keyword}
          onChange={(event) => setKeyword(event.target.value)}
          placeholder="Ticker or company"
        />
        <OverlayContents
          title="Filter help"
          onOpenConfirm={() => setConfirmOpen(true)}
          onShowToast={showStatus}
        />
        <div className="space-y-2 pt-2" aria-label="Additional filter fields">
          {['Signal status', 'Action', 'Time range', 'Confidence', 'Source'].map((label) => (
            <label key={label} className="block space-y-1 text-sm text-secondary-text">
              <span>{label}</span>
              <input className="h-9 w-full rounded-lg border border-border bg-transparent px-3 text-foreground" />
            </label>
          ))}
        </div>
      </FilterSheet>

      <ConfirmDialog
        isOpen={confirmOpen}
        title="Confirm contract action"
        message="The confirmation must remain the only active dialog while it is topmost."
        onConfirm={() => setConfirmOpen(false)}
        onCancel={() => setConfirmOpen(false)}
      />
    </main>
  );
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ThemeProvider>
      <UiLanguageProvider>
        <ToastProvider>
          <OverlayContractFixture />
        </ToastProvider>
      </UiLanguageProvider>
    </ThemeProvider>
  </StrictMode>,
);
