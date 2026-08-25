// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type React from 'react';
import { Button, type SearchableSelectOption } from '../../common';
import {
  LocalModelsWithKronos,
  LLMChannelEditor,
  type ModelReferenceReplacement,
} from '..';
import {
  AiOverviewCard,
  AiTaskRoutingCard,
  AiReliabilityCard,
} from '../AiModelsViewCards';
import { SETTINGS_ROUTE_QUERY_KEYS } from '../../../routing/routes';
import type { ModelAccessFieldFocusRequest } from '../../../utils/modelAccessFieldKey';
import type { UiLanguage } from '../../../i18n/uiText';
import { SETTINGS_PAGE_TEXT } from '../../../locales/settingsPage';
import type { SettingsSectionId } from '../settingsInformationArchitecture';
import type {
  AvailableModelEntry,
  ConfigValidationIssue,
  LlmConnectionFieldSchema,
  LlmProviderCatalogEntry,
  SystemConfigItem,
  SystemConfigUpdateItem,
} from '../../../types/systemConfig';
import { LOCAL_MODEL_CONFIG_KEYS } from './settingsPageConstants';

type AiModelsSectionProps = {
  isAiOverview: boolean;
  isAiLocalModels: boolean;
  isAiTaskRouting: boolean;
  isAiReliability: boolean;
  isTopLevelAdvanced: boolean;
  activeCategory: string;
  allValuesByKey: Record<string, string>;
  availableModelRefSet: Set<string>;
  availableModelsError: unknown;
  availableModelsLoading: boolean;
  formatConfiguredModel: (value: string) => string;
  selectSectionView: (section: SettingsSectionId, view: string) => void;
  reloadAvailableModels: () => void;
  uiLanguage: UiLanguage;
  refreshAfterExternalSave: (keys: string[]) => Promise<void>;
  applyPostSaveEffects: () => void;
  aiModelItems: SystemConfigItem[];
  issueByKey: Record<string, ConfigValidationIssue[]>;
  isSaving: boolean;
  isLoading: boolean;
  setDraftValue: (key: string, value: string) => void;
  readOnlyDiagnosticForItem: (item: SystemConfigItem, categoryHint?: string) => string | undefined;
  taskRoutingItems: SystemConfigItem[];
  modelSelectorOptions: SearchableSelectOption[];
  availableModels: AvailableModelEntry[];
  configuredTaskRoutes: Array<{ key: string; value: string }>;
  hasSafeFallbackPlacement: boolean;
  resolveConfiguredModelRef: (value: string) => string;
  goToModelAccessFromTaskRouting: () => void;
  fallbackRoutingItem: SystemConfigItem | undefined;
  sourceQuery: string | null;
  returnToTaskRouting: () => void;
  isProviderCatalogLoading: boolean;
  providerCatalogError: unknown;
  providerConnectionSchemaUnavailable: boolean;
  channelsOverriddenByMode: 'yaml' | 'legacy' | null;
  hasUnsafeModelAccessSchema: boolean;
  setLlmChannelAddSignal: React.Dispatch<React.SetStateAction<number>>;
  configVersion: string;
  rawActiveItems: SystemConfigItem[];
  providerCatalog: LlmProviderCatalogEntry[];
  providerConnectionFields: LlmConnectionFieldSchema[] | undefined;
  providerEmptyApiKeyHosts: string[];
  maskToken: string;
  llmChannelDraftItems: SystemConfigUpdateItem[];
  handleLlmChannelDraftItemsChange: (items: Array<{ key: string; value: string }>) => void;
  handleLlmChannelValidityChange: (valid: boolean) => void;
  llmChannelResetSignal: number;
  llmChannelAddSignal: number;
  llmFocusFieldRequest: ModelAccessFieldFocusRequest | null;
  providerConnectionSchemaAllowsInspection: boolean;
  reloadProviderCatalog: () => void;
  taskModelRefs: Array<{ key: string; label: string; route: string }>;
  replaceModelReferences: (replacements: ModelReferenceReplacement[]) => void;
};

