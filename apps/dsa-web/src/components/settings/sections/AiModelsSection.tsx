// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
/* eslint-disable @typescript-eslint/no-explicit-any -- mechanical section props accept page model shapes */
import type React from 'react';
import type { UiLanguage } from '../../../i18n/uiLanguages';
import type { SearchableSelectOption } from '../../common';
import { Button } from '../../common';
import {
  LocalModelsWithKronos,
  LLMChannelEditor,
} from '..';
import {
  AiOverviewCard,
  AiTaskRoutingCard,
  AiReliabilityCard,
} from '../AiModelsViewCards';
import { SETTINGS_ROUTE_QUERY_KEYS } from '../../../routing/routes';
import { LOCAL_MODEL_CONFIG_KEYS } from './settingsPageConstants';
import type { SystemConfigItem } from '../../../types/systemConfig';
import type { ModelAccessFieldFocusRequest } from '../../../utils/modelAccessFieldKey';
import type { ModelReferenceReplacement } from '../llmChannelEditorModel';

export type AiModelsSectionProps = {
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
  selectSectionView: (...args: any[]) => void;
  reloadAvailableModels: () => void;
  language: UiLanguage;
  refreshAfterExternalSave: (keys: string[]) => Promise<void>;
  applyPostSaveEffects: () => void;
  itemsByCategory: Record<string, SystemConfigItem[]>;
  issueByKey: Record<string, any>;
  isSaving: boolean;
  isLoading: boolean;
  setDraftValue: (key: string, value: string) => void;
  readOnlyDiagnosticForItem: (item: SystemConfigItem, category?: string) => string | undefined;
  taskRoutingItems: SystemConfigItem[];
  modelSelectorOptions: SearchableSelectOption[];
  availableModels: any[];
  configuredTaskRoutes: Array<{ key: string; value: string }>;
  hasSafeFallbackPlacement: boolean;
  resolveConfiguredModelRef: (value: string) => string;
  goToModelAccessFromTaskRouting: () => void;
  fallbackRoutingItem?: SystemConfigItem;
  searchParams: URLSearchParams;
  settingsText: any;
  isProviderCatalogLoading: boolean;
  providerCatalogError: unknown;
  providerConnectionSchemaUnavailable: boolean;
  channelsOverriddenByMode: any;
  hasUnsafeModelAccessSchema: boolean;
  setLlmChannelAddSignal: React.Dispatch<React.SetStateAction<number>>;
  returnToTaskRouting: () => void;
  configVersion: string;
  rawActiveItems: SystemConfigItem[];
  providerCatalog: any[];
  providerConnectionFields: any;
  providerEmptyApiKeyHosts: string[];
  availableModelsList: any[];
  maskToken: string;
  llmChannelDraftItems: any[];
  handleLlmChannelDraftItemsChange: (items: any) => void;
  handleLlmChannelValidityChange: (valid: boolean) => void;
  llmChannelResetSignal: number;
  llmChannelAddSignal: number;
  llmFocusFieldRequest: ModelAccessFieldFocusRequest | null;
  providerConnectionSchemaAllowsInspection: boolean;
  reloadProviderCatalog: () => void;
  taskModelRefs: any[];
  replaceModelReferences: (replacements: ModelReferenceReplacement[]) => void;
};

