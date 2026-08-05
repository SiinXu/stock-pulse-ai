// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type React from 'react';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { formatUiText } from '../../i18n/uiText';
import { SETTINGS_PAGE_TEXT, SETTINGS_TASK_ROUTE_LABELS } from '../../locales/settingsPage';
import type {
  AvailableModelEntry,
  ConfigValidationIssue,
  LlmConnectionFieldSchema,
  LlmProviderCatalogEntry,
  SystemConfigItem,
  SystemConfigUpdateItem,
} from '../../types/systemConfig';
import { getUiListSeparator } from '../../utils/uiLocale';
import { getFieldTitleZh } from '../../utils/systemConfigI18n';
import {
  isFieldEnabledByContract,
  resolveFieldRequirement,
} from '../../utils/configConditions';
import {
  Button,
  SearchableSelect,
  type SearchableSelectOption,
} from '../common';
import { AiOverviewMatrix } from './AiOverviewMatrix';
import type { ModelReferenceReplacement } from './llmChannelEditorModel';
import type { ModelAccessFieldFocusRequest } from '../../utils/modelAccessFieldKey';
import { TASK_MODEL_KEYS } from './aiModelsViewModel';
// Barrel imports so SettingsPage.testHarness mocks apply to nested cards.
import {
  LLMChannelEditor,
  ModelFallbackEditor,
  SettingsAlert,
  SettingsField,
  SettingsSectionCard,
} from './index';

export type AiOverviewCardProps = {
  allValuesByKey: Record<string, string>;
  availableRoutes: Set<string>;
  availableModelsError: unknown;
  availableModelsLoading: boolean;
  formatModel: (value: string) => string;
  onEditRouting: () => void;
  onReloadModels: () => void;
};

const AiOverviewCard: React.FC<AiOverviewCardProps> = ({
  allValuesByKey,
  availableRoutes,
  availableModelsError,
  availableModelsLoading,
  formatModel,
  onEditRouting,
  onReloadModels,
}) => {
  const { language: uiLanguage, t } = useUiLanguage();
  const settingsText = SETTINGS_PAGE_TEXT[uiLanguage];

  return (
    <SettingsSectionCard
      title={t('settings.llmAccess')}
      description={t('settings.llmAccessDescription')}
      contentBordered
    >
      {availableModelsError ? (
        <SettingsAlert
          variant="error"
          title={settingsText.modelCatalogFailed}
          message={settingsText.modelCatalogOverviewError}
          actionLabel={settingsText.reload}
          onAction={onReloadModels}
        />
      ) : availableModelsLoading ? (
        <p className="text-xs text-secondary-text">
          {settingsText.loadingModels}
        </p>
      ) : (
        <AiOverviewMatrix
          getValue={(key) => allValuesByKey[key.toUpperCase()] ?? ''}
          language={uiLanguage}
          onEditRouting={onEditRouting}
          availableRoutes={availableRoutes}
          formatModel={formatModel}
        />
      )}
    </SettingsSectionCard>
  );
};

export type AiTaskRoutingCardProps = {
  taskRoutingItems: SystemConfigItem[];
  fallbackModelsValue: string;
  issueByKey: Record<string, ConfigValidationIssue[]>;
  allValuesByKey: Record<string, string>;
  modelSelectorOptions: SearchableSelectOption[];
  availableModels: AvailableModelEntry[];
  availableModelsError: unknown;
  availableModelsLoading: boolean;
  configuredTaskRoutes: Array<{ key: string; value: string }>;
  hasSafeFallbackPlacement: boolean;
  isSaving: boolean;
  setDraftValue: (key: string, value: string) => void;
  resolveConfiguredModelRef: (value: string) => string;
  formatConfiguredModel: (value: string) => string;
  readOnlyDiagnosticForItem: (item: SystemConfigItem, categoryHint?: string) => string | undefined;
  onGoToModelAccess: () => void;
  onEditReliability: () => void;
  onReloadModels: () => void;
};

