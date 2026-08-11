/* eslint-disable react-refresh/only-export-components -- Scenario modules intentionally export renderer registries. */
import { lazy, useState, type ReactNode } from 'react';
import { Button } from '../../components/common';
import { AuthSettingsCard } from '../../components/settings/AuthSettingsCard';
import { ChangePasswordCard } from '../../components/settings/ChangePasswordCard';
import { DataProvidersPanel } from '../../components/settings/DataProvidersPanel';
import { FirstRunWizard } from '../../components/settings/FirstRunWizard';
import { GenerationBackendStatusPanel } from '../../components/settings/GenerationBackendStatusPanel';
import { KronosSettingsFields } from '../../components/settings/KronosSettingsFields';
import { KronosStatusPanel } from '../../components/settings/KronosStatusPanel';
import { LocalModelsWithKronos } from '../../components/settings/LocalModelsWithKronos';
import { IntelligentImport } from '../../components/settings/IntelligentImport';
import { IntelligenceSourcesPanel } from '../../components/settings/IntelligenceSourcesPanel';
import { InvestmentFrameworkPromptPreview } from '../../components/settings/InvestmentFrameworkPromptPreview';
import { InvestmentFrameworkSettingsCard } from '../../components/settings/InvestmentFrameworkSettingsCard';
import { emptyInvestmentFrameworkContent } from '../../components/settings/investmentFrameworkEditorModel';
import { LLMChannelEditor } from '../../components/settings/LLMChannelEditor';
import { SettingsOnboardingHosts } from '../../components/onboarding/SettingsOnboardingHosts';
import type { SetupStatusResponse } from '../../types/systemConfig';
import { LLMConfigModeBanner } from '../../components/settings/LLMConfigModeBanner';
import { LocalModelsPanel } from '../../components/settings/LocalModelsPanel';
import { ModelFallbackEditor } from '../../components/settings/ModelFallbackEditor';
import { ModelMultiSelect } from '../../components/settings/ModelMultiSelect';
import { MultiSelectDropdown } from '../../components/settings/MultiSelectDropdown';
import { NotificationChannelsPanel } from '../../components/settings/NotificationChannelsPanel';
import { NotificationTestPanel } from '../../components/settings/NotificationTestPanel';
import { buildNotificationEventRoutes } from '../../components/settings/notificationEventRoutes';
import { ProviderQuickLinks } from '../../components/settings/ProviderQuickLinks';
import { SettingsAlert } from '../../components/settings/SettingsAlert';
import { SettingsConfigurationSummary, SystemConfigSummary } from '../../components/settings/SettingsConfigurationSummary';
import { SettingsErrorSummary } from '../../components/settings/SettingsErrorSummary';
import { SettingsField } from '../../components/settings/SettingsField';
import { SettingsHelpButton } from '../../components/settings/SettingsHelpButton';
import { SettingsLoading } from '../../components/settings/SettingsLoading';
import { SettingsSectionNav, SettingsViewTabs } from '../../components/settings/SettingsNavigation';
import { SettingsPanelErrorBoundary } from '../../components/settings/SettingsPanelErrorBoundary';
import { SettingsSectionCard } from '../../components/settings/SettingsSectionCard';
import type { SettingsSectionId } from '../../components/settings/settingsInformationArchitecture';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { PLAYGROUND_TEXT } from '../../locales/playground';
import type {
  AvailableModelEntry,
  ConfigValidationIssue,
  LlmConnectionFieldSchema,
  LLMConfigModeStatus,
  SystemConfigItem,
} from '../../types/systemConfig';
import {
  fixtureProviders,
  fixtureSystemConfigItems,
} from '../fixtures';
import { usePlaygroundScenario } from '../scenarioContext';
import type { PlaygroundScenarioRenderer } from '../types';

const MASK_TOKEN = '******';
const MODEL_REF = 'modelref:v1:fixture:fixture%2Ffixture-route';

const useStoryText = () => {
  const { language } = useUiLanguage();
  return { language, text: PLAYGROUND_TEXT[language].samples };
};

