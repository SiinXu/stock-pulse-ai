import type React from 'react';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useBlocker, useSearchParams } from 'react-router-dom';
import { CheckCircle2, CircleAlert, Clock, RefreshCw } from 'lucide-react';
import { useAuth, useBeginnerMode, useSystemConfig } from '../hooks';
import { useProviderCatalog } from '../hooks/useProviderCatalog';
import { useAvailableModels } from '../hooks/useAvailableModels';
import { useUiLanguage } from '../contexts/UiLanguageContext';
import {
  SETTINGS_ROUTE_QUERY_KEYS,
  SETTINGS_SECTION_IDS,
  SETTINGS_VIEW_IDS,
} from '../routing/routes';
import { getUiListSeparator } from '../utils/uiLocale';
import { createParsedApiError, getParsedApiError, type ParsedApiError } from '../api/error';
import { analysisApi } from '../api/analysis';
import { alphasiftApi, notifyAlphaSiftConfigChanged, notifySystemConfigChanged } from '../api/alphasift';
import { systemConfigApi } from '../api/systemConfig';
import { ApiErrorAlert, AppPage, Button, ConfirmDialog, Modal, PageHeader, Surface, ToastViewport, type SearchableSelectOption } from '../components/common';
import { SettingsModeToggle } from '../components/settings/SettingsModeToggle';
import {
  AuthSettingsCard,
  InvestmentFrameworkSettingsCard,
  ChangePasswordCard,
  GenerationBackendStatusPanel,
  IntelligentImport,
  LoadedExtensionsPanel, LocalModelsWithKronos,
  LLMChannelEditor,
  LLMConfigModeBanner,
  NotificationTestPanel,
  NOTIFICATION_FIELD_GROUP_ORDER,
  getNotificationFieldGroupId,
  getNotificationFieldOrder,
  getCategoryFieldGroupOrder,
  getCategoryFieldGroupId,
  getCategoryFieldOrder,
  getSubCategories,
  getSubCategoryOfKey,
  getSubCategoryFieldOrder,
  SettingsAlert,
  SettingsField,
  SettingsLoading,
  SettingsPanelErrorBoundary,
  SettingsSectionCard,
  SettingsErrorSummary,
  type ErrorSummaryEntry,
  type WizardDraftItem,
  type WizardCompleteResult,
  type ModelReferenceReplacement,
} from '../components/settings';
import { parseModelAccessFieldKey, type ModelAccessFieldFocusRequest } from '../utils/modelAccessFieldKey';
import { connectionItemsRespectSchema } from '../components/settings/settingsConnectionUpdateContract';
import { SettingsSectionNav, SettingsViewTabs } from '../components/settings/SettingsNavigation';
import SystemAboutCard from '../components/settings/SystemAboutCard';
import ConfigBackupCard from '../components/settings/ConfigBackupCard';
import ConfigPresetsPanel from '../components/settings/ConfigPresetsPanel';
import AlphaSiftSettingsCard from '../components/settings/AlphaSiftSettingsCard';
import {
  AiOverviewCard,
  AiTaskRoutingCard,
  AiReliabilityCard,
} from '../components/settings/AiModelsViewCards';
import {
  TASK_MODEL_KEYS,
  buildModelSelectorOptions,
  buildAvailableModelRefSet,
  buildAvailableModelsByRoute,
  resolveConfiguredModelRef as resolveConfiguredModelRefValue,
  formatConfiguredModel as formatConfiguredModelValue,
} from '../components/settings/aiModelsViewModel';
import { getDesktopRuntimeApi } from '../components/settings/desktopUpdateModel';
import {
  getUnsafeAiPlacement,
  mergeGenerationBackendDraftItems,
  isPromptCacheAdvancedSetting,
} from '../components/settings/settingsGenerationDraftModel';
import SettingsConflictPanel from '../components/settings/SettingsConflictPanel';
import SettingsActiveConfigPanel from '../components/settings/SettingsActiveConfigPanel';
import { SettingsOnboardingHosts } from '../components/onboarding/SettingsOnboardingHosts';
import {
  SETTINGS_SECTIONS,
  getDefaultView,
  getSectionViews,
  isSettingsSectionId,
  legacyToSectionView,
  sectionLabel,
  sectionViewToLegacy,
  type SettingsSectionId,
} from '../components/settings/settingsInformationArchitecture';
import { computeSectionStatus } from '../components/settings/settingsSectionStatus';
import { keyBelongsToSection, placementForKey, SCHEDULER_SETTING_KEYS } from '../components/settings/settingsFieldPlacement';
import {
  type SettingsGroupSaveState,
  type SettingsSaveStatus,
  SETTINGS_AUTOSAVE_DEBOUNCE_MS,
  classifyAiModelGate,
  computeGroupFingerprint,
  shouldMarkDirtyOnConflict,
} from '../components/settings/autosaveMachine';
import { IntelligenceSourcesPanel } from '../components/settings/IntelligenceSourcesPanel';
import FirstRunSetupCard from '../components/settings/FirstRunSetupCard';
import SchedulerSettingsCard from '../components/settings/SchedulerSettingsCard';
import ScheduledTasksPanel from '../components/settings/ScheduledTasksPanel';
import SecurityAuditPanel from '../components/settings/SecurityAuditPanel';
import OutboundActivityPanel from '../components/settings/OutboundActivityPanel';
import SignalScorecardPanel from '../components/settings/SignalScorecardPanel';
import { getConfigItem } from '../components/settings/settingsConfigItems';
import { parseStockListValue } from '../utils/stockList';
import { getCategoryDescription, getCategoryTitle } from '../utils/systemConfigI18n';
import {
  hasUnknownConfigContractCondition,
  isFieldVisibleByContract,
  isFieldEnabledByContract,
  resolveFieldRequirement,
} from '../utils/configConditions';
import type {
  LLMConfigModeStatus,
  SetupStatusResponse,
  SystemConfigCategory,
  SystemConfigItem,
  SystemConfigUpdateItem,
} from '../types/systemConfig';
import { SETTINGS_PAGE_TEXT, SETTINGS_TASK_REFERENCE_LABELS } from '../locales/settingsPage';
import { SETTINGS_NOTIFICATION_TEXT } from '../locales/settingsNotifications';
import { resolveSettingsFieldTitle } from '../locales/settingsFieldTitle';
import TokenUsagePage from '../components/usage/TokenUsagePage';
// Routing fields whose options must be limited to channels the user has
// actually configured (values follow ROUTABLE_NOTIFICATION_CHANNELS).
const CHANNEL_ROUTING_FIELD_KEYS = new Set([
  'NOTIFICATION_REPORT_CHANNELS',
  'NOTIFICATION_ALERT_CHANNELS',
  'NOTIFICATION_SYSTEM_ERROR_CHANNELS',
]);
const LOCAL_MODEL_CONFIG_KEYS = [
  'GENERATION_BACKEND',
  'LLM_CONFIG_MODE',
  'LLM_CHANNELS',
  'LLM_OLLAMA_PROVIDER',
  'LLM_OLLAMA_PROTOCOL',
  'LLM_OLLAMA_BASE_URL',
  'LLM_OLLAMA_MODELS',
  'LLM_OLLAMA_ENABLED',
  'LITELLM_MODEL',
  'AGENT_LITELLM_MODEL',
];
function parseSetupStockList(value: unknown) {
  return parseStockListValue(String(value ?? ''));
}