const AiTaskRoutingCard: React.FC<AiTaskRoutingCardProps> = ({
  taskRoutingItems,
  fallbackModelsValue,
  issueByKey,
  allValuesByKey,
  modelSelectorOptions,
  availableModels,
  availableModelsError,
  availableModelsLoading,
  configuredTaskRoutes,
  hasSafeFallbackPlacement,
  isSaving,
  setDraftValue,
  resolveConfiguredModelRef,
  formatConfiguredModel,
  readOnlyDiagnosticForItem,
  onGoToModelAccess,
  onEditReliability,
  onReloadModels,
}) => {
  const { language: uiLanguage } = useUiLanguage();
  const settingsText = SETTINGS_PAGE_TEXT[uiLanguage];

  return (
    <SettingsSectionCard
      title={settingsText.taskRouting}
      description={settingsText.taskRoutingDescription}
    >
      {availableModelsError ? (
        <SettingsAlert
          variant="error"
          title={settingsText.modelCatalogFailed}
          message={settingsText.modelCatalogRoutingError}
          actionLabel={settingsText.reload}
          onAction={onReloadModels}
        />
      ) : availableModelsLoading && availableModels.length === 0 ? (
        <p className="mb-3 text-xs text-secondary-text">{settingsText.loadingModels}</p>
      ) : availableModels.length === 0 ? (
        <div className="mb-3 rounded-lg border border-dashed border-[var(--settings-border)] bg-[var(--settings-surface)] px-4 py-5 text-center">
          <p className="text-sm font-medium text-foreground">
            {settingsText.noModels}
          </p>
          <p className="mt-1 text-sm text-secondary-text">
            {(allValuesByKey.LLM_CHANNELS || '').trim()
              ? settingsText.connectedWithoutModels
              : settingsText.connectFirst}
          </p>
          <Button
            type="button"
            variant="primary"
            size="default"
            className="mt-3"
            onClick={onGoToModelAccess}
          >
            {settingsText.goModelAccess}
          </Button>
          {configuredTaskRoutes.length > 0 ? (
            <div className="mt-4 space-y-1 text-left text-xs text-warning">
              {configuredTaskRoutes.map((route) => (
                <p key={route.key}>
                  {formatUiText(settingsText.staleValue, {
                    value: formatConfiguredModel(route.value),
                  })}
                </p>
              ))}
            </div>
          ) : null}
        </div>
      ) : null}
      {!availableModelsError && !availableModelsLoading && availableModels.length > 0 ? (
        <>
          {taskRoutingItems.length > 0 ? (
            <div className="overflow-hidden rounded-lg border border-[var(--settings-border)] bg-[var(--settings-surface)]">
              {taskRoutingItems.map((item) => (
                TASK_MODEL_KEYS.has(item.key) ? (
                  <div key={item.key} className="grid gap-2 px-3 py-2.5 md:grid-cols-[minmax(0,1fr)_260px] md:items-center md:gap-6">
                    <label htmlFor={`setting-${item.key}`} className="text-sm text-foreground">
                      {SETTINGS_TASK_ROUTE_LABELS[uiLanguage][item.key] ?? getFieldTitleZh(item.key, item.key)}
                    </label>
                    <div className="min-w-0">
                      <SearchableSelect
                        id={`setting-${item.key}`}
                        value={resolveConfiguredModelRef(item.value)}
                        onChange={(next) => setDraftValue(item.key, next)}
                        options={modelSelectorOptions}
                        disabled={isSaving || !isFieldEnabledByContract(item.schema?.contract, allValuesByKey)}
                        ariaLabel={SETTINGS_TASK_ROUTE_LABELS[uiLanguage][item.key] ?? getFieldTitleZh(item.key, item.key)}
                        placeholder={item.key === 'LITELLM_MODEL'
                          ? settingsText.selectModel
                          : settingsText.inheritReportModel}
                        error={(issueByKey[item.key] || []).some((issue) => issue.severity === 'error')}
                        ariaDescribedBy={(issueByKey[item.key] || [])
                          .map((issue) => `setting-${item.key}-issue-${issue.code}`)
                          .join(' ') || undefined}
                        emptyText={settingsText.noModelOptions}
                        searchPlaceholder={settingsText.searchModels}
                        staleValueText={formatConfiguredModel(item.value)}
                        staleValueLabel={formatUiText(settingsText.staleValue, {
                          value: formatConfiguredModel(item.value),
                        })}
                        clearable={item.key !== 'LITELLM_MODEL'}
                      />
                      {(issueByKey[item.key] || []).map((issue) => (
                        <p
                          id={`setting-${item.key}-issue-${issue.code}`}
                          key={`${issue.key}-${issue.code}`}
                          className="mt-1 text-xs text-danger"
                        >
                          {issue.message}
                        </p>
                      ))}
                      {readOnlyDiagnosticForItem(item, 'ai_model') ? (
                        <p className="mt-1 text-xs text-warning">
                          {readOnlyDiagnosticForItem(item, 'ai_model')}
                        </p>
                      ) : null}
                    </div>
                  </div>
                ) : (
                  <SettingsField
                    key={item.key}
                    item={item}
                    value={item.value}
                    disabled={isSaving}
                    onChange={setDraftValue}
                    issues={issueByKey[item.key] || []}
                    requirement={resolveFieldRequirement(item.schema?.contract, allValuesByKey)}
                    dependencyLocked={!isFieldEnabledByContract(item.schema?.contract, allValuesByKey)}
                    readOnlyDiagnostic={readOnlyDiagnosticForItem(item, 'ai_model')}
                  />
                )
              ))}
            </div>
          ) : (
            <p className="text-xs text-muted-text">
              {settingsText.noRoutingFields}
            </p>
          )}
          <div className="mt-3 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-secondary-text">
            <span>{settingsText.fallbackOrderLabel}</span>
            <span className="font-medium text-foreground">
              {fallbackModelsValue
                ? fallbackModelsValue
                  .split(',')
                  .map((entry) => formatConfiguredModel(entry.trim()))
                  .join(getUiListSeparator(uiLanguage))
                : settingsText.noneSet}
            </span>
            {hasSafeFallbackPlacement ? (
              <button
                type="button"
                className="settings-accent-text inline-flex min-h-11 min-w-11 items-center underline-offset-2 hover:underline"
                onClick={onEditReliability}
              >
                {settingsText.editReliability}
              </button>
            ) : null}
          </div>
        </>
      ) : null}
    </SettingsSectionCard>
  );
};