const makeConfigItem = (
  key: string,
  value: string,
  category: SystemConfigItem['schema'] extends infer Schema
    ? Schema extends { category: infer Category } ? Category : never
    : never,
  uiControl: NonNullable<SystemConfigItem['schema']>['uiControl'] = 'text',
  sensitive = false,
): SystemConfigItem => ({
  key,
  value,
  rawValueExists: value.length > 0,
  isMasked: sensitive && value.length > 0,
  schema: {
    key,
    category,
    dataType: 'string',
    uiControl,
    isSensitive: sensitive,
    isRequired: false,
    isEditable: true,
    options: [],
    validation: {},
    displayOrder: 10,
  },
});

const DATA_PROVIDER_ITEMS: SystemConfigItem[] = [
  makeConfigItem('TUSHARE_TOKEN', MASK_TOKEN, 'data_source', 'password', true),
  makeConfigItem('TAVILY_API_KEYS', MASK_TOKEN, 'data_source', 'password', true),
];

const NOTIFICATION_ITEMS: SystemConfigItem[] = [
  makeConfigItem('EMAIL_SENDER', 'fixture@example.invalid', 'notification'),
  makeConfigItem('EMAIL_PASSWORD', MASK_TOKEN, 'notification', 'password', true),
  makeConfigItem('EMAIL_RECEIVERS', 'preview@example.invalid', 'notification'),
  makeConfigItem('CUSTOM_WEBHOOK_URL', 'https://example.invalid/webhook', 'notification'),
];

const CONNECTION_FIELDS: LlmConnectionFieldSchema[] = [
  { key: 'connection_name', dataType: 'string', isSensitive: false, isRequired: true, contract: { requirement: 'required' } },
  { key: 'display_name', dataType: 'string', isSensitive: false, isRequired: false, contract: { requirement: 'optional' } },
  { key: 'provider_id', dataType: 'string', isSensitive: false, isRequired: true, contract: { requirement: 'required' } },
  { key: 'protocol', dataType: 'string', isSensitive: false, isRequired: true, contract: { requirement: 'required' } },
  { key: 'base_url', dataType: 'string', isSensitive: false, isRequired: false, contract: { requirement: 'optional' } },
  { key: 'api_key', dataType: 'string', isSensitive: true, isRequired: true, contract: { requirement: 'required' } },
  { key: 'models', dataType: 'array', isSensitive: false, isRequired: true, contract: { requirement: 'required' } },
  { key: 'enabled', dataType: 'boolean', isSensitive: false, isRequired: true, contract: { requirement: 'required' } },
];

const CHANNEL_ITEMS = [
  { key: 'LLM_CHANNELS', value: 'fixture' },
  { key: 'LLM_FIXTURE_DISPLAY_NAME', value: 'Fixture Cloud' },
  { key: 'LLM_FIXTURE_PROVIDER', value: 'fixture-cloud' },
  { key: 'LLM_FIXTURE_PROTOCOL', value: 'openai' },
  { key: 'LLM_FIXTURE_BASE_URL', value: 'https://api.example.invalid/v1' },
  { key: 'LLM_FIXTURE_ENABLED', value: 'true' },
  { key: 'LLM_FIXTURE_API_KEY', value: MASK_TOKEN, rawValueExists: true },
  { key: 'LLM_FIXTURE_MODELS', value: 'fixture-route' },
  { key: 'LITELLM_MODEL', value: MODEL_REF },
];

const AVAILABLE_MODELS: AvailableModelEntry[] = [{
  modelRef: MODEL_REF,
  route: 'fixture/fixture-route',
  display: 'Fixture Route',
  connection: 'fixture',
  connectionId: 'fixture',
  connectionName: 'Fixture Cloud',
  provider: 'openai',
  providerId: 'fixture-cloud',
  providerLabel: 'Fixture Cloud',
  available: true,
}];

const agentSettingsScenarios = () => import('./agentBehaviorPanelScenario');
const LazyAgentSettingsStory = lazy(agentSettingsScenarios);
const AiOverviewMatrixStory = () => <LazyAgentSettingsStory story="overview" />;
const SettingsAgentOnboardingHostStory = () => <LazyAgentSettingsStory story="onboarding" />;
const SettingsModeToggleStory = () => <LazyAgentSettingsStory story="mode" />;
const AgentBehaviorPanelStory = () => <LazyAgentSettingsStory story="presets" />;