const SettingsPage: React.FC = () => {
  const { passwordChangeable } = useAuth();
  const { language: uiLanguage, t } = useUiLanguage();
  const settingsText = SETTINGS_PAGE_TEXT[uiLanguage];
  const [llmFocusFieldRequest, setLlmFocusFieldRequest] = useState<ModelAccessFieldFocusRequest | null>(null);
  const [showResetConfirm, setShowResetConfirm] = useState(false);
  const [schedulerStatusRefreshToken, setSchedulerStatusRefreshToken] = useState(0);
  const [schedulerRuntimeEnabled, setSchedulerRuntimeEnabled] = useState<boolean | null>(null);
  const [schedulerOverrideFromUi, setSchedulerOverrideFromUi] = useState<boolean | null>(null);
  const [setupStatus, setSetupStatus] = useState<SetupStatusResponse | null>(null);
  const [isWizardOpen, setIsWizardOpen] = useState(false);
  const [isAgentOnboardingOpen, setIsAgentOnboardingOpen] = useState(false);
  const [isIntelligentImportOpen, setIsIntelligentImportOpen] = useState(false);
  const { beginnerMode, mode: settingsMode, setMode: setSettingsMode } = useBeginnerMode();
  // Advanced sections stay hidden until the user reveals them; re-hiding on
  // Essentials mode keeps the simplified navigation predictable.
  const [advancedRevealed, setAdvancedRevealed] = useState(false);
  const handleSettingsModeChange = useCallback((next: 'essentials' | 'expert') => {
    setSettingsMode(next);
    if (next === 'essentials') {
      setAdvancedRevealed(false);
    }
  }, [setSettingsMode]);
  const [isRefreshingSetupStatus, setIsRefreshingSetupStatus] = useState(false);
  const [setupStatusError, setSetupStatusError] = useState<ParsedApiError | null>(null);
  const [isRunningSetupSmoke, setIsRunningSetupSmoke] = useState(false);
  const [setupSmokeError, setSetupSmokeError] = useState<ParsedApiError | null>(null);
  const [setupSmokeSuccess, setSetupSmokeSuccess] = useState('');
  const [llmChannelDraftItems, setLlmChannelDraftItems] = useState<SystemConfigUpdateItem[]>([]);
  const [groupSaveStates, setGroupSaveStates] = useState<Record<string, SettingsGroupSaveState>>({});
  const groupSaveStatesRef = useRef<Record<string, SettingsGroupSaveState>>({});
  const pendingGroupsRef = useRef<Map<string, SystemConfigUpdateItem[]>>(new Map());
  const autosaveTimerRef = useRef<number | null>(null);
  const autosaveInFlightRef = useRef<string | null>(null);
  const lastSaveGroupRef = useRef<string | null>(null);
  // Structural completeness gate reported by the LLM channel editor; blocks the
  // unified Save & Apply while an enabled channel is incomplete.
  const [llmChannelDraftValid, setLlmChannelDraftValid] = useState(true);
  // Bumped to tell the mounted channel editor to discard its draft on Reset.
  const [llmChannelResetSignal, setLlmChannelResetSignal] = useState(0);
  // Bumped by the page-level primary action to open the add-connection dialog.
  const [llmChannelAddSignal, setLlmChannelAddSignal] = useState(0);
  const setupStatusRequestIdRef = useRef(0);
  const onboardingWizardOpenedRef = useRef(false);
  const isDesktopRuntime = Boolean(getDesktopRuntimeApi());

  const [searchParams, setSearchParams] = useSearchParams();
  // Seed the active tab from the URL once so deep links / refresh restore it.
  // Prefer the new section/view scheme; fall back to (and migrate from) the
  // legacy category/sub params below.
  const [initialTab] = useState(() => {
    const section = searchParams.get(SETTINGS_ROUTE_QUERY_KEYS.section);
    if (section) {
      const legacy = sectionViewToLegacy(
        section,
        searchParams.get(SETTINGS_ROUTE_QUERY_KEYS.view),
      );
      return { category: legacy.category, subCategory: legacy.sub };
    }
    const category = searchParams.get(SETTINGS_ROUTE_QUERY_KEYS.legacyCategory);
    return category
      ? { category, subCategory: searchParams.get(SETTINGS_ROUTE_QUERY_KEYS.legacySub) }
      : undefined;
  });

  const {
    itemsByCategory,
    issueByKey,
    selectTab,
    hasDirty,
    dirtyKeys,
    toast,
    clearToast,
    isLoading,
    isSaving,
    loadError,
    saveError,
    retryAction,
    conflictState,
    resolveConflictField,
    resolveAllConflicts,
    load,
    retry,
    save,
    serverItems,
    resetDraftKeys,
    setDraftValue,
    applyPartialUpdate,
    getChangedItems,
    refreshAfterExternalSave,
    configVersion,
    maskToken,
    configuredNotificationChannels,
  } = useSystemConfig(initialTab);
  // Authoritative provider catalog (single source of truth) for the wizard and
  // the model-access page.
  const {
    providers: providerCatalog,
    connectionFields: providerConnectionFields,
    connectionSchemaDefinition: providerConnectionSchemaDefinition,
    emptyApiKeyHosts: providerEmptyApiKeyHosts,
    isLoading: isProviderCatalogLoading,
    error: providerCatalogError,
    reload: reloadProviderCatalog,
  } = useProviderCatalog();
  const providerConnectionSchemaUnavailable = providerConnectionSchemaDefinition.mode === 'schema'
    && !providerConnectionSchemaDefinition.usable;
  const providerConnectionSchemaAllowsInspection = providerConnectionSchemaDefinition.reason
    === 'unknown_condition';
  // Available model routes (authoritative) refetched when the saved config changes.
  const {
    models: availableModels,
    isLoading: availableModelsLoading,
    error: availableModelsError,
    reload: reloadAvailableModels,
  } = useAvailableModels(configVersion);

  // section/view is the single source of truth for navigation, driven by the
  // URL so Back/Forward/refresh/deep-links all work. Legacy category/sub only
  // seeds the initial state and is migrated away; it never decides the section
  // (which is why Reports vs Alerts, or Conversation vs Agent, no longer jump).
  const activeSection = useMemo<SettingsSectionId>(() => {
    const section = searchParams.get(SETTINGS_ROUTE_QUERY_KEYS.section);
    if (section && isSettingsSectionId(section)) {
      return section;
    }
    const category = searchParams.get(SETTINGS_ROUTE_QUERY_KEYS.legacyCategory);
    if (category) {
      return legacyToSectionView(
        category,
        searchParams.get(SETTINGS_ROUTE_QUERY_KEYS.legacySub),
      ).section;
    }
    return SETTINGS_SECTIONS[0].id;
  }, [searchParams]);
  useEffect(() => {
    document.title = t(activeSection === SETTINGS_SECTION_IDS.usage
      ? 'usage.documentTitle'
      : 'settings.pageTitleDocument');
  }, [activeSection, t]);
  const activeView = useMemo<string>(() => {
    const view = searchParams.get(SETTINGS_ROUTE_QUERY_KEYS.view);
    if (getSectionViews(activeSection).some((entry) => entry.id === view)) {
      return view as string;
    }
    const category = searchParams.get(SETTINGS_ROUTE_QUERY_KEYS.legacyCategory);
    if (category && !searchParams.get(SETTINGS_ROUTE_QUERY_KEYS.section)) {
      const legacy = legacyToSectionView(
        category,
        searchParams.get(SETTINGS_ROUTE_QUERY_KEYS.legacySub),
      );
      if (legacy.section === activeSection) {
        return legacy.view;
      }
    }
    return getDefaultView(activeSection);
  }, [searchParams, activeSection]);

  // Rendering still works off backend (category, sub); derive it from the
  // canonical section/view. All existing activeCategory/activeSubCategory reads
  // consume these, so section/view stays the single source of truth.
  const { category: activeCategory, sub: activeSubCategory } = sectionViewToLegacy(activeSection, activeView);

  const selectSectionView = useCallback((section: SettingsSectionId, view: string) => {
    const next = new URLSearchParams(searchParams);
    next.delete(SETTINGS_ROUTE_QUERY_KEYS.legacyCategory);
    next.delete(SETTINGS_ROUTE_QUERY_KEYS.legacySub);
    next.delete(SETTINGS_ROUTE_QUERY_KEYS.source);
    next.set(SETTINGS_ROUTE_QUERY_KEYS.section, section);
    const resolvedView = getSectionViews(section).some((entry) => entry.id === view)
      ? view
      : getDefaultView(section);
    if (resolvedView) {
      next.set(SETTINGS_ROUTE_QUERY_KEYS.view, resolvedView);
    } else {
      next.delete(SETTINGS_ROUTE_QUERY_KEYS.view);
    }
    // Normal navigation pushes a history entry so Back/Forward return here.
    setSearchParams(next, { replace: false });
  }, [searchParams, setSearchParams]);

  const goToModelAccessFromTaskRouting = useCallback(() => {
    const next = new URLSearchParams(searchParams);
    next.delete(SETTINGS_ROUTE_QUERY_KEYS.legacyCategory);
    next.delete(SETTINGS_ROUTE_QUERY_KEYS.legacySub);
    next.set(SETTINGS_ROUTE_QUERY_KEYS.section, 'ai_models');
    next.set(SETTINGS_ROUTE_QUERY_KEYS.view, 'connections');
    next.set(SETTINGS_ROUTE_QUERY_KEYS.source, 'task_routing');
    setSearchParams(next, { replace: false });
  }, [searchParams, setSearchParams]);

  const returnToTaskRouting = useCallback(() => {
    const next = new URLSearchParams(searchParams);
    next.delete(SETTINGS_ROUTE_QUERY_KEYS.legacyCategory);
    next.delete(SETTINGS_ROUTE_QUERY_KEYS.legacySub);
    next.delete(SETTINGS_ROUTE_QUERY_KEYS.source);
    next.set(SETTINGS_ROUTE_QUERY_KEYS.section, 'ai_models');
    next.set(SETTINGS_ROUTE_QUERY_KEYS.view, 'task_routing');
    setSearchParams(next, { replace: false });
  }, [searchParams, setSearchParams]);

  // On small screens the section selector is above the content, so after a
  // selection move focus into the content region for screen readers and to
  // scroll the newly selected section into view (desktop clicks are unaffected).
  const contentRegionRef = useRef<HTMLElement | null>(null);
  const selectSectionFromMobile = useCallback((section: SettingsSectionId) => {
    selectSectionView(section, getDefaultView(section));
    requestAnimationFrame(() => requestAnimationFrame(() => {
      contentRegionRef.current?.focus();
    }));
  }, [selectSectionView]);

  // Migrate legacy category/sub URLs and normalize non-canonical params to the
  // canonical section/view URL. This is the ONLY place that uses replace.
  useEffect(() => {
    const hasLegacy = searchParams.has(SETTINGS_ROUTE_QUERY_KEYS.legacyCategory)
      || searchParams.has(SETTINGS_ROUTE_QUERY_KEYS.legacySub);
    const canonical = !hasLegacy
      && searchParams.get(SETTINGS_ROUTE_QUERY_KEYS.section) === activeSection
      && (searchParams.get(SETTINGS_ROUTE_QUERY_KEYS.view) ?? '') === activeView;
    if (canonical) {
      return;
    }
    const next = new URLSearchParams(searchParams);
    next.delete(SETTINGS_ROUTE_QUERY_KEYS.legacyCategory);
    next.delete(SETTINGS_ROUTE_QUERY_KEYS.legacySub);
    next.set(SETTINGS_ROUTE_QUERY_KEYS.section, activeSection);
    if (activeView) {
      next.set(SETTINGS_ROUTE_QUERY_KEYS.view, activeView);
    } else {
      next.delete(SETTINGS_ROUTE_QUERY_KEYS.view);
    }
    setSearchParams(next, { replace: true });
  }, [searchParams, activeSection, activeView, setSearchParams]);

  // Keep useSystemConfig's internal tab in sync so config reloads preserve the
  // right category; rendering itself reads the derived activeCategory above.
  useEffect(() => {
    selectTab(activeCategory, activeSubCategory);
  }, [activeCategory, activeSubCategory, selectTab]);

  // Per-section badge state for the first-level nav (error / unsaved only).
  const settingsSectionStatus = useMemo(
    () => computeSectionStatus(itemsByCategory, dirtyKeys ?? [], Object.keys(issueByKey)),
    [itemsByCategory, dirtyKeys, issueByKey],
  );

  // Which model config source (channels/yaml/legacy) is actually effective.
  const [llmModeStatus, setLlmModeStatus] = useState<LLMConfigModeStatus | null>(null);
  useEffect(() => {
    let alive = true;
    systemConfigApi
      .getLlmConfigModeStatus()
      .then((next) => { if (alive) setLlmModeStatus(next); })
      .catch(() => { /* advisory status; ignore load failures */ });
    return () => { alive = false; };
  }, [configVersion]);
  // The channel editor is read-only when a non-channels source is effective, so
  // the active configuration source is unambiguous (MC-02 mutual exclusion).
  const channelsOverriddenByMode =
    llmModeStatus?.effectiveMode && llmModeStatus.effectiveMode !== 'channels'
      ? llmModeStatus.effectiveMode
      : null;

  const currentChangedItems = getChangedItems();
  const currentChangedItemsFingerprint = JSON.stringify(currentChangedItems);
  const llmChannelDraftItemsFingerprint = JSON.stringify(llmChannelDraftItems);
  const configCategoryByKey = useMemo(() => {
    const categories = new Map<string, string>();
    for (const [category, items] of Object.entries(itemsByCategory)) {
      for (const item of items) {
        categories.set(item.key.toUpperCase(), item.schema?.category ?? category);
      }
    }
    return categories;
  }, [itemsByCategory]);
  const groupForConfigKey = useCallback((key: string): string => {
    const normalized = key.toUpperCase();
    if (
      normalized === 'LLM_CHANNELS'
      || normalized.startsWith('LLM_')
      || ['LITELLM_MODEL', 'LITELLM_FALLBACK_MODELS', 'AGENT_LITELLM_MODEL', 'VISION_MODEL'].includes(normalized)
    ) {
      return 'ai_model';
    }
    return configCategoryByKey.get(normalized) ?? 'system';
  }, [configCategoryByKey]);
  const pendingGroups = (() => {
    const groups = new Map<string, Map<string, SystemConfigUpdateItem>>();
    const add = (item: SystemConfigUpdateItem) => {
      const group = groupForConfigKey(item.key);
      const values = groups.get(group) ?? new Map<string, SystemConfigUpdateItem>();
      values.set(item.key.toUpperCase(), item);
      groups.set(group, values);
    };
    currentChangedItems.forEach(add);
    if (
      schedulerOverrideFromUi !== null
      && schedulerRuntimeEnabled !== null
      && schedulerOverrideFromUi !== schedulerRuntimeEnabled
      && !currentChangedItems.some((item) => item.key === 'SCHEDULE_ENABLED')
    ) {
      add({ key: 'SCHEDULE_ENABLED', value: schedulerOverrideFromUi ? 'true' : 'false' });
    }
    llmChannelDraftItems.forEach(add);
    return new Map(Array.from(groups, ([group, values]) => [group, Array.from(values.values())]));
  })();
  const pendingGroupsFingerprint = JSON.stringify(Array.from(pendingGroups.entries()));
  pendingGroupsRef.current = pendingGroups;
  const setGroupSaveState = useCallback((group: string, state: SettingsGroupSaveState) => {
    const next = { ...groupSaveStatesRef.current, [group]: state };
    groupSaveStatesRef.current = next;
    setGroupSaveStates(next);
  }, []);
  // The LLM channel draft feeds the same unified Save & Apply as normal fields;
  // switching tabs keeps it in this parent state and rehydrates on remount.
  const generationBackendDraftItems = useMemo(
    () => mergeGenerationBackendDraftItems(currentChangedItems, llmChannelDraftItems),
    // Fingerprints keep the status panel from refreshing when parent renders do not change draft content.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [currentChangedItemsFingerprint, llmChannelDraftItemsFingerprint],
  );
  const handleLlmChannelDraftItemsChange = useCallback((items: Array<{ key: string; value: string }>) => {
    setLlmChannelDraftItems(items);
  }, []);
  const handleLlmChannelValidityChange = useCallback((valid: boolean) => {
    setLlmChannelDraftValid(valid);
  }, []);
  const resolveSettingsConflict = useCallback((key: string, choice: 'server' | 'local') => {
    if (choice === 'server' && llmChannelDraftItems.some((item) => item.key === key)) {
      setLlmChannelDraftItems((current) => current.filter((item) => item.key !== key));
      setLlmChannelResetSignal((current) => current + 1);
    }
    const group = groupForConfigKey(key);
    const hasRemainingInGroup = conflictState?.fields.some(
      (field) => field.key !== key && groupForConfigKey(field.key) === group,
    );
    resolveConflictField(key, choice);
    if (!hasRemainingInGroup) {
      // Clearing the conflicted marker lets the existing autosave effect retry
      // kept-local drafts against the refreshed server version. Server choices
      // have no remaining draft and simply return the group to idle.
      setGroupSaveState(group, { status: 'idle', fingerprint: '' });
    }
  }, [conflictState, groupForConfigKey, llmChannelDraftItems, resolveConflictField, setGroupSaveState]);

  const resolveAllSettingsConflicts = useCallback((choice: 'server' | 'local') => {
    const affectedGroups = new Set(
      (conflictState?.fields ?? []).map((field) => groupForConfigKey(field.key)),
    );
    if (choice === 'server' && conflictState) {
      const conflictKeys = new Set(conflictState.fields.map((field) => field.key));
      setLlmChannelDraftItems((current) => current.filter((item) => !conflictKeys.has(item.key)));
      setLlmChannelResetSignal((current) => current + 1);
    }
    resolveAllConflicts(choice);
    affectedGroups.forEach((group) => {
      setGroupSaveState(group, { status: 'idle', fingerprint: '' });
    });
  }, [conflictState, groupForConfigKey, resolveAllConflicts, setGroupSaveState]);

  const refreshSetupStatus = useCallback(async () => {
    const requestId = setupStatusRequestIdRef.current + 1;
    setupStatusRequestIdRef.current = requestId;
    setSetupStatusError(null);
    setIsRefreshingSetupStatus(true);
    try {
      const status = await systemConfigApi.getSetupStatus();
      if (setupStatusRequestIdRef.current !== requestId) {
        return;
      }
      setSetupStatus(status);
    } catch (error: unknown) {
      if (setupStatusRequestIdRef.current !== requestId) {
        return;
      }
      setSetupStatusError(getParsedApiError(error));
    } finally {
      if (setupStatusRequestIdRef.current === requestId) {
        setIsRefreshingSetupStatus(false);
      }
    }
  }, []);

  // Unified post-save side effects. Every successful config transaction — the
  // Save button, a save retry, and the Legacy→Channels migration — runs this
  // exact flow so status panels never drift from the persisted config. Config
  // snapshot/version reload, validationIssues clearing and the success toast are
  // handled inside useSystemConfig.save()/load(); the generation-backend panel
  // and config-mode banner re-fetch off the reloaded config/version.
  const applyPostSaveEffects = useCallback(() => {
    notifySystemConfigChanged();
    setSchedulerStatusRefreshToken((current) => current + 1);
    void refreshSetupStatus();
  }, [refreshSetupStatus]);

  const [isToastPaused, setIsToastPaused] = useState(false);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    void refreshSetupStatus();
  }, [refreshSetupStatus]);

  useEffect(() => {
    if (
      onboardingWizardOpenedRef.current
      || searchParams.get(SETTINGS_ROUTE_QUERY_KEYS.source) !== 'onboarding'
      || !setupStatus
    ) {
      return;
    }
    const needsLlmSetup = setupStatus.requiredMissingKeys.includes('llm_primary')
      || setupStatus.checks.some((check) => (
        check.key === 'llm_primary' && check.status === 'needs_action'
      ));
    if (!needsLlmSetup) {
      onboardingWizardOpenedRef.current = true;
      return;
    }
    if (isProviderCatalogLoading) {
      return;
    }
    onboardingWizardOpenedRef.current = true;
    if (providerCatalog.length > 0) {
      setIsWizardOpen(true);
    }
  }, [isProviderCatalogLoading, providerCatalog.length, searchParams, setupStatus]);

  useEffect(() => {
    if (!toast || toast.type !== 'success' || isToastPaused) {
      return;
    }

    const timer = window.setTimeout(() => {
      clearToast();
    }, 3200);

    return () => {
      window.clearTimeout(timer);
    };
  }, [clearToast, isToastPaused, toast]);

  const rawActiveItems = itemsByCategory[activeCategory] || [];
  const firstSetupStockCode = parseSetupStockList(getConfigItem(itemsByCategory.base || [], 'STOCK_LIST')?.value)[0] || '';
  const alphasiftItem = (itemsByCategory.data_source || []).find((item) => item.key === 'ALPHASIFT_ENABLED');
  const alphasiftEnabled = String(alphasiftItem?.value ?? '').trim().toLowerCase() === 'true';
  const shouldShowFirstRunSetup = activeCategory === 'base';
  const shouldShowAlphaSiftSettings =
    activeCategory === 'data_source' && activeSubCategory === 'providers' && Boolean(alphasiftItem);
  const effectiveDirtyCount = Array.from(pendingGroups.values())
    .reduce((count, items) => count + items.length, 0);
  const effectiveHasDirty = effectiveDirtyCount > 0;
  const leaveGuardCount = effectiveDirtyCount;
  // Guard leaving while there are unsaved edits (including the LLM channel draft).
  const shouldGuardLeave = effectiveHasDirty;

  // Warn before leaving/refreshing/closing the tab while there are unsaved config edits.
  useEffect(() => {
    if (!shouldGuardLeave) {
      return;
    }
    const handleBeforeUnload = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = '';
    };
    window.addEventListener('beforeunload', handleBeforeUnload);
    return () => window.removeEventListener('beforeunload', handleBeforeUnload);
  }, [shouldGuardLeave]);

  // beforeunload only covers full page unloads; SPA route changes would
  // silently drop draft edits, so block them behind a confirm dialog.
  const leaveBlocker = useBlocker(
    useCallback(
      ({ currentLocation, nextLocation }: {
        currentLocation: { pathname: string };
        nextLocation: { pathname: string };
      }) => shouldGuardLeave && currentLocation.pathname !== nextLocation.pathname,
      [shouldGuardLeave],
    ),
  );

  const handleSchedulerRuntimeStateChange = useCallback(({ runtimeEnabled, overrideEnabled }: {
    runtimeEnabled: boolean | null;
    overrideEnabled: boolean | null;
  }) => {
    setSchedulerRuntimeEnabled(runtimeEnabled);
    setSchedulerOverrideFromUi(overrideEnabled);
  }, []);

  // UI rendering rule only: a field whose backend schema declares a
  // uiPlacement is owned by a dedicated surface (Model Access / Task Routing /
  // Reliability / developer diagnostics) or is a hidden legacy provider key,
  // so the generic category views never render it. The backend registry is the
  // single source of this ownership — the Web keeps no provider/field lists.
  // This does not alter save/refresh payloads or migration/rollback behavior.
  const SYSTEM_HIDDEN_KEYS = new Set([
    'ADMIN_AUTH_ENABLED',
    ...SCHEDULER_SETTING_KEYS,
  ]);
  const DATA_SOURCE_HIDDEN_KEYS = new Set([
    'ALPHASIFT_ENABLED',
  ]);
  const placementFilteredItems = rawActiveItems.filter((item) => (
    activeCategory !== 'ai_model' && !item.schema?.uiPlacement
  ));
  const activeItems =
    activeCategory === 'system'
      ? placementFilteredItems.filter((item) => !SYSTEM_HIDDEN_KEYS.has(item.key))
      : activeCategory === 'data_source'
        ? placementFilteredItems.filter((item) => !DATA_SOURCE_HIDDEN_KEYS.has(item.key))
      : placementFilteredItems;
  // Current (draft-applied) value of every field, for evaluating cross-field
  // schema contract conditions (visibleWhen / enabledWhen).
  const allValuesByKey = useMemo(() => {
    const map: Record<string, string> = {};
    for (const categoryItems of Object.values(itemsByCategory)) {
      for (const item of categoryItems) {
        map[item.key.toUpperCase()] = String(item.value ?? '');
      }
    }
    return map;
  }, [itemsByCategory]);
  const persistedValuesByKey = useMemo(() => {
    const map: Record<string, string> = {};
    serverItems.forEach((item) => { map[item.key.toUpperCase()] = String(item.value ?? ''); });
    return map;
  }, [serverItems]);
  const rawValueKeys = useMemo(() => {
    const keys = new Set<string>();
    for (const categoryItems of Object.values(itemsByCategory)) {
      for (const item of categoryItems) {
        if (item.rawValueExists !== false) {
          keys.add(item.key.toUpperCase());
        }
      }
    }
    return keys;
  }, [itemsByCategory]);
  // Channel routing fields only offer channels the backend confirms are
  // configured. A null status means an older backend omitted the authority
  // field during a rolling upgrade; in that case leave the catalog unfiltered
  // instead of misrepresenting "unknown" as "none configured".
  const hasConfiguredNotificationChannelStatus = configuredNotificationChannels !== null;
  const configuredRoutingValues = useMemo(
    () => new Set(configuredNotificationChannels ?? []),
    [configuredNotificationChannels],
  );
  const channelRoutingOptionFilter = useCallback(
    (optionValue: string) => configuredRoutingValues.has(optionValue),
    [configuredRoutingValues],
  );
  const notificationText = SETTINGS_NOTIFICATION_TEXT[uiLanguage];
  // One group-level banner carries the "no channels yet" guidance so the three
  // routing rows don't each repeat a bulky empty-state card.
  const channelRoutingEmptyState = (
    <p className="text-xs leading-6 text-muted-text md:text-right">—</p>
  );
  const channelRoutingEmptyBanner = (
    <div
      data-testid="channel-routing-empty-banner"
      className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-border bg-background/35 px-3 py-2"
    >
      <p className="text-xs text-muted-text">{notificationText.noRoutableChannels}</p>
      <Button
        type="button"
        variant="secondary"
        size="default"
        className="text-xs shadow-none"
        onClick={() => selectSectionView('notifications', 'channels')}
      >
        {notificationText.goConfigureChannels}
      </Button>
    </div>
  );
  const hasUnsafeModelAccessSchema = rawActiveItems.some((item) => (
    (
      getUnsafeAiPlacement(item, activeCategory) !== null
      || hasUnknownConfigContractCondition(item.schema?.contract, allValuesByKey)
    )
    && (item.key === 'LLM_CHANNELS' || Boolean(parseModelAccessFieldKey(item.key)))
  ));
  const readOnlyDiagnosticForItem = useCallback((item: SystemConfigItem, categoryHint?: string) => {
    const unsafePlacement = getUnsafeAiPlacement(item, categoryHint);
    if (unsafePlacement) {
      return `${settingsText.diagnostics}: schema_ui_placement_${unsafePlacement}`;
    }
    if (hasUnknownConfigContractCondition(item.schema?.contract, allValuesByKey)) {
      return `${settingsText.diagnostics}: schema_condition_unknown`;
    }
    return undefined;
  }, [allValuesByKey, settingsText.diagnostics]);
  // Backend category for every key, so a validation error can be routed to the
  // section/view that owns the field via the placement map.
  const categoryByKey = useMemo(() => {
    const map: Record<string, string> = {};
    for (const [category, categoryItems] of Object.entries(itemsByCategory)) {
      for (const item of categoryItems) {
        map[item.key] = category;
      }
    }
    return map;
  }, [itemsByCategory]);
  const configItemByKey = useMemo(
    () => new Map(Object.values(itemsByCategory).flat().map((item) => [item.key, item])),
    [itemsByCategory],
  );
  // Page-level validation summary: every errored field, routed to its owning
  // section/view via the placement map so errors on a non-open section are
  // still reachable in one click (SR-19).
  const errorSummaryEntries = useMemo<ErrorSummaryEntry[]>(() => {
    const entries: ErrorSummaryEntry[] = [];
    for (const [key, issues] of Object.entries(issueByKey)) {
      const firstError = issues.find((issue) => issue.severity === 'error');
      if (!firstError) {
        continue;
      }
      const target = parseModelAccessFieldKey(key)
        ? { section: 'ai_models', view: 'connections' }
        : placementForKey(categoryByKey[key] ?? '', key);
      const item = configItemByKey.get(key);
      const fallbackTitle = item?.schema?.title ?? key;
      entries.push({
        key,
        label: resolveSettingsFieldTitle({
          itemKey: item?.key ?? key,
          schemaKey: item?.schema?.key,
          fallbackTitle,
          language: uiLanguage,
        }),
        message: firstError.message,
        section: target.section,
        view: target.view,
      });
    }
    return entries;
  }, [issueByKey, categoryByKey, configItemByKey, uiLanguage]);
  const jumpToErrorField = useCallback((entry: ErrorSummaryEntry) => {
    selectSectionView(entry.section as SettingsSectionId, entry.view);
    if (parseModelAccessFieldKey(entry.key)) {
      setLlmFocusFieldRequest((previous) => ({ requestId: (previous?.requestId ?? 0) + 1, key: entry.key }));
      return;
    }
    // Focus + reveal the field once the target section commits (two frames).
    requestAnimationFrame(() => requestAnimationFrame(() => {
      const el = document.getElementById(`setting-${entry.key}`);
      if (el) {
        el.focus();
        el.scrollIntoView({ block: 'center' });
      }
    }));
  }, [selectSectionView]);
  // Some settings (e.g. WEBUI host/port, log dir) only take effect after a
  // restart. Surface a page-level notice when any *changed* field is one of
  // them so the user knows a save alone won't apply them.
  const hasDirtyRestartRequired = useMemo(() => {
    const dirtySet = new Set(dirtyKeys ?? []);
    if (dirtySet.size === 0) {
      return false;
    }
    for (const categoryItems of Object.values(itemsByCategory)) {
      for (const item of categoryItems) {
        if (dirtySet.has(item.key) && item.schema?.warningCodes?.includes('restart_required')) {
          return true;
        }
      }
    }
    return false;
  }, [dirtyKeys, itemsByCategory]);
  // The AI & Models Overview view shows a task-routing matrix instead of raw
  // fields / the channel editor.
  const isAiOverview = activeSection === SETTINGS_SECTION_IDS.aiModels
    && activeView === SETTINGS_VIEW_IDS.aiModels.overview;
  const isAiLocalModels = activeSection === SETTINGS_SECTION_IDS.aiModels
    && activeView === SETTINGS_VIEW_IDS.aiModels.localModels;
  const isInvestmentFrameworkView = activeSection === 'agent_behavior'
    && activeView === 'investment_framework';
  // Task Routing view: the single place to edit which model each task uses.
  const isAiTaskRouting = activeSection === 'ai_models' && activeView === 'task_routing';
  const pickAiModelItems = useCallback(
    (keys: string[]) => keys
      .map((key) => configItemByKey.get(key))
      .filter((item): item is NonNullable<typeof item> => Boolean(item)),
    [configItemByKey],
  );
  // Task Routing is the single canonical editor for per-task models and the
  // generation temperature. Fallback order is edited under Reliability only, so
  // here it is a read-only summary with a jump link (no duplicate editor).
  const taskRoutingItems = useMemo(
    () => pickAiModelItems(['LITELLM_MODEL', 'AGENT_LITELLM_MODEL', 'VISION_MODEL', 'LLM_TEMPERATURE'])
      .filter((item) => item.schema?.uiPlacement === 'task_routing'),
    [pickAiModelItems],
  );
  const fallbackRoutingItem = configItemByKey.get('LITELLM_FALLBACK_MODELS');
  const hasSafeFallbackPlacement = fallbackRoutingItem?.schema?.uiPlacement === 'task_routing';
  const configuredTaskRoutes = useMemo(
    () => taskRoutingItems
      .filter((item) => TASK_MODEL_KEYS.has(item.key) && item.value.trim())
      .map((item) => ({ key: item.key, value: item.value.trim() })),
    [taskRoutingItems],
  );
  // Per-task model fields render a model selector fed by the authoritative
  // available-model catalog (grouped by connection), so users pick a display
  // name and never hand-type a provider/model route.
  const modelSelectorOptions = useMemo<SearchableSelectOption[]>(
    () => buildModelSelectorOptions(availableModels, providerCatalog, uiLanguage),
    [availableModels, providerCatalog, uiLanguage],
  );
  // Authoritative routable route set for AI Overview Active/Unavailable status.
  const availableModelRefSet = useMemo(
    () => buildAvailableModelRefSet(availableModels),
    [availableModels],
  );
  const availableModelsByRoute = useMemo(
    () => buildAvailableModelsByRoute(availableModels),
    [availableModels],
  );
  const resolveConfiguredModelRef = useCallback((value: string): string => (
    resolveConfiguredModelRefValue(value, availableModelRefSet, availableModelsByRoute)
  ), [availableModelRefSet, availableModelsByRoute]);
  const formatConfiguredModel = useCallback((value: string): string => (
    formatConfiguredModelValue(value, availableModels, resolveConfiguredModelRef)
  ), [availableModels, resolveConfiguredModelRef]);
  // Task -> route references, used by the model-access manager to show which
  // tasks use each connection and to protect referenced connections on delete.
  const taskModelRefs = useMemo(() => {
    const refs: Array<{ key: string; label: string; route: string }> = [];
    const add = (key: string, label: string, route: string) => {
      const trimmed = (route || '').trim();
      if (trimmed) {
        refs.push({ key, label, route: trimmed });
      }
    };
    add('LITELLM_MODEL', SETTINGS_TASK_REFERENCE_LABELS[uiLanguage].LITELLM_MODEL, allValuesByKey.LITELLM_MODEL || '');
    add('AGENT_LITELLM_MODEL', SETTINGS_TASK_REFERENCE_LABELS[uiLanguage].AGENT_LITELLM_MODEL, allValuesByKey.AGENT_LITELLM_MODEL || '');
    add('VISION_MODEL', SETTINGS_TASK_REFERENCE_LABELS[uiLanguage].VISION_MODEL, allValuesByKey.VISION_MODEL || '');
    for (const route of (allValuesByKey.LITELLM_FALLBACK_MODELS || '').split(',')) {
      add('LITELLM_FALLBACK_MODELS', SETTINGS_TASK_REFERENCE_LABELS[uiLanguage].LITELLM_FALLBACK_MODELS, route);
    }
    return refs;
  }, [allValuesByKey, uiLanguage]);
  const replaceModelReferences = useCallback((replacements: ModelReferenceReplacement[]) => {
    const nextValues = new Map<string, string>();
    for (const replacement of replacements) {
      const referencedKeys = new Set(
        replacement.references
          .map((reference) => reference.key)
          .filter((key): key is string => Boolean(key)),
      );
      for (const key of referencedKeys) {
        const currentValue = nextValues.get(key) ?? allValuesByKey[key] ?? '';
        if (key === 'LITELLM_FALLBACK_MODELS') {
          const nextRoutes = currentValue
            .split(',')
            .map((route) => route.trim())
            .filter(Boolean)
            .map((route) => (
              route === replacement.fromRoute || resolveConfiguredModelRef(route) === replacement.fromRoute
                ? replacement.toRoute
                : route
            ));
          nextValues.set(key, Array.from(new Set(nextRoutes)).join(','));
        } else {
          const configuredRoute = currentValue.trim();
          const comparableRoute = key === 'AGENT_LITELLM_MODEL'
            && configuredRoute
            && !configuredRoute.includes('/')
            && !availableModelRefSet.has(configuredRoute)
            ? `openai/${configuredRoute}`
            : configuredRoute;
          if (
            comparableRoute === replacement.fromRoute
            || resolveConfiguredModelRef(comparableRoute) === replacement.fromRoute
          ) {
            nextValues.set(key, replacement.toRoute);
          }
        }
      }
    }
    for (const [key, value] of nextValues) {
      setDraftValue(key, value);
    }
  }, [allValuesByKey, availableModelRefSet, resolveConfiguredModelRef, setDraftValue]);
  // Reliability is the user-facing model fallback order. Execution-backend
  // failover is an implementation diagnostic and lives under Advanced only.
  const isAiReliability = activeSection === 'ai_models' && activeView === 'reliability';
  // Event Monitor lives under the agent backend category but belongs to the
  // Alerts section (see the placement map). Render it there via a dedicated
  // card so it doesn't leak into Agent Behavior.
  const eventMonitorItems = useMemo(
    () => (itemsByCategory.agent || [])
      .filter((item) => item.key.toUpperCase().startsWith('AGENT_EVENT_'))
      .filter((item) => isFieldVisibleByContract(item.schema?.contract, allValuesByKey))
      .sort((a, b) => (a.schema?.displayOrder ?? 0) - (b.schema?.displayOrder ?? 0)),
    [itemsByCategory, allValuesByKey],
  );
  const isAlertsSection = activeSection === 'alerts';
  // Top-level Advanced section aggregates internal/low-level keys across backend
  // categories via the placement map (e.g. HMAC usage secrets). This keeps
  // everyday views uncluttered (MC-18).
  const isTopLevelAdvanced = activeSection === 'advanced';
  const advancedSectionItems = useMemo(
    () => Object.entries(itemsByCategory)
      .flatMap(([category, categoryItems]) =>
        categoryItems.filter((item) => (
          item.schema?.uiPlacement === 'developer_diagnostics'
          || getUnsafeAiPlacement(item, category) !== null
          || hasUnknownConfigContractCondition(item.schema?.contract, allValuesByKey)
          || (!item.schema?.uiPlacement && placementForKey(category, item.key).section === 'advanced')
        )))
      .filter((item) => isFieldVisibleByContract(item.schema?.contract, allValuesByKey))
      .sort((a, b) => (a.schema?.displayOrder ?? 0) - (b.schema?.displayOrder ?? 0)),
    [itemsByCategory, allValuesByKey],
  );
  const contractVisibleItems = activeItems.filter((item) =>
    isFieldVisibleByContract(item.schema?.contract, allValuesByKey),
  );
  const promptCacheAdvancedItems = activeCategory === 'ai_model'
    ? contractVisibleItems.filter(isPromptCacheAdvancedSetting)
    : [];
  const visibleActiveItems = activeCategory === 'ai_model'
    ? contractVisibleItems.filter((item) => !isPromptCacheAdvancedSetting(item))
    : contractVisibleItems;
  const hasActiveConfigItems = visibleActiveItems.length > 0 || promptCacheAdvancedItems.length > 0;
  const activeSubCategoriesList = getSubCategories(activeCategory);
  const hasSubNav = activeSubCategoriesList != null;
  // Field-level placement splits sections that share one backend category:
  // Reports vs Alerts (both `notification`) and Conversation vs Agent Behavior
  // (both `agent`). For every other section this is a no-op (the placement
  // delegates back to the category's own section).
  const belongsToActiveSection = (key: string) => keyBelongsToSection(activeCategory, key, activeSection);
  const subFilteredItems = (hasSubNav
    ? visibleActiveItems
      .filter((item) => getSubCategoryOfKey(activeCategory, item.key) === activeSubCategory)
      .sort((a, b) => getSubCategoryFieldOrder(activeCategory, a.key) - getSubCategoryFieldOrder(activeCategory, b.key))
    : visibleActiveItems
  ).filter((item) => belongsToActiveSection(item.key))
    // Alerts, System & Security and Data Sources split their fields into
    // per-view tabs; the placement map is the same authority that drives
    // error-summary jumps.
    .filter((item) => (
      !(isAlertsSection || activeSection === 'system_security' || activeSection === 'data_sources')
      || placementForKey(activeCategory, item.key).view === activeView
    ));
  const activeSubPromptCacheItems =
    activeCategory === 'ai_model' ? promptCacheAdvancedItems : [];
  const isNotificationChannelsSub = activeCategory === 'notification' && activeSubCategory === 'channels';
  const isDataProvidersSub = activeCategory === 'data_source' && activeSubCategory === 'providers';
  const activeSubTitle = hasSubNav && activeSubCategory
    ? t((activeSubCategoriesList?.find((sub) => sub.id === activeSubCategory)?.titleKey) ?? 'settings.activePanelTitle')
    : '';
  // Whether the field panel (SettingsSectionCard with fields) has any content for the active tab.
  const hasSubFieldContent =
    isNotificationChannelsSub ||
    isDataProvidersSub ||
    subFilteredItems.length > 0 ||
    activeSubPromptCacheItems.length > 0;

  const persistConfigGroup = useCallback(async (
    group: string,
    changedItemsToSave: SystemConfigUpdateItem[],
  ) => {
    const changedAlphaSiftItem = changedItemsToSave.find((item) => item.key === 'ALPHASIFT_ENABLED');
    const result = await save(changedItemsToSave, { silent: true });
    if (!result.success) {
      return result;
    }
    if (group === 'ai_model') {
      const submittedLlmValues = new Map(
        changedItemsToSave.map((item) => [item.key.toUpperCase(), item.value]),
      );
      // Preserve edits made while this transaction was in flight.
      setLlmChannelDraftItems((current) => current.filter((item) => (
        submittedLlmValues.get(item.key.toUpperCase()) !== item.value
      )));
      setLlmChannelDraftValid(true);
    }
    applyPostSaveEffects();
    if (!changedAlphaSiftItem) {
      return result;
    }

    try {
      const isAlphaSiftEnabled = changedAlphaSiftItem.value.trim().toLowerCase() === 'true';
      if (isAlphaSiftEnabled) {
        await alphasiftApi.enable();
        await refreshAfterExternalSave(['ALPHASIFT_ENABLED']);
        return result;
      }

      notifyAlphaSiftConfigChanged();
    } catch {
      await refreshAfterExternalSave(['ALPHASIFT_ENABLED']);
    }
    return result;
  }, [applyPostSaveEffects, refreshAfterExternalSave, save]);

  const runGroupAutosave = useCallback(async (group: string) => {
    if (autosaveInFlightRef.current) {
      return;
    }
    const items = pendingGroupsRef.current.get(group) ?? [];
    if (items.length === 0) {
      setGroupSaveState(group, { status: 'idle', fingerprint: '' });
      return;
    }
    const fingerprint = computeGroupFingerprint(items);
    if (group === 'ai_model') {
      const changesConnection = items.some((item) => (
        item.key.toUpperCase() === 'LLM_CHANNELS'
        || parseModelAccessFieldKey(item.key) !== null
      ));
      const blocked = classifyAiModelGate(
        {
          catalogLoading: isProviderCatalogLoading,
          catalogError: Boolean(providerCatalogError),
          schemaUnavailable: providerConnectionSchemaUnavailable,
          channelDraftValid: llmChannelDraftValid,
          changesConnection,
          connectionRespectsSchema: changesConnection
            ? connectionItemsRespectSchema(
                items,
                allValuesByKey,
                rawValueKeys,
                providerCatalog,
                providerConnectionFields,
                providerEmptyApiKeyHosts,
              )
            : true,
        },
        { checkConnection: true },
      );
      if (blocked) {
        setGroupSaveState(group, { status: blocked, fingerprint });
        return;
      }
    }

    autosaveInFlightRef.current = group;
    lastSaveGroupRef.current = group;
    setGroupSaveState(group, { status: 'saving', fingerprint });
    try {
      const result = await persistConfigGroup(group, items);
      setGroupSaveState(group, {
        status: result.success
          ? 'saved'
          : result.message === 'config_conflict'
            ? 'conflicted'
            : 'failed',
        fingerprint,
      });
    } finally {
      autosaveInFlightRef.current = null;
    }
  }, [
    allValuesByKey,
    isProviderCatalogLoading,
    llmChannelDraftValid,
    persistConfigGroup,
    providerCatalog,
    providerCatalogError,
    providerConnectionFields,
    providerConnectionSchemaUnavailable,
    providerEmptyApiKeyHosts,
    rawValueKeys,
    setGroupSaveState,
  ]);

  useEffect(() => {
    if (autosaveTimerRef.current !== null) {
      window.clearTimeout(autosaveTimerRef.current);
      autosaveTimerRef.current = null;
    }
    const currentPendingGroups = pendingGroupsRef.current;
    if (isLoading || autosaveInFlightRef.current || conflictState || currentPendingGroups.size === 0) {
      // Autosave is paused (initial load, another group in flight, or an
      // unresolved version conflict). While a conflict blocks the write, groups
      // with pending edits are explicitly `dirty` rather than left on a stale
      // status; they return to `scheduled` once the conflict is resolved.
      if (conflictState) {
        for (const [group, items] of currentPendingGroups) {
          const previous = groupSaveStatesRef.current[group];
          if (!shouldMarkDirtyOnConflict(previous?.status)) {
            continue;
          }
          const fingerprint = computeGroupFingerprint(items);
          if (previous?.status !== 'dirty' || previous.fingerprint !== fingerprint) {
            setGroupSaveState(group, { status: 'dirty', fingerprint });
          }
        }
      }
      return undefined;
    }

    let nextGroup: string | null = null;
    for (const [group, items] of currentPendingGroups) {
      const fingerprint = computeGroupFingerprint(items);
      if (group === 'ai_model') {
        const blocked = classifyAiModelGate(
          {
            catalogLoading: isProviderCatalogLoading,
            catalogError: Boolean(providerCatalogError),
            schemaUnavailable: providerConnectionSchemaUnavailable,
            channelDraftValid: llmChannelDraftValid,
            changesConnection: false,
            connectionRespectsSchema: true,
          },
          { checkConnection: false },
        );
        if (blocked) {
          setGroupSaveState(group, { status: blocked, fingerprint });
          continue;
        }
      }
      const previous = groupSaveStatesRef.current[group];
      if (
        previous
        && (previous.status === 'failed' || previous.status === 'conflicted')
        && previous.fingerprint === fingerprint
      ) {
        continue;
      }
      setGroupSaveState(group, { status: 'scheduled', fingerprint });
      nextGroup ??= group;
    }
    if (!nextGroup) {
      return undefined;
    }
    autosaveTimerRef.current = window.setTimeout(() => {
      autosaveTimerRef.current = null;
      void runGroupAutosave(nextGroup!);
    }, SETTINGS_AUTOSAVE_DEBOUNCE_MS);
    return () => {
      if (autosaveTimerRef.current !== null) {
        window.clearTimeout(autosaveTimerRef.current);
        autosaveTimerRef.current = null;
      }
    };
  }, [
    conflictState,
    isLoading,
    isProviderCatalogLoading,
    llmChannelDraftValid,
    pendingGroupsFingerprint,
    runGroupAutosave,
    providerCatalogError,
    providerConnectionSchemaUnavailable,
    setGroupSaveState,
  ]);

  const retryAutosaveGroup = useCallback((group: string) => {
    const items = pendingGroupsRef.current.get(group) ?? [];
    setGroupSaveState(group, { status: 'scheduled', fingerprint: computeGroupFingerprint(items) });
    void runGroupAutosave(group);
  }, [runGroupAutosave, setGroupSaveState]);

  const restoreAutosaveGroup = useCallback((group: string) => {
    const items = pendingGroupsRef.current.get(group) ?? [];
    resetDraftKeys(items.map((item) => item.key));
    if (group === 'ai_model') {
      setLlmChannelDraftItems([]);
      setLlmChannelDraftValid(true);
      setLlmChannelResetSignal((current) => current + 1);
    }
    if (items.some((item) => item.key === 'SCHEDULE_ENABLED')) {
      setSchedulerOverrideFromUi(schedulerRuntimeEnabled);
    }
    setGroupSaveState(group, { status: 'idle', fingerprint: '' });
  }, [resetDraftKeys, schedulerRuntimeEnabled, setGroupSaveState]);

  // First-run wizard commits its minimal config through the same save
  // transaction (validate + update + apply server payload), so channel keys are
  // persisted atomically and the normal post-save effects run. The result is
  // returned so the wizard can surface backend validation errors in place.
  const handleWizardComplete = async (items: WizardDraftItem[]): Promise<WizardCompleteResult> => {
    const changesConnection = items.some((item) => (
      item.key.toUpperCase() === 'LLM_CHANNELS'
      || parseModelAccessFieldKey(item.key) !== null
    ));
    if (
      changesConnection
      && (
        providerConnectionSchemaUnavailable
        || !connectionItemsRespectSchema(
          items,
          allValuesByKey,
          rawValueKeys,
          providerCatalog,
          providerConnectionFields,
          providerEmptyApiKeyHosts,
        )
      )
    ) {
      return { success: false, error: settingsText.connectionSchemaUnavailable };
    }
    const result = await save(items);
    if (!result.success) {
      const error = result.issues && result.issues.length > 0
        ? result.issues.map((issue) => issue.message).join('；')
        : result.message;
      return { success: false, error };
    }
    applyPostSaveEffects();
    return { success: true };
  };
  const existingChannelNames = useMemo(
    () => (allValuesByKey.LLM_CHANNELS || '')
      .split(',')
      .map((entry) => entry.trim())
      .filter(Boolean),
    [allValuesByKey],
  );

  const handleRunSetupSmoke = async () => {
    setSetupSmokeError(null);
    setSetupSmokeSuccess('');

    if (!setupStatus?.readyForSmoke) {
      setSetupSmokeError(createParsedApiError({
        title: t('settings.setupGuideSmokeUnavailableTitle'),
        message: t('settings.setupGuideSmokeNotReady'),
        rawMessage: t('settings.setupGuideSmokeNotReady'),
        category: 'missing_params',
      }));
      return;
    }

    if (!firstSetupStockCode) {
      setSetupSmokeError(createParsedApiError({
        title: t('settings.setupGuideSmokeUnavailableTitle'),
        message: t('settings.setupGuideSmokeNeedsStock'),
        rawMessage: t('settings.setupGuideSmokeNeedsStock'),
        category: 'missing_params',
      }));
      return;
    }

    setIsRunningSetupSmoke(true);
    try {
      const result = await analysisApi.analyzeAsync({
        stockCode: firstSetupStockCode,
        reportType: 'brief',
        asyncMode: true,
        notify: false,
        originalQuery: firstSetupStockCode,
        selectionSource: 'manual',
      });
      const taskId = 'taskId' in result ? result.taskId : result.accepted?.[0]?.taskId;
      setSetupSmokeSuccess(
        taskId
          ? t('settings.setupGuideSmokeAcceptedWithTask', { stock: firstSetupStockCode, taskId })
          : t('settings.setupGuideSmokeAccepted', { stock: firstSetupStockCode }),
      );
      void refreshSetupStatus();
    } catch (error: unknown) {
      setSetupSmokeError(getParsedApiError(error));
    } finally {
      setIsRunningSetupSmoke(false);
    }
  };

  const shouldGuardActiveConfigPanel = activeCategory === 'notification' || activeCategory === 'agent';
  const activeConfigPanelErrorTitle = activeCategory === 'agent' ? t('settings.agentSettings') : t('settings.notificationSettings');
  const settingsPanelDiagnosticHint = isDesktopRuntime
    ? <>{settingsText.desktopDiagnosticPrefix} <code>desktop.log</code>{settingsText.desktopDiagnosticSuffix}</>
    : t('settings.diagnosticHintWeb');
  const isNotificationCategory = activeCategory === 'notification';
  const activeFieldGroupOrder = isNotificationCategory
    ? NOTIFICATION_FIELD_GROUP_ORDER
    : getCategoryFieldGroupOrder(activeCategory);
  const fieldGroupIdOf = (key: string) =>
    isNotificationCategory ? getNotificationFieldGroupId(key) : getCategoryFieldGroupId(activeCategory, key);
  const fieldGroupOrderOf = (key: string) =>
    isNotificationCategory ? getNotificationFieldOrder(key) : getCategoryFieldOrder(activeCategory, key);
  const activeCategoryTitle = getCategoryTitle(activeCategory as SystemConfigCategory, t('settings.activePanelTitle'), uiLanguage);
  const activeCategoryDescription = getCategoryDescription(activeCategory as SystemConfigCategory, '', uiLanguage);
  // Sections split out of a shared backend category get their own title/copy so
  // the panel doesn't reuse the sibling category's heading (for example,
  // Reports must not use the Notifications heading).
  const splitSectionCopy: Partial<Record<SettingsSectionId, { title: string; description: string }>> = {
    reports: {
      title: sectionLabel('reports', uiLanguage),
      description: settingsText.reportsDescription,
    },
    conversation: {
      title: sectionLabel('conversation', uiLanguage),
      description: settingsText.conversationDescription,
    },
  };
  const sectionScopedCopy = splitSectionCopy[activeSection];
  const activeConfigPanelTitle = sectionScopedCopy?.title
    ?? (hasSubNav && activeSubTitle ? activeSubTitle : activeCategoryTitle);
  const activeConfigPanelDescription = sectionScopedCopy?.description ?? activeCategoryDescription;
  const persistedAgentModel = (persistedValuesByKey.AGENT_LITELLM_MODEL ?? '').trim();
  const persistedReportModel = (persistedValuesByKey.LITELLM_MODEL ?? '').trim();
  const effectivePersistedAgentModel = persistedAgentModel || persistedReportModel;
  const resolvedPersistedAgentModel = effectivePersistedAgentModel ? resolveConfiguredModelRef(effectivePersistedAgentModel) : '';
  const agentModelSummary = {
    value: effectivePersistedAgentModel ? formatConfiguredModel(effectivePersistedAgentModel) : '',
    source: persistedAgentModel ? 'explicit' as const : 'inherited' as const,
    readiness: availableModelsLoading
      ? 'checking' as const
      : availableModelsError
        ? 'unknown' as const
        : !effectivePersistedAgentModel
          ? 'unconfigured' as const
          : availableModelRefSet.has(resolvedPersistedAgentModel) ? 'ready' as const : 'unavailable' as const,
  };
  // For single-tab categories that a section split can narrow (agent →
  // Conversation / Agent Behavior), gate on the section-filtered content so an
  // empty section never renders a bare card.
  const hasSectionFieldContent = subFilteredItems.length > 0 || activeSubPromptCacheItems.length > 0;
  const shouldRenderFieldPanel = (hasSubNav ? hasSubFieldContent : hasSectionFieldContent)
    && !isAiOverview
    && !isAiLocalModels
    && !isAiTaskRouting
    && !isAiReliability
    && !isInvestmentFrameworkView
    && !isTopLevelAdvanced
    && !(isAlertsSection && activeView === 'events')
    && !(activeSection === 'system_security' && (activeView === 'security' || activeView === 'about' || activeView === 'extensions'));
  const showActiveConfigEmptyState = !(
    activeSection === 'overview'
    || activeSection === 'ai_models'
    || activeSection === 'advanced'
    || isInvestmentFrameworkView
    || activeCategory === 'system'
    || (isAlertsSection && activeView === 'events' && eventMonitorItems.length > 0)
    || (activeCategory === 'data_source' && activeSubCategory !== 'providers')
  );
  const activeConfigPanel = (
    <SettingsActiveConfigPanel
      panelKey={`${activeSection}:${activeView}`}
      title={activeConfigPanelTitle}
      description={activeConfigPanelDescription || t('settings.activePanelDescription')}
      shouldRender={shouldRenderFieldPanel}
      showEmptyState={showActiveConfigEmptyState}
      isNotificationChannelsSub={isNotificationChannelsSub}
      isDataProvidersSub={isDataProvidersSub}
      visibleActiveItems={visibleActiveItems}
      subFilteredItems={subFilteredItems}
      activeSubPromptCacheItems={activeSubPromptCacheItems}
      activeFieldGroupOrder={activeFieldGroupOrder}
      fieldGroupIdOf={fieldGroupIdOf}
      fieldGroupOrderOf={fieldGroupOrderOf}
      configuredNotificationChannels={configuredNotificationChannels}
      hasConfiguredNotificationChannelStatus={hasConfiguredNotificationChannelStatus}
      configuredRoutingValues={configuredRoutingValues}
      channelRoutingFieldKeys={CHANNEL_ROUTING_FIELD_KEYS}
      channelRoutingEmptyBanner={channelRoutingEmptyBanner}
      channelRoutingEmptyState={channelRoutingEmptyState}
      channelRoutingOptionFilter={channelRoutingOptionFilter}
      isSaving={isSaving}
      issueByKey={issueByKey}
      allValuesByKey={allValuesByKey}
      persistedValuesByKey={persistedValuesByKey}
      alphasiftEnabled={alphasiftEnabled}
      setDraftValue={setDraftValue}
      applyPartialUpdate={applyPartialUpdate}
      resetDraftKeys={resetDraftKeys}
      activeSaveStatus={groupSaveStates[activeCategory]?.status ?? 'idle'}
      agentModelSummary={agentModelSummary}
      readOnlyDiagnosticForItem={readOnlyDiagnosticForItem}
      activeCategory={activeCategory}
    />
  );
  const activeSaveGroup = activeCategory;
  const activeGroupDirtyCount = pendingGroups.get(activeSaveGroup)?.length ?? 0;
  const saveStatusLabel = (status: SettingsSaveStatus): string => {
    switch (status) {
      case 'dirty': return settingsText.autosaveScheduled;
      case 'scheduled': return settingsText.autosaveScheduled;
      case 'saving': return settingsText.autosaveSaving;
      case 'saved': return settingsText.autosaveSaved;
      case 'failed': return settingsText.autosaveFailed;
      case 'conflicted': return settingsText.autosaveConflicted;
      default: return '';
    }
  };
  const visibleGroupSaveStates = Object.entries(groupSaveStates)
    .filter(([, state]) => state.status !== 'idle');
  const settingsSaveActions = visibleGroupSaveStates.length > 0 || activeGroupDirtyCount > 0 ? (
    <div className="flex flex-wrap items-center justify-end gap-2" aria-live="polite">
      {visibleGroupSaveStates.map(([group, state]) => (
        <span
          key={group}
          className="inline-flex min-h-11 items-center gap-1.5 rounded-md border border-[var(--settings-border)] px-2.5 text-xs text-secondary-text"
        >
          {state.status === 'saved' ? (
            <CheckCircle2 className="h-4 w-4 text-success" aria-hidden="true" />
          ) : state.status === 'failed' || state.status === 'conflicted' ? (
            <CircleAlert className="h-4 w-4 text-danger" aria-hidden="true" />
          ) : (
            <Clock className="h-4 w-4 text-warning" aria-hidden="true" />
          )}
          <span>{getCategoryTitle(group as SystemConfigCategory, group, uiLanguage)}: {saveStatusLabel(state.status)}</span>
          {state.status === 'failed' ? (
            <button type="button" className="settings-accent-text inline-flex min-h-11 min-w-11 items-center justify-center px-1 underline" onClick={() => retryAutosaveGroup(group)}>
              {settingsText.autosaveRetry}
            </button>
          ) : null}
          {state.status === 'failed' || state.status === 'conflicted' ? (
            <button type="button" className="inline-flex min-h-11 min-w-11 items-center justify-center px-1 text-danger underline" onClick={() => restoreAutosaveGroup(group)}>
              {settingsText.autosaveRestore}
            </button>
          ) : null}
        </span>
      ))}
      {activeGroupDirtyCount > 0 ? (
        <Button
          type="button"
          variant="secondary"
          size="default"
          onClick={() => setShowResetConfirm(true)}
          disabled={isLoading || groupSaveStates[activeSaveGroup]?.status === 'saving'}
        >
          <RefreshCw className="h-4 w-4" aria-hidden="true" />
          {settingsText.autosaveResetGroup}
        </Button>
      ) : null}
    </div>
  ) : null;

  return (
    <AppPage className="settings-page pb-6">
      <div className="mb-4">
        <PageHeader
          title={t('settings.pageTitle')}
          description={t('settings.pageDescription')}
          actions={settingsSaveActions}
        />

        {saveError ? (
          <ApiErrorAlert
            className="mt-3"
            error={saveError}
            actionLabel={retryAction === 'save' && lastSaveGroupRef.current ? settingsText.autosaveRetry : undefined}
            onAction={retryAction === 'save' && lastSaveGroupRef.current
              ? () => retryAutosaveGroup(lastSaveGroupRef.current!)
              : undefined}
          />
        ) : null}

        {conflictState ? (
          <SettingsConflictPanel
            fields={conflictState.fields}
            onResolveField={resolveSettingsConflict}
            onResolveAll={resolveAllSettingsConflicts}
          />
        ) : null}
      </div>

      {loadError && activeSection !== SETTINGS_SECTION_IDS.usage ? (
        <ApiErrorAlert
          error={loadError}
          actionLabel={retryAction === 'load' ? t('common.retry') : t('settings.reload')}
          onAction={() => void retry()}
          className="mb-4"
        />
      ) : null}

      {isLoading && activeSection !== SETTINGS_SECTION_IDS.usage ? (
        <SettingsLoading />
      ) : (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-[220px_minmax(0,1fr)]">
          <aside className="lg:sticky lg:top-4 lg:self-start space-y-3">
            <SettingsSectionNav
              activeSection={activeSection}
              onSelectSection={(section) => selectSectionView(section, getDefaultView(section))}
              onMobileSelectSection={selectSectionFromMobile}
              sectionStatus={settingsSectionStatus}
              language={uiLanguage}
              navLabel={t('settings.categoryNavTitle')}
              beginnerMode={beginnerMode}
              advancedRevealed={advancedRevealed}
              onRevealAdvanced={() => setAdvancedRevealed(true)}
            />
            <SettingsModeToggle
              mode={settingsMode}
              onModeChange={handleSettingsModeChange}
              language={uiLanguage}
            />
          </aside>

          <section ref={contentRegionRef} tabIndex={-1} className="space-y-4 outline-none">
            {activeSection === SETTINGS_SECTION_IDS.usage ? (
              <TokenUsagePage embedded />
            ) : (
              <>
                <SettingsViewTabs
                  section={activeSection}
                  activeView={activeView}
                  onSelectView={(view) => selectSectionView(activeSection, view)}
                  language={uiLanguage}
                  tabsLabel={t('settings.categoryNavTitle')}
                />
                <SettingsErrorSummary
                  entries={errorSummaryEntries}
                  onJump={jumpToErrorField}
                  language={uiLanguage}
                />
                {hasDirtyRestartRequired ? (
              <SettingsAlert
                variant="warning"
                title={t('settings.fieldRestartRequired')}
                message={t('settings.restartRequiredNotice')}
              />
            ) : null}
            {shouldShowFirstRunSetup && !setupStatus?.isComplete ? (
              <Surface level="interactive" className="flex flex-col gap-2 px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
                <div className="min-w-0">
                  <p className="text-sm font-semibold text-foreground">
                    {settingsText.quickSetup}
                  </p>
                  <p className="mt-0.5 text-xs text-muted-text">
                    {settingsText.quickSetupDescription}
                  </p>
                </div>
                <Button
                  type="button"
                  variant="primary"
                  size="default"
                  className="shrink-0"
                  disabled={isProviderCatalogLoading || providerCatalog.length === 0}
                  onClick={() => setIsWizardOpen(true)}
                >
                  {settingsText.startWizard}
                </Button>
              </Surface>
            ) : null}
            {shouldShowFirstRunSetup ? (
              <FirstRunSetupCard
                status={setupStatus}
                isLoading={isRefreshingSetupStatus}
                error={setupStatusError}
                firstStockCode={firstSetupStockCode}
                isSaving={isSaving}
                isRunningSmoke={isRunningSetupSmoke}
                smokeError={setupSmokeError}
                smokeSuccess={setupSmokeSuccess}
                onRefresh={refreshSetupStatus}
                onSelectCategory={(category) => {
                  const target = legacyToSectionView(category, null);
                  selectSectionView(target.section, target.view);
                }}
                onRunSmoke={handleRunSetupSmoke}
                showStartWizard={Boolean(setupStatus?.isComplete)}
                canStartWizard={!isProviderCatalogLoading && providerCatalog.length > 0}
                startWizardLabel={settingsText.startWizard}
                onStartWizard={() => setIsWizardOpen(true)}
                listSeparator={getUiListSeparator(uiLanguage)}
                t={t}
              />
            ) : null}
            {shouldShowAlphaSiftSettings ? (
              <AlphaSiftSettingsCard
                enabled={alphasiftEnabled}
                configVersion={configVersion}
                maskToken={maskToken}
                disabled={isSaving || isLoading}
                onViewConfigItems={() => selectSectionView('data_sources', 'providers')}
                onAfterChange={async () => {
                  await refreshAfterExternalSave(['ALPHASIFT_ENABLED']);
                }}
              />
            ) : null}
            {activeCategory === 'system' && activeView === 'security' ? (
              <>
                <AuthSettingsCard />
                <OutboundActivityPanel
                  disabled={isSaving || isLoading}
                  t={t}
                  language={uiLanguage}
                />
                <SecurityAuditPanel
                  disabled={isSaving || isLoading}
                  t={t}
                  language={uiLanguage}
                />
              </>
            ) : null}
            {isInvestmentFrameworkView ? <InvestmentFrameworkSettingsCard /> : null}
            {activeCategory === 'system' && activeView === 'runtime' ? (
              <>
                <SchedulerSettingsCard
                  items={rawActiveItems}
                  disabled={isSaving || isLoading}
                  issueByKey={issueByKey}
                  statusRefreshToken={schedulerStatusRefreshToken}
                  onSchedulerStateChange={handleSchedulerRuntimeStateChange}
                  onChange={setDraftValue}
                  t={t}
                  language={uiLanguage}
                />
                <ScheduledTasksPanel
                  disabled={isSaving || isLoading}
                  t={t}
                  language={uiLanguage}
                />
              </>
            ) : null}
            {activeCategory === 'system' && activeView === 'general' ? (
              <SignalScorecardPanel
                publicEnabled={['1', 'true', 'yes', 'on'].includes(
                  String(allValuesByKey.SIGNAL_SCORECARD_PUBLIC_ENABLED ?? '').trim().toLowerCase(),
                )}
                minSamples={(() => {
                  const raw = String(allValuesByKey.SIGNAL_SCORECARD_MIN_SAMPLES ?? '').trim();
                  if (!raw) return 10;
                  const parsed = Number.parseInt(raw, 10);
                  return Number.isFinite(parsed) ? parsed : 10;
                })()}
                disabled={isSaving || isLoading}
                t={t}
                language={uiLanguage}
              />
            ) : null}
            {activeCategory === 'system' && activeView === 'about' ? (
              <SystemAboutCard />
            ) : null}
            {activeCategory === 'system' && activeView === 'extensions' ? <LoadedExtensionsPanel disabled={isSaving || isLoading} t={t} language={uiLanguage} /> : null}
            {isTopLevelAdvanced && activeView === 'backup' ? (
              <>
                <ConfigPresetsPanel configVersion={configVersion} disabled={isSaving || isLoading} t={t} language={uiLanguage} onApplied={async (keys) => { await refreshAfterExternalSave(keys); applyPostSaveEffects(); }} />
                <ConfigBackupCard configVersion={configVersion} hasDirty={hasDirty} disabled={isSaving || isLoading} load={load} onSchedulerKeysImported={() => setSchedulerStatusRefreshToken((c) => c + 1)} onRefreshSetupStatus={() => { void refreshSetupStatus(); }} onRolledBack={async (result) => { await refreshAfterExternalSave(result.updatedKeys); applyPostSaveEffects(); }} onReloadLatest={() => refreshAfterExternalSave([])} />
              </>
            ) : null}
            {activeCategory === 'base' ? (
              <>
                <SettingsSectionCard
                  title={t('settings.intelligentImport')}
                  description={t('settings.intelligentImportDescription')}
                  actions={(
                    <Button
                      type="button"
                      variant="secondary"
                      size="default"
                      aria-haspopup="dialog"
                      onClick={() => setIsIntelligentImportOpen(true)}
                    >
                      {t('settings.openConfigItems')}
                    </Button>
                  )}
                >
                  <p className="text-xs leading-6 text-muted-text">
                    {t('settings.intelligentImportSupportedInputs')}
                    {' · '}
                    {t('settings.intelligentImportHint')}
                  </p>
                </SettingsSectionCard>
                <Modal
                  isOpen={isIntelligentImportOpen}
                  onClose={() => setIsIntelligentImportOpen(false)}
                  title={t('settings.intelligentImport')}
                  description={t('settings.intelligentImportDescription')}
                  size="wide"
                >
                  <IntelligentImport
                    stockListValue={
                      (activeItems.find((i) => i.key === 'STOCK_LIST')?.value as string) ?? ''
                    }
                    configVersion={configVersion}
                    maskToken={maskToken}
                    onMerged={async () => {
                      await refreshAfterExternalSave(['STOCK_LIST']);
                      applyPostSaveEffects();
                    }}
                    disabled={isSaving || isLoading}
                  />
                </Modal>
              </>
            ) : null}
            {isAiOverview ? (
              <AiOverviewCard
                allValuesByKey={allValuesByKey}
                availableRoutes={availableModelRefSet}
                availableModelsError={availableModelsError}
                availableModelsLoading={availableModelsLoading}
                formatModel={formatConfiguredModel}
                onEditRouting={() => selectSectionView('ai_models', 'task_routing')}
                onReloadModels={() => reloadAvailableModels()}
              />
            ) : null}
            {isAiLocalModels ? (
              <LocalModelsWithKronos
                language={uiLanguage}
                onConfigurationChanged={async () => {
                  await refreshAfterExternalSave(LOCAL_MODEL_CONFIG_KEYS);
                  applyPostSaveEffects();
                }}
                kronosItems={itemsByCategory.ai_model || []}
                allValuesByKey={allValuesByKey}
                issueByKey={issueByKey}
                disabled={isSaving || isLoading}
                onKronosChange={setDraftValue}
                readOnlyDiagnostic={(item) => readOnlyDiagnosticForItem(item, 'ai_model')}
              />
            ) : null}
            {isAiTaskRouting ? (
              <AiTaskRoutingCard
                taskRoutingItems={taskRoutingItems}
                fallbackModelsValue={allValuesByKey.LITELLM_FALLBACK_MODELS || ''}
                issueByKey={issueByKey}
                allValuesByKey={allValuesByKey}
                modelSelectorOptions={modelSelectorOptions}
                availableModels={availableModels}
                availableModelsError={availableModelsError}
                availableModelsLoading={availableModelsLoading}
                configuredTaskRoutes={configuredTaskRoutes}
                hasSafeFallbackPlacement={hasSafeFallbackPlacement}
                isSaving={isSaving}
                setDraftValue={setDraftValue}
                resolveConfiguredModelRef={resolveConfiguredModelRef}
                formatConfiguredModel={formatConfiguredModel}
                readOnlyDiagnosticForItem={readOnlyDiagnosticForItem}
                onGoToModelAccess={goToModelAccessFromTaskRouting}
                onEditReliability={() => selectSectionView('ai_models', 'reliability')}
                onReloadModels={() => reloadAvailableModels()}
              />
            ) : null}
            {isAiReliability ? (
              <AiReliabilityCard
                fallbackValue={allValuesByKey.LITELLM_FALLBACK_MODELS || ''}
                fallbackIssues={issueByKey.LITELLM_FALLBACK_MODELS || []}
                fallbackItem={fallbackRoutingItem}
                hasSafeFallbackPlacement={hasSafeFallbackPlacement}
                modelSelectorOptions={modelSelectorOptions}
                primaryRoute={resolveConfiguredModelRef(allValuesByKey.LITELLM_MODEL || '')}
                allValuesByKey={allValuesByKey}
                isSaving={isSaving}
                setDraftValue={setDraftValue}
                resolveConfiguredModelRef={resolveConfiguredModelRef}
              />
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
                        readOnlyDiagnostic={readOnlyDiagnosticForItem(item, categoryByKey[item.key])}
                      />
                    ))}
                  </form>
                ) : null}
              </SettingsSectionCard>
            ) : null}
            {activeCategory === 'ai_model' && !isAiOverview && !isAiLocalModels && !isAiTaskRouting && !isAiReliability && !isTopLevelAdvanced ? (
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
                    {searchParams.get(SETTINGS_ROUTE_QUERY_KEYS.source) === 'task_routing' ? (
                      <Button type="button" variant="secondary" onClick={returnToTaskRouting}>
                        {settingsText.returnTaskRouting}
                      </Button>
                    ) : null}
                    <Button
                      type="button"
                      variant="primary"
                      disabled={isSaving || isLoading || isProviderCatalogLoading || Boolean(providerCatalogError) || providerConnectionSchemaUnavailable || Boolean(channelsOverriddenByMode) || hasUnsafeModelAccessSchema}
                      onClick={() => setLlmChannelAddSignal((signal) => signal + 1)}
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
                  onDraftItemsChange={handleLlmChannelDraftItemsChange}
                  onValidityChange={handleLlmChannelValidityChange}
                  resetSignal={llmChannelResetSignal}
                  addSignal={llmChannelAddSignal}
                  focusFieldRequest={llmFocusFieldRequest}
                  disabled={isSaving || isLoading || isProviderCatalogLoading || Boolean(providerCatalogError) || (providerConnectionSchemaUnavailable && !providerConnectionSchemaAllowsInspection) || hasUnsafeModelAccessSchema}
                  catalogUnavailable={Boolean(providerCatalogError)}
                  onReloadCatalog={() => reloadProviderCatalog()}
                  overriddenByMode={channelsOverriddenByMode}
                  onViewDiagnostics={() => selectSectionView('advanced', 'raw_config')}
                  taskModelRefs={taskModelRefs}
                  onManageModels={() => selectSectionView('ai_models', 'task_routing')}
                  onReplaceModelReferences={replaceModelReferences}
                />
              </section>
            ) : null}
            {activeCategory === 'system' && activeView === 'security' && passwordChangeable ? (
              <ChangePasswordCard />
            ) : null}
            {activeCategory === 'notification' && activeSubCategory === 'channels' ? (
              <SettingsPanelErrorBoundary
                title={t('settings.notificationTest')}
                resetKey={`notification-test:${configVersion}`}
                diagnosticHint={settingsPanelDiagnosticHint}
              >
                <NotificationTestPanel
                  items={rawActiveItems.map((item) => ({ key: item.key, value: String(item.value ?? '') }))}
                  maskToken={maskToken}
                  disabled={isSaving || isLoading}
                />
              </SettingsPanelErrorBoundary>
            ) : null}
            {shouldGuardActiveConfigPanel && hasActiveConfigItems ? (
              <SettingsPanelErrorBoundary
                title={activeConfigPanelErrorTitle}
                resetKey={`${activeCategory}:${activeSubCategory ?? ''}:${configVersion}`}
                diagnosticHint={settingsPanelDiagnosticHint}
              >
                {activeConfigPanel}
              </SettingsPanelErrorBoundary>
            ) : activeConfigPanel}
            {activeCategory === 'data_source' && activeView === 'intelligence' ? (
              <SettingsPanelErrorBoundary
                title={t('settings.pageTitle')}
                resetKey={`intelligence:${configVersion}`}
                diagnosticHint={settingsPanelDiagnosticHint}
              >
                <div className="mt-2">
                  <IntelligenceSourcesPanel />
                </div>
              </SettingsPanelErrorBoundary>
            ) : null}
            {isAlertsSection && activeView === 'events' && eventMonitorItems.length > 0 ? (
              <SettingsSectionCard
                title={settingsText.eventMonitor}
                description={settingsText.eventMonitorDescription}
              >
                <form
                  className="overflow-hidden rounded-lg border border-[var(--settings-border)] bg-[var(--settings-surface)]"
                  onSubmit={(event) => event.preventDefault()}
                >
                  {eventMonitorItems.map((item) => (
                    <SettingsField
                      key={item.key}
                      item={item}
                      value={item.value}
                      disabled={isSaving}
                      onChange={setDraftValue}
                      issues={issueByKey[item.key] || []}
                      requirement={resolveFieldRequirement(item.schema?.contract, allValuesByKey)}
                      dependencyLocked={!isFieldEnabledByContract(item.schema?.contract, allValuesByKey)}
                      readOnlyDiagnostic={readOnlyDiagnosticForItem(item, 'agent')}
                    />
                  ))}
                </form>
              </SettingsSectionCard>
                ) : null}
              </>
            )}
          </section>
        </div>
      )}

      {toast ? (
        <ToastViewport>
          <div
            className="pointer-events-auto"
            onMouseEnter={() => setIsToastPaused(true)}
            onMouseLeave={() => setIsToastPaused(false)}
            onFocusCapture={() => setIsToastPaused(true)}
            onBlurCapture={(event) => {
              if (!event.currentTarget.contains(event.relatedTarget as Node | null)) {
                setIsToastPaused(false);
              }
            }}
          >
            {toast.type === 'success'
              ? (
                  <SettingsAlert
                    title={t('settings.actionSuccess')}
                    message={toast.message}
                    variant="success"
                  />
                )
              : <ApiErrorAlert error={toast.error} />}
          </div>
        </ToastViewport>
      ) : null}
      <ConfirmDialog
        isOpen={showResetConfirm}
        title={t('settings.resetConfirmTitle')}
        message={t('settings.resetConfirmMessage', { count: activeGroupDirtyCount })}
        confirmText={t('settings.resetConfirmContinue')}
        cancelText={t('common.cancel')}
        onConfirm={() => {
          setShowResetConfirm(false);
          restoreAutosaveGroup(activeSaveGroup);
        }}
        onCancel={() => {
          setShowResetConfirm(false);
        }}
      />
      <ConfirmDialog
        isOpen={leaveBlocker.state === 'blocked'}
        title={t('settings.leaveConfirmTitle')}
        message={t('settings.leaveConfirmMessage', { count: leaveGuardCount })}
        confirmText={t('settings.leaveConfirmContinue')}
        cancelText={t('common.cancel')}
        onConfirm={() => {
          leaveBlocker.proceed?.();
        }}
        onCancel={() => {
          leaveBlocker.reset?.();
        }}
      />
      <SettingsOnboardingHosts
        isWizardOpen={isWizardOpen}
        isAgentOnboardingOpen={isAgentOnboardingOpen}
        setIsWizardOpen={setIsWizardOpen}
        setIsAgentOnboardingOpen={setIsAgentOnboardingOpen}
        handleWizardComplete={handleWizardComplete}
        isSaving={isSaving}
        uiLanguage={uiLanguage}
        existingChannelNames={existingChannelNames}
        providerCatalog={providerCatalog}
        providerConnectionFields={providerConnectionFields}
        providerEmptyApiKeyHosts={providerEmptyApiKeyHosts}
        modelSelectorOptions={modelSelectorOptions}
        initialFallbackModels={(allValuesByKey.LITELLM_FALLBACK_MODELS || '').split(',').map((entry) => resolveConfiguredModelRef(entry)).filter(Boolean).join(',')}
        initialVisionModel={resolveConfiguredModelRef(allValuesByKey.VISION_MODEL || '')}
        onViewRouting={() => { setIsWizardOpen(false); selectSectionView('ai_models', 'task_routing'); }}
        onLocalModelConfigurationChanged={async () => { await refreshAfterExternalSave(LOCAL_MODEL_CONFIG_KEYS); applyPostSaveEffects(); }}
        onAgentApplied={() => { void refreshAfterExternalSave([]); applyPostSaveEffects(); }}
        setupStatus={setupStatus}
        t={t}
      />
    </AppPage>
  );
};

export default SettingsPage;
