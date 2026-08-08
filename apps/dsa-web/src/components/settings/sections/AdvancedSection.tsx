// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
/* eslint-disable @typescript-eslint/no-explicit-any -- mechanical section props accept page model shapes */
import type React from 'react';
import type { UiLanguage } from '../../../i18n/uiLanguages';
import type { SystemConfigItem, SystemConfigUpdateItem, LLMConfigModeStatus, UpdateSystemConfigResponse } from '../../../types/systemConfig';
import { GenerationBackendStatusPanel, LLMConfigModeBanner, SettingsField, SettingsSectionCard } from '..';
import ConfigBackupCard from '../ConfigBackupCard';
import ConfigPresetsPanel from '../ConfigPresetsPanel';
import {
  isFieldEnabledByContract,
  resolveFieldRequirement,
} from '../../../utils/configConditions';

export type AdvancedSectionProps = {
  isTopLevelAdvanced: boolean;
  activeView: string;
  configVersion: string;
  hasDirty: boolean;
  isSaving: boolean;
  isLoading: boolean;
  load: () => Promise<boolean>;
  setSchedulerStatusRefreshToken: React.Dispatch<React.SetStateAction<number>>;
  refreshSetupStatus: () => void;
  refreshAfterExternalSave: (keys: string[]) => Promise<void>;
  applyPostSaveEffects: () => void;
  llmModeStatus: LLMConfigModeStatus | null;
  generationBackendDraftItems: SystemConfigUpdateItem[];
  maskToken: string;
  advancedSectionItems: SystemConfigItem[];
  setDraftValue: (key: string, value: string) => void;
  issueByKey: Record<string, any>;
  allValuesByKey: Record<string, string>;
  categoryByKey: Record<string, string>;
  readOnlyDiagnosticForItem: (item: SystemConfigItem, category?: string) => string | undefined;
  settingsText: { diagnostics: string; advancedDescription: string };
  t: (...args: any[]) => string;
  language: UiLanguage;
};

/** Advanced section views: backup, raw_config, diagnostics. */
export const AdvancedSection: React.FC<AdvancedSectionProps> = (props) => {
  const {
    isTopLevelAdvanced,
    activeView,
    configVersion,
    hasDirty,
    isSaving,
    isLoading,
    load,
    setSchedulerStatusRefreshToken,
    refreshSetupStatus,
    refreshAfterExternalSave,
    applyPostSaveEffects,
    llmModeStatus,
    generationBackendDraftItems,
    maskToken,
    advancedSectionItems,
    setDraftValue,
    issueByKey,
    allValuesByKey,
    categoryByKey,
    readOnlyDiagnosticForItem,
    settingsText,
    t,
    language,
  } = props;

  return (
    <>
      {isTopLevelAdvanced && activeView === 'backup' ? (
        <>
          <ConfigPresetsPanel
            configVersion={configVersion}
            disabled={isSaving || isLoading}
            t={t}
            language={language}
            onApplied={async (keys) => {
              await refreshAfterExternalSave(keys);
              applyPostSaveEffects();
            }}
          />
          <ConfigBackupCard
            configVersion={configVersion}
            hasDirty={hasDirty}
            disabled={isSaving || isLoading}
            load={load}
            onSchedulerKeysImported={() => setSchedulerStatusRefreshToken((c) => c + 1)}
            onRefreshSetupStatus={() => {
              void refreshSetupStatus();
            }}
            onRolledBack={async (result: UpdateSystemConfigResponse) => {
              await refreshAfterExternalSave(result.updatedKeys);
              applyPostSaveEffects();
            }}
            onReloadLatest={() => refreshAfterExternalSave([])}
          />
        </>
      ) : null}
      {isTopLevelAdvanced && activeView === 'raw_config' ? (
        <>
          <LLMConfigModeBanner
            status={llmModeStatus}
            configVersion={configVersion}
            onMigrated={() => {
              void (async () => {
                await load();
                applyPostSaveEffects();
              })();
            }}
          />
          <GenerationBackendStatusPanel
            items={generationBackendDraftItems}
            maskToken={maskToken}
            disabled={isSaving || isLoading}
          />
        </>
      ) : null}
      {isTopLevelAdvanced && activeView === 'diagnostics' ? (
        <SettingsSectionCard
          title={settingsText.diagnostics}
          description={settingsText.advancedDescription}
        >
          {advancedSectionItems.length > 0 ? (
            <form
              className="overflow-hidden rounded-lg border border-[var(--settings-border)] bg-[var(--settings-surface)]"
              onSubmit={(event) => event.preventDefault()}
            >
              {advancedSectionItems.map((item) => (
                <SettingsField
                  key={item.key}
                  item={item}
                  value={item.value}
                  disabled={isSaving}
                  onChange={setDraftValue}
                  issues={issueByKey[item.key] || []}
                  requirement={resolveFieldRequirement(item.schema?.contract, allValuesByKey)}
                  dependencyLocked={!isFieldEnabledByContract(item.schema?.contract, allValuesByKey)}
                  readOnlyDiagnostic={readOnlyDiagnosticForItem(item, categoryByKey[item.key]) as string | undefined}
                />
              ))}
            </form>
          ) : null}
        </SettingsSectionCard>
      ) : null}
    </>
  );
};