const DataProvidersPanelStory = () => {
  const { scenario } = usePlaygroundScenario();
  const [items, setItems] = useState(scenario === 'empty' ? [] : DATA_PROVIDER_ITEMS);
  return (
    <DataProvidersPanel
      items={items}
      disabled={false}
      issueByKey={{}}
      onChange={(key, value) => setItems((current) => current.map((item) => item.key === key ? { ...item, value } : item))}
    />
  );
};

const FirstRunWizardStory = () => {
  const { language, text } = useStoryText();
  const { scenario } = usePlaygroundScenario();
  return (
    <FirstRunWizard
      language={language}
      providers={scenario === 'error' ? [] : fixtureProviders}
      connectionFields={CONNECTION_FIELDS}
      existingChannelNames={[]}
      isSaving={false}
      onClose={() => undefined}
      onComplete={async () => scenario === 'error' ? { success: false, error: text.error } : { success: true }}
    />
  );
};

const GenerationBackendStatusPanelStory = () => {
  const { scenario } = usePlaygroundScenario();
  return (
    <GenerationBackendStatusPanel
      items={scenario === 'loading' ? [{ key: 'GENERATION_BACKEND', value: 'litellm' }] : []}
      maskToken={MASK_TOKEN}
    />
  );
};

const KronosStatusPanelStory = () => <KronosStatusPanel />;

const KronosSettingsFieldsStory = () => (
  <KronosSettingsFields
    items={[]}
    allValuesByKey={{}}
    issueByKey={{}}
    onChange={() => undefined}
  />
);

const LocalModelsWithKronosStory = () => (
  <LocalModelsWithKronos
    language="en"
    kronosItems={[]}
    allValuesByKey={{}}
    issueByKey={{}}
    onKronosChange={() => undefined}
  />
);

const IntelligentImportStory = () => {
  const [value, setValue] = useState('600519,AAPL');
  return <IntelligentImport stockListValue={value} configVersion="fixture-v1" maskToken={MASK_TOKEN} onMerged={setValue} />;
};

const LLMChannelEditorStory = () => {
  const { scenario } = usePlaygroundScenario();
  return (
    <LLMChannelEditor
      items={scenario === 'empty' ? [] : CHANNEL_ITEMS}
      providers={scenario === 'error' ? [] : fixtureProviders}
      connectionFields={CONNECTION_FIELDS}
      availableModelRoutes={AVAILABLE_MODELS.map((item) => item.route)}
      availableModels={AVAILABLE_MODELS}
      maskToken={MASK_TOKEN}
      catalogUnavailable={scenario === 'error'}
      onReloadCatalog={() => undefined}
      onDraftItemsChange={() => undefined}
      onValidityChange={() => undefined}
      onManageModels={() => undefined}
    />
  );
};

const LLMConfigModeBannerStory = () => {
  const { scenario } = usePlaygroundScenario();
  const { text } = useStoryText();
  const status: LLMConfigModeStatus = {
    requestedMode: 'auto',
    effectiveMode: scenario === 'error' ? null : 'legacy',
    detectedSources: scenario === 'loading' ? [] : ['legacy'],
    overriddenSources: [],
    issues: scenario === 'error' ? [{ key: 'LLM_CONFIG_MODE', code: 'fixture', severity: 'error', message: text.error }] : [],
  };
  return <LLMConfigModeBanner status={status} configVersion="fixture-v1" onMigrated={() => undefined} />;
};

const LocalModelsPanelStory = () => {
  const { language } = useStoryText();
  return <LocalModelsPanel language={language} />;
};

const ModelFallbackEditorStory = () => {
  const { language } = useStoryText();
  const { scenario } = usePlaygroundScenario();
  const [value, setValue] = useState(scenario === 'empty' ? '' : 'fixture/fixture-route-fast');
  return (
    <ModelFallbackEditor
      value={value}
      onChange={setValue}
      language={language}
      primaryRoute={MODEL_REF}
      options={[
        { value: MODEL_REF, label: 'Fixture Route', group: 'Fixture Cloud' },
        { value: 'fixture/fixture-route-fast', label: 'Fixture Route Fast', group: 'Fixture Cloud' },
      ]}
    />
  );
};

