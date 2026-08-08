// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
/* eslint-disable @typescript-eslint/no-explicit-any -- mechanical section props accept page model shapes */
import type React from 'react';
import { Button, Modal } from '../../common';
import { IntelligentImport, SettingsSectionCard } from '..';

export type WatchlistSectionProps = {
  activeCategory: string;
  isIntelligentImportOpen: boolean;
  setIsIntelligentImportOpen: (open: boolean) => void;
  stockListValue: string;
  configVersion: string;
  maskToken: string;
  isSaving: boolean;
  isLoading: boolean;
  refreshAfterExternalSave: (keys: string[]) => Promise<void>;
  applyPostSaveEffects: () => void;
  t: (...args: any[]) => string;
};

export const WatchlistSection: React.FC<WatchlistSectionProps> = (p) => (
  p.activeCategory === 'base' ? (
    <>
      <SettingsSectionCard
        title={p.t('settings.intelligentImport')}
        description={p.t('settings.intelligentImportDescription')}
        actions={(
          <Button
            type="button"
            variant="secondary"
            size="default"
            aria-haspopup="dialog"
            onClick={() => p.setIsIntelligentImportOpen(true)}
          >
            {p.t('settings.openConfigItems')}
          </Button>
        )}
      >
        <p className="text-xs leading-6 text-muted-text">
          {p.t('settings.intelligentImportSupportedInputs')}
          {' · '}
          {p.t('settings.intelligentImportHint')}
        </p>
      </SettingsSectionCard>
      <Modal
        isOpen={p.isIntelligentImportOpen}
        onClose={() => p.setIsIntelligentImportOpen(false)}
        title={p.t('settings.intelligentImport')}
        description={p.t('settings.intelligentImportDescription')}
        size="wide"
      >
        <IntelligentImport
          stockListValue={p.stockListValue}
          configVersion={p.configVersion}
          maskToken={p.maskToken}
          onMerged={async () => {
            await p.refreshAfterExternalSave(['STOCK_LIST']);
            p.applyPostSaveEffects();
          }}
          disabled={p.isSaving || p.isLoading}
        />
      </Modal>
    </>
  ) : null
);
