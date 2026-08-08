// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
/* eslint-disable @typescript-eslint/no-explicit-any -- mechanical section props accept page model shapes */
import type React from 'react';
import type { ParsedApiError } from '../../../api/error';
import type { SetupStatusResponse } from '../../../types/systemConfig';
import { Button, Surface } from '../../common';
import FirstRunSetupCard from '../FirstRunSetupCard';
import AlphaSiftSettingsCard from '../AlphaSiftSettingsCard';
import { legacyToSectionView } from '../settingsInformationArchitecture';

export type OverviewSectionProps = {
  shouldShowFirstRunSetup: boolean;
  setupStatus: SetupStatusResponse | null;
  isProviderCatalogLoading: boolean;
  providerCatalogLength: number;
  settingsText: any;
  setIsWizardOpen: (open: boolean) => void;
  isRefreshingSetupStatus: boolean;
  setupStatusError: ParsedApiError | null;
  firstSetupStockCode: string;
  isSaving: boolean;
  isLoading: boolean;
  isRunningSetupSmoke: boolean;
  setupSmokeError: ParsedApiError | null;
  setupSmokeSuccess: string;
  refreshSetupStatus: () => void;
  selectSectionView: (...args: any[]) => void;
  handleRunSetupSmoke: () => void;
  listSeparator: string;
  t: (...args: any[]) => string;
  shouldShowAlphaSiftSettings: boolean;
  alphasiftEnabled: boolean;
  configVersion: string;
  maskToken: string;
  refreshAfterExternalSave: (keys: string[]) => Promise<void>;
};

export const OverviewSection: React.FC<OverviewSectionProps> = (p) => (
  <>
    {p.shouldShowFirstRunSetup && !p.setupStatus?.isComplete ? (
      <Surface level="interactive" className="flex flex-col gap-2 px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0">
          <p className="text-sm font-semibold text-foreground">{p.settingsText.quickSetup}</p>
          <p className="mt-0.5 text-xs text-muted-text">{p.settingsText.quickSetupDescription}</p>
        </div>
        <Button
          type="button"
          variant="primary"
          size="default"
          className="shrink-0"
          disabled={p.isProviderCatalogLoading || p.providerCatalogLength === 0}
          onClick={() => p.setIsWizardOpen(true)}
        >
          {p.settingsText.startWizard}
        </Button>
      </Surface>
    ) : null}
    {p.shouldShowFirstRunSetup ? (
      <FirstRunSetupCard
        status={p.setupStatus}
        isLoading={p.isRefreshingSetupStatus}
        error={p.setupStatusError}
        firstStockCode={p.firstSetupStockCode}
        isSaving={p.isSaving}
        isRunningSmoke={p.isRunningSetupSmoke}
        smokeError={p.setupSmokeError}
        smokeSuccess={p.setupSmokeSuccess}
        onRefresh={p.refreshSetupStatus}
        onSelectCategory={(category) => {
          const target = legacyToSectionView(category, null);
          p.selectSectionView(target.section, target.view);
        }}
        onRunSmoke={p.handleRunSetupSmoke}
        showStartWizard={Boolean(p.setupStatus?.isComplete)}
        canStartWizard={!p.isProviderCatalogLoading && p.providerCatalogLength > 0}
        startWizardLabel={p.settingsText.startWizard}
        onStartWizard={() => p.setIsWizardOpen(true)}
        listSeparator={p.listSeparator}
        t={p.t}
      />
    ) : null}
    {p.shouldShowAlphaSiftSettings ? (
      <AlphaSiftSettingsCard
        enabled={p.alphasiftEnabled}
        configVersion={p.configVersion}
        maskToken={p.maskToken}
        disabled={p.isSaving || p.isLoading}
        onViewConfigItems={() => p.selectSectionView('data_sources', 'providers')}
        onAfterChange={async () => {
          await p.refreshAfterExternalSave(['ALPHASIFT_ENABLED']);
        }}
      />
    ) : null}
  </>
);