export type AiReliabilityCardProps = {
  fallbackValue: string;
  fallbackIssues: ConfigValidationIssue[];
  fallbackItem: SystemConfigItem | undefined;
  hasSafeFallbackPlacement: boolean;
  modelSelectorOptions: SearchableSelectOption[];
  primaryRoute: string;
  allValuesByKey: Record<string, string>;
  isSaving: boolean;
  setDraftValue: (key: string, value: string) => void;
  resolveConfiguredModelRef: (value: string) => string;
};

const AiReliabilityCard: React.FC<AiReliabilityCardProps> = ({
  fallbackValue,
  fallbackIssues,
  fallbackItem,
  hasSafeFallbackPlacement,
  modelSelectorOptions,
  primaryRoute,
  allValuesByKey,
  isSaving,
  setDraftValue,
  resolveConfiguredModelRef,
}) => {
  const { language: uiLanguage } = useUiLanguage();
  const settingsText = SETTINGS_PAGE_TEXT[uiLanguage];

  return (
    <SettingsSectionCard
      title={settingsText.fallbackTitle}
      description={settingsText.fallbackDescription}
    >
      {hasSafeFallbackPlacement ? (
        <ModelFallbackEditor
          value={fallbackValue}
          onChange={(next) => setDraftValue('LITELLM_FALLBACK_MODELS', next)}
          options={modelSelectorOptions}
          primaryRoute={primaryRoute}
          resolveConfiguredModelRef={resolveConfiguredModelRef}
          language={uiLanguage}
          disabled={isSaving || !isFieldEnabledByContract(fallbackItem?.schema?.contract, allValuesByKey)}
        />
      ) : null}
      {fallbackIssues.map((issue) => (
        <p key={`${issue.key}-${issue.code}`} className="mt-1 text-xs text-danger">{issue.message}</p>
      ))}
    </SettingsSectionCard>
  );
};