export const AiModelsSection: React.FC<AiModelsSectionProps> = (p) => (
  <>
    {p.isAiOverview ? (
      <AiOverviewCard
        allValuesByKey={p.allValuesByKey}
        availableRoutes={p.availableModelRefSet}
        availableModelsError={p.availableModelsError}
        availableModelsLoading={p.availableModelsLoading}
        formatModel={p.formatConfiguredModel}
        onEditRouting={() => p.selectSectionView('ai_models', 'task_routing')}
        onReloadModels={() => p.reloadAvailableModels()}
      />
    ) : null}
    {p.isAiLocalModels ? (
      <LocalModelsWithKronos
        language={p.language}
        onConfigurationChanged={async () => {
          await p.refreshAfterExternalSave(LOCAL_MODEL_CONFIG_KEYS);
          p.applyPostSaveEffects();
        }}
        kronosItems={p.itemsByCategory.ai_model || []}
        allValuesByKey={p.allValuesByKey}
        issueByKey={p.issueByKey}
        disabled={p.isSaving || p.isLoading}
        onKronosChange={p.setDraftValue}
        readOnlyDiagnostic={(item) => p.readOnlyDiagnosticForItem(item, 'ai_model') as any}
      />
    ) : null}
    {p.isAiTaskRouting ? (
      <AiTaskRoutingCard
        taskRoutingItems={p.taskRoutingItems}
        fallbackModelsValue={p.allValuesByKey.LITELLM_FALLBACK_MODELS || ''}
        issueByKey={p.issueByKey}
        allValuesByKey={p.allValuesByKey}
        modelSelectorOptions={p.modelSelectorOptions}
        availableModels={p.availableModels}
        availableModelsError={p.availableModelsError}
        availableModelsLoading={p.availableModelsLoading}
        configuredTaskRoutes={p.configuredTaskRoutes}
        hasSafeFallbackPlacement={p.hasSafeFallbackPlacement}
        isSaving={p.isSaving}
        setDraftValue={p.setDraftValue}
        resolveConfiguredModelRef={p.resolveConfiguredModelRef}
        formatConfiguredModel={p.formatConfiguredModel}
        readOnlyDiagnosticForItem={p.readOnlyDiagnosticForItem as any}
        onGoToModelAccess={p.goToModelAccessFromTaskRouting}
        onEditReliability={() => p.selectSectionView('ai_models', 'reliability')}
        onReloadModels={() => p.reloadAvailableModels()}
      />
    ) : null}
    {p.isAiReliability ? (
      <AiReliabilityCard
        fallbackValue={p.allValuesByKey.LITELLM_FALLBACK_MODELS || ''}
        fallbackIssues={p.issueByKey.LITELLM_FALLBACK_MODELS || []}
        fallbackItem={p.fallbackRoutingItem}
        hasSafeFallbackPlacement={p.hasSafeFallbackPlacement}
        modelSelectorOptions={p.modelSelectorOptions}
        primaryRoute={p.resolveConfiguredModelRef(p.allValuesByKey.LITELLM_MODEL || '')}
        allValuesByKey={p.allValuesByKey}
        isSaving={p.isSaving}
        setDraftValue={p.setDraftValue}
        resolveConfiguredModelRef={p.resolveConfiguredModelRef}
      />
    ) : null}
    {p.activeCategory === 'ai_model' && !p.isAiOverview && !p.isAiLocalModels && !p.isAiTaskRouting && !p.isAiReliability && !p.isTopLevelAdvanced ? (
      <section className="space-y-4" aria-labelledby="model-access-heading" data-testid="model-access-section">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div className="min-w-0 space-y-1">
            <h2 id="model-access-heading" className="text-base font-semibold text-foreground">
              {p.settingsText.modelAccess}
            </h2>
            <p className="text-sm leading-6 text-muted-text">
              {p.settingsText.modelAccessDescription}
            </p>
          </div>
          <div className="flex shrink-0 flex-wrap items-center gap-2">
            {p.searchParams.get(SETTINGS_ROUTE_QUERY_KEYS.source) === 'task_routing' ? (
              <Button type="button" variant="secondary" onClick={p.returnToTaskRouting}>
                {p.settingsText.returnTaskRouting}
              </Button>
            ) : null}
            <Button
              type="button"
              variant="primary"
              disabled={p.isSaving || p.isLoading || p.isProviderCatalogLoading || Boolean(p.providerCatalogError) || p.providerConnectionSchemaUnavailable || Boolean(p.channelsOverriddenByMode) || p.hasUnsafeModelAccessSchema}
              onClick={() => p.setLlmChannelAddSignal((signal) => signal + 1)}
            >
              {p.settingsText.addModelService}
            </Button>
          </div>
        </div>
        <LLMChannelEditor
          key={`llm-connections-${p.configVersion}`}
          items={p.rawActiveItems}
          providers={p.providerCatalog}
          connectionFields={p.providerConnectionFields}
          catalogLoading={p.isProviderCatalogLoading}
          emptyApiKeyHosts={p.providerEmptyApiKeyHosts}
          availableModels={p.availableModels}
          availableModelRoutes={p.availableModels.map((model) => model.route)}
          maskToken={p.maskToken}
          persistedDraftItems={p.llmChannelDraftItems}
          onDraftItemsChange={p.handleLlmChannelDraftItemsChange}
          onValidityChange={p.handleLlmChannelValidityChange}
          resetSignal={p.llmChannelResetSignal}
          addSignal={p.llmChannelAddSignal}
          focusFieldRequest={p.llmFocusFieldRequest}
          disabled={p.isSaving || p.isLoading || p.isProviderCatalogLoading || Boolean(p.providerCatalogError) || (p.providerConnectionSchemaUnavailable && !p.providerConnectionSchemaAllowsInspection) || p.hasUnsafeModelAccessSchema}
          catalogUnavailable={Boolean(p.providerCatalogError)}
          onReloadCatalog={() => p.reloadProviderCatalog()}
          overriddenByMode={p.channelsOverriddenByMode as any}
          onViewDiagnostics={() => p.selectSectionView('advanced', 'raw_config')}
          taskModelRefs={p.taskModelRefs}
          onManageModels={() => p.selectSectionView('ai_models', 'task_routing')}
          onReplaceModelReferences={p.replaceModelReferences}
        />
      </section>
    ) : null}
  </>
);