const ModelMultiSelectStory = () => {
  const { language, text } = useStoryText();
  const { scenario } = usePlaygroundScenario();
  const [selected, setSelected] = useState<Set<string>>(new Set(scenario === 'empty' ? [] : ['fixture-route']));
  const options = scenario === 'empty' ? [] : ['fixture-route', 'fixture-route-fast', 'fixture-route-vision'];
  return (
    <ModelMultiSelect
      options={options}
      isSelected={(model) => selected.has(model)}
      onToggle={(model) => setSelected((current) => {
        const next = new Set(current);
        if (next.has(model)) next.delete(model); else next.add(model);
        return next;
      })}
      language={language}
      ariaLabel={text.details}
    />
  );
};

const MultiSelectDropdownStory = () => {
  const { language, text } = useStoryText();
  const { scenario } = usePlaygroundScenario();
  const [selected, setSelected] = useState(['one']);
  return (
    <MultiSelectDropdown
      options={[
        { value: 'one', label: text.optionOne },
        { value: 'two', label: text.optionTwo },
        { value: 'three', label: text.optionThree },
      ]}
      selected={selected}
      onChange={setSelected}
      disabled={scenario === 'states'}
      hasError={scenario === 'states'}
      language={language}
      ariaLabel={text.details}
    />
  );
};

const NotificationChannelsPanelStory = () => {
  const { scenario } = usePlaygroundScenario();
  const [items, setItems] = useState(scenario === 'empty' ? [] : NOTIFICATION_ITEMS);
  return (
    <NotificationChannelsPanel
      items={items}
      configuredChannels={scenario === 'empty' ? [] : ['email', 'custom']}
      disabled={false}
      issueByKey={{}}
      onChange={(key, value) => setItems((current) => current.map((item) => item.key === key ? { ...item, value } : item))}
      eventRoutes={buildNotificationEventRoutes(scenario === 'empty' ? {} : {
        NOTIFICATION_REPORT_CHANNELS: 'email,custom',
        NOTIFICATION_ALERT_CHANNELS: 'email',
        NOTIFICATION_SYSTEM_ERROR_CHANNELS: '',
      }, scenario === 'empty' ? [] : ['email', 'custom'])}
      maskToken={MASK_TOKEN}
    />
  );
};

const NotificationTestPanelStory = () => (
  <NotificationTestPanel items={NOTIFICATION_ITEMS.map(({ key, value }) => ({ key, value }))} maskToken={MASK_TOKEN} />
);

const ProviderQuickLinksStory = () => {
  const { language, text } = useStoryText();
  const provider = {
    ...fixtureProviders[0],
    credentialUrl: 'https://example.invalid/credentials',
    consoleUrl: 'https://example.invalid/console',
    modelsUrl: 'https://example.invalid/models',
    docsUrl: 'https://example.invalid/docs',
  };
  return (
    <ProviderQuickLinks
      provider={provider}
      context="credentials"
      language={language}
      primaryLabel={text.primaryAction}
      secondaryLabel={text.secondaryAction}
    />
  );
};

const SettingsAlertStory = () => {
  const { text } = useStoryText();
  return (
    <div className="space-y-3">
      {(['success', 'warning', 'error'] as const).map((variant) => (
        <SettingsAlert
          key={variant}
          variant={variant}
          title={text[variant]}
          message={text.preview}
          actionLabel={text.retry}
          onAction={() => undefined}
        />
      ))}
    </div>
  );
};

const SettingsErrorSummaryStory = () => {
  const { language, text } = useStoryText();
  const { scenario } = usePlaygroundScenario();
  return (
    <SettingsErrorSummary
      language={language}
      entries={scenario === 'empty' ? [] : [{
        key: 'TUSHARE_TOKEN',
        label: text.fieldLabel,
        message: text.fieldError,
        section: 'data_sources',
        view: 'providers',
      }]}
      onJump={() => undefined}
    />
  );
};

const SettingsFieldStory = () => {
  const { scenario } = usePlaygroundScenario();
  const item = fixtureSystemConfigItems[2];
  const [value, setValue] = useState(item.value);
  const issues: ConfigValidationIssue[] = scenario === 'states'
    ? [{ key: item.key, code: 'fixture', message: 'playground_fixture_error', severity: 'error' }]
    : [];
  return (
    <div className="max-w-xl">
      <SettingsField item={item} value={value} onChange={(_, next) => setValue(next)} issues={issues} disabled={scenario === 'states'} />
    </div>
  );
};