const AiModelsSection: React.FC<AiModelsSectionProps> = (props) => {
  const settingsText = SETTINGS_PAGE_TEXT[props.uiLanguage];

  return (
    <>
      {props.isAiOverview ? (
        <AiOverviewCard
          allValuesByKey={props.allValuesByKey}
          availableRoutes={props.availableModelRefSet}
          availableModelsError={props.availableModelsError}
          availableModelsLoading={props.availableModelsLoading}
          formatModel={props.formatConfiguredModel}
          onEditRouting={() => props.selectSectionView('ai_models', 'task_routing')}
          onReloadModels={() => props.reloadAvailableModels()}
        />
      ) : null}
      {props.isAiLocalModels ? (
        <LocalModelsWithKronos
          language={props.uiLanguage}
          onConfigurationChanged={async () => {
            await props.refreshAfterExternalSave(LOCAL_MODEL_CONFIG_KEYS);
            props.applyPostSaveEffects();
          }}
          kronosItems={props.aiModelItems}
          allValuesByKey={props.allValuesByKey}
          issueByKey={props.issueByKey}
          disabled={props.isSaving || props.isLoading}
          onKronosChange={props.setDraftValue}
          readOnlyDiagnostic={(item) => props.readOnlyDiagnosticForItem(item, 'ai_model')}
        />
      ) : null}
      {props.isAiTaskRouting ? (
        <AiTaskRoutingCard
          taskRoutingItems={props.taskRoutingItems}
          fallbackModelsValue={props.allValuesByKey.LITELLM_FALLBACK_MODELS || ''}
          issueByKey={props.issueByKey}
          allValuesByKey={props.allValuesByKey}
          modelSelectorOptions={props.modelSelectorOptions}
          availableModels={props.availableModels}
          availableModelsError={props.availableModelsError}
          availableModelsLoading={props.availableModelsLoading}
          configuredTaskRoutes={props.configuredTaskRoutes}
          hasSafeFallbackPlacement={props.hasSafeFallbackPlacement}
          isSaving={props.isSaving}
          setDraftValue={props.setDraftValue}
          resolveConfiguredModelRef={props.resolveConfiguredModelRef}
          formatConfiguredModel={props.formatConfiguredModel}
          readOnlyDiagnosticForItem={props.readOnlyDiagnosticForItem}
          onGoToModelAccess={props.goToModelAccessFromTaskRouting}
          onEditReliability={() => props.selectSectionView('ai_models', 'reliability')}
          onReloadModels={() => props.reloadAvailableModels()}
        />
      ) : null}
      {props.isAiReliability ? (
        <AiReliabilityCard
          fallbackValue={props.allValuesByKey.LITELLM_FALLBACK_MODELS || ''}
          fallbackIssues={props.issueByKey.LITELLM_FALLBACK_MODELS || []}
          fallbackItem={props.fallbackRoutingItem}
          hasSafeFallbackPlacement={props.hasSafeFallbackPlacement}
          modelSelectorOptions={props.modelSelectorOptions}
          primaryRoute={props.resolveConfiguredModelRef(props.allValuesByKey.LITELLM_MODEL || '')}
          allValuesByKey={props.allValuesByKey}
          isSaving={props.isSaving}
          setDraftValue={props.setDraftValue}
          resolveConfiguredModelRef={props.resolveConfiguredModelRef}
        />
      ) : null}
      {props.activeCategory === 'ai_model' && !props.isAiOverview && !props.isAiLocalModels && !props.isAiTaskRouting && !props.isAiReliability && !props.isTopLevelAdvanced ? (
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
              {props.sourceQuery === 'task_routing' ? (
                <Button type="button" variant="secondary" onClick={props.returnToTaskRouting}>
                  {settingsText.returnTaskRouting}
                </Button>
              ) : null}
              <Button
                type="button"
                variant="primary"
                disabled={props.isSaving || props.isLoading || props.isProviderCatalogLoading || Boolean(props.providerCatalogError) || props.providerConnectionSchemaUnavailable || Boolean(props.channelsOverriddenByMode) || props.hasUnsafeModelAccessSchema}
                onClick={() => props.setLlmChannelAddSignal((signal) => signal + 1)}
              >
                {settingsText.addModelService}
              </Button>
            </div>
          </div>
          <LLMChannelEditor
            key={`llm-connections-${props.configVersion}`}
            items={props.rawActiveItems}
            providers={props.providerCatalog}
            connectionFields={props.providerConnectionFields}
            catalogLoading={props.isProviderCatalogLoading}
            emptyApiKeyHosts={props.providerEmptyApiKeyHosts}
            availableModels={props.availableModels}
            availableModelRoutes={props.availableModels.map((model) => model.route)}
            maskToken={props.maskToken}
            persistedDraftItems={props.llmChannelDraftItems}
            onDraftItemsChange={props.handleLlmChannelDraftItemsChange}
            onValidityChange={props.handleLlmChannelValidityChange}
            resetSignal={props.llmChannelResetSignal}
            addSignal={props.llmChannelAddSignal}
            focusFieldRequest={props.llmFocusFieldRequest}
            disabled={props.isSaving || props.isLoading || props.isProviderCatalogLoading || Boolean(props.providerCatalogError) || (props.providerConnectionSchemaUnavailable && !props.providerConnectionSchemaAllowsInspection) || props.hasUnsafeModelAccessSchema}
            catalogUnavailable={Boolean(props.providerCatalogError)}
            onReloadCatalog={() => props.reloadProviderCatalog()}
            overriddenByMode={props.channelsOverriddenByMode}
            onViewDiagnostics={() => props.selectSectionView('advanced', 'raw_config')}
            taskModelRefs={props.taskModelRefs}
            onManageModels={() => props.selectSectionView('ai_models', 'task_routing')}
            onReplaceModelReferences={props.replaceModelReferences}
          />
        </section>
      ) : null}
    </>
  );
};

export default AiModelsSection;
