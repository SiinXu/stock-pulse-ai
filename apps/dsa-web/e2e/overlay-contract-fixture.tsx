// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
/* eslint-disable react-refresh/only-export-components -- this Vite-only fixture defines and mounts its test harness in one entry file */
import { StrictMode, useState } from 'react';
import { createRoot } from 'react-dom/client';
import '@fontsource-variable/geist/index.css';
import '../src/index.css';
import '../src/App.css';
import { ConfirmDialog, Drawer, Modal } from '../src/components/common';
import { SettingsHelpButton } from '../src/components/settings/SettingsHelpButton';
import { ThemeProvider } from '../src/components/theme/ThemeProvider';
import { UiLanguageProvider } from '../src/contexts/UiLanguageContext';

type OuterOverlay = 'modal' | 'drawer' | null;

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
}: {
  title: string;
  onOpenConfirm: () => void;
}) {
  return (
    <div className="flex flex-wrap items-center gap-3">
      <HelpButton title={title} />
      <button
        type="button"
        className="min-h-11 rounded-full border border-border px-4 py-2"
        data-testid="open-confirm"
        onClick={onOpenConfirm}
      >
        Open confirmation
      </button>
    </div>
  );
}

function OverlayContractFixture() {
  const [outerOverlay, setOuterOverlay] = useState<OuterOverlay>(null);
  const [confirmOpen, setConfirmOpen] = useState(false);

  return (
    <main className="min-h-dvh bg-background p-4 text-foreground">
      <div className="flex flex-wrap items-center gap-3">
        <HelpButton title="Standalone help" />
        <button
          type="button"
          className="min-h-11 rounded-full border border-border px-4 py-2"
          data-testid="open-modal"
          onClick={() => setOuterOverlay('modal')}
        >
          Open outer modal
        </button>
        <button
          type="button"
          className="min-h-11 rounded-full border border-border px-4 py-2"
          data-testid="open-drawer"
          onClick={() => setOuterOverlay('drawer')}
        >
          Open outer drawer
        </button>
      </div>

      <Modal
        isOpen={outerOverlay === 'modal'}
        onClose={() => setOuterOverlay(null)}
        title="Outer modal"
      >
        <OverlayContents title="Modal help" onOpenConfirm={() => setConfirmOpen(true)} />
      </Modal>

      <Drawer
        isOpen={outerOverlay === 'drawer'}
        onClose={() => setOuterOverlay(null)}
        title="Outer drawer"
        variant="detail"
      >
        <OverlayContents title="Drawer help" onOpenConfirm={() => setConfirmOpen(true)} />
      </Drawer>

      <ConfirmDialog
        isOpen={confirmOpen}
        title="Confirm contract action"
        message="The confirmation must remain the only active overlay while it is topmost."
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
        <OverlayContractFixture />
      </UiLanguageProvider>
    </ThemeProvider>
  </StrictMode>,
);
