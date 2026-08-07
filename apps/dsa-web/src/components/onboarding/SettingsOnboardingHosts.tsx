// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type React from 'react';
import { useNavigate } from 'react-router-dom';
import {
  FirstRunWizard,
  type WizardCompleteResult,
  type WizardDraftItem,
} from '../settings';
import type { LlmConnectionFieldSchema, LlmProviderCatalogEntry, SetupStatusResponse } from '../../types/systemConfig';
import type { SearchableSelectOption } from '../common';
import type { UiLang } from '../settings/settingsInformationArchitecture';
import type { UiTextKey } from '../../i18n/uiText';
import { buildAnalysisWorkbenchHref } from '../../routing/routes';
import { SettingsAgentOnboardingHost } from './SettingsAgentOnboardingHost';

export type SettingsOnboardingHostsProps = {
  isWizardOpen: boolean;
  isAgentOnboardingOpen: boolean;
  setIsWizardOpen: (open: boolean) => void;
  setIsAgentOnboardingOpen: (open: boolean) => void;
  handleWizardComplete: (items: WizardDraftItem[]) => Promise<WizardCompleteResult>;
  isSaving: boolean;
  uiLanguage: UiLang;
  existingChannelNames: string[];
  providerCatalog: LlmProviderCatalogEntry[];
  providerConnectionFields?: LlmConnectionFieldSchema[];
  providerEmptyApiKeyHosts?: string[];
  modelSelectorOptions: SearchableSelectOption[];
  initialFallbackModels: string;
  initialVisionModel: string;
  onViewRouting: () => void;
  onLocalModelConfigurationChanged: () => void | Promise<void>;
  onAgentApplied: () => void;
  setupStatus: SetupStatusResponse | null;
  t: (key: UiTextKey, params?: Record<string, string | number>) => string;
};

/** First-run wizard + agent onboarding host extracted for Settings max-lines. */
export const SettingsOnboardingHosts: React.FC<SettingsOnboardingHostsProps> = ({
  isWizardOpen,
  isAgentOnboardingOpen,
  setIsWizardOpen,
  setIsAgentOnboardingOpen,
  handleWizardComplete,
  isSaving,
  uiLanguage,
  existingChannelNames,
  providerCatalog,
  providerConnectionFields,
  providerEmptyApiKeyHosts,
  modelSelectorOptions,
  initialFallbackModels,
  initialVisionModel,
  onViewRouting,
  onLocalModelConfigurationChanged,
  onAgentApplied,
  setupStatus,
  t,
}) => {
  const navigate = useNavigate();
  return (
    <>
      {isWizardOpen ? (
        <FirstRunWizard
          onComplete={handleWizardComplete}
          onClose={() => setIsWizardOpen(false)}
          isSaving={isSaving}
          language={uiLanguage}
          existingChannelNames={existingChannelNames}
          providers={providerCatalog}
          connectionFields={providerConnectionFields}
          emptyApiKeyHosts={providerEmptyApiKeyHosts}
          routingOptions={modelSelectorOptions}
          initialFallbackModels={initialFallbackModels}
          initialVisionModel={initialVisionModel}
          onViewRouting={onViewRouting}
          onLocalModelConfigurationChanged={onLocalModelConfigurationChanged}
          onStartFirstAnalysis={() => {
            setIsWizardOpen(false);
            navigate(buildAnalysisWorkbenchHref());
          }}
          onContinueAgentOnboarding={() => {
            setIsWizardOpen(false);
            setIsAgentOnboardingOpen(true);
          }}
        />
      ) : null}
      <SettingsAgentOnboardingHost
        open={isAgentOnboardingOpen}
        onClose={() => setIsAgentOnboardingOpen(false)}
        onApplied={onAgentApplied}
        setupStatus={setupStatus}
        reportLanguage={uiLanguage === 'zh' ? 'zh' : 'en'}
        t={t}
      />
    </>
  );
};

export default SettingsOnboardingHosts;
