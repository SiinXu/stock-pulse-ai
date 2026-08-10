// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type React from 'react';
import { useUiLanguage } from '../../../contexts/UiLanguageContext';
import { SETTINGS_PAGE_TEXT } from '../../../locales/settingsPage';
import { getUiListSeparator } from '../../../utils/uiLocale';
import { Button, Surface } from '../../common';
import AlphaSiftSettingsCard from '../AlphaSiftSettingsCard';
import FirstRunSetupCard from '../FirstRunSetupCard';
import {
  legacyToSectionView,
  type SettingsSectionId,
} from '../settingsInformationArchitecture';

type FirstRunSetupProps = React.ComponentProps<typeof FirstRunSetupCard>;

type OverviewSectionProps = {
  shouldShowFirstRunSetup: boolean;
  setupStatus: FirstRunSetupProps['status'];
  isProviderCatalogLoading: boolean;
  providerCatalogLength: number;
  setIsWizardOpen: (open: boolean) => void;
  isRefreshingSetupStatus: boolean;
  setupStatusError: FirstRunSetupProps['error'];
  firstSetupStockCode: string;
  isSaving: boolean;
  isLoading: boolean;
  isRunningSetupSmoke: boolean;
  setupSmokeError: FirstRunSetupProps['smokeError'];
  setupSmokeSuccess: string;
  refreshSetupStatus: () => void;
  selectSectionView: (section: SettingsSectionId, view: string) => void;
  handleRunSetupSmoke: () => void;
  shouldShowAlphaSiftSettings: boolean;
  alphasiftEnabled: boolean;
  configVersion: string;
  maskToken: string;
  refreshAfterExternalSave: (keys: string[]) => Promise<void>;
};

const OverviewSection: React.FC<OverviewSectionProps> = (props) => {
  const { language, t } = useUiLanguage();
  const settingsText = SETTINGS_PAGE_TEXT[language];
  const canStartWizard = !props.isProviderCatalogLoading && props.providerCatalogLength > 0;

  return (
    <>
      {props.shouldShowFirstRunSetup && !props.setupStatus?.isComplete ? (
        <Surface level="interactive" className="flex flex-col gap-2 px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="min-w-0">
            <p className="text-sm font-semibold text-foreground">{settingsText.quickSetup}</p>
            <p className="mt-0.5 text-xs text-muted-text">{settingsText.quickSetupDescription}</p>
          </div>
          <Button
            type="button"
            variant="primary"
            size="default"
            className="shrink-0"
            disabled={!canStartWizard}
            onClick={() => props.setIsWizardOpen(true)}
          >
            {settingsText.startWizard}
          </Button>
        </Surface>
      ) : null}
      {props.shouldShowFirstRunSetup ? (
        <FirstRunSetupCard
          status={props.setupStatus}
          isLoading={props.isRefreshingSetupStatus}
          error={props.setupStatusError}
          firstStockCode={props.firstSetupStockCode}
          isSaving={props.isSaving}
          isRunningSmoke={props.isRunningSetupSmoke}
          smokeError={props.setupSmokeError}
          smokeSuccess={props.setupSmokeSuccess}
          onRefresh={props.refreshSetupStatus}
          onSelectCategory={(category) => {
            const target = legacyToSectionView(category, null);
            props.selectSectionView(target.section, target.view);
          }}
          onRunSmoke={props.handleRunSetupSmoke}
          showStartWizard={Boolean(props.setupStatus?.isComplete)}
          canStartWizard={canStartWizard}
          startWizardLabel={settingsText.startWizard}
          onStartWizard={() => props.setIsWizardOpen(true)}
          listSeparator={getUiListSeparator(language)}
          t={t}
        />
      ) : null}
      {props.shouldShowAlphaSiftSettings ? (
        <AlphaSiftSettingsCard
          enabled={props.alphasiftEnabled}
          configVersion={props.configVersion}
          maskToken={props.maskToken}
          disabled={props.isSaving || props.isLoading}
          onViewConfigItems={() => props.selectSectionView('data_sources', 'providers')}
          onAfterChange={async () => {
            await props.refreshAfterExternalSave(['ALPHASIFT_ENABLED']);
          }}
        />
      ) : null}
    </>
  );
};

export default OverviewSection;