const SettingsHelpButtonStory = () => {
  const { text } = useStoryText();
  return (
    <div className="flex min-h-32 items-start justify-center rounded-lg border border-border bg-card p-4">
      <SettingsHelpButton
        fieldKey="PLAYGROUND_FIELD"
        title={text.fieldLabel}
        description={text.fieldHint}
      />
    </div>
  );
};

const SettingsSectionNavStory = () => {
  const { language, text } = useStoryText();
  const { scenario } = usePlaygroundScenario();
  const [section, setSection] = useState<SettingsSectionId>('overview');
  return (
    <div className="max-w-xs">
      <SettingsSectionNav
        activeSection={section}
        onSelectSection={setSection}
        language={language}
        navLabel={text.navigation}
        sectionStatus={scenario === 'states' ? { ai_models: { hasError: true }, notifications: { isDirty: true } } : undefined}
      />
    </div>
  );
};

const SettingsViewTabsStory = () => {
  const { language, text } = useStoryText();
  const [view, setView] = useState('connections');
  return <SettingsViewTabs section="ai_models" activeView={view} onSelectView={setView} language={language} tabsLabel={text.tabs} />;
};

const ThrowingContent = ({ message }: { message: string }): ReactNode => {
  throw new Error(message);
};

const SettingsPanelErrorBoundaryStory = () => {
  const { text } = useStoryText();
  const { scenario } = usePlaygroundScenario();
  return (
    <SettingsPanelErrorBoundary title={text.panelTitle} resetKey={scenario}>
      {scenario === 'error' ? <ThrowingContent message={text.error} /> : <p className="text-sm text-secondary-text">{text.preview}</p>}
    </SettingsPanelErrorBoundary>
  );
};

const SettingsSectionCardStory = () => {
  const { text } = useStoryText();
  return (
    <SettingsSectionCard
      title={text.panelTitle}
      description={text.fieldHint}
      actions={<Button variant="secondary">{text.secondaryAction}</Button>}
      contentBordered
    >
      <p className="text-sm text-secondary-text">{text.preview}</p>
    </SettingsSectionCard>
  );
};

const SettingsConfigurationSummaryStory = () => {
  const { text } = useStoryText();
  return (
    <SettingsConfigurationSummary
      ariaLabel={text.details}
      entries={[
        { id: 'first', label: text.optionOne, value: text.optionTwo },
        { id: 'second', label: text.optionTwo, value: text.preview },
      ]}
    />
  );
};

const SystemConfigSummaryStory = () => (
  <SystemConfigSummary items={NOTIFICATION_ITEMS} maskToken={MASK_TOKEN} />
);

const FIXTURE_SETUP_STATUS: SetupStatusResponse = {
  isComplete: false,
  readyForSmoke: false,
  requiredMissingKeys: ['LITELLM_MODEL'],
  nextStepKey: 'llm_primary',
  checks: [
    {
      key: 'llm_primary',
      title: 'Primary model',
      category: 'ai_model',
      required: true,
      status: 'needs_action',
      message: 'Primary model is not configured.',
      nextStep: 'Configure a primary model in Settings.',
    },
    {
      key: 'auth',
      title: 'Authentication',
      category: 'system',
      required: false,
      status: 'optional',
      message: 'Password login is optional for local use.',
    },
  ],
};

const InvestmentFrameworkPromptPreviewStory = () => {
  const { scenario } = usePlaygroundScenario();
  const { text } = useStoryText();
  const content = scenario === 'empty'
    ? emptyInvestmentFrameworkContent()
    : {
      ...emptyInvestmentFrameworkContent(),
      title: 'Quality first',
      freeFormRules: 'Prefer durable cash flow',
      riskRules: ['Cap single-name size at 10%'],
      trackingCriteria: ['Review earnings revisions'],
    };
  return (
    <InvestmentFrameworkPromptPreview
      content={content}
      frameworkId={scenario === 'empty' ? null : 1}
      frameworkVersion={scenario === 'empty' ? null : 2}
      draft
      reportLanguage="en"
      title={text.panelTitle}
      description={text.fieldHint}
      emptyLabel={text.preview}
    />
  );
};

