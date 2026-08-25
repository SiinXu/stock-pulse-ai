// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type React from 'react';
import { lazy, Suspense } from 'react';
import {
  GenerationBackendStatusPanel,
  LLMConfigModeBanner,
  SettingsField,
  SettingsLoading,
  SettingsSectionCard,
} from '..';
import ConfigBackupCard from '../ConfigBackupCard';
import ConfigPresetsPanel from '../ConfigPresetsPanel';
import {
  isFieldEnabledByContract,
  resolveFieldRequirement,
} from '../../../utils/configConditions';
import type { UiLanguage, UiTextKey } from '../../../i18n/uiText';
import { SETTINGS_PAGE_TEXT } from '../../../locales/settingsPage';
import type {
  ConfigValidationIssue,
  LLMConfigModeStatus,
  SystemConfigItem,
  SystemConfigUpdateItem,
  UpdateSystemConfigResponse,
} from '../../../types/systemConfig';

const RuntimeCapabilitiesPanel = lazy(async () => {
  const module = await import('../RuntimeCapabilitiesPanel');
  return { default: module.RuntimeCapabilitiesPanel };
});

type AdvancedSectionProps = {
  isTopLevelAdvanced: boolean;
  activeView: string;
  configVersion: string;
  isSaving: boolean;
  isLoading: boolean;
  hasDirty: boolean;
  load: () => Promise<boolean>;
  refreshAfterExternalSave: (keys: string[]) => Promise<void>;
  applyPostSaveEffects: () => void;
  setSchedulerStatusRefreshToken: React.Dispatch<React.SetStateAction<number>>;
  refreshSetupStatus: () => Promise<void>;
  llmModeStatus: LLMConfigModeStatus | null;
  generationBackendDraftItems: SystemConfigUpdateItem[];
  maskToken: string;
  uiLanguage: UiLanguage;
  advancedSectionItems: SystemConfigItem[];
  setDraftValue: (key: string, value: string) => void;
  issueByKey: Record<string, ConfigValidationIssue[]>;
  allValuesByKey: Record<string, string>;
  readOnlyDiagnosticForItem: (item: SystemConfigItem, categoryHint?: string) => string | undefined;
  categoryByKey: Record<string, string>;
  t: (key: UiTextKey, params?: Record<string, string | number>) => string;
};

const AdvancedSection: React.FC<AdvancedSectionProps> = (props) => {
  const settingsText = SETTINGS_PAGE_TEXT[props.uiLanguage];
  if (!props.isTopLevelAdvanced) return null;

  return (
    <>
      {props.activeView === 'backup' ? (
        <>
          <ConfigPresetsPanel configVersion={props.configVersion} disabled={props.isSaving || props.isLoading} t={props.t} language={props.uiLanguage} onApplied={async (keys) => { await props.refreshAfterExternalSave(keys); props.applyPostSaveEffects(); }} />
          <ConfigBackupCard configVersion={props.configVersion} hasDirty={props.hasDirty} disabled={props.isSaving || props.isLoading} load={props.load} onSchedulerKeysImported={() => props.setSchedulerStatusRefreshToken((c) => c + 1)} onRefreshSetupStatus={() => { void props.refreshSetupStatus(); }} onRolledBack={async (result: UpdateSystemConfigResponse) => { await props.refreshAfterExternalSave(result.updatedKeys); props.applyPostSaveEffects(); }} onReloadLatest={() => props.refreshAfterExternalSave([])} />
        </>
      ) : null}
      {props.activeView === 'raw_config' ? (
        <>
          <LLMConfigModeBanner
            status={props.llmModeStatus}
            configVersion={props.configVersion}
            onMigrated={() => {
              void (async () => {
                await props.load();
                props.applyPostSaveEffects();
              })();
            }}
          />
          <GenerationBackendStatusPanel
            items={props.generationBackendDraftItems}
            maskToken={props.maskToken}
            disabled={props.isSaving || props.isLoading}
          />
        </>
      ) : null}
      {props.activeView === 'diagnostics' ? (
        <SettingsSectionCard
          title={settingsText.diagnostics}
          description={settingsText.advancedDescription}
        >
          {props.advancedSectionItems.length > 0 ? (
            <form
              className="overflow-hidden rounded-lg border border-[var(--settings-border)] bg-[var(--settings-surface)]"
              onSubmit={(event) => event.preventDefault()}
            >
              {props.advancedSectionItems.map((item) => (
                <SettingsField
                  key={item.key}
                  item={item}
                  value={item.value}
                  disabled={props.isSaving}
                  onChange={props.setDraftValue}
                  issues={props.issueByKey[item.key] || []}
                  requirement={resolveFieldRequirement(item.schema?.contract, props.allValuesByKey)}
                  dependencyLocked={!isFieldEnabledByContract(item.schema?.contract, props.allValuesByKey)}
                  readOnlyDiagnostic={props.readOnlyDiagnosticForItem(item, props.categoryByKey[item.key])}
                />
              ))}
            </form>
          ) : null}
        </SettingsSectionCard>
      ) : null}
      {props.activeView === 'capabilities' ? (
        <Suspense fallback={<SettingsLoading />}>
          <RuntimeCapabilitiesPanel />
        </Suspense>
      ) : null}
    </>
  );
};

export default AdvancedSection;