export type AiModelAccessSectionProps = {
  rawActiveItems: SystemConfigItem[];
  providerCatalog: LlmProviderCatalogEntry[];
  providerConnectionFields: LlmConnectionFieldSchema[];
  isProviderCatalogLoading: boolean;
  providerCatalogError: unknown;
  providerEmptyApiKeyHosts: string[];
  providerConnectionSchemaUnavailable: boolean;
  providerConnectionSchemaAllowsInspection: boolean;
  hasUnsafeModelAccessSchema: boolean;
  availableModels: AvailableModelEntry[];
  maskToken: string;
  configVersion: string;
  llmChannelDraftItems: SystemConfigUpdateItem[];
  llmChannelResetSignal: number;
  llmChannelAddSignal: number;
  llmFocusFieldRequest: ModelAccessFieldFocusRequest | null;
  channelsOverriddenByMode: 'legacy' | 'yaml' | null;
  isSaving: boolean;
  isLoading: boolean;
  taskModelRefs: Array<{ key: string; label: string; route: string }>;
  showReturnToTaskRouting: boolean;
  onDraftItemsChange: (items: Array<{ key: string; value: string }>) => void;
  onValidityChange: (valid: boolean) => void;
  onAddConnection: () => void;
  onReloadCatalog: () => void;
  onViewDiagnostics: () => void;
  onManageModels: () => void;
  onReplaceModelReferences: (replacements: ModelReferenceReplacement[]) => void;
  onReturnToTaskRouting: () => void;
};

const AiModelAccessSection: React.FC<AiModelAccessSectionProps> = ({
  rawActiveItems,
  providerCatalog,
  providerConnectionFields,
  isProviderCatalogLoading,
  providerCatalogError,
  providerEmptyApiKeyHosts,
  providerConnectionSchemaUnavailable,
  providerConnectionSchemaAllowsInspection,
  hasUnsafeModelAccessSchema,
  availableModels,
  maskToken,
  configVersion,
  llmChannelDraftItems,
  llmChannelResetSignal,
  llmChannelAddSignal,
  llmFocusFieldRequest,
  channelsOverriddenByMode,
  isSaving,
  isLoading,
  taskModelRefs,
  showReturnToTaskRouting,
  onDraftItemsChange,
  onValidityChange,
  onAddConnection,
  onReloadCatalog,
  onViewDiagnostics,
  onManageModels,
  onReplaceModelReferences,
  onReturnToTaskRouting,
}) => {
  const { language: uiLanguage } = useUiLanguage();
  const settingsText = SETTINGS_PAGE_TEXT[uiLanguage];

  return (
    <section className="space-y-4" aria-labelledby="model-access-heading" data-testid="model-access-section">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0 space-y-1">
          <h2 id="model-access-heading" className="text-base font-semibold text-foreground">
            {settingsText.modelAccess}
          </h2>
          <p className="text-sm leading-6 text-muted-text">
            {settingsText.modelAccessDescription}
          </p>
        </div>
        <div className="flex shrink-0 flex-wrap items-center gap-2">
          {showReturnToTaskRouting ? (
            <Button type="button" variant="secondary" onClick={onReturnToTaskRouting}>
              {settingsText.returnTaskRouting}
            </Button>
          ) : null}
          <Button
            type="button"
            variant="primary"
            disabled={isSaving || isLoading || isProviderCatalogLoading || Boolean(providerCatalogError) || providerConnectionSchemaUnavailable || Boolean(channelsOverriddenByMode) || hasUnsafeModelAccessSchema}
            onClick={onAddConnection}
          >
            {settingsText.addModelService}
          </Button>
        </div>
      </div>
      <LLMChannelEditor
        key={`llm-connections-${configVersion}`}
        items={rawActiveItems}
        providers={providerCatalog}
        connectionFields={providerConnectionFields}
        catalogLoading={isProviderCatalogLoading}
        emptyApiKeyHosts={providerEmptyApiKeyHosts}
        availableModels={availableModels}
        availableModelRoutes={availableModels.map((model) => model.route)}
        maskToken={maskToken}
        persistedDraftItems={llmChannelDraftItems}
        onDraftItemsChange={onDraftItemsChange}
        onValidityChange={onValidityChange}
        resetSignal={llmChannelResetSignal}
        addSignal={llmChannelAddSignal}
        focusFieldRequest={llmFocusFieldRequest}
        disabled={isSaving || isLoading || isProviderCatalogLoading || Boolean(providerCatalogError) || (providerConnectionSchemaUnavailable && !providerConnectionSchemaAllowsInspection) || hasUnsafeModelAccessSchema}
        catalogUnavailable={Boolean(providerCatalogError)}
        onReloadCatalog={onReloadCatalog}
        overriddenByMode={channelsOverriddenByMode}
        onViewDiagnostics={onViewDiagnostics}
        taskModelRefs={taskModelRefs}
        onManageModels={onManageModels}
        onReplaceModelReferences={onReplaceModelReferences}
      />
    </section>
  );
};

export { AiOverviewCard, AiTaskRoutingCard, AiReliabilityCard, AiModelAccessSection };