const SettingsOnboardingHostsStory = () => {
  const { language, text } = useStoryText();
  const { t } = useUiLanguage();
  const [isWizardOpen, setIsWizardOpen] = useState(false);
  const [isAgentOnboardingOpen, setIsAgentOnboardingOpen] = useState(true);
  return (
    <div className="space-y-3">
      <Button variant="secondary" onClick={() => setIsWizardOpen(true)}>{text.openFirstRunWizard}</Button>
      <Button variant="primary" onClick={() => setIsAgentOnboardingOpen(true)}>{text.openAgentOnboarding}</Button>
      <SettingsOnboardingHosts
        isWizardOpen={isWizardOpen}
        isAgentOnboardingOpen={isAgentOnboardingOpen}
        setIsWizardOpen={setIsWizardOpen}
        setIsAgentOnboardingOpen={setIsAgentOnboardingOpen}
        handleWizardComplete={async () => ({ success: true })}
        isSaving={false}
        uiLanguage={language}
        existingChannelNames={[]}
        providerCatalog={fixtureProviders}
        providerConnectionFields={CONNECTION_FIELDS}
        modelSelectorOptions={[{ value: MODEL_REF, label: 'Fixture Route' }]}
        initialFallbackModels=""
        initialVisionModel=""
        onViewRouting={() => undefined}
        onLocalModelConfigurationChanged={() => undefined}
        onAgentApplied={() => setIsAgentOnboardingOpen(false)}
        setupStatus={FIXTURE_SETUP_STATUS}
        t={t}
      />
      <p className="text-xs text-muted-text">{text.preview}</p>
    </div>
  );
};

export const SETTINGS_SCENARIOS: Record<string, PlaygroundScenarioRenderer> = {
  'agent-behavior-panel': AgentBehaviorPanelStory,
  'ai-overview-matrix': AiOverviewMatrixStory,
  'auth-settings-card': AuthSettingsCard,
  'change-password-card': ChangePasswordCard,
  'data-providers-panel': DataProvidersPanelStory,
  'first-run-wizard': FirstRunWizardStory,
  'generation-backend-status-panel': GenerationBackendStatusPanelStory,
  'kronos-status-panel': KronosStatusPanelStory,
  'kronos-settings-fields': KronosSettingsFieldsStory,
  'local-models-with-kronos': LocalModelsWithKronosStory,
  'intelligent-import': IntelligentImportStory,
  'investment-framework-settings-card': InvestmentFrameworkSettingsCard,
  'investment-framework-prompt-preview': InvestmentFrameworkPromptPreviewStory,
  'settings-mode-toggle': SettingsModeToggleStory,
  'settings-agent-onboarding-host': SettingsAgentOnboardingHostStory,
  'settings-onboarding-hosts': SettingsOnboardingHostsStory,
  'intelligence-sources-panel': IntelligenceSourcesPanel,
  'llm-channel-editor': LLMChannelEditorStory,
  'llm-config-mode-banner': LLMConfigModeBannerStory,
  'local-models-panel': LocalModelsPanelStory,
  'model-fallback-editor': ModelFallbackEditorStory,
  'model-multi-select': ModelMultiSelectStory,
  'multi-select-dropdown': MultiSelectDropdownStory,
  'notification-channels-panel': NotificationChannelsPanelStory,
  'notification-test-panel': NotificationTestPanelStory,
  'provider-quick-links': ProviderQuickLinksStory,
  'settings-alert': SettingsAlertStory,
  'settings-configuration-summary': SettingsConfigurationSummaryStory,
  'settings-error-summary': SettingsErrorSummaryStory,
  'settings-field': SettingsFieldStory,
  'settings-help-button': SettingsHelpButtonStory,
  'settings-loading': SettingsLoading,
  'settings-section-nav': SettingsSectionNavStory,
  'settings-view-tabs': SettingsViewTabsStory,
  'settings-panel-error-boundary': SettingsPanelErrorBoundaryStory,
  'settings-section-card': SettingsSectionCardStory,
  'system-config-summary': SystemConfigSummaryStory,
};
