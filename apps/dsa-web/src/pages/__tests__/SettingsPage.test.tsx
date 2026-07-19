import React from 'react';
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { resolveWebBuildInfo } from '../../utils/constants';
import type { LlmConnectionFieldSchema, SetupStatusResponse } from '../../types/systemConfig';
import { getDefaultSubCategory } from '../../components/settings/settingsSubCategories';
import { legacyToSectionView } from '../../components/settings/settingsInformationArchitecture';
import { UiLanguageProvider } from '../../contexts/UiLanguageContext';
import { loadUiLanguageTranslations } from '../../i18n/translations';
import { getFieldTitle } from '../../utils/systemConfigI18n';
import SettingsPage from '../SettingsPage';

const {
  analyzeAsync,
  exportEnv,
  getSchedulerStatus,
  getSetupStatus,
  getLlmProviderCatalog,
  getLlmAvailableModels,
  importEnv,
  runSchedulerNow,
  updateSystemConfig,
  alphasiftEnable,
  alphasiftInstall,
  notifyAlphaSiftConfigChanged,
  notifySystemConfigChanged,
  desktopCheckForUpdates,
  desktopGetUpdateState,
  desktopInstallDownloadedUpdate,
  desktopOnUpdateStateChange,
  desktopOpenReleasePage,
  load,
  clearToast,
  setActiveCategory,
  selectTab,
  save,
  resetDraft,
  resetDraftKeys,
  setDraftValue,
  applyPartialUpdate,
  getChangedItems,
  refreshAfterExternalSave,
  refreshStatus,
  settingsPanelErrorBoundary,
  useAuthMock,
  useSystemConfigMock,
  webBuildInfoMock,
  showToast,
  dismissToast,
  clearToasts,
} = vi.hoisted(() => ({
  analyzeAsync: vi.fn(),
  exportEnv: vi.fn(),
  getSchedulerStatus: vi.fn(),
  getSetupStatus: vi.fn(),
  getLlmProviderCatalog: vi.fn(),
  getLlmAvailableModels: vi.fn(),
  importEnv: vi.fn(),
  runSchedulerNow: vi.fn(),
  updateSystemConfig: vi.fn(),
  alphasiftEnable: vi.fn(),
  alphasiftInstall: vi.fn(),
  notifyAlphaSiftConfigChanged: vi.fn(),
  notifySystemConfigChanged: vi.fn(),
  desktopCheckForUpdates: vi.fn(),
  desktopGetUpdateState: vi.fn(),
  desktopInstallDownloadedUpdate: vi.fn(),
  desktopOnUpdateStateChange: vi.fn(),
  desktopOpenReleasePage: vi.fn(),
  load: vi.fn(),
  clearToast: vi.fn(),
  setActiveCategory: vi.fn(),
  selectTab: vi.fn(),
  save: vi.fn(),
  resetDraft: vi.fn(),
  resetDraftKeys: vi.fn(),
  setDraftValue: vi.fn(),
  applyPartialUpdate: vi.fn(),
  getChangedItems: vi.fn(),
  refreshAfterExternalSave: vi.fn(),
  refreshStatus: vi.fn(),
  settingsPanelErrorBoundary: vi.fn(),
  useAuthMock: vi.fn(),
  useSystemConfigMock: vi.fn(),
  showToast: vi.fn(() => 'settings-toast'),
  dismissToast: vi.fn(),
  clearToasts: vi.fn(),
  webBuildInfoMock: {
    version: '3.11.0',
    rawVersion: '3.11.0',
    buildId: 'build-20260329-021530Z',
    buildTime: '2026-03-29T02:15:30.000Z',
    isFallbackVersion: false,
  },
}));

vi.mock('../../components/common/toastContext', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../components/common/toastContext')>();
  return {
    ...actual,
    useToast: () => ({ showToast, dismissToast, clearToasts }),
  };
});

const mockedAnchorClick = vi.fn();

const TEST_CONNECTION_NAME_FIELD: LlmConnectionFieldSchema = {
  key: 'connection_name', dataType: 'string', isSensitive: false, isRequired: true, contract: { requirement: 'required' },
};
const TEST_PROVIDER_ID_FIELD: LlmConnectionFieldSchema = {
  key: 'provider_id', dataType: 'string', isSensitive: false, isRequired: true, contract: { requirement: 'required' },
};
const TEST_MODELS_FIELD: LlmConnectionFieldSchema = {
  key: 'models', dataType: 'array', isSensitive: false, isRequired: false, contract: { requirement: 'optional' },
};

const TEST_HIDDEN_INHERITED_CONTRACT: LlmConnectionFieldSchema['contract'] = {
  requirement: 'inherited',
  visibleWhen: [{ key: '__test_hidden', operator: 'equals', value: 'true' }],
};

const TEST_CONNECTION_CORE_FIELDS: LlmConnectionFieldSchema[] = [
  TEST_CONNECTION_NAME_FIELD,
  { key: 'display_name', dataType: 'string', isSensitive: false, isRequired: false, contract: TEST_HIDDEN_INHERITED_CONTRACT },
  TEST_PROVIDER_ID_FIELD,
  { key: 'protocol', dataType: 'string', isSensitive: false, isRequired: false, contract: TEST_HIDDEN_INHERITED_CONTRACT },
  { key: 'base_url', dataType: 'string', isSensitive: false, isRequired: false, contract: TEST_HIDDEN_INHERITED_CONTRACT },
  { key: 'api_key', dataType: 'string', isSensitive: true, isRequired: false, contract: TEST_HIDDEN_INHERITED_CONTRACT },
  { key: 'api_keys', dataType: 'array', isSensitive: true, isRequired: false, contract: TEST_HIDDEN_INHERITED_CONTRACT },
  TEST_MODELS_FIELD,
  { key: 'extra_headers', dataType: 'json', isSensitive: true, isRequired: false, contract: TEST_HIDDEN_INHERITED_CONTRACT },
  { key: 'enabled', dataType: 'boolean', isSensitive: false, isRequired: false, contract: TEST_HIDDEN_INHERITED_CONTRACT },
];

function withTestConnectionCoreFields(
  fields: LlmConnectionFieldSchema[],
): LlmConnectionFieldSchema[] {
  const byKey = new Map(
    [...TEST_CONNECTION_CORE_FIELDS, ...fields].map((field) => [field.key, field]),
  );
  return Array.from(byKey.values());
}

vi.mock('../../hooks', () => ({
  useAuth: () => useAuthMock(),
  useSystemConfig: () => useSystemConfigMock(),
}));

type BlockerArgs = { currentLocation: { pathname: string }; nextLocation: { pathname: string } };

const routerBlockerMock = vi.hoisted(() => ({
  state: 'unblocked' as 'unblocked' | 'blocked',
  proceed: vi.fn(),
  reset: vi.fn(),
  shouldBlock: null as null | ((args: unknown) => boolean),
}));

const routerSearchParamsMock = vi.hoisted(() => {
  const params = new URLSearchParams();
  const setParams = vi.fn();
  return { params, setParams };
});
vi.mock('react-router-dom', async (importOriginal) => ({
  ...(await importOriginal<typeof import('react-router-dom')>()),
  useBlocker: (shouldBlock: (args: unknown) => boolean) => {
    routerBlockerMock.shouldBlock = shouldBlock;
    return routerBlockerMock;
  },
  useSearchParams: () => [routerSearchParamsMock.params, routerSearchParamsMock.setParams] as const,
}));

vi.mock('../../api/systemConfig', () => ({
  systemConfigApi: {
    exportEnv: (...args: unknown[]) => exportEnv(...args),
    getSchedulerStatus: (...args: unknown[]) => getSchedulerStatus(...args),
    getSetupStatus: (...args: unknown[]) => getSetupStatus(...args),
    getLlmConfigModeStatus: () => Promise.resolve({
      requestedMode: 'auto',
      effectiveMode: 'channels',
      detectedSources: ['channels'],
      overriddenSources: [],
      issues: [],
    }),
    getLlmProviderCatalog: (...args: unknown[]) => getLlmProviderCatalog(...args),
    getLlmAvailableModels: (...args: unknown[]) => getLlmAvailableModels(...args),
    importEnv: (...args: unknown[]) => importEnv(...args),
    runSchedulerNow: (...args: unknown[]) => runSchedulerNow(...args),
    update: (...args: unknown[]) => updateSystemConfig(...args),
  },
}));

vi.mock('../../api/analysis', () => ({
  analysisApi: {
    analyzeAsync: (...args: unknown[]) => analyzeAsync(...args),
  },
}));

vi.mock('../../api/alphasift', () => ({
  alphasiftApi: {
    enable: (...args: unknown[]) => alphasiftEnable(...args),
    install: (...args: unknown[]) => alphasiftInstall(...args),
  },
  notifyAlphaSiftConfigChanged: (...args: unknown[]) => notifyAlphaSiftConfigChanged(...args),
  notifySystemConfigChanged: (...args: unknown[]) => notifySystemConfigChanged(...args),
}));

vi.mock('../../utils/constants', async () => {
  const actual = await vi.importActual<typeof import('../../utils/constants')>('../../utils/constants');
  return {
    ...actual,
    WEB_BUILD_INFO: webBuildInfoMock,
  };
});

vi.mock('../../components/settings', async () => ({
  ...(await import('../../components/settings/notificationFieldGroups')),
  ...(await import('../../components/settings/categoryFieldGroups')),
  ...(await import('../../components/settings/settingsSubCategories')),
  ...(await import('../../components/settings/notificationChannels')),
  ...(await import('../../components/settings/FirstRunSetupCard')),
  ...(await import('../../components/settings/SchedulerSettingsCard')),
  NotificationChannelsPanel: ({ items }: { items: Array<{ key: string }> }) => (
    <div>
      {items.map((item) => (
        <div key={item.key}>{item.key}</div>
      ))}
    </div>
  ),
  DataProvidersPanel: ({ items }: { items: Array<{ key: string }> }) => (
    <div data-testid="data-providers-panel">
      {items.map((item) => (
        <div key={item.key}>{item.key}</div>
      ))}
    </div>
  ),
  AuthSettingsCard: () => <div>认证与登录保护</div>,
  ChangePasswordCard: () => <div>修改密码</div>,
  IntelligentImport: ({ onMerged }: { onMerged: (value: string) => void }) => (
    <button type="button" onClick={() => onMerged('SZ000001,SZ000002')}>
      merge stock list
    </button>
  ),
  LLMChannelEditor: ({
    items,
    onDraftItemsChange,
    onValidityChange,
    taskModelRefs,
    onReplaceModelReferences,
    focusFieldRequest,
    disabled,
    catalogUnavailable,
  }: {
    items: Array<{ key: string; value: string }>;
    onDraftItemsChange?: (items: Array<{ key: string; value: string }>) => void;
    onValidityChange?: (valid: boolean) => void;
    taskModelRefs?: Array<{ key?: string; label: string; route: string }>;
    onReplaceModelReferences?: (replacements: Array<{
      fromRoute: string;
      toRoute: string;
      references: Array<{ key?: string; label: string; route: string }>;
    }>) => void;
    focusFieldRequest?: { requestId: number; key: string } | null;
    disabled?: boolean;
    catalogUnavailable?: boolean;
  }) => {
    const [inspectionOpen, setInspectionOpen] = React.useState(false);
    React.useEffect(() => () => onValidityChange?.(true), [onValidityChange]);
    return (
      <div>
      <div
        data-testid="llm-channel-editor-items"
        data-disabled={disabled ? 'true' : 'false'}
        data-catalog-unavailable={catalogUnavailable ? 'true' : 'false'}
      >
        {items.map((item) => item.key).join(',')}
      </div>
      <div data-testid="llm-channel-focus-request">{focusFieldRequest?.key ?? ''}</div>
      <button
        type="button"
        disabled={disabled}
        onClick={() => setInspectionOpen(true)}
      >
        inspect existing connection
      </button>
      {inspectionOpen ? <div role="dialog" aria-label="existing connection inspection" /> : null}
      <button
        type="button"
        onClick={() => onDraftItemsChange?.([
          { key: 'LLM_CHANNELS', value: 'draft,backup' },
          { key: 'LITELLM_MODEL', value: 'openai/draft-model' },
          { key: 'GENERATION_BACKEND', value: 'codex_cli' },
        ])}
      >
        emit llm draft
      </button>
      <button
        type="button"
        onClick={() => onDraftItemsChange?.([
          { key: 'LLM_CHANNELS', value: 'draft,backup' },
          { key: 'LITELLM_MODEL', value: 'openai/draft-model' },
        ])}
      >
        emit connection draft
      </button>
      <button
        type="button"
        onClick={() => onDraftItemsChange?.([
          { key: 'LLM_CHANNELS', value: 'deepseek' },
          { key: 'LLM_DEEPSEEK_PROVIDER', value: 'deepseek' },
        ])}
      >
        emit schema-valid connection draft
      </button>
      <button type="button" onClick={() => onValidityChange?.(false)}>
        mark llm draft invalid
      </button>
      <button
        type="button"
        onClick={() => onReplaceModelReferences?.([{
          fromRoute: 'deepseek/shared-model',
          toRoute: 'openai/replacement-model',
          references: (taskModelRefs ?? []).filter((reference) => reference.route === 'deepseek/shared-model'),
        }])}
      >
        replace model references
      </button>
      <button
        type="button"
        onClick={() => onReplaceModelReferences?.([{
          fromRoute: 'openai/gpt-4o-mini',
          toRoute: 'openai/gpt-5.5',
          references: (taskModelRefs ?? []).filter((reference) => reference.key === 'AGENT_LITELLM_MODEL'),
        }])}
      >
        replace bare Agent reference
      </button>
      </div>
    );
  },
  GenerationBackendStatusPanel: ({ items }: { items: Array<{ key: string; value: string }> }) => (
    <div data-testid="generation-backend-status-items">
      {items.map((item) => `${item.key}=${item.value}`).join('|')}
    </div>
  ),
  ModelFallbackEditor: (await import('../../components/settings/ModelFallbackEditor')).ModelFallbackEditor,
  LLMConfigModeBanner: ({ onMigrated }: { onMigrated?: () => void }) => (
    <div data-testid="llm-config-mode-banner">
      <button type="button" onClick={() => onMigrated?.()}>trigger migration</button>
    </div>
  ),
  NotificationTestPanel: ({ items }: { items: Array<{ key: string; value: string }> }) => (
    <div>通知测试面板:{items.map((item) => item.key).join(',')}</div>
  ),
  SettingsAlert: ({
    title,
    message,
    actionLabel,
    onAction,
  }: {
    title: string;
    message: string;
    actionLabel?: string;
    onAction?: () => void;
  }) => (
    <div>
      <span>{title}</span>
      <span>{message}</span>
      {actionLabel ? (
        <button type="button" onClick={onAction}>
          {actionLabel}
        </button>
      ) : null}
    </div>
  ),
  SettingsField: ({
    item,
    value,
    disabled,
    dependencyLocked,
    readOnlyDiagnostic,
    enumOptionFilter,
    enumEmptyState,
  }: {
    item: {
      key: string;
      schema?: {
        description?: string;
        options?: Array<string | { label: string; value: string }>;
      };
    };
    value?: string;
    disabled?: boolean;
    dependencyLocked?: boolean;
    readOnlyDiagnostic?: string;
    enumOptionFilter?: (optionValue: string) => boolean;
    enumEmptyState?: React.ReactNode;
  }) => {
    // Mirror the real component's option filtering just enough to assert the
    // page-level wiring: filtered options hide, already-selected values stay,
    // and a fully-filtered field falls back to the empty state.
    const selectedValues = (value ?? '').split(',').map((entry) => entry.trim()).filter(Boolean);
    const visibleOptions = (item.schema?.options ?? []).filter((option) => {
      const optionValue = typeof option === 'string' ? option : option.value;
      return !enumOptionFilter || enumOptionFilter(optionValue) || selectedValues.includes(optionValue);
    });
    if (enumEmptyState && enumOptionFilter && visibleOptions.length === 0 && selectedValues.length === 0) {
      return <div data-testid={`settings-field-${item.key}`}>{enumEmptyState}</div>;
    }
    return (
      <div
        data-testid={`settings-field-${item.key}`}
        data-readonly={disabled || dependencyLocked || Boolean(readOnlyDiagnostic) ? 'true' : 'false'}
      >
        <div>{item.key}</div>
        {readOnlyDiagnostic ? <p>{readOnlyDiagnostic}</p> : null}
        {item.schema?.description ? <p>{item.schema.description}</p> : null}
        {visibleOptions.map((option) => {
          const label = typeof option === 'string' ? option : option.label;
          const optionValue = typeof option === 'string' ? option : option.value;
          return <span key={`${item.key}-${optionValue}`}>{label}</span>;
        })}
      </div>
    );
  },
  SettingsLoading: () => <div>loading</div>,
  SettingsPanelErrorBoundary: ({
    title,
    diagnosticHint,
    children,
  }: {
    title: string;
    diagnosticHint?: React.ReactNode;
    children: React.ReactNode;
  }) => {
    settingsPanelErrorBoundary(title);
    return (
      <>
        {diagnosticHint ? <div>{diagnosticHint}</div> : null}
        {children}
      </>
    );
  },
  SettingsSectionCard: ({
    title,
    description,
    children,
  }: {
    title: string;
    description?: string;
    children: React.ReactNode;
  }) => (
    <section>
      <h2>{title}</h2>
      {description ? <p>{description}</p> : null}
      {children}
    </section>
  ),
  FirstRunWizard: ({
    onComplete,
    onClose,
  }: {
    onComplete: (items: Array<{ key: string; value: string }>) => void;
    onClose: () => void;
  }) => (
    <div role="dialog" aria-label="first-run-wizard">
      <button
        type="button"
        onClick={() => onComplete([
          { key: 'LLM_CHANNELS', value: 'deepseek' },
          { key: 'LLM_DEEPSEEK_API_KEY', value: 'sk-wizard' },
        ])}
      >
        wizard apply
      </button>
      <button
        type="button"
        onClick={() => onComplete([
          { key: 'LLM_CHANNELS', value: 'deepseek' },
          { key: 'LLM_DEEPSEEK_PROVIDER', value: 'deepseek' },
          { key: 'LLM_DEEPSEEK_BASE_URL', value: 'https://injected.example/v1' },
        ])}
      >
        wizard inject read-only field
      </button>
      <button
        type="button"
        onClick={() => onComplete([
          { key: 'LLM_CHANNELS', value: 'unknown' },
          { key: 'LLM_UNKNOWN_DISPLAY_NAME', value: 'Unknown Provider' },
          { key: 'LLM_UNKNOWN_PROVIDER', value: 'unknown-provider' },
          { key: 'LLM_UNKNOWN_PROTOCOL', value: 'openai' },
          { key: 'LLM_UNKNOWN_ENABLED', value: 'true' },
        ])}
      >
        wizard apply unknown provider
      </button>
      <button type="button" onClick={onClose}>wizard close</button>
    </div>
  ),
  SettingsErrorSummary: ({
    entries,
    onJump,
  }: {
    entries: Array<{ key: string; label: string; message: string; section: string; view: string }>;
    onJump: (entry: { key: string; label: string; message: string; section: string; view: string }) => void;
  }) => (
    entries.length ? (
      <div role="alert">
        <p>{`有 ${entries.length} 项配置需要修正`}</p>
        <ul>
          {entries.map((entry) => (
            <li key={entry.key}>
              <button type="button" aria-label={`前往修正: ${entry.label}`} onClick={() => onJump(entry)}>
                <span>{entry.label}</span>
                <span>{entry.message}</span>
              </button>
            </li>
          ))}
        </ul>
      </div>
    ) : null
  ),
}));

function createDesktopRuntime(overrides: Record<string, unknown> = {}) {
  return {
    version: '3.12.0',
    getUpdateState: desktopGetUpdateState,
    checkForUpdates: desktopCheckForUpdates,
    installDownloadedUpdate: desktopInstallDownloadedUpdate,
    openReleasePage: desktopOpenReleasePage,
    onUpdateStateChange: desktopOnUpdateStateChange,
    ...overrides,
  };
}

const baseCategories = [
  { category: 'system', title: 'System', description: '系统设置', displayOrder: 1, fields: [] },
  { category: 'base', title: 'Base', description: '基础配置', displayOrder: 2, fields: [] },
  { category: 'ai_model', title: 'AI', description: '模型配置', displayOrder: 3, fields: [] },
  { category: 'notification', title: 'Notification', description: '通知配置', displayOrder: 4, fields: [] },
  { category: 'agent', title: 'Agent', description: 'Agent 配置', displayOrder: 5, fields: [] },
];

type ConfigState = {
  categories: Array<{ category: string; title: string; description: string; displayOrder: number; fields: [] }>;
  itemsByCategory: Record<string, Array<Record<string, unknown>>>;
  issueByKey: Record<string, unknown[]>;
  activeCategory: string;
  activeSubCategory: string | null;
  selectCategory: typeof setActiveCategory;
  selectTab: typeof selectTab;
  hasDirty: boolean;
  dirtyCount: number;
  dirtyKeys: string[];
  toast: null;
  clearToast: typeof clearToast;
  isLoading: boolean;
  isSaving: boolean;
  loadError: null;
  saveError: null;
  retryAction: null;
  conflictState?: {
    fields: Array<{
      key: string;
      base: string;
      server: string;
      local: string;
      isSensitive: boolean;
      title?: string;
      category?: string;
    }>;
    serverVersion: string;
  } | null;
  resolveConflictField?: ReturnType<typeof vi.fn>;
  resolveAllConflicts?: ReturnType<typeof vi.fn>;
  load: typeof load;
  retry: ReturnType<typeof vi.fn>;
  save: typeof save;
  resetDraft: typeof resetDraft;
  setDraftValue: typeof setDraftValue;
  applyPartialUpdate: typeof applyPartialUpdate;
  getChangedItems: () => Array<{ key: string; value: string }>;
  refreshAfterExternalSave: typeof refreshAfterExternalSave;
  configVersion: string;
  maskToken: string;
  configuredNotificationChannels: string[] | null;
};

type ConfigOverride = Partial<ConfigState>;

const defaultItemsByCategory: Record<string, Array<Record<string, unknown>>> = {
      system: [
        {
          key: 'ADMIN_AUTH_ENABLED',
          value: 'true',
          rawValueExists: true,
          isMasked: false,
          schema: {
            key: 'ADMIN_AUTH_ENABLED',
            category: 'system',
            dataType: 'boolean',
            uiControl: 'switch',
            isSensitive: false,
            isRequired: false,
            isEditable: true,
            options: [],
            validation: {},
            displayOrder: 1,
          },
        },
      ],
      base: [
        {
          key: 'STOCK_LIST',
          value: 'SH600000',
          rawValueExists: true,
          isMasked: false,
          schema: {
            key: 'STOCK_LIST',
            category: 'base',
            dataType: 'string',
            uiControl: 'textarea',
            isSensitive: false,
            isRequired: false,
            isEditable: true,
            options: [],
            validation: {},
            displayOrder: 1,
          },
        },
      ],
      ai_model: [
        {
          key: 'LLM_CHANNELS',
          value: 'primary',
          rawValueExists: true,
          isMasked: false,
          schema: {
            key: 'LLM_CHANNELS',
            category: 'ai_model',
            dataType: 'string',
            uiControl: 'textarea',
            isSensitive: false,
            isRequired: false,
            isEditable: true,
            options: [],
            validation: {},
            displayOrder: 1,
          },
        },
      ],
      agent: [
        {
          key: 'AGENT_ORCHESTRATOR_TIMEOUT_S',
          value: '600',
          rawValueExists: true,
          isMasked: false,
          schema: {
            key: 'AGENT_ORCHESTRATOR_TIMEOUT_S',
            category: 'agent',
            dataType: 'integer',
            uiControl: 'number',
            isSensitive: false,
            isRequired: false,
            isEditable: true,
            options: [],
            validation: {},
            displayOrder: 1,
          },
        },
      ],
      notification: [
        {
          key: 'WECHAT_WEBHOOK_URL',
          value: 'https://qyapi.example.com/hook',
          rawValueExists: true,
          isMasked: false,
          schema: {
            key: 'WECHAT_WEBHOOK_URL',
            category: 'notification',
            dataType: 'string',
            uiControl: 'password',
            isSensitive: true,
            isRequired: false,
            isEditable: true,
            options: [],
            validation: {},
            displayOrder: 1,
          },
        },
      ],
};

function buildSystemConfigState(overrides: ConfigOverride = {}) {
  const activeCategory = overrides.activeCategory ?? 'system';
  const itemsByCategory = overrides.itemsByCategory ?? defaultItemsByCategory;
  const activeSubCategory = overrides.activeSubCategory !== undefined
    ? overrides.activeSubCategory
    : getDefaultSubCategory(activeCategory, itemsByCategory as Record<string, Array<{ key: string }>>);
  // SettingsPage now reads the active tab from the section/view URL. Drive the
  // mocked router params from the requested (category, sub) so tests keep
  // selecting the intended tab via the useSystemConfig override.
  const target = legacyToSectionView(activeCategory, activeSubCategory);
  routerSearchParamsMock.params = new URLSearchParams({ section: target.section, view: target.view });
  return {
    categories: baseCategories,
    itemsByCategory,
    issueByKey: {},
    activeCategory,
    activeSubCategory,
    selectCategory: setActiveCategory,
    selectTab,
    hasDirty: false,
    dirtyCount: 0,
    toast: null,
    clearToast,
    isLoading: false,
    isSaving: false,
    loadError: null,
    saveError: null,
    retryAction: null,
    load,
    retry: vi.fn(),
    save,
    resetDraft,
    resetDraftKeys,
    setDraftValue,
    applyPartialUpdate,
    getChangedItems: () => [],
    refreshAfterExternalSave,
    configVersion: 'v1',
    maskToken: '******',
    configuredNotificationChannels: [],
    ...overrides,
  };
}

function useAdvancedConfigState(overrides: ConfigOverride = {}) {
  const state = buildSystemConfigState({ ...overrides, activeCategory: 'ai_model' });
  useSystemConfigMock.mockReturnValue(state);
  routerSearchParamsMock.params = new URLSearchParams({ section: 'advanced', view: 'raw_config' });
  return state;
}

function createDeferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((promiseResolve, promiseReject) => {
    resolve = promiseResolve;
    reject = promiseReject;
  });
  return { promise, resolve, reject };
}

async function expectConnectionDraftAutosaveBlockedBySchema(
  connectionFields: LlmConnectionFieldSchema[],
): Promise<void> {
  getLlmProviderCatalog.mockResolvedValueOnce({
    providers: [
      { id: 'deepseek', label: 'DeepSeek', protocol: 'deepseek', defaultBaseUrl: 'https://api.deepseek.com', capabilities: [], requiresApiKey: true, requiresBaseUrl: false, supportsDiscovery: true, isLocal: false, isCustom: false },
    ],
    connectionFields,
  });
  save.mockResolvedValue({ success: true });
  useSystemConfigMock.mockReturnValue(buildSystemConfigState({ activeCategory: 'ai_model' }));

  render(<SettingsPage />);
  await waitFor(() => expect(screen.getByTestId('llm-channel-editor-items'))
    .toHaveAttribute('data-disabled', 'true'));
  fireEvent.click(screen.getByRole('button', { name: 'emit connection draft' }));

  await act(async () => {
    await new Promise((resolve) => window.setTimeout(resolve, 850));
  });
  expect(save).not.toHaveBeenCalled();
}

describe('SettingsPage', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.clearAllMocks();
    // Reset the mocked router params so section/view state does not leak between
    // tests (buildSystemConfigState sets it per render from the tab override).
    routerSearchParamsMock.params = new URLSearchParams();
    routerBlockerMock.state = 'unblocked';
    routerBlockerMock.shouldBlock = null;
    Object.assign(webBuildInfoMock, {
      version: '3.11.0',
      rawVersion: '3.11.0',
      buildId: 'build-20260329-021530Z',
      buildTime: '2026-03-29T02:15:30.000Z',
      isFallbackVersion: false,
    });
    load.mockResolvedValue(true);
    save.mockReset();
    save.mockResolvedValue({ success: true });
    exportEnv.mockResolvedValue({
      content: 'STOCK_LIST=600519\n',
      configVersion: 'v1',
      updatedAt: '2026-03-21T00:00:00Z',
    });
    getSchedulerStatus.mockResolvedValue({
      enabled: true,
      running: false,
      scheduleTimes: ['09:20', '15:10'],
      nextRunAt: '2026-06-21T09:20:00+08:00',
      lastRunAt: null,
      lastSuccessAt: null,
      lastError: null,
    });
    getSetupStatus.mockResolvedValue({
      isComplete: true,
      readyForSmoke: true,
      requiredMissingKeys: [],
      nextStepKey: null,
      checks: [
        {
          key: 'stock_list',
          title: '自选股',
          category: 'base',
          required: true,
          status: 'configured',
          message: '已配置自选股。',
          nextStep: null,
        },
        {
          key: 'llm_channels',
          title: '模型渠道',
          category: 'ai_model',
          required: true,
          status: 'configured',
          message: '已配置模型渠道。',
          nextStep: null,
        },
        {
          key: 'notification',
          title: '通知',
          category: 'notification',
          required: false,
          status: 'optional',
          message: '通知可选。',
          nextStep: null,
        },
      ],
    });
    // clearAllMocks keeps queued mockResolvedValueOnce implementations. A test
    // that unmounts before fetching the Catalog must not leak that response into
    // the next Schema-authority scenario.
    getLlmProviderCatalog.mockReset();
    getLlmProviderCatalog.mockResolvedValue({
      providers: [
        { id: 'deepseek', label: 'DeepSeek', protocol: 'deepseek', defaultBaseUrl: 'https://api.deepseek.com', capabilities: [], requiresApiKey: true, requiresBaseUrl: false, supportsDiscovery: true, isLocal: false, isCustom: false },
      ],
    });
    getLlmAvailableModels.mockResolvedValue({
      models: [
        { route: 'deepseek/deepseek-v4-flash', display: 'deepseek-v4-flash', connection: 'deepseek', provider: 'deepseek' },
        { route: 'deepseek/deepseek-v4-pro', display: 'deepseek-v4-pro', connection: 'deepseek', provider: 'deepseek' },
      ],
    });
    analyzeAsync.mockResolvedValue({
      taskId: 'task-setup-smoke',
      status: 'pending',
      message: 'accepted',
    });
    runSchedulerNow.mockResolvedValue({
      accepted: true,
      running: true,
    });
    importEnv.mockResolvedValue({
      success: true,
      configVersion: 'v2',
      appliedCount: 1,
      skippedMaskedCount: 0,
      reloadTriggered: true,
      updatedKeys: ['STOCK_LIST'],
      warnings: [],
    });
    updateSystemConfig.mockResolvedValue({
      success: true,
      configVersion: 'v2',
      updatedKeys: ['ALPHASIFT_ENABLED'],
      reloadTriggered: true,
    });
    alphasiftInstall.mockResolvedValue({
      installed: true,
      alreadyInstalled: true,
      installSpecIsDefault: true,
    });
    alphasiftEnable.mockResolvedValue(undefined);
    desktopGetUpdateState.mockResolvedValue({
      status: 'idle',
      currentVersion: '3.12.0',
      latestVersion: '',
      message: '',
    });
    desktopCheckForUpdates.mockResolvedValue({
      status: 'up-to-date',
      currentVersion: '3.12.0',
      latestVersion: '3.12.0',
      message: '当前桌面端已是最新版本。',
    });
    desktopInstallDownloadedUpdate.mockResolvedValue(true);
    desktopOpenReleasePage.mockResolvedValue(true);
    desktopOnUpdateStateChange.mockImplementation(() => () => undefined);
    useAuthMock.mockReturnValue({
      authEnabled: true,
      passwordChangeable: true,
      refreshStatus,
    });
    useSystemConfigMock.mockReturnValue(buildSystemConfigState());
    delete (window as { dsaDesktop?: unknown }).dsaDesktop;
    vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:mock');
    vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => undefined);
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(mockedAnchorClick);
  });

  it('renders category navigation and auth settings modules', async () => {
    render(<SettingsPage />);

    expect(await screen.findByRole('heading', { name: '系统设置' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('tab', { name: '认证与登录保护' }));
    expect(screen.getByText('认证与登录保护', { selector: 'div' })).toBeVisible();
    expect(screen.getByText('修改密码')).toBeVisible();
    expect(load).toHaveBeenCalled();
  });

  it('renders first-run setup checks and routes setup actions', async () => {
    useSystemConfigMock.mockReturnValue(buildSystemConfigState({ activeCategory: 'base' }));

    render(<SettingsPage />);

    expect(await screen.findByTestId('first-run-setup-card')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: '首次启动配置检查' })).toBeInTheDocument();
    expect(screen.getByText('自选股')).toBeInTheDocument();
    expect(screen.getAllByText('已配置')).toHaveLength(2);

    const lastSection = () => routerSearchParamsMock.setParams.mock.calls.at(-1)?.[0].get('section');

    fireEvent.click(screen.getByRole('button', { name: '配置模型' }));
    expect(lastSection()).toBe('ai_models');
    fireEvent.click(screen.getByRole('button', { name: '维护自选股' }));
    expect(lastSection()).toBe('overview');
    fireEvent.click(screen.getByRole('button', { name: '配置通知' }));
    expect(lastSection()).toBe('notifications');
  });

  it('keeps first-run setup summary neutral while setup status is loading', async () => {
    getSetupStatus.mockImplementation(() => new Promise(() => undefined));
    useSystemConfigMock.mockReturnValue(buildSystemConfigState({ activeCategory: 'base' }));

    render(<SettingsPage />);

    expect(await screen.findByText('正在检查首次启动配置')).toBeInTheDocument();
    expect(screen.getByText('正在读取配置状态，完成后会显示缺失项和试跑入口。')).toBeInTheDocument();
    expect(screen.queryByText('基础配置已满足最小可用分析')).not.toBeInTheDocument();
    expect(screen.queryByText('还有基础配置需要处理')).not.toBeInTheDocument();
    expect(screen.queryByText('所有必需项已就绪，可运行一次简短分析验证链路。')).not.toBeInTheDocument();
  });

  it('keeps first-run setup summary neutral when setup status fails', async () => {
    getSetupStatus.mockRejectedValue(new Error('setup status unavailable'));
    useSystemConfigMock.mockReturnValue(buildSystemConfigState({ activeCategory: 'base' }));

    render(<SettingsPage />);

    expect(await screen.findByText('暂无法判断配置状态')).toBeInTheDocument();
    expect(screen.getByText('配置状态读取失败。可先检查或修改设置项，稍后刷新检查结果。')).toBeInTheDocument();
    expect(screen.queryByText('基础配置已满足最小可用分析')).not.toBeInTheDocument();
    expect(screen.queryByText('还有基础配置需要处理')).not.toBeInTheDocument();
    expect(screen.queryByText('所有必需项已就绪，可运行一次简短分析验证链路。')).not.toBeInTheDocument();
  });

  it('keeps the latest first-run setup status when refresh responses resolve out of order', async () => {
    const staleRefresh = createDeferred<SetupStatusResponse>();
    const latestRefresh = createDeferred<SetupStatusResponse>();
    const initialStatus: SetupStatusResponse = {
      isComplete: true,
      readyForSmoke: true,
      requiredMissingKeys: [],
      nextStepKey: null,
      checks: [
        {
          key: 'initial-status',
          title: '初始状态',
          category: 'base',
          required: true,
          status: 'configured',
          message: '初始配置状态。',
          nextStep: null,
        },
      ],
    };
    const staleStatus: SetupStatusResponse = {
      isComplete: false,
      readyForSmoke: false,
      requiredMissingKeys: ['LLM_CHANNELS'],
      nextStepKey: 'LLM_CHANNELS',
      checks: [
        {
          key: 'stale-status',
          title: '过期状态',
          category: 'ai_model',
          required: true,
          status: 'needs_action',
          message: '过期的配置状态。',
          nextStep: '这条旧响应不应覆盖最新状态。',
        },
      ],
    };
    const latestStatus: SetupStatusResponse = {
      isComplete: true,
      readyForSmoke: true,
      requiredMissingKeys: [],
      nextStepKey: null,
      checks: [
        {
          key: 'latest-status',
          title: '最新状态',
          category: 'base',
          required: true,
          status: 'configured',
          message: '最新配置状态。',
          nextStep: null,
        },
      ],
    };

    getSetupStatus
      .mockResolvedValueOnce(initialStatus)
      .mockImplementationOnce(() => staleRefresh.promise)
      .mockImplementationOnce(() => latestRefresh.promise);
    useSystemConfigMock.mockReturnValue(buildSystemConfigState({ activeCategory: 'base' }));

    render(<SettingsPage />);

    expect(await screen.findByText('初始状态')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '刷新检查' }));
    fireEvent.click(screen.getByRole('button', { name: 'merge stock list' }));

    await waitFor(() => expect(getSetupStatus).toHaveBeenCalledTimes(3));

    await act(async () => {
      latestRefresh.resolve(latestStatus);
      await latestRefresh.promise;
    });

    expect(await screen.findByText('最新状态')).toBeInTheDocument();
    expect(screen.queryByText('过期状态')).not.toBeInTheDocument();

    await act(async () => {
      staleRefresh.resolve(staleStatus);
      await staleRefresh.promise;
    });

    await waitFor(() => expect(screen.getByText('最新状态')).toBeInTheDocument());
    expect(screen.queryByText('过期状态')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: '简短试跑' })).toBeEnabled();
  });

  it('runs a brief setup smoke analysis with the first watchlist stock', async () => {
    useSystemConfigMock.mockReturnValue(buildSystemConfigState({ activeCategory: 'base' }));

    render(<SettingsPage />);

    await screen.findByText('基础配置已满足最小可用分析');
    fireEvent.click(screen.getByRole('button', { name: '简短试跑' }));

    await waitFor(() => expect(analyzeAsync).toHaveBeenCalledWith({
      stockCode: 'SH600000',
      reportType: 'brief',
      asyncMode: true,
      notify: false,
      originalQuery: 'SH600000',
      selectionSource: 'manual',
    }));
    expect(await screen.findByText(/task-setup-smoke/)).toBeInTheDocument();
  });

  it('allows brief setup smoke when only the Agent channel is incomplete', async () => {
    useSystemConfigMock.mockReturnValue(buildSystemConfigState({ activeCategory: 'base' }));
    getSetupStatus.mockResolvedValue({
      isComplete: false,
      readyForSmoke: true,
      requiredMissingKeys: ['llm_agent'],
      nextStepKey: 'llm_agent',
      checks: [
        {
          key: 'llm_primary',
          title: 'LLM 主渠道',
          category: 'ai_model',
          required: true,
          status: 'configured',
          message: '已启用 Claude Code CLI 本地生成 Backend（experimental/limited）。',
          nextStep: null,
        },
        {
          key: 'llm_agent',
          title: 'Agent 渠道',
          category: 'agent',
          required: true,
          status: 'needs_action',
          message: 'Agent 工具调用需要 LiteLLM 模型配置；local CLI 主生成方式不会被自动继承。',
          nextStep: '如需使用 Ask-Stock Agent，请配置 LiteLLM 模型。',
        },
        {
          key: 'stock_list',
          title: '自选股',
          category: 'base',
          required: true,
          status: 'configured',
          message: '已配置 1 只股票。',
          nextStep: null,
        },
      ],
    });

    render(<SettingsPage />);

    await screen.findByText('还缺少 1 项：Agent 渠道');
    expect(screen.getByRole('button', { name: '简短试跑' })).toBeEnabled();

    fireEvent.click(screen.getByRole('button', { name: '简短试跑' }));

    await waitFor(() => expect(analyzeAsync).toHaveBeenCalledWith({
      stockCode: 'SH600000',
      reportType: 'brief',
      asyncMode: true,
      notify: false,
      originalQuery: 'SH600000',
      selectionSource: 'manual',
    }));
  });

  it('shows missing setup items and lets the user reopen the setup check', async () => {
    getSetupStatus.mockResolvedValue({
      isComplete: false,
      readyForSmoke: false,
      requiredMissingKeys: ['LLM_CHANNELS'],
      nextStepKey: 'LLM_CHANNELS',
      checks: [
        {
          key: 'llm_channels',
          title: '模型渠道',
          category: 'ai_model',
          required: true,
          status: 'needs_action',
          message: '还没有配置模型渠道。',
          nextStep: '请先配置模型渠道。',
        },
      ],
    });
    useSystemConfigMock.mockReturnValue(buildSystemConfigState({ activeCategory: 'base' }));

    render(<SettingsPage />);

    expect(await screen.findByText('还有基础配置需要处理')).toBeInTheDocument();
    expect(screen.getByText('还缺少 1 项：模型渠道')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '简短试跑' })).toBeDisabled();

    fireEvent.click(screen.getByRole('button', { name: '暂时隐藏' }));
    expect(screen.getByText('首次启动配置检查已隐藏')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '展开检查' }));
    expect(screen.getByText('首次启动配置检查')).toBeInTheDocument();
  });

  it('renders web build info in system settings', async () => {
    render(<SettingsPage />);

    expect(await screen.findByRole('heading', { name: '版本信息' })).toBeInTheDocument();
    expect(screen.getByText('3.11.0')).toBeInTheDocument();
    expect(screen.getByText('build-20260329-021530Z')).toBeInTheDocument();
    expect(screen.getByText('2026-03-29T02:15:30.000Z')).toBeInTheDocument();
  });

  it('renders desktop app version in system settings during desktop runtime', async () => {
    (window as { dsaDesktop?: unknown }).dsaDesktop = { version: '3.12.0' };

    render(<SettingsPage />);

    expect(await screen.findByRole('heading', { name: '版本信息' })).toBeInTheDocument();
    expect(screen.getByText('桌面端版本')).toBeInTheDocument();
    expect(screen.getByText('3.12.0')).toBeInTheDocument();
  });

  it('keeps version grid at three columns when desktop runtime has no usable version', async () => {
    (window as { dsaDesktop?: unknown }).dsaDesktop = { version: '   ' };

    render(<SettingsPage />);

    const section = (await screen.findByRole('heading', { name: '版本信息' })).closest('section');
    const versionGrid = section?.querySelector('div.grid.grid-cols-1.gap-3');

    expect(screen.queryByText('桌面端版本')).not.toBeInTheDocument();
    expect(versionGrid).toHaveClass('md:grid-cols-3');
    expect(versionGrid).not.toHaveClass('md:grid-cols-4');
  });

  it('ignores non-string desktop runtime version values without breaking render', async () => {
    (window as { dsaDesktop?: unknown }).dsaDesktop = { version: 3120 };

    render(<SettingsPage />);

    const section = (await screen.findByRole('heading', { name: '版本信息' })).closest('section');
    const versionGrid = section?.querySelector('div.grid.grid-cols-1.gap-3');

    expect(screen.queryByText('桌面端版本')).not.toBeInTheDocument();
    expect(versionGrid).toHaveClass('md:grid-cols-3');
  });

  it('normalizes malformed desktop update payloads instead of throwing', async () => {
    desktopGetUpdateState.mockResolvedValue({
      status: 123,
      currentVersion: 3120,
      latestVersion: null,
      releaseUrl: { href: 'https://example.com' },
      checkedAt: ['2026-04-25T01:02:00Z'],
      message: false,
      releaseName: { text: 'v3.13.0' },
      tagName: undefined,
    });
    (window as { dsaDesktop?: unknown }).dsaDesktop = createDesktopRuntime();

    render(<SettingsPage />);

    await waitFor(() => {
      expect(desktopGetUpdateState).toHaveBeenCalledTimes(1);
    });
    expect(screen.getByRole('button', { name: '检查更新' })).toBeInTheDocument();
    expect(screen.queryByText('检查更新失败')).not.toBeInTheDocument();
    expect(screen.queryByText('发现新版本')).not.toBeInTheDocument();
  });

  it('falls back to build identifier when package version is still placeholder', () => {
    expect(resolveWebBuildInfo({
      packageVersion: '0.0.0',
      buildTimestamp: '2026-03-29T02:15:30.000Z',
    })).toEqual({
      version: 'build-20260329-021530Z',
      rawVersion: '0.0.0',
      buildId: 'build-20260329-021530Z',
      buildTime: '2026-03-29T02:15:30.000Z',
      isFallbackVersion: true,
    });
  });

  it('renders fallback version hint when package version is placeholder', async () => {
    Object.assign(webBuildInfoMock, {
      version: 'build-20260329-021530Z',
      rawVersion: '0.0.0',
      buildId: 'build-20260329-021530Z',
      buildTime: '2026-03-29T02:15:30.000Z',
      isFallbackVersion: true,
    });

    render(<SettingsPage />);

    expect(await screen.findByRole('heading', { name: '版本信息' })).toBeInTheDocument();
    expect(screen.getByText(/当前 package\.json 仍为占位版本 0\.0\.0/)).toBeInTheDocument();
    expect(screen.getAllByText('build-20260329-021530Z')).toHaveLength(2);
  });

  it('resets only the current autosave group from the page header', () => {
    useSystemConfigMock.mockReturnValue(buildSystemConfigState({
      hasDirty: true,
      dirtyCount: 1,
      getChangedItems: () => [{ key: 'WEBUI_PORT', value: '9000' }],
    }));

    render(<SettingsPage />);

    // Clear the initial load call from useEffect
    vi.clearAllMocks();

    // Reset now asks for confirmation before discarding dirty drafts.
    fireEvent.click(screen.getByRole('button', { name: '重置当前分组' }));
    fireEvent.click(screen.getByRole('button', { name: '放弃修改' }));

    expect(resetDraftKeys).toHaveBeenCalledWith(['WEBUI_PORT']);
    expect(resetDraft).not.toHaveBeenCalled();
    expect(load).not.toHaveBeenCalled();
  });

  it('blocks in-app navigation only when there are unsaved changes', () => {
    useSystemConfigMock.mockReturnValue(buildSystemConfigState({
      hasDirty: true,
      dirtyCount: 1,
      getChangedItems: () => [{ key: 'WEBUI_PORT', value: '9000' }],
    }));

    render(<SettingsPage />);

    const args: BlockerArgs = {
      currentLocation: { pathname: '/settings' },
      nextLocation: { pathname: '/' },
    };
    expect(routerBlockerMock.shouldBlock?.(args)).toBe(true);
    expect(routerBlockerMock.shouldBlock?.({
      currentLocation: { pathname: '/settings' },
      nextLocation: { pathname: '/settings' },
    } satisfies BlockerArgs)).toBe(false);
  });

  it('does not block navigation without unsaved changes', () => {
    useSystemConfigMock.mockReturnValue(buildSystemConfigState({ hasDirty: false, dirtyCount: 0 }));

    render(<SettingsPage />);

    expect(routerBlockerMock.shouldBlock?.({
      currentLocation: { pathname: '/settings' },
      nextLocation: { pathname: '/' },
    } satisfies BlockerArgs)).toBe(false);
  });

  it('confirms or cancels leaving settings with unsaved changes', () => {
    useSystemConfigMock.mockReturnValue(buildSystemConfigState({ hasDirty: true, dirtyCount: 2 }));
    routerBlockerMock.state = 'blocked';

    render(<SettingsPage />);

    expect(screen.getByText('离开设置页？')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '取消' }));
    expect(routerBlockerMock.reset).toHaveBeenCalledTimes(1);
    expect(routerBlockerMock.proceed).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: '离开' }));
    expect(routerBlockerMock.proceed).toHaveBeenCalledTimes(1);
  });

  it('keeps agent execution fields on Agent Behavior but moves Event Monitor to the Alerts section', () => {
    const agentItems = () => buildSystemConfigState({
      activeCategory: 'agent',
      itemsByCategory: {
        ...buildSystemConfigState().itemsByCategory,
        agent: [
          {
            key: 'AGENT_ORCHESTRATOR_TIMEOUT_S',
            value: '600',
            rawValueExists: true,
            isMasked: false,
            schema: {
              key: 'AGENT_ORCHESTRATOR_TIMEOUT_S',
              category: 'agent',
              dataType: 'integer',
              uiControl: 'number',
              isSensitive: false,
              isRequired: false,
              isEditable: true,
              options: [],
              validation: {},
              displayOrder: 1,
            },
          },
          {
            key: 'AGENT_DEEP_RESEARCH_BUDGET',
            value: '30000',
            rawValueExists: true,
            isMasked: false,
            schema: {
              key: 'AGENT_DEEP_RESEARCH_BUDGET',
              category: 'agent',
              dataType: 'integer',
              uiControl: 'number',
              isSensitive: false,
              isRequired: false,
              isEditable: true,
              options: [],
              validation: {},
              displayOrder: 2,
            },
          },
          {
            key: 'AGENT_EVENT_MONITOR_ENABLED',
            value: 'false',
            rawValueExists: true,
            isMasked: false,
            schema: {
              key: 'AGENT_EVENT_MONITOR_ENABLED',
              category: 'agent',
              dataType: 'boolean',
              uiControl: 'switch',
              isSensitive: false,
              isRequired: false,
              isEditable: true,
              options: [],
              validation: {},
              displayOrder: 3,
            },
          },
        ],
      },
    });

    // Agent Behavior section: execution fields only, Event Monitor moved out.
    useSystemConfigMock.mockReturnValue(agentItems());
    const { rerender } = render(<SettingsPage />);
    expect(screen.getByText('AGENT_ORCHESTRATOR_TIMEOUT_S')).toBeInTheDocument();
    expect(screen.getByText('AGENT_DEEP_RESEARCH_BUDGET')).toBeInTheDocument();
    expect(screen.queryByText('AGENT_EVENT_MONITOR_ENABLED')).not.toBeInTheDocument();
    expect(settingsPanelErrorBoundary).toHaveBeenCalledWith('Agent 设置');

    // Alerts section: the Event Monitor card renders the agent-category event keys.
    useSystemConfigMock.mockReturnValue(agentItems());
    routerSearchParamsMock.params = new URLSearchParams({ section: 'alerts', view: 'rules' });
    rerender(<SettingsPage />);
    expect(screen.getByText('事件监控')).toBeInTheDocument();
    expect(screen.getByText('AGENT_EVENT_MONITOR_ENABLED')).toBeInTheDocument();
    expect(screen.queryByText('AGENT_ORCHESTRATOR_TIMEOUT_S')).not.toBeInTheDocument();
  });

  it('renders context compression profile labels and blank preset guidance in the Conversation section', () => {
    const configState = buildSystemConfigState();
    useSystemConfigMock.mockReturnValue(buildSystemConfigState({
      activeCategory: 'agent',
      itemsByCategory: {
        ...configState.itemsByCategory,
        agent: [
          {
            key: 'AGENT_CONTEXT_COMPRESSION_PROFILE',
            value: 'balanced',
            rawValueExists: true,
            isMasked: false,
            schema: {
              key: 'AGENT_CONTEXT_COMPRESSION_PROFILE',
              category: 'agent',
              dataType: 'string',
              uiControl: 'select',
              isSensitive: false,
              isRequired: false,
              isEditable: true,
              options: [
                { label: '成本优先', value: 'cost' },
                { label: '均衡推荐', value: 'balanced' },
                { label: '长上下文原文优先', value: 'long_context_raw_first' },
              ],
              validation: {
                enum: ['cost', 'balanced', 'long_context_raw_first'],
              },
              displayOrder: 72,
            },
          },
          {
            key: 'AGENT_CONTEXT_COMPRESSION_TRIGGER_TOKENS',
            value: '',
            rawValueExists: false,
            isMasked: false,
            schema: {
              key: 'AGENT_CONTEXT_COMPRESSION_TRIGGER_TOKENS',
              category: 'agent',
              dataType: 'integer',
              uiControl: 'number',
              isSensitive: false,
              isRequired: false,
              isEditable: true,
              options: [],
              validation: { min: 1000 },
              displayOrder: 73,
              description: '估算历史 token 超过该值时触发摘要；留空则跟随当前上下文压缩策略 profile 默认值。',
            },
          },
          {
            key: 'AGENT_CONTEXT_PROTECTED_TURNS',
            value: '',
            rawValueExists: false,
            isMasked: false,
            schema: {
              key: 'AGENT_CONTEXT_PROTECTED_TURNS',
              category: 'agent',
              dataType: 'integer',
              uiControl: 'number',
              isSensitive: false,
              isRequired: false,
              isEditable: true,
              options: [],
              validation: { min: 1 },
              displayOrder: 74,
              description: '压缩时最近 N 个用户轮次及其后的回复保持原文；留空则跟随当前上下文压缩策略 profile 默认值。',
            },
          },
        ],
      },
    }));
    // Context compression fields now live under the Conversation section
    // (split out of the Agent category by the field placement map).
    routerSearchParamsMock.params = new URLSearchParams({ section: 'conversation', view: 'context' });

    render(<SettingsPage />);

    expect(screen.getByText('AGENT_CONTEXT_COMPRESSION_PROFILE')).toBeInTheDocument();
    expect(screen.getByText('成本优先')).toBeInTheDocument();
    expect(screen.getByText('均衡推荐')).toBeInTheDocument();
    expect(screen.getByText('长上下文原文优先')).toBeInTheDocument();
    expect(screen.getByText(/估算历史 token 超过该值时触发摘要/)).toHaveTextContent('留空则跟随当前上下文压缩策略 profile 默认值');
    expect(screen.getByText(/压缩时最近 N 个用户轮次及其后的回复保持原文/)).toHaveTextContent('留空则跟随当前上下文压缩策略 profile 默认值');
  });

  it('group reset discards local changes without a network request', () => {
    // Simulate user has unsaved drafts
    const dirtyState = buildSystemConfigState({
      hasDirty: true,
      dirtyCount: 1,
      getChangedItems: () => [{ key: 'WEBUI_PORT', value: '9000' }],
    });

    useSystemConfigMock.mockReturnValue(dirtyState);

    render(<SettingsPage />);

    // Clear initial useEffect load call
    vi.clearAllMocks();

    // Click reset button, then confirm discarding drafts.
    fireEvent.click(screen.getByRole('button', { name: '重置当前分组' }));
    fireEvent.click(screen.getByRole('button', { name: '放弃修改' }));

    // Verify semantic: reset should only discard local changes
    // It should NOT trigger a network load
    expect(resetDraftKeys).toHaveBeenCalledWith(['WEBUI_PORT']);
    expect(resetDraft).not.toHaveBeenCalled();
    expect(load).not.toHaveBeenCalled();
    expect(save).not.toHaveBeenCalled();
  });

  it('refreshes server state after intelligent import merges stock list', async () => {
    useSystemConfigMock.mockReturnValue(buildSystemConfigState({ activeCategory: 'base' }));

    render(<SettingsPage />);

    fireEvent.click(screen.getByRole('button', { name: 'merge stock list' }));

    expect(refreshAfterExternalSave).toHaveBeenCalledWith(['STOCK_LIST']);
    expect(load).toHaveBeenCalledTimes(1);
  });

  it('autosaves the llm channel and task-routing draft as one group', async () => {
    save.mockResolvedValue({ success: true });
    useSystemConfigMock.mockReturnValue(buildSystemConfigState({ activeCategory: 'ai_model' }));

    render(<SettingsPage />);

    fireEvent.click(screen.getByRole('button', { name: 'emit connection draft' }));

    expect(screen.queryByRole('button', { name: /保存配置/ })).not.toBeInTheDocument();
    expect(await screen.findByText(/等待自动保存/)).toBeInTheDocument();
    await waitFor(() => expect(save).toHaveBeenCalledTimes(1), { timeout: 2000 });
    const payload = save.mock.calls[0][0];
    expect(payload).toEqual(expect.arrayContaining([
      expect.objectContaining({ key: 'LLM_CHANNELS', value: 'draft,backup' }),
      expect.objectContaining({ key: 'LITELLM_MODEL', value: 'openai/draft-model' }),
    ]));
  });

  it('does not autosave an AI draft before the Catalog establishes schema presence', async () => {
    const catalog = createDeferred<{ providers: Array<Record<string, unknown>> }>();
    getLlmProviderCatalog.mockReturnValueOnce(catalog.promise);
    save.mockResolvedValue({ success: true });
    useSystemConfigMock.mockReturnValue(buildSystemConfigState({ activeCategory: 'ai_model' }));

    render(<SettingsPage />);
    fireEvent.click(screen.getByRole('button', { name: 'emit connection draft' }));

    expect(screen.getByTestId('llm-channel-editor-items')).toHaveAttribute('data-disabled', 'true');
    await act(async () => {
      await new Promise((resolve) => window.setTimeout(resolve, 850));
    });
    expect(save).not.toHaveBeenCalled();

    await act(async () => {
      catalog.resolve({
        providers: [
          { id: 'deepseek', label: 'DeepSeek', protocol: 'deepseek' },
        ],
      });
      await catalog.promise;
    });
    await waitFor(() => expect(save).toHaveBeenCalledTimes(1), { timeout: 2500 });
  });

  it('does not autosave a Connection draft under a present empty schema', async () => {
    await expectConnectionDraftAutosaveBlockedBySchema([]);
  });

  it('does not autosave a Connection draft under a models-only schema', async () => {
    await expectConnectionDraftAutosaveBlockedBySchema([TEST_MODELS_FIELD]);
  });

  it('does not autosave a Connection draft when connection_name is missing', async () => {
    await expectConnectionDraftAutosaveBlockedBySchema([
      TEST_PROVIDER_ID_FIELD,
      TEST_MODELS_FIELD,
    ]);
  });

  it('does not autosave a Connection draft when provider_id is missing', async () => {
    await expectConnectionDraftAutosaveBlockedBySchema([
      TEST_CONNECTION_NAME_FIELD,
      TEST_MODELS_FIELD,
    ]);
  });

  it('does not autosave a Connection draft under a read-only identity schema', async () => {
    await expectConnectionDraftAutosaveBlockedBySchema(withTestConnectionCoreFields([
      TEST_CONNECTION_NAME_FIELD,
      {
        ...TEST_PROVIDER_ID_FIELD,
        isRequired: false,
        contract: { requirement: 'inherited' },
      },
      TEST_MODELS_FIELD,
    ]));
  });

  it('does not autosave a Connection draft with an unknown visible required field', async () => {
    await expectConnectionDraftAutosaveBlockedBySchema(withTestConnectionCoreFields([{
      key: 'future_token',
      dataType: 'string',
      isSensitive: false,
      isRequired: true,
      contract: { requirement: 'required' },
    }]));
  });

  it('does not autosave when an unknown required field becomes visible for the draft provider', async () => {
    getLlmProviderCatalog.mockResolvedValueOnce({
      providers: [
        { id: 'deepseek', label: 'DeepSeek', protocol: 'deepseek', defaultBaseUrl: 'https://api.deepseek.com', capabilities: [], requiresApiKey: true, requiresBaseUrl: false, supportsDiscovery: true, isLocal: false, isCustom: false },
      ],
      connectionFields: withTestConnectionCoreFields([{
        key: 'future_token',
        dataType: 'string',
        isSensitive: true,
        isRequired: true,
        contract: {
          requirement: 'required',
          visibleWhen: [{ key: 'provider_id', operator: 'equals', value: 'deepseek' }],
        },
      }]),
    });
    save.mockResolvedValue({ success: true });
    useSystemConfigMock.mockReturnValue(buildSystemConfigState({ activeCategory: 'ai_model' }));

    render(<SettingsPage />);
    fireEvent.click(screen.getByRole('button', { name: 'emit schema-valid connection draft' }));

    await act(async () => {
      await new Promise((resolve) => window.setTimeout(resolve, 850));
    });
    expect(save).not.toHaveBeenCalled();
  });

  it('autosaves when an unknown required field stays hidden for the draft provider', async () => {
    getLlmProviderCatalog.mockResolvedValueOnce({
      providers: [
        { id: 'deepseek', label: 'DeepSeek', protocol: 'deepseek', defaultBaseUrl: 'https://api.deepseek.com', capabilities: [], requiresApiKey: true, requiresBaseUrl: false, supportsDiscovery: true, isLocal: false, isCustom: false },
      ],
      connectionFields: withTestConnectionCoreFields([{
        key: 'future_token',
        dataType: 'string',
        isSensitive: true,
        isRequired: true,
        contract: {
          requirement: 'required',
          visibleWhen: [{ key: 'provider_id', operator: 'equals', value: 'openai' }],
        },
      }]),
    });
    save.mockResolvedValue({ success: true });
    useSystemConfigMock.mockReturnValue(buildSystemConfigState({ activeCategory: 'ai_model' }));

    render(<SettingsPage />);
    fireEvent.click(await screen.findByRole('button', { name: 'emit schema-valid connection draft' }));

    await waitFor(() => expect(save).toHaveBeenCalledTimes(1), { timeout: 2000 });
  });

  it('autosaves when an unknown visible field is optional', async () => {
    getLlmProviderCatalog.mockResolvedValueOnce({
      providers: [
        { id: 'deepseek', label: 'DeepSeek', protocol: 'deepseek', defaultBaseUrl: 'https://api.deepseek.com', capabilities: [], requiresApiKey: true, requiresBaseUrl: false, supportsDiscovery: true, isLocal: false, isCustom: false },
      ],
      connectionFields: withTestConnectionCoreFields([{
        key: 'future_hint',
        dataType: 'string',
        isSensitive: false,
        isRequired: false,
        contract: { requirement: 'optional' },
      }]),
    });
    save.mockResolvedValue({ success: true });
    useSystemConfigMock.mockReturnValue(buildSystemConfigState({ activeCategory: 'ai_model' }));

    render(<SettingsPage />);
    fireEvent.click(await screen.findByRole('button', { name: 'emit schema-valid connection draft' }));

    await waitFor(() => expect(save).toHaveBeenCalledTimes(1), { timeout: 2000 });
  });

  it('revalidates the retained Connection payload when an unmounted editor resets child validity', async () => {
    getLlmProviderCatalog.mockResolvedValueOnce({
      providers: [
        { id: 'deepseek', label: 'DeepSeek', protocol: 'deepseek', defaultBaseUrl: 'https://api.deepseek.com', capabilities: [], requiresApiKey: true, requiresBaseUrl: false, supportsDiscovery: true, isLocal: false, isCustom: false },
      ],
      connectionFields: withTestConnectionCoreFields([
        TEST_CONNECTION_NAME_FIELD,
        TEST_PROVIDER_ID_FIELD,
      ]),
    });
    save.mockResolvedValue({ success: true });
    useSystemConfigMock.mockReturnValue(buildSystemConfigState({ activeCategory: 'ai_model' }));

    const { rerender } = render(<SettingsPage />);
    fireEvent.click(screen.getByRole('button', { name: 'mark llm draft invalid' }));
    fireEvent.click(screen.getByRole('button', { name: 'emit connection draft' }));

    expect(await screen.findByText(/自动保存失败/, {}, { timeout: 2000 })).toBeInTheDocument();
    expect(save).not.toHaveBeenCalled();

    routerSearchParamsMock.params = new URLSearchParams({ section: 'advanced', view: 'raw_config' });
    rerender(<SettingsPage />);
    fireEvent.click(screen.getByRole('button', { name: '重试' }));

    await act(async () => {
      await new Promise((resolve) => window.setTimeout(resolve, 50));
    });
    expect(save).not.toHaveBeenCalled();
  });

  it('autosaves a payload that satisfies the present Schema and authoritative Catalog', async () => {
    getLlmProviderCatalog.mockResolvedValueOnce({
      providers: [
        { id: 'deepseek', label: 'DeepSeek', protocol: 'deepseek', defaultBaseUrl: 'https://api.deepseek.com', capabilities: [], requiresApiKey: true, requiresBaseUrl: false, supportsDiscovery: true, isLocal: false, isCustom: false },
      ],
      connectionFields: withTestConnectionCoreFields([
        TEST_CONNECTION_NAME_FIELD,
        TEST_PROVIDER_ID_FIELD,
      ]),
    });
    save.mockResolvedValue({ success: true });
    useSystemConfigMock.mockReturnValue(buildSystemConfigState({ activeCategory: 'ai_model' }));

    render(<SettingsPage />);
    fireEvent.click(screen.getByRole('button', { name: 'emit schema-valid connection draft' }));

    await waitFor(() => expect(save).toHaveBeenCalledWith([
      { key: 'LLM_CHANNELS', value: 'deepseek' },
      { key: 'LLM_DEEPSEEK_PROVIDER', value: 'deepseek' },
    ], { silent: true }), { timeout: 2000 });
  });

  it('keeps existing Connections inspectable but blocks mutations for an unknown schema condition', async () => {
    const connectionFields = withTestConnectionCoreFields([
      TEST_CONNECTION_NAME_FIELD,
      TEST_PROVIDER_ID_FIELD,
      {
        ...TEST_MODELS_FIELD,
        contract: {
          requirement: 'optional' as const,
          enabledWhen: [{ key: 'provider_id', operator: 'futureOperator' as never, value: 'deepseek' }],
        },
      },
    ]);
    getLlmProviderCatalog.mockResolvedValueOnce({
      providers: [
        { id: 'deepseek', label: 'DeepSeek', protocol: 'deepseek', defaultBaseUrl: 'https://api.deepseek.com', capabilities: [], requiresApiKey: true, requiresBaseUrl: false, supportsDiscovery: true, isLocal: false, isCustom: false },
      ],
      connectionFields,
    });
    save.mockResolvedValue({ success: true });
    const configState = buildSystemConfigState({ activeCategory: 'ai_model' });
    useSystemConfigMock.mockReturnValue(buildSystemConfigState({
      activeCategory: 'ai_model',
      itemsByCategory: {
        ...configState.itemsByCategory,
        ai_model: configState.itemsByCategory.ai_model.map((item) => ({
          ...item,
          schema: {
            ...(item.schema as Record<string, unknown>),
            uiPlacement: 'model_access',
          },
        })),
      },
    }));

    render(<SettingsPage />);

    const inspect = await screen.findByRole('button', { name: 'inspect existing connection' });
    await waitFor(() => expect(inspect).toBeEnabled());
    expect(screen.getByRole('button', { name: /添加模型服务/ })).toBeDisabled();
    fireEvent.click(inspect);
    expect(screen.getByRole('dialog', { name: 'existing connection inspection' })).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'emit connection draft' }));
    await act(async () => {
      await new Promise((resolve) => window.setTimeout(resolve, 850));
    });
    expect(save).not.toHaveBeenCalled();
  });

  it('keeps AI autosave and the editor blocked after a Catalog failure', async () => {
    getLlmProviderCatalog.mockRejectedValueOnce(new Error('catalog failed'));
    save.mockResolvedValue({ success: true });
    useSystemConfigMock.mockReturnValue(buildSystemConfigState({ activeCategory: 'ai_model' }));

    render(<SettingsPage />);
    await waitFor(() => expect(screen.getByTestId('llm-channel-editor-items'))
      .toHaveAttribute('data-catalog-unavailable', 'true'));
    fireEvent.click(screen.getByRole('button', { name: 'emit connection draft' }));

    await act(async () => {
      await new Promise((resolve) => window.setTimeout(resolve, 850));
    });
    expect(save).not.toHaveBeenCalled();
    expect(screen.getByTestId('llm-channel-editor-items')).toHaveAttribute('data-disabled', 'true');
  });

  it('passes merged generation backend draft items to the backend status panel', async () => {
    useSystemConfigMock.mockReturnValue(buildSystemConfigState({
      activeCategory: 'ai_model',
      getChangedItems: () => [
        { key: 'GENERATION_BACKEND', value: 'litellm' },
        { key: 'LLM_CHANNELS', value: 'saved' },
        { key: 'OPENAI_MODEL', value: 'gpt-draft' },
        { key: 'GEMINI_MODEL', value: 'gemini-draft' },
        { key: 'OLLAMA_API_BASE', value: 'http://localhost:11434' },
        { key: 'WECHAT_WEBHOOK_URL', value: 'not-a-url' },
      ],
    }));

    const { rerender } = render(<SettingsPage />);

    fireEvent.click(screen.getByRole('button', { name: 'emit llm draft' }));

    // The status panel now lives in the top-level Advanced diagnostics area.
    routerSearchParamsMock.params = new URLSearchParams({ section: 'advanced', view: 'diagnostics' });
    rerender(<SettingsPage />);

    const statusItems = await screen.findByTestId('generation-backend-status-items');
    await waitFor(() => {
      expect(statusItems).toHaveTextContent('GENERATION_BACKEND=litellm');
      expect(statusItems).toHaveTextContent('LLM_CHANNELS=draft,backup');
      expect(statusItems).toHaveTextContent('LITELLM_MODEL=openai/draft-model');
      expect(statusItems).not.toHaveTextContent('OPENAI_MODEL=gpt-draft');
      expect(statusItems).not.toHaveTextContent('GEMINI_MODEL=gemini-draft');
      expect(statusItems).not.toHaveTextContent('OLLAMA_API_BASE=http://localhost:11434');
      expect(statusItems).not.toHaveTextContent('GENERATION_BACKEND=codex_cli');
      expect(statusItems).not.toHaveTextContent('WECHAT_WEBHOOK_URL=not-a-url');
    });
  });

  it('clears llm channel draft items after autosave succeeds', async () => {
    save.mockResolvedValue({ success: true });
    useSystemConfigMock.mockReturnValue(buildSystemConfigState({ activeCategory: 'ai_model' }));

    const { rerender } = render(<SettingsPage />);

    fireEvent.click(screen.getByRole('button', { name: 'emit llm draft' }));

    // The status panel now lives in the top-level Advanced diagnostics area.
    routerSearchParamsMock.params = new URLSearchParams({ section: 'advanced', view: 'diagnostics' });
    rerender(<SettingsPage />);
    expect(await screen.findByTestId('generation-backend-status-items')).toHaveTextContent('LLM_CHANNELS=draft,backup');

    await waitFor(() => {
      expect(screen.getByTestId('generation-backend-status-items')).not.toHaveTextContent('LLM_CHANNELS=draft,backup');
    }, { timeout: 2000 });
    await waitFor(() => expect(save).toHaveBeenCalledTimes(1), { timeout: 2000 });
  });

  it('debounces a group autosave and reports saving then saved', async () => {
    vi.useFakeTimers();
    try {
      const pendingSave = createDeferred<{ success: boolean }>();
      save.mockReturnValueOnce(pendingSave.promise);
      useSystemConfigMock.mockReturnValue(buildSystemConfigState({
        activeCategory: 'system',
        hasDirty: true,
        dirtyCount: 1,
        getChangedItems: () => [{ key: 'WEBUI_PORT', value: '9000' }],
      }));

      render(<SettingsPage />);

      expect(screen.queryByRole('button', { name: /保存配置/ })).not.toBeInTheDocument();
      expect(screen.getByText(/等待自动保存/)).toBeInTheDocument();
      expect(save).not.toHaveBeenCalled();

      await act(async () => {
        await vi.advanceTimersByTimeAsync(700);
      });
      expect(screen.getByText(/自动保存中/)).toBeInTheDocument();
      expect(save).toHaveBeenCalledTimes(1);

      await act(async () => {
        pendingSave.resolve({ success: true });
        await pendingSave.promise;
      });
      expect(screen.getByText(/已自动保存/)).toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }
  });

  it('keeps a failed autosave draft and retries the same group', async () => {
    save
      .mockResolvedValueOnce({ success: false, message: '保存失败' })
      .mockResolvedValueOnce({ success: true });
    useSystemConfigMock.mockReturnValue(buildSystemConfigState({
      activeCategory: 'system',
      hasDirty: true,
      dirtyCount: 1,
      getChangedItems: () => [{ key: 'WEBUI_PORT', value: '9000' }],
    }));

    render(<SettingsPage />);

    expect(await screen.findByText(/自动保存失败/, {}, { timeout: 2000 })).toBeInTheDocument();
    expect(resetDraftKeys).not.toHaveBeenCalled();
    const retryButton = screen.getByRole('button', { name: '重试' });
    expect(retryButton).toHaveClass('ui-touch-target', 'h-auto', 'min-w-7');
    fireEvent.click(retryButton);

    await waitFor(() => expect(save).toHaveBeenCalledTimes(2));
    expect(await screen.findByText(/已自动保存/)).toBeInTheDocument();
  });

  it('marks a 409 autosave as conflicted and can restore that group', async () => {
    save.mockResolvedValueOnce({ success: false, message: 'config_conflict' });
    useSystemConfigMock.mockReturnValue(buildSystemConfigState({
      activeCategory: 'system',
      hasDirty: true,
      dirtyCount: 1,
      getChangedItems: () => [{ key: 'WEBUI_PORT', value: '9000' }],
    }));

    render(<SettingsPage />);

    expect(await screen.findByText(/保存冲突/, {}, { timeout: 2000 })).toBeInTheDocument();
    const restoreButton = screen.getByRole('button', { name: '恢复服务器值' });
    expect(restoreButton).toHaveClass('ui-touch-target', 'h-auto', 'min-w-7');
    fireEvent.click(restoreButton);
    expect(resetDraftKeys).toHaveBeenCalledWith(['WEBUI_PORT']);
  });

  it.each([
    { language: 'de', expectedTitle: 'Liste ausgewählter Aktien', backendTitleVisible: false },
    { language: 'en', expectedTitle: 'Server Watchlist Title', backendTitleVisible: true },
  ] as const)(
    'uses the $language field-title contract in the 409 conflict panel',
    async ({ language, expectedTitle, backendTitleVisible }) => {
      useSystemConfigMock.mockReturnValue(buildSystemConfigState({
        activeCategory: 'base',
        conflictState: {
          fields: [{
            key: 'STOCK_LIST',
            base: 'AAPL',
            server: 'MSFT',
            local: 'NVDA',
            isSensitive: false,
            title: 'Server Watchlist Title',
            category: 'base',
          }],
          serverVersion: 'v2',
        },
        resolveConflictField: vi.fn(),
        resolveAllConflicts: vi.fn(),
      }));
      await loadUiLanguageTranslations(language);

      render(
        <UiLanguageProvider initialLanguage={language}>
          <SettingsPage />
        </UiLanguageProvider>,
      );

      expect(screen.getByText(expectedTitle)).toBeInTheDocument();
      if (backendTitleVisible) {
        expect(screen.getByText('Server Watchlist Title')).toBeInTheDocument();
      } else {
        expect(screen.queryByText('Server Watchlist Title')).not.toBeInTheDocument();
      }
    },
  );

  it('runs the unified post-save effects after a legacy migration applies', async () => {
    useSystemConfigMock.mockReturnValue(buildSystemConfigState({ activeCategory: 'ai_model' }));
    // The migration banner lives in the top-level Advanced diagnostics area.
    routerSearchParamsMock.params = new URLSearchParams({ section: 'advanced', view: 'diagnostics' });

    render(<SettingsPage />);

    // Ignore the effects fired during initial mount.
    load.mockClear();
    notifySystemConfigChanged.mockClear();
    getSetupStatus.mockClear();

    fireEvent.click(screen.getByRole('button', { name: 'trigger migration' }));

    // Migration must reload config and then run the same post-save flow as Save.
    await waitFor(() => expect(load).toHaveBeenCalled());
    await waitFor(() => expect(notifySystemConfigChanged).toHaveBeenCalled());
    await waitFor(() => expect(getSetupStatus).toHaveBeenCalled());
  });

  it('renders the two-level IA navigation and routes section clicks through the section/view URL', () => {
    useSystemConfigMock.mockReturnValue(buildSystemConfigState({ activeCategory: 'ai_model', activeSubCategory: 'model' }));

    render(<SettingsPage />);

    // The AI & Models section is active and its second-level view tabs render.
    expect(screen.getByRole('button', { name: /AI 与模型/ })).toHaveAttribute('aria-current', 'page');
    expect(screen.getByRole('tab', { name: '模型接入' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: '任务路由' })).toBeInTheDocument();

    // Clicking a first-level section pushes the canonical section/view URL
    // (section is the single source of truth; no legacy params leak).
    fireEvent.click(screen.getByRole('button', { name: /系统与安全/ }));
    const [nextParams, options] = routerSearchParamsMock.setParams.mock.calls.at(-1) ?? [];
    expect(nextParams?.get('section')).toBe('system_security');
    expect(nextParams?.has('category')).toBe(false);
    expect(nextParams?.has('sub')).toBe(false);
    // Normal navigation must push history (not replace) so Back returns here.
    expect(options?.replace).toBe(false);
  });

  it('round-trips from empty Task Routing through Model Access with an explicit origin', async () => {
    getLlmAvailableModels.mockResolvedValue({ models: [] });
    useSystemConfigMock.mockReturnValue(buildSystemConfigState({ activeCategory: 'ai_model' }));
    routerSearchParamsMock.params = new URLSearchParams({ section: 'ai_models', view: 'task_routing' });

    const { rerender } = render(<SettingsPage />);

    fireEvent.click(await screen.findByRole('button', { name: '前往模型接入' }));
    const [modelAccessParams, modelAccessOptions] = routerSearchParamsMock.setParams.mock.calls.at(-1) ?? [];
    expect(modelAccessParams?.get('section')).toBe('ai_models');
    expect(modelAccessParams?.get('view')).toBe('connections');
    expect(modelAccessParams?.get('from')).toBe('task_routing');
    expect(modelAccessOptions?.replace).toBe(false);

    routerSearchParamsMock.params = new URLSearchParams({
      section: 'ai_models',
      view: 'connections',
      from: 'task_routing',
    });
    rerender(<SettingsPage />);

    fireEvent.click(await screen.findByRole('button', { name: '返回任务路由' }));
    const [returnParams, returnOptions] = routerSearchParamsMock.setParams.mock.calls.at(-1) ?? [];
    expect(returnParams?.get('section')).toBe('ai_models');
    expect(returnParams?.get('view')).toBe('task_routing');
    expect(returnParams?.has('from')).toBe(false);
    expect(returnOptions?.replace).toBe(false);
  });

  it('does not report task routes as unavailable while the available-model catalog failed', async () => {
    getLlmAvailableModels.mockRejectedValue(new Error('catalog unavailable'));
    useSystemConfigMock.mockReturnValue(buildSystemConfigState({ activeCategory: 'ai_model' }));
    routerSearchParamsMock.params = new URLSearchParams({ section: 'ai_models', view: 'overview' });

    render(<SettingsPage />);

    expect(screen.getByRole('tab', { name: '总览' })).toHaveAttribute('aria-selected', 'true');
    await waitFor(() => expect(getLlmAvailableModels).toHaveBeenCalledTimes(1));
    await expect(getLlmAvailableModels.mock.results[0]?.value).rejects.toThrow('catalog unavailable');
    expect(await screen.findByText('可用模型加载失败')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '重新加载' })).toBeInTheDocument();
    expect(screen.queryByText('当前配置不可用')).not.toBeInTheDocument();
  });

  it('moves every referenced task route into the unified draft when replacing a model', async () => {
    const modelField = (key: string, value: string, displayOrder: number) => ({
      key,
      value,
      rawValueExists: true,
      isMasked: false,
      schema: {
        key,
        category: 'ai_model',
        dataType: 'string',
        uiControl: 'text',
        isSensitive: false,
        isRequired: false,
        isEditable: true,
        options: [],
        validation: {},
        displayOrder,
        uiPlacement: key === 'LITELLM_FALLBACK_MODELS' ? 'reliability' as const : 'task_routing' as const,
      },
    });
    useSystemConfigMock.mockReturnValue(buildSystemConfigState({
      activeCategory: 'ai_model',
      itemsByCategory: {
        ...defaultItemsByCategory,
        ai_model: [
          ...defaultItemsByCategory.ai_model,
          modelField('LITELLM_MODEL', 'deepseek/shared-model', 2),
          modelField('AGENT_LITELLM_MODEL', 'deepseek/shared-model', 3),
          modelField('VISION_MODEL', 'openai/vision-model', 4),
          modelField('LITELLM_FALLBACK_MODELS', 'deepseek/shared-model,openai/backup-model', 5),
        ],
      },
    }));
    routerSearchParamsMock.params = new URLSearchParams({ section: 'ai_models', view: 'connections' });

    render(<SettingsPage />);
    fireEvent.click(await screen.findByRole('button', { name: 'replace model references' }));

    expect(setDraftValue).toHaveBeenCalledWith('LITELLM_MODEL', 'openai/replacement-model');
    expect(setDraftValue).toHaveBeenCalledWith('AGENT_LITELLM_MODEL', 'openai/replacement-model');
    expect(setDraftValue).toHaveBeenCalledWith(
      'LITELLM_FALLBACK_MODELS',
      'openai/replacement-model,openai/backup-model',
    );
    expect(setDraftValue).not.toHaveBeenCalledWith('VISION_MODEL', expect.anything());
  });

  it('replaces a historical bare Agent reference using backend-equivalent route identity', async () => {
    getLlmAvailableModels.mockResolvedValue({
      models: [
        { route: 'openai/gpt-4o-mini', display: 'gpt-4o-mini', connection: 'openai', provider: 'openai' },
        { route: 'openai/gpt-5.5', display: 'gpt-5.5', connection: 'openai', provider: 'openai' },
      ],
    });
    useSystemConfigMock.mockReturnValue(buildSystemConfigState({
      activeCategory: 'ai_model',
      itemsByCategory: {
        ...defaultItemsByCategory,
        ai_model: [
          ...defaultItemsByCategory.ai_model,
          {
            key: 'AGENT_LITELLM_MODEL',
            value: 'gpt-4o-mini',
            rawValueExists: true,
            isMasked: false,
            schema: {
              key: 'AGENT_LITELLM_MODEL',
              category: 'ai_model',
              dataType: 'string',
              uiControl: 'text',
              isSensitive: false,
              isRequired: false,
              isEditable: true,
              options: [],
              validation: {},
              displayOrder: 3,
              uiPlacement: 'task_routing' as const,
            },
          },
        ],
      },
    }));
    routerSearchParamsMock.params = new URLSearchParams({ section: 'ai_models', view: 'connections' });

    render(<SettingsPage />);
    await waitFor(() => expect(getLlmAvailableModels).toHaveBeenCalled());
    fireEvent.click(screen.getByRole('button', { name: 'replace bare Agent reference' }));

    expect(setDraftValue).toHaveBeenCalledWith('AGENT_LITELLM_MODEL', 'openai/gpt-5.5');
  });

  it('makes Task Routing the single editor for per-task models and links fallback out to Reliability', async () => {
    const aiField = (key: string, value: string, displayOrder: number) => ({
      key,
      value,
      rawValueExists: Boolean(value),
      isMasked: false,
      schema: {
        key,
        category: 'ai_model',
        dataType: 'string',
        uiControl: 'text',
        isSensitive: false,
        isRequired: false,
        isEditable: true,
        options: [],
        validation: {},
        displayOrder,
        // Mirrors the backend registry: task-model keys are owned by the
        // Task Routing surface.
        uiPlacement: 'task_routing' as const,
      },
    });
    const configState = buildSystemConfigState();
    useSystemConfigMock.mockReturnValue(buildSystemConfigState({
      activeCategory: 'ai_model',
      activeSubCategory: 'model',
      itemsByCategory: {
        ...configState.itemsByCategory,
        ai_model: [
          aiField('LITELLM_MODEL', 'openai/gpt-4o-mini', 1),
          aiField('AGENT_LITELLM_MODEL', 'openai/gpt-4o', 2),
          aiField('VISION_MODEL', 'gemini/gemini-3-pro', 3),
          aiField('LLM_TEMPERATURE', '0.7', 4),
          aiField('LITELLM_FALLBACK_MODELS', 'deepseek/deepseek-v4-pro', 5),
        ],
      },
    }));
    // Drive the Task Routing view directly (buildSystemConfigState defaults the
    // ai_model tab to the connections view).
    routerSearchParamsMock.params = new URLSearchParams({ section: 'ai_models', view: 'task_routing' });

    render(<SettingsPage />);

    // Per-task model fields render as strict list selectors (SearchableSelect
    // trigger buttons opening a listbox), not raw text inputs; temperature
    // stays a plain field. Current routes not present in the available-model
    // catalog are surfaced as "unavailable" instead of being silently dropped.
    expect(await screen.findByText('当前配置不可用：openai/gpt-4o-mini')).toBeInTheDocument();
    expect(screen.getByText('当前配置不可用：openai/gpt-4o')).toBeInTheDocument();
    expect(screen.getByText('当前配置不可用：gemini/gemini-3-pro')).toBeInTheDocument();
    const modelTriggers = document.querySelectorAll('button[aria-haspopup="listbox"]');
    expect(modelTriggers.length).toBeGreaterThanOrEqual(3);
    expect(screen.getByTestId('settings-field-LLM_TEMPERATURE')).toBeInTheDocument();
    // Fallback order is NOT an editable field here; it is a read-only summary.
    expect(screen.queryByTestId('settings-field-LITELLM_FALLBACK_MODELS')).not.toBeInTheDocument();
    expect(screen.getByText(/deepseek-v4-pro · deepseek/)).toBeInTheDocument();

    // The jump link routes to the Reliability view (the canonical fallback editor).
    const reliabilityButton = screen.getByRole('button', { name: /前往可靠性设置/ });
    expect(reliabilityButton).toHaveClass('ui-touch-target', 'h-auto', 'min-w-7');
    fireEvent.click(reliabilityButton);
    const [nextParams] = routerSearchParamsMock.setParams.mock.calls.at(-1) ?? [];
    expect(nextParams?.get('section')).toBe('ai_models');
    expect(nextParams?.get('view')).toBe('reliability');
  });

  it('keeps duplicate runtime routes separate and saves the selected Connection ModelRef', async () => {
    const modelField = {
      key: 'LITELLM_MODEL',
      value: 'openai/gpt-4o',
      rawValueExists: true,
      isMasked: false,
      schema: {
        key: 'LITELLM_MODEL',
        category: 'ai_model' as const,
        dataType: 'string' as const,
        uiControl: 'text' as const,
        isSensitive: false,
        isRequired: true,
        isEditable: true,
        options: [],
        validation: {},
        displayOrder: 1,
        uiPlacement: 'task_routing' as const,
      },
    };
    const configState = buildSystemConfigState();
    useSystemConfigMock.mockReturnValue(buildSystemConfigState({
      activeCategory: 'ai_model',
      activeSubCategory: 'model',
      itemsByCategory: { ...configState.itemsByCategory, ai_model: [modelField] },
    }));
    routerSearchParamsMock.params = new URLSearchParams({ section: 'ai_models', view: 'task_routing' });
    getLlmAvailableModels.mockResolvedValue({
      models: [
        {
          modelRef: 'modelref:v1:personal:openai%2Fgpt-4o',
          route: 'openai/gpt-4o',
          display: 'gpt-4o',
          connection: 'personal',
          connectionId: 'personal',
          connectionName: 'Personal',
          provider: 'openai',
          providerId: 'openai',
          providerLabel: 'OpenAI',
          available: true,
        },
        {
          modelRef: 'modelref:v1:work:openai%2Fgpt-4o',
          route: 'openai/gpt-4o',
          display: 'gpt-4o',
          connection: 'work',
          connectionId: 'work',
          connectionName: 'Work',
          provider: 'openai',
          providerId: 'openai',
          providerLabel: 'OpenAI',
          available: true,
        },
      ],
    });

    render(<SettingsPage />);

    const trigger = await screen.findByRole('button', { name: '主要模型' });
    expect(setDraftValue).not.toHaveBeenCalledWith('LITELLM_MODEL', expect.stringContaining('modelref:v1:'));
    fireEvent.click(trigger);
    const workOption = screen.getAllByRole('option', { name: /gpt-4o/ })
      .find((option) => option.textContent?.includes('Work'));
    expect(workOption).toBeDefined();
    fireEvent.click(workOption!);

    expect(setDraftValue).toHaveBeenCalledWith(
      'LITELLM_MODEL',
      'modelref:v1:work:openai%2Fgpt-4o',
    );
  });

  it('resolves one legacy route for display without dirtying or saving config on load', async () => {
    const modelField = {
      key: 'LITELLM_MODEL',
      value: 'openai/gpt-4o',
      rawValueExists: true,
      isMasked: false,
      schema: {
        key: 'LITELLM_MODEL',
        category: 'ai_model' as const,
        dataType: 'string' as const,
        uiControl: 'text' as const,
        isSensitive: false,
        isRequired: true,
        isEditable: true,
        options: [],
        validation: {},
        displayOrder: 1,
        uiPlacement: 'task_routing' as const,
      },
    };
    const configState = buildSystemConfigState();
    useSystemConfigMock.mockReturnValue(buildSystemConfigState({
      activeCategory: 'ai_model',
      activeSubCategory: 'model',
      itemsByCategory: { ...configState.itemsByCategory, ai_model: [modelField] },
    }));
    routerSearchParamsMock.params = new URLSearchParams({ section: 'ai_models', view: 'task_routing' });
    getLlmAvailableModels.mockResolvedValue({
      models: [{
        modelRef: 'modelref:v1:personal:openai%2Fgpt-4o',
        route: 'openai/gpt-4o',
        display: 'GPT-4o',
        connection: 'personal',
        connectionId: 'personal',
        connectionName: 'Personal Connection',
        provider: 'openai',
        providerId: 'openai',
        providerLabel: 'OpenAI',
        available: true,
      }],
    });

    render(<SettingsPage />);

    const trigger = await screen.findByRole('button', { name: '主要模型' });
    await waitFor(() => {
      expect(trigger).toHaveAttribute(
        'data-value',
        'modelref:v1:personal:openai%2Fgpt-4o',
      );
      expect(trigger).toHaveTextContent('GPT-4o');
      expect(trigger).toHaveTextContent('Personal Connection');
    });
    expect(setDraftValue).not.toHaveBeenCalled();
    expect(save).not.toHaveBeenCalled();
    expect(updateSystemConfig).not.toHaveBeenCalled();
  });

  it('resolves a unique legacy fallback for display without mutating or saving config on load', async () => {
    const fallbackModelRef = 'modelref:v1:personal:openai%2Fgpt-4o';
    const fallbackField = {
      key: 'LITELLM_FALLBACK_MODELS',
      value: 'openai/gpt-4o',
      rawValueExists: true,
      isMasked: false,
      schema: {
        key: 'LITELLM_FALLBACK_MODELS',
        category: 'ai_model' as const,
        dataType: 'string' as const,
        uiControl: 'text' as const,
        isSensitive: false,
        isRequired: false,
        isEditable: true,
        options: [],
        validation: {},
        displayOrder: 2,
        uiPlacement: 'task_routing' as const,
      },
    };
    const configState = buildSystemConfigState();
    useSystemConfigMock.mockReturnValue(buildSystemConfigState({
      activeCategory: 'ai_model',
      activeSubCategory: 'model',
      itemsByCategory: { ...configState.itemsByCategory, ai_model: [fallbackField] },
    }));
    routerSearchParamsMock.params = new URLSearchParams({ section: 'ai_models', view: 'reliability' });
    getLlmAvailableModels.mockResolvedValue({
      models: [{
        modelRef: fallbackModelRef,
        route: 'openai/gpt-4o',
        display: 'GPT-4o',
        connection: 'personal',
        connectionId: 'personal',
        connectionName: 'Personal Connection',
        provider: 'openai',
        providerId: 'openai',
        providerLabel: 'OpenAI',
        available: true,
      }],
    });

    render(<SettingsPage />);

    expect((await screen.findAllByText('GPT-4o · OpenAI · Personal Connection')).length)
      .toBeGreaterThan(0);
    expect(screen.queryByText('当前配置不可用')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '选择备用模型' }));
    expect(screen.getByRole('checkbox', {
      name: 'GPT-4o · OpenAI · Personal Connection',
    })).toBeChecked();
    expect(setDraftValue).not.toHaveBeenCalled();
    expect(save).not.toHaveBeenCalled();
    expect(updateSystemConfig).not.toHaveBeenCalled();
  });

  it('decodes a stale ModelRef for display while preserving its stored value', async () => {
    const staleModelRef = 'modelref:v1:retired_connection:openai%2Fretired-model';
    const modelField = {
      key: 'LITELLM_MODEL',
      value: staleModelRef,
      rawValueExists: true,
      isMasked: false,
      schema: {
        key: 'LITELLM_MODEL',
        category: 'ai_model' as const,
        dataType: 'string' as const,
        uiControl: 'text' as const,
        isSensitive: false,
        isRequired: true,
        isEditable: true,
        options: [],
        validation: {},
        displayOrder: 1,
        uiPlacement: 'task_routing' as const,
      },
    };
    const configState = buildSystemConfigState();
    useSystemConfigMock.mockReturnValue(buildSystemConfigState({
      activeCategory: 'ai_model',
      activeSubCategory: 'model',
      itemsByCategory: { ...configState.itemsByCategory, ai_model: [modelField] },
    }));
    routerSearchParamsMock.params = new URLSearchParams({ section: 'ai_models', view: 'task_routing' });
    getLlmAvailableModels.mockResolvedValue({
      models: [{
        modelRef: 'modelref:v1:current:openai%2Fgpt-4o',
        route: 'openai/gpt-4o',
        display: 'GPT-4o',
        connection: 'current',
        connectionId: 'current',
        connectionName: 'Current Connection',
        provider: 'openai',
        providerId: 'openai',
        providerLabel: 'OpenAI',
        available: true,
      }],
    });

    render(<SettingsPage />);

    const trigger = await screen.findByRole('button', { name: '主要模型' });
    await waitFor(() => expect(trigger).toHaveTextContent(
      'openai/retired-model · retired_connection',
    ));
    expect(trigger).toHaveAttribute('data-value', staleModelRef);
    expect(screen.getByText(
      '当前配置不可用：openai/retired-model · retired_connection',
    )).toBeInTheDocument();
    expect(setDraftValue).not.toHaveBeenCalled();
  });

  it('splits notification fields so Reports and Alerts render independent field sets', () => {
    const notifyField = (key: string, uiControl = 'text') => ({
      key,
      value: '',
      rawValueExists: false,
      isMasked: false,
      schema: {
        key,
        category: 'notification',
        dataType: 'string',
        uiControl,
        isSensitive: false,
        isRequired: false,
        isEditable: true,
        options: [],
        validation: {},
        displayOrder: 1,
      },
    });
    const notificationItems = [
      notifyField('REPORT_TYPE'),
      notifyField('REPORT_LANGUAGE'),
      notifyField('NOTIFICATION_ALERT_CHANNELS'),
      notifyField('NOTIFICATION_QUIET_HOURS'),
      notifyField('WECHAT_WEBHOOK_URL'),
    ];
    const configState = buildSystemConfigState();
    useSystemConfigMock.mockReturnValue(buildSystemConfigState({
      activeCategory: 'notification',
      itemsByCategory: { ...configState.itemsByCategory, notification: notificationItems },
    }));

    // Reports section: only report-output fields; no delivery-rule or channel fields.
    routerSearchParamsMock.params = new URLSearchParams({ section: 'reports', view: 'output' });
    const { rerender } = render(<SettingsPage />);
    expect(screen.getByTestId('settings-field-REPORT_TYPE')).toBeInTheDocument();
    expect(screen.getByTestId('settings-field-REPORT_LANGUAGE')).toBeInTheDocument();
    expect(screen.queryByTestId('settings-field-NOTIFICATION_ALERT_CHANNELS')).not.toBeInTheDocument();
    expect(screen.queryByTestId('settings-field-WECHAT_WEBHOOK_URL')).not.toBeInTheDocument();

    // Alerts section: delivery-rule fields; no report-output fields.
    routerSearchParamsMock.params = new URLSearchParams({ section: 'alerts', view: 'rules' });
    rerender(<SettingsPage />);
    expect(screen.getByTestId('settings-field-NOTIFICATION_ALERT_CHANNELS')).toBeInTheDocument();
    expect(screen.getByTestId('settings-field-NOTIFICATION_QUIET_HOURS')).toBeInTheDocument();
    expect(screen.queryByTestId('settings-field-REPORT_TYPE')).not.toBeInTheDocument();
    expect(screen.queryByTestId('settings-field-WECHAT_WEBHOOK_URL')).not.toBeInTheDocument();
  });

  it('limits channel routing options to configured channels and guides setup when none exist', () => {
    const routingItem = (options: string[]) => ({
      key: 'NOTIFICATION_ALERT_CHANNELS',
      value: '',
      rawValueExists: false,
      isMasked: false,
      schema: {
        key: 'NOTIFICATION_ALERT_CHANNELS',
        category: 'notification',
        dataType: 'array',
        uiControl: 'textarea',
        isSensitive: false,
        isRequired: false,
        isEditable: true,
        options: options.map((option) => ({ label: option, value: option })),
        validation: { allowed_values: options, multi_value: true, delimiter: ',' },
        displayOrder: 1,
      },
    });
    const channelItem = (key: string, value: string) => ({
      key,
      value,
      rawValueExists: value !== '',
      isMasked: false,
      schema: {
        key,
        category: 'notification',
        dataType: 'string',
        uiControl: 'text',
        isSensitive: false,
        isRequired: false,
        isEditable: true,
        options: [],
        validation: {},
        displayOrder: 2,
      },
    });
    const configState = buildSystemConfigState();
    useSystemConfigMock.mockReturnValue(buildSystemConfigState({
      activeCategory: 'notification',
      configuredNotificationChannels: ['wechat'],
      itemsByCategory: {
        ...configState.itemsByCategory,
        notification: [
          routingItem(['wechat', 'feishu', 'custom']),
          channelItem('WECHAT_WEBHOOK_URL', 'https://wx.example/hook'),
          channelItem('CUSTOM_WEBHOOK_URLS', ''),
        ],
      },
    }));
    routerSearchParamsMock.params = new URLSearchParams({ section: 'alerts', view: 'rules' });

    // Only channels with a configured key stay selectable.
    const { rerender, unmount } = render(<SettingsPage />);
    const field = screen.getByTestId('settings-field-NOTIFICATION_ALERT_CHANNELS');
    expect(within(field).getByText('wechat')).toBeInTheDocument();
    expect(within(field).queryByText('feishu')).not.toBeInTheDocument();
    expect(within(field).queryByText('custom')).not.toBeInTheDocument();

    // With no configured channel at all, the field shows guidance that jumps
    // to the notification channels setup view.
    useSystemConfigMock.mockReturnValue(buildSystemConfigState({
      activeCategory: 'notification',
      configuredNotificationChannels: [],
      itemsByCategory: {
        ...configState.itemsByCategory,
        notification: [
          routingItem(['wechat', 'feishu', 'custom']),
          channelItem('WECHAT_WEBHOOK_URL', ''),
        ],
      },
    }));
    // buildSystemConfigState resets the router params; restore the alerts view.
    routerSearchParamsMock.params = new URLSearchParams({ section: 'alerts', view: 'rules' });
    rerender(<SettingsPage />);
    const emptyField = screen.getByTestId('settings-field-NOTIFICATION_ALERT_CHANNELS');
    expect(within(emptyField).getByText('尚未配置任何通知渠道，配置成功后才能在这里选择接收渠道。')).toBeInTheDocument();
    fireEvent.click(within(emptyField).getByRole('button', { name: '去配置通知渠道' }));
    const [nextParams] = routerSearchParamsMock.setParams.mock.calls.at(-1) ?? [];
    expect(nextParams?.get('section')).toBe('notifications');
    expect(nextParams?.get('view')).toBe('channels');

    // During a rolling upgrade an old backend omits the authoritative channel
    // status. Keep the catalog and stored selection usable instead of treating
    // unknown as a confirmed empty set.
    useSystemConfigMock.mockReturnValue(buildSystemConfigState({
      activeCategory: 'notification',
      configuredNotificationChannels: null,
      itemsByCategory: {
        ...configState.itemsByCategory,
        notification: [
          { ...routingItem(['wechat', 'feishu', 'custom']), value: 'feishu' },
          channelItem('WECHAT_WEBHOOK_URL', '******'),
        ],
      },
    }));
    routerSearchParamsMock.params = new URLSearchParams({ section: 'alerts', view: 'rules' });
    rerender(<SettingsPage />);
    const unknownField = screen.getByTestId('settings-field-NOTIFICATION_ALERT_CHANNELS');
    expect(within(unknownField).getByText('feishu')).toBeInTheDocument();
    expect(within(unknownField).queryByText('尚未配置任何通知渠道，配置成功后才能在这里选择接收渠道。')).not.toBeInTheDocument();
    expect(within(unknownField).getByText('wechat')).toBeInTheDocument();
    expect(within(unknownField).getByText('custom')).toBeInTheDocument();
    unmount();
  });

  it('keeps masked ntfy and Gotify channels available from the backend routing status', () => {
    const routingItem = {
      key: 'NOTIFICATION_ALERT_CHANNELS',
      value: '',
      rawValueExists: false,
      isMasked: false,
      schema: {
        key: 'NOTIFICATION_ALERT_CHANNELS',
        category: 'notification',
        dataType: 'array',
        uiControl: 'textarea',
        isSensitive: false,
        isRequired: false,
        isEditable: true,
        options: ['ntfy', 'gotify', 'wechat'].map((option) => ({ label: option, value: option })),
        validation: {
          allowed_values: ['ntfy', 'gotify', 'wechat'],
          multi_value: true,
          delimiter: ',',
        },
        displayOrder: 1,
      },
    };
    const maskedChannelItem = (key: string) => ({
      key,
      value: '******',
      rawValueExists: true,
      isMasked: true,
      schema: {
        key,
        category: 'notification',
        dataType: 'string',
        uiControl: 'password',
        isSensitive: true,
        isRequired: false,
        isEditable: true,
        options: [],
        validation: {},
        displayOrder: 2,
      },
    });
    const configState = buildSystemConfigState();
    useSystemConfigMock.mockReturnValue(buildSystemConfigState({
      activeCategory: 'notification',
      configuredNotificationChannels: ['ntfy', 'gotify'],
      itemsByCategory: {
        ...configState.itemsByCategory,
        notification: [
          routingItem,
          maskedChannelItem('NTFY_URL'),
          maskedChannelItem('GOTIFY_URL'),
          maskedChannelItem('GOTIFY_TOKEN'),
        ],
      },
    }));
    routerSearchParamsMock.params = new URLSearchParams({ section: 'alerts', view: 'rules' });

    render(<SettingsPage />);

    const field = screen.getByTestId('settings-field-NOTIFICATION_ALERT_CHANNELS');
    expect(within(field).getByText('ntfy')).toBeInTheDocument();
    expect(within(field).getByText('gotify')).toBeInTheDocument();
    expect(within(field).queryByText('wechat')).not.toBeInTheDocument();
  });

  it('lists validation errors and jumps to the errored field section from any section', () => {
    useSystemConfigMock.mockReturnValue(buildSystemConfigState({
      activeCategory: 'system',
      issueByKey: {
        WECHAT_WEBHOOK_URL: [
          { key: 'WECHAT_WEBHOOK_URL', code: 'invalid', message: '企业微信 Webhook 地址格式不正确', severity: 'error' },
        ],
      },
    }));
    // Start on a section that does not own the errored field.
    routerSearchParamsMock.params = new URLSearchParams({ section: 'system_security', view: 'runtime' });

    render(<SettingsPage />);

    expect(screen.getByText('有 1 项配置需要修正')).toBeInTheDocument();
    expect(screen.getByText('企业微信 Webhook 地址格式不正确')).toBeInTheDocument();

    // Clicking the summary entry navigates to the section that owns the field.
    fireEvent.click(screen.getByRole('button', { name: /前往修正/ }));
    const [nextParams] = routerSearchParamsMock.setParams.mock.calls.at(-1) ?? [];
    expect(nextParams?.get('section')).toBe('notifications');
    expect(nextParams?.get('view')).toBe('channels');
  });

  it.each(['de', 'ja', 'zh-TW'] as const)(
    'uses the per-field %s title for a known field without a help key in the validation error summary',
    async (language) => {
      const configState = buildSystemConfigState();
      useSystemConfigMock.mockReturnValue(buildSystemConfigState({
        activeCategory: 'system',
        itemsByCategory: {
          ...configState.itemsByCategory,
          ai_model: [
            ...configState.itemsByCategory.ai_model,
            {
              key: 'OPENAI_VISION_MODEL',
              value: 'gpt-4o',
              rawValueExists: true,
              isMasked: false,
              schema: {
                key: 'OPENAI_VISION_MODEL',
                title: 'OpenAI Vision Model',
                category: 'ai_model',
                dataType: 'string',
                uiControl: 'text',
                isSensitive: false,
                isRequired: false,
                isEditable: true,
                options: [],
                validation: {},
                displayOrder: 2,
              },
            },
          ],
        },
        issueByKey: {
          OPENAI_VISION_MODEL: [
            {
              key: 'OPENAI_VISION_MODEL',
              code: 'invalid',
              message: 'Unsupported backend',
              severity: 'error',
            },
          ],
        },
      }));
      routerSearchParamsMock.params = new URLSearchParams({ section: 'system_security', view: 'runtime' });
      await loadUiLanguageTranslations(language);
      const expectedTitle = getFieldTitle('OPENAI_VISION_MODEL', undefined, language);

      render(
        <UiLanguageProvider initialLanguage={language}>
          <SettingsPage />
        </UiLanguageProvider>,
      );

      expect(expectedTitle).not.toBe('OpenAI Vision Model');
      expect(screen.getByRole('button', { name: `前往修正: ${expectedTitle}` })).toBeInTheDocument();
      expect(screen.queryByText('OpenAI Vision Model')).not.toBeInTheDocument();
    },
  );

  it('routes a dynamic connection error to Model Access and sends an explicit field-focus request', async () => {
    const configState = buildSystemConfigState();
    useSystemConfigMock.mockReturnValue(buildSystemConfigState({
      activeCategory: 'system',
      itemsByCategory: {
        ...configState.itemsByCategory,
        ai_model: [
          ...configState.itemsByCategory.ai_model,
          {
            key: 'LLM_OPENAI_API_KEY',
            value: '******',
            rawValueExists: true,
            isMasked: true,
            schema: {
              key: 'LLM_OPENAI_API_KEY',
              category: 'ai_model',
              dataType: 'string',
              uiControl: 'password',
              isSensitive: true,
              isRequired: false,
              isEditable: true,
              options: [],
              validation: {},
              displayOrder: 9000,
              uiPlacement: 'model_access' as const,
            },
          },
        ],
      },
      issueByKey: {
        LLM_OPENAI_API_KEY: [
          { key: 'LLM_OPENAI_API_KEY', code: 'invalid', message: 'API 密钥无效', severity: 'error' },
        ],
      },
    }));
    routerSearchParamsMock.params = new URLSearchParams({ section: 'system_security', view: 'runtime' });

    const { rerender } = render(<SettingsPage />);
    fireEvent.click(screen.getByRole('button', { name: /前往修正/ }));

    const [nextParams] = routerSearchParamsMock.setParams.mock.calls.at(-1) ?? [];
    expect(nextParams?.get('section')).toBe('ai_models');
    expect(nextParams?.get('view')).toBe('connections');

    routerSearchParamsMock.params = nextParams;
    rerender(<SettingsPage />);
    expect(await screen.findByTestId('llm-channel-focus-request')).toHaveTextContent('LLM_OPENAI_API_KEY');
  });

  it('warns that changed restart-required settings need a restart to take effect', () => {
    const restartField = {
      key: 'WEBUI_PORT',
      value: '8001',
      rawValueExists: true,
      isMasked: false,
      schema: {
        key: 'WEBUI_PORT',
        category: 'system',
        dataType: 'integer',
        uiControl: 'number',
        isSensitive: false,
        isRequired: false,
        isEditable: true,
        options: [],
        validation: {},
        displayOrder: 2,
        warningCodes: ['restart_required'],
      },
    };
    const configState = buildSystemConfigState();
    // No dirty restart field -> no notice.
    useSystemConfigMock.mockReturnValue(buildSystemConfigState({
      activeCategory: 'system',
      itemsByCategory: { ...configState.itemsByCategory, system: [restartField] },
      dirtyKeys: [],
    }));
    const { rerender } = render(<SettingsPage />);
    expect(screen.queryByText(/部分已修改的配置需要重启服务后才会生效/, { exact: false })).not.toBeInTheDocument();

    // The restart-required field is now dirty -> the page-level notice shows.
    useSystemConfigMock.mockReturnValue(buildSystemConfigState({
      activeCategory: 'system',
      itemsByCategory: { ...configState.itemsByCategory, system: [restartField] },
      dirtyKeys: ['WEBUI_PORT'],
    }));
    rerender(<SettingsPage />);
    expect(screen.getByText(/部分已修改的配置需要重启服务后才会生效/, { exact: false })).toBeInTheDocument();
  });

  it('moves internal HMAC keys to the top-level Advanced section, out of Connections', () => {
    const aiField = (key: string, value: string, displayOrder: number, uiControl = 'text') => ({
      key,
      value,
      rawValueExists: Boolean(value),
      isMasked: false,
      schema: {
        key,
        category: 'ai_model',
        dataType: 'string',
        uiControl,
        isSensitive: false,
        isRequired: false,
        isEditable: true,
        options: [],
        validation: {},
        displayOrder,
      },
    });
    const configState = buildSystemConfigState();
    const withAiItems = () => buildSystemConfigState({
      activeCategory: 'ai_model',
      activeSubCategory: 'model',
      itemsByCategory: {
        ...configState.itemsByCategory,
        ai_model: [
          aiField('LLM_CHANNELS', 'openai', 1),
          aiField('LLM_USAGE_HMAC_SECRET', '', 9, 'password'),
          aiField('LLM_USAGE_HMAC_KEY_VERSION', '1', 10),
        ],
      },
    });

    // Connections view: the internal HMAC keys no longer clutter it.
    useSystemConfigMock.mockReturnValue(withAiItems());
    routerSearchParamsMock.params = new URLSearchParams({ section: 'ai_models', view: 'connections' });
    const { rerender } = render(<SettingsPage />);
    expect(screen.queryByTestId('settings-field-LLM_USAGE_HMAC_SECRET')).not.toBeInTheDocument();

    // Top-level Advanced section: renders the aggregated internal keys.
    useSystemConfigMock.mockReturnValue(withAiItems());
    routerSearchParamsMock.params = new URLSearchParams({ section: 'advanced', view: 'raw_config' });
    rerender(<SettingsPage />);
    expect(screen.getByTestId('settings-field-LLM_USAGE_HMAC_SECRET')).toBeInTheDocument();
    expect(screen.getByTestId('settings-field-LLM_USAGE_HMAC_KEY_VERSION')).toBeInTheDocument();
  });

  it('opens the first-run wizard from Overview and saves its minimal config', async () => {
    save.mockResolvedValue({ success: true });
    // The wizard entry is only the first-time path when setup is incomplete.
    getSetupStatus.mockResolvedValue({
      isComplete: false,
      readyForSmoke: false,
      requiredMissingKeys: ['LITELLM_MODEL'],
      checks: [],
    });
    useSystemConfigMock.mockReturnValue(buildSystemConfigState({ activeCategory: 'base' }));

    render(<SettingsPage />);

    // The entry button is enabled once the async provider catalog has loaded.
    await waitFor(() => expect(screen.getByRole('button', { name: '启动向导' })).toBeEnabled());
    fireEvent.click(screen.getByRole('button', { name: '启动向导' }));
    expect(screen.getByRole('dialog', { name: 'first-run-wizard' })).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'wizard apply' }));

    await waitFor(() => expect(save).toHaveBeenCalledWith([
      { key: 'LLM_CHANNELS', value: 'deepseek' },
      { key: 'LLM_DEEPSEEK_API_KEY', value: 'sk-wizard' },
    ]));
    // The wizard closes once the save succeeds.
    await waitFor(() =>
      expect(screen.queryByRole('dialog', { name: 'first-run-wizard' })).not.toBeInTheDocument());
  });

  it('rejects a Wizard Connection payload at the page adapter under a partial schema', async () => {
    getSetupStatus.mockResolvedValue({
      isComplete: false,
      readyForSmoke: false,
      requiredMissingKeys: ['LITELLM_MODEL'],
      checks: [],
    });
    getLlmProviderCatalog.mockResolvedValueOnce({
      providers: [
        { id: 'deepseek', label: 'DeepSeek', protocol: 'deepseek', defaultBaseUrl: 'https://api.deepseek.com', capabilities: [], requiresApiKey: true, requiresBaseUrl: false, supportsDiscovery: true, isLocal: false, isCustom: false },
      ],
      connectionFields: [{
        key: 'models',
        dataType: 'array',
        isSensitive: false,
        isRequired: false,
        contract: { requirement: 'optional' },
      }],
    });
    useSystemConfigMock.mockReturnValue(buildSystemConfigState({ activeCategory: 'base' }));

    render(<SettingsPage />);
    await waitFor(() => expect(screen.getByRole('button', { name: '启动向导' })).toBeEnabled());
    fireEvent.click(screen.getByRole('button', { name: '启动向导' }));
    fireEvent.click(screen.getByRole('button', { name: 'wizard apply' }));

    await waitFor(() => expect(save).not.toHaveBeenCalled());
  });

  it('rejects a Wizard field that a complete schema marks read-only', async () => {
    getSetupStatus.mockResolvedValue({
      isComplete: false,
      readyForSmoke: false,
      requiredMissingKeys: ['LITELLM_MODEL'],
      checks: [],
    });
    getLlmProviderCatalog.mockResolvedValueOnce({
      providers: [
        { id: 'deepseek', label: 'DeepSeek', protocol: 'deepseek', defaultBaseUrl: 'https://api.deepseek.com', capabilities: [], requiresApiKey: true, requiresBaseUrl: false, supportsDiscovery: true, isLocal: false, isCustom: false },
      ],
      connectionFields: withTestConnectionCoreFields([
        TEST_CONNECTION_NAME_FIELD,
        TEST_PROVIDER_ID_FIELD,
        {
          key: 'base_url',
          dataType: 'string',
          isSensitive: false,
          isRequired: false,
          contract: { requirement: 'inherited' },
        },
      ]),
    });
    useSystemConfigMock.mockReturnValue(buildSystemConfigState({ activeCategory: 'base' }));

    render(<SettingsPage />);
    await waitFor(() => expect(screen.getByRole('button', { name: '启动向导' })).toBeEnabled());
    fireEvent.click(screen.getByRole('button', { name: '启动向导' }));
    fireEvent.click(screen.getByRole('button', { name: 'wizard inject read-only field' }));

    await waitFor(() => expect(save).not.toHaveBeenCalled());
    expect(screen.getByRole('dialog', { name: 'first-run-wizard' })).toBeInTheDocument();
  });

  it('rejects a Wizard provider identity that is absent from the authoritative Catalog', async () => {
    getSetupStatus.mockResolvedValue({
      isComplete: false,
      readyForSmoke: false,
      requiredMissingKeys: ['LITELLM_MODEL'],
      checks: [],
    });
    getLlmProviderCatalog.mockResolvedValueOnce({
      providers: [
        { id: 'deepseek', label: 'DeepSeek', protocol: 'deepseek', defaultBaseUrl: 'https://api.deepseek.com', capabilities: [], requiresApiKey: true, requiresBaseUrl: false, supportsDiscovery: true, isLocal: false, isCustom: false },
      ],
      connectionFields: withTestConnectionCoreFields([
        TEST_CONNECTION_NAME_FIELD,
        { key: 'display_name', dataType: 'string', isSensitive: false, isRequired: true, contract: { requirement: 'required' } },
        TEST_PROVIDER_ID_FIELD,
        { key: 'protocol', dataType: 'string', isSensitive: false, isRequired: true, contract: { requirement: 'required' } },
        { key: 'enabled', dataType: 'boolean', isSensitive: false, isRequired: true, contract: { requirement: 'required' } },
      ]),
    });
    useSystemConfigMock.mockReturnValue(buildSystemConfigState({ activeCategory: 'base' }));

    render(<SettingsPage />);
    await waitFor(() => expect(screen.getByRole('button', { name: '启动向导' })).toBeEnabled());
    fireEvent.click(screen.getByRole('button', { name: '启动向导' }));
    fireEvent.click(screen.getByRole('button', { name: 'wizard apply unknown provider' }));

    await waitFor(() => expect(save).not.toHaveBeenCalled());
    expect(screen.getByRole('dialog', { name: 'first-run-wizard' })).toBeInTheDocument();
  });

  it('hides the first-run wizard entry once setup is complete', async () => {
    getSetupStatus.mockResolvedValue({
      isComplete: true,
      readyForSmoke: true,
      requiredMissingKeys: [],
      checks: [],
    });
    useSystemConfigMock.mockReturnValue(buildSystemConfigState({ activeCategory: 'base' }));

    render(<SettingsPage />);

    // Configured users no longer see the first-run "Start wizard" entry — they
    // add a service from the model-access cards instead.
    await waitFor(() => expect(getSetupStatus).toHaveBeenCalled());
    await waitFor(() =>
      expect(screen.queryByRole('button', { name: '启动向导' })).not.toBeInTheDocument());
  });

  it('routes prompt cache settings to their explicit developer diagnostics placement', () => {
    const aiField = (key: string, displayOrder: number, value = '') => ({
      key,
      value,
      rawValueExists: Boolean(value),
      isMasked: false,
      schema: {
        key,
        category: 'ai_model',
        dataType: 'string',
        uiControl: key === 'LLM_PROMPT_CACHE_DIAGNOSTICS_LEVEL' ? 'select' : 'text',
        isSensitive: false,
        isRequired: false,
        isEditable: true,
        options: key === 'LLM_PROMPT_CACHE_DIAGNOSTICS_LEVEL' ? ['off', 'basic', 'debug'] : [],
        validation: {},
        displayOrder,
        uiPlacement: 'developer_diagnostics' as const,
      },
    });
    const configState = buildSystemConfigState();
    useSystemConfigMock.mockReturnValue(buildSystemConfigState({
      activeCategory: 'ai_model',
      activeSubCategory: 'model',
      itemsByCategory: {
        ...configState.itemsByCategory,
        ai_model: [
          aiField('LITELLM_CONFIG', 10, './litellm.yaml'),
          aiField('LLM_PROMPT_CACHE_TELEMETRY_ENABLED', 20, 'true'),
          aiField('LLM_PROMPT_CACHE_HINTS_ENABLED', 21, 'false'),
          aiField('LLM_PROMPT_CACHE_DIAGNOSTICS_LEVEL', 22, 'off'),
        ],
      },
    }));

    routerSearchParamsMock.params = new URLSearchParams({ section: 'ai_models', view: 'connections' });
    const { rerender } = render(<SettingsPage />);
    expect(screen.queryByTestId('settings-field-LLM_PROMPT_CACHE_TELEMETRY_ENABLED')).not.toBeInTheDocument();

    routerSearchParamsMock.params = new URLSearchParams({ section: 'advanced', view: 'raw_config' });
    rerender(<SettingsPage />);
    expect(screen.getByTestId('settings-field-LLM_PROMPT_CACHE_TELEMETRY_ENABLED')).toBeInTheDocument();
    expect(screen.getByTestId('settings-field-LLM_PROMPT_CACHE_HINTS_ENABLED')).toBeInTheDocument();
    expect(screen.getByTestId('settings-field-LLM_PROMPT_CACHE_DIAGNOSTICS_LEVEL')).toBeInTheDocument();
  });

  it('notifies alphasift status update after its autosave group is persisted as false', async () => {
    save.mockResolvedValue({ success: true });
    getChangedItems.mockReturnValue([{ key: 'ALPHASIFT_ENABLED', value: 'false' }]);

    useSystemConfigMock.mockReturnValue(buildSystemConfigState({
      hasDirty: true,
      dirtyCount: 1,
      getChangedItems: () => [{ key: 'ALPHASIFT_ENABLED', value: 'false' }],
    }));

    render(<SettingsPage />);

    await waitFor(() => expect(save).toHaveBeenCalledTimes(1), { timeout: 2000 });
    expect(notifyAlphaSiftConfigChanged).toHaveBeenCalledTimes(1);
    expect(notifySystemConfigChanged).toHaveBeenCalledTimes(1);
    expect(alphasiftEnable).not.toHaveBeenCalled();
    expect(alphasiftInstall).not.toHaveBeenCalled();
  });

  it('runs the AlphaSift enable flow after autosave persists ALPHASIFT_ENABLED', async () => {
    save.mockResolvedValue({ success: true });
    getChangedItems.mockReturnValue([{ key: 'ALPHASIFT_ENABLED', value: 'true' }]);

    useSystemConfigMock.mockReturnValue(buildSystemConfigState({
      hasDirty: true,
      dirtyCount: 1,
      getChangedItems: () => [{ key: 'ALPHASIFT_ENABLED', value: 'true' }],
    }));

    render(<SettingsPage />);

    await waitFor(() => expect(save).toHaveBeenCalledTimes(1), { timeout: 2000 });
    expect(notifySystemConfigChanged).toHaveBeenCalledTimes(1);
    expect(alphasiftEnable).toHaveBeenCalledTimes(1);
    expect(alphasiftInstall).not.toHaveBeenCalled();
    expect(refreshAfterExternalSave).toHaveBeenCalledWith(['ALPHASIFT_ENABLED']);
  });

  it('does not notify alphasift status when another autosave group updates', async () => {
    save.mockResolvedValue({ success: true });
    useSystemConfigMock.mockReturnValue(buildSystemConfigState({
      hasDirty: true,
      dirtyCount: 1,
      getChangedItems: () => [{ key: 'LLM_CHANNELS', value: 'primary,backup' }],
    }));

    render(<SettingsPage />);

    await waitFor(() => expect(save).toHaveBeenCalledTimes(1), { timeout: 2000 });
    expect(notifySystemConfigChanged).toHaveBeenCalledTimes(1);
    expect(notifyAlphaSiftConfigChanged).not.toHaveBeenCalled();
  });

  it('runs AlphaSift enable flow from the settings card', async () => {
    const configState = buildSystemConfigState();
    useSystemConfigMock.mockReturnValue(buildSystemConfigState({
      activeCategory: 'data_source',
      activeSubCategory: 'providers',
      itemsByCategory: {
        ...configState.itemsByCategory,
        data_source: [
          {
            key: 'ALPHASIFT_ENABLED',
            value: 'false',
            rawValueExists: true,
            isMasked: false,
            schema: {
              key: 'ALPHASIFT_ENABLED',
              category: 'data_source',
              dataType: 'boolean',
              uiControl: 'switch',
              isSensitive: false,
              isRequired: false,
              isEditable: true,
              options: [],
              validation: {},
              displayOrder: 16,
            },
          },
          {
            key: 'ALPHASIFT_INSTALL_SPEC',
            value: 'git+https://github.com/ZhuLinsen/alphasift.git@2c76b2b6074ae3bae01d52e5e830a4af3e3246b2',
            rawValueExists: true,
            isMasked: false,
            schema: {
              key: 'ALPHASIFT_INSTALL_SPEC',
              category: 'data_source',
              dataType: 'string',
              uiControl: 'password',
              isSensitive: true,
              isRequired: false,
              isEditable: true,
              options: [],
              validation: {},
              displayOrder: 17,
            },
          },
        ],
      },
    }));

    render(<SettingsPage />);

    fireEvent.click(screen.getByRole('button', { name: '开启选股' }));

    await waitFor(() => expect(alphasiftEnable).toHaveBeenCalledTimes(1));
    expect(updateSystemConfig).not.toHaveBeenCalled();
    expect(alphasiftInstall).not.toHaveBeenCalled();
    expect(refreshAfterExternalSave).toHaveBeenCalledWith(['ALPHASIFT_ENABLED']);
  });

  it('does not render raw AlphaSift install spec in the settings card', () => {
    const privateInstallSpec = 'git+https://user:token@example.com/internal/alphasift.git';
    const configState = buildSystemConfigState();
    useSystemConfigMock.mockReturnValue(buildSystemConfigState({
      activeCategory: 'data_source',
      activeSubCategory: 'providers',
      itemsByCategory: {
        ...configState.itemsByCategory,
        data_source: [
          {
            key: 'ALPHASIFT_ENABLED',
            value: 'true',
            rawValueExists: true,
            isMasked: false,
            schema: {
              key: 'ALPHASIFT_ENABLED',
              category: 'data_source',
              dataType: 'boolean',
              uiControl: 'switch',
              isSensitive: false,
              isRequired: false,
              isEditable: true,
              options: [],
              validation: {},
              displayOrder: 16,
            },
          },
          {
            key: 'ALPHASIFT_INSTALL_SPEC',
            value: privateInstallSpec,
            rawValueExists: true,
            isMasked: true,
            schema: {
              key: 'ALPHASIFT_INSTALL_SPEC',
              category: 'data_source',
              dataType: 'string',
              uiControl: 'password',
              isSensitive: true,
              isRequired: false,
              isEditable: true,
              options: [],
              validation: {},
              displayOrder: 17,
            },
          },
        ],
      },
    }));

    render(<SettingsPage />);

    expect(screen.getByText('启用内置 AlphaSift 实验性质选股能力。')).toBeInTheDocument();
    expect(screen.queryByText(privateInstallSpec)).not.toBeInTheDocument();
    expect(screen.queryByText(/安装来源/)).not.toBeInTheDocument();
  });

  it('maps ALPHASIFT_ENABLED to the AlphaSift card instead of a generic settings field', () => {
    const configState = buildSystemConfigState();
    useSystemConfigMock.mockReturnValue(buildSystemConfigState({
      activeCategory: 'data_source',
      activeSubCategory: 'providers',
      itemsByCategory: {
        ...configState.itemsByCategory,
        data_source: [
          {
            key: 'ALPHASIFT_ENABLED',
            value: 'false',
            rawValueExists: true,
            isMasked: false,
            schema: {
              key: 'ALPHASIFT_ENABLED',
              category: 'data_source',
              dataType: 'boolean',
              uiControl: 'switch',
              isSensitive: false,
              isRequired: false,
              isEditable: true,
              options: [],
              validation: {},
              displayOrder: 16,
            },
          },
          {
            key: 'ALPHASIFT_INSTALL_SPEC',
            value: '******',
            rawValueExists: true,
            isMasked: true,
            schema: {
              key: 'ALPHASIFT_INSTALL_SPEC',
              category: 'data_source',
              dataType: 'string',
              uiControl: 'password',
              isSensitive: true,
              isRequired: false,
              isEditable: true,
              options: [],
              validation: {},
              displayOrder: 17,
            },
          },
        ],
      },
    }));

    render(<SettingsPage />);

    expect(screen.getByRole('button', { name: '开启选股' })).toBeInTheDocument();
    expect(screen.queryByTestId('settings-field-ALPHASIFT_ENABLED')).not.toBeInTheDocument();
    const providersPanel = screen.getByTestId('data-providers-panel');
    expect(within(providersPanel).getByText('ALPHASIFT_INSTALL_SPEC')).toBeInTheDocument();
    expect(within(providersPanel).queryByText('ALPHASIFT_ENABLED')).not.toBeInTheDocument();
  });

  it('scopes setup and AlphaSift helper cards to their related categories', async () => {
    const configState = buildSystemConfigState();
    const dataSourceItems = [
      {
        key: 'ALPHASIFT_ENABLED',
        value: 'false',
        rawValueExists: true,
        isMasked: false,
        schema: {
          key: 'ALPHASIFT_ENABLED',
          category: 'data_source',
          dataType: 'boolean',
          uiControl: 'switch',
          isSensitive: false,
          isRequired: false,
          isEditable: true,
          options: [],
          validation: {},
          displayOrder: 16,
        },
      },
      {
        key: 'NEWS_MAX_AGE_DAYS',
        value: '3',
        rawValueExists: true,
        isMasked: false,
        schema: {
          key: 'NEWS_MAX_AGE_DAYS',
          category: 'data_source',
          dataType: 'integer',
          uiControl: 'number',
          isSensitive: false,
          isRequired: false,
          isEditable: true,
          options: [],
          validation: {},
          displayOrder: 1,
        },
      },
    ];

    useSystemConfigMock.mockReturnValue(buildSystemConfigState({
      activeCategory: 'base',
      itemsByCategory: {
        ...configState.itemsByCategory,
        data_source: dataSourceItems,
      },
    }));

    const { rerender } = render(<SettingsPage />);

    expect(await screen.findByRole('heading', { name: '首次启动配置检查' })).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'AlphaSift 选股' })).not.toBeInTheDocument();

    useSystemConfigMock.mockReturnValue(buildSystemConfigState({
      activeCategory: 'ai_model',
      itemsByCategory: {
        ...configState.itemsByCategory,
        data_source: dataSourceItems,
      },
    }));
    rerender(<SettingsPage />);

    expect(screen.queryByRole('heading', { name: '首次启动配置检查' })).not.toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'AlphaSift 选股' })).not.toBeInTheDocument();

    useSystemConfigMock.mockReturnValue(buildSystemConfigState({
      activeCategory: 'data_source',
      itemsByCategory: {
        ...configState.itemsByCategory,
        data_source: dataSourceItems,
      },
    }));
    rerender(<SettingsPage />);

    // The default data_source tab is the source tab; the AlphaSift card
    // lives on the providers tab only.
    expect(screen.queryByRole('heading', { name: 'AlphaSift 选股' })).not.toBeInTheDocument();

    useSystemConfigMock.mockReturnValue(buildSystemConfigState({
      activeCategory: 'data_source',
      activeSubCategory: 'providers',
      itemsByCategory: {
        ...configState.itemsByCategory,
        data_source: dataSourceItems,
      },
    }));
    rerender(<SettingsPage />);

    expect(await screen.findByRole('heading', { name: 'AlphaSift 选股' })).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: '首次启动配置检查' })).not.toBeInTheDocument();
  });

  it('maps schedule settings to the scheduler card instead of generic raw fields', async () => {
    const configState = buildSystemConfigState();
    useSystemConfigMock.mockReturnValue(buildSystemConfigState({
      activeCategory: 'system',
      itemsByCategory: {
        ...configState.itemsByCategory,
        system: [
          ...configState.itemsByCategory.system,
          {
            key: 'SCHEDULE_ENABLED',
            value: 'true',
            rawValueExists: true,
            isMasked: false,
            schema: {
              key: 'SCHEDULE_ENABLED',
              category: 'system',
              dataType: 'boolean',
              uiControl: 'switch',
              isSensitive: false,
              isRequired: false,
              isEditable: true,
              options: [],
              validation: {},
              displayOrder: 8,
            },
          },
          {
            key: 'SCHEDULE_TIME',
            value: '18:00',
            rawValueExists: true,
            isMasked: false,
            schema: {
              key: 'SCHEDULE_TIME',
              category: 'system',
              dataType: 'time',
              uiControl: 'time',
              isSensitive: false,
              isRequired: false,
              isEditable: true,
              options: [],
              validation: {},
              displayOrder: 10,
            },
          },
          {
            key: 'SCHEDULE_TIMES',
            value: '09:20,15:10',
            rawValueExists: true,
            isMasked: false,
            schema: {
              key: 'SCHEDULE_TIMES',
              category: 'system',
              dataType: 'string',
              uiControl: 'text',
              isSensitive: false,
              isRequired: false,
              isEditable: true,
              options: [],
              validation: {},
              displayOrder: 11,
            },
          },
          {
            key: 'SCHEDULE_RUN_IMMEDIATELY',
            value: 'false',
            rawValueExists: true,
            isMasked: false,
            schema: {
              key: 'SCHEDULE_RUN_IMMEDIATELY',
              category: 'system',
              dataType: 'boolean',
              uiControl: 'switch',
              isSensitive: false,
              isRequired: false,
              isEditable: true,
              options: [],
              validation: {},
              displayOrder: 12,
            },
          },
          {
            key: 'LOG_LEVEL',
            value: 'INFO',
            rawValueExists: true,
            isMasked: false,
            schema: {
              key: 'LOG_LEVEL',
              category: 'system',
              dataType: 'string',
              uiControl: 'select',
              isSensitive: false,
              isRequired: false,
              isEditable: true,
              options: ['INFO', 'DEBUG'],
              validation: {},
              displayOrder: 50,
            },
          },
        ],
      },
    }));

    render(<SettingsPage />);

    fireEvent.click(screen.getByRole('tab', { name: '定时任务' }));
    expect(await screen.findByTestId('scheduler-settings-card')).toBeInTheDocument();
    expect(screen.queryByTestId('settings-field-SCHEDULE_ENABLED')).not.toBeInTheDocument();
    expect(screen.queryByTestId('settings-field-SCHEDULE_TIME')).not.toBeInTheDocument();
    expect(screen.queryByTestId('settings-field-SCHEDULE_TIMES')).not.toBeInTheDocument();
    expect(screen.queryByTestId('settings-field-SCHEDULE_RUN_IMMEDIATELY')).not.toBeInTheDocument();
    expect(screen.getByTestId('settings-field-LOG_LEVEL')).toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: '删除时间' })[0]).toHaveClass('h-8', 'w-8');
    const enabledSwitch = screen.getByTestId('scheduler-enabled-switch');
    expect(enabledSwitch).toHaveAttribute('role', 'switch');
    expect(enabledSwitch).toHaveClass('h-11', 'w-11');
    expect(enabledSwitch.firstElementChild).toHaveClass('h-6', 'w-10');
    const timeInput = screen.getByTestId('scheduler-time-input-0');
    expect(timeInput).toHaveClass('h-9', 'min-h-9');
    expect(timeInput).toHaveAttribute('type', 'button');

    fireEvent.click(timeInput);
    fireEvent.click(document.querySelector<HTMLButtonElement>('[data-time-hour="10"]')!);
    fireEvent.click(document.querySelector<HTMLButtonElement>('[data-time-minute="30"]')!);
    fireEvent.click(screen.getByRole('button', { name: '确定' }));

    expect(setDraftValue).toHaveBeenCalledWith('SCHEDULE_TIMES', '10:30,15:10');

    const callCountBeforeAdd = setDraftValue.mock.calls.length;
    fireEvent.click(screen.getByTestId('scheduler-add-time-button'));
    const newTimeInput = screen.getByTestId('scheduler-new-time-input');
    expect(setDraftValue).toHaveBeenCalledTimes(callCountBeforeAdd);
    await waitFor(() => expect(newTimeInput).toHaveAttribute('aria-expanded', 'true'));
    fireEvent.click(document.querySelector<HTMLButtonElement>('[data-time-hour="18"]')!);
    fireEvent.click(document.querySelector<HTMLButtonElement>('[data-time-minute="30"]')!);
    fireEvent.click(screen.getByRole('button', { name: '确定' }));
    expect(setDraftValue).toHaveBeenLastCalledWith('SCHEDULE_TIMES', '09:20,15:10,18:30');

    fireEvent.click(screen.getByTestId('scheduler-run-now-button'));

    await waitFor(() => expect(runSchedulerNow).toHaveBeenCalledTimes(1));
  });

  it('commits valid values from the shared schedule time picker', async () => {
    const configState = buildSystemConfigState();
    useSystemConfigMock.mockReturnValue(buildSystemConfigState({
      activeCategory: 'system',
      itemsByCategory: {
        ...configState.itemsByCategory,
        system: [
          ...configState.itemsByCategory.system,
          {
            key: 'SCHEDULE_ENABLED',
            value: 'true',
            rawValueExists: true,
            isMasked: false,
            schema: {
              key: 'SCHEDULE_ENABLED',
              category: 'system',
              dataType: 'boolean',
              uiControl: 'switch',
              isSensitive: false,
              isRequired: false,
              isEditable: true,
              options: [],
              validation: {},
              displayOrder: 8,
            },
          },
          {
            key: 'SCHEDULE_TIMES',
            value: '18:00,15:10',
            rawValueExists: true,
            isMasked: false,
            schema: {
              key: 'SCHEDULE_TIMES',
              category: 'system',
              dataType: 'string',
              uiControl: 'text',
              isSensitive: false,
              isRequired: false,
              isEditable: true,
              options: [],
              validation: {},
              displayOrder: 11,
            },
          },
        ],
      },
    }));

    render(<SettingsPage />);

    const timeInput = await screen.findByTestId('scheduler-time-input-0');

    expect(timeInput).toHaveAttribute('type', 'button');
    fireEvent.click(timeInput);
    fireEvent.click(document.querySelector<HTMLButtonElement>('[data-time-hour="09"]')!);
    fireEvent.click(document.querySelector<HTMLButtonElement>('[data-time-minute="05"]')!);
    fireEvent.click(screen.getByRole('button', { name: '确定' }));
    expect(setDraftValue).toHaveBeenCalledWith('SCHEDULE_TIMES', '09:05,15:10');
  });

  it('shows an error when run-now is rejected because analysis is already running', async () => {
    runSchedulerNow.mockRejectedValueOnce(new Error('A scheduled analysis is already running'));
    const configState = buildSystemConfigState();
    useSystemConfigMock.mockReturnValue(buildSystemConfigState({
      activeCategory: 'system',
      itemsByCategory: {
        ...configState.itemsByCategory,
        system: [
          ...configState.itemsByCategory.system,
          {
            key: 'SCHEDULE_ENABLED',
            value: 'true',
            rawValueExists: true,
            isMasked: false,
            schema: {
              key: 'SCHEDULE_ENABLED',
              category: 'system',
              dataType: 'boolean',
              uiControl: 'switch',
              isSensitive: false,
              isRequired: false,
              isEditable: true,
              options: [],
              validation: {},
              displayOrder: 8,
            },
          },
          {
            key: 'SCHEDULE_TIMES',
            value: '18:00',
            rawValueExists: true,
            isMasked: false,
            schema: {
              key: 'SCHEDULE_TIMES',
              category: 'system',
              dataType: 'string',
              uiControl: 'text',
              isSensitive: false,
              isEditable: true,
              options: [],
              validation: {},
              displayOrder: 11,
            },
          },
        ],
      },
    }));

    render(<SettingsPage />);

    fireEvent.click(await screen.findByTestId('scheduler-run-now-button'));

    await waitFor(() => expect(runSchedulerNow).toHaveBeenCalledTimes(1));
    expect(await screen.findByText(/A scheduled analysis is already running/)).toBeInTheDocument();
  });

  it('does not show a failed run as the last successful scheduler run', async () => {
    const configState = buildSystemConfigState();
    getSchedulerStatus.mockResolvedValueOnce({
      enabled: true,
      running: false,
      scheduleTimes: ['18:00'],
      nextRunAt: null,
      lastRunAt: '2026-06-21T17:00:00+08:00',
      lastSuccessAt: null,
      lastError: 'analysis failed',
    });
    useSystemConfigMock.mockReturnValue(buildSystemConfigState({
      activeCategory: 'system',
      itemsByCategory: {
        ...configState.itemsByCategory,
        system: [
          ...configState.itemsByCategory.system,
          {
            key: 'SCHEDULE_ENABLED',
            value: 'true',
            rawValueExists: true,
            isMasked: false,
            schema: {
              key: 'SCHEDULE_ENABLED',
              category: 'system',
              dataType: 'boolean',
              uiControl: 'switch',
              isSensitive: false,
              isRequired: false,
              isEditable: true,
              options: [],
              validation: {},
              displayOrder: 8,
            },
          },
          {
            key: 'SCHEDULE_TIMES',
            value: '18:00',
            rawValueExists: true,
            isMasked: false,
            schema: {
              key: 'SCHEDULE_TIMES',
              category: 'system',
              dataType: 'string',
              uiControl: 'text',
              isSensitive: false,
              isRequired: false,
              isEditable: true,
              options: [],
              validation: {},
              displayOrder: 11,
            },
          },
        ],
      },
    }));

    render(<SettingsPage />);

    expect(await screen.findByTestId('scheduler-last-success')).toHaveTextContent('-');
    expect(screen.getByTestId('scheduler-last-error')).toHaveTextContent('analysis failed');
  });

  it('shows active runtime scheduler state even when saved schedule flag is false', async () => {
    const configState = buildSystemConfigState();
    getSchedulerStatus.mockResolvedValueOnce({
      enabled: true,
      running: false,
      scheduleTimes: ['18:00'],
      nextRunAt: null,
      lastRunAt: null,
      lastSuccessAt: null,
      lastError: null,
    });
    useSystemConfigMock.mockReturnValue(buildSystemConfigState({
      activeCategory: 'system',
      itemsByCategory: {
        ...configState.itemsByCategory,
        system: [
          ...configState.itemsByCategory.system,
          {
            key: 'SCHEDULE_ENABLED',
            value: 'false',
            rawValueExists: true,
            isMasked: false,
            schema: {
              key: 'SCHEDULE_ENABLED',
              category: 'system',
              dataType: 'boolean',
              uiControl: 'switch',
              isSensitive: false,
              isRequired: false,
              isEditable: true,
              options: [],
              validation: {},
              displayOrder: 8,
            },
          },
          {
            key: 'SCHEDULE_TIMES',
            value: '18:00',
            rawValueExists: true,
            isMasked: false,
            schema: {
              key: 'SCHEDULE_TIMES',
              category: 'system',
              dataType: 'string',
              uiControl: 'text',
              isSensitive: false,
              isRequired: false,
              isEditable: true,
              options: [],
              validation: {},
              displayOrder: 11,
            },
          },
        ],
      },
    }));

    render(<SettingsPage />);

    const enabledSwitch = await screen.findByTestId('scheduler-enabled-switch');
    expect(enabledSwitch).toBeChecked();

    fireEvent.click(enabledSwitch);

    expect(setDraftValue).toHaveBeenCalledWith('SCHEDULE_ENABLED', 'false');
    await waitFor(() => expect(enabledSwitch).not.toBeChecked());
  });

  it('keeps local scheduler toggle edits when runtime and saved states are initially consistent', async () => {
    const configState = buildSystemConfigState();
    useSystemConfigMock.mockReturnValue(buildSystemConfigState({
      activeCategory: 'system',
      itemsByCategory: {
        ...configState.itemsByCategory,
        system: [
          ...configState.itemsByCategory.system,
          {
            key: 'SCHEDULE_ENABLED',
            value: 'true',
            rawValueExists: true,
            isMasked: false,
            schema: {
              key: 'SCHEDULE_ENABLED',
              category: 'system',
              dataType: 'boolean',
              uiControl: 'switch',
              isSensitive: false,
              isRequired: false,
              isEditable: true,
              options: [],
              validation: {},
              displayOrder: 8,
            },
          },
          {
            key: 'SCHEDULE_TIMES',
            value: '18:00',
            rawValueExists: true,
            isMasked: false,
            schema: {
              key: 'SCHEDULE_TIMES',
              category: 'system',
              dataType: 'string',
              uiControl: 'text',
              isSensitive: false,
              isRequired: false,
              isEditable: true,
              options: [],
              validation: {},
              displayOrder: 11,
            },
          },
        ],
      },
    }));
    render(<SettingsPage />);

    const enabledSwitch = await screen.findByTestId('scheduler-enabled-switch');
    expect(enabledSwitch).toBeChecked();

    fireEvent.click(enabledSwitch);

    expect(setDraftValue).toHaveBeenCalledWith('SCHEDULE_ENABLED', 'false');
    await waitFor(() => expect(screen.getByTestId('scheduler-enabled-switch')).not.toBeChecked());

    const refreshButton = screen.getByTestId('scheduler-refresh-status-button');
    fireEvent.click(refreshButton);
    await waitFor(() => expect(screen.getByTestId('scheduler-enabled-switch')).not.toBeChecked());
  });

  it('can reconcile runtime scheduler state when runtime is enabled but saved value is disabled', async () => {
    save.mockResolvedValue({ success: true });
    getChangedItems.mockReturnValue([]);
    const configState = buildSystemConfigState();
    getSchedulerStatus.mockResolvedValueOnce({
      enabled: true,
      running: false,
      scheduleTimes: ['18:00'],
      nextRunAt: null,
      lastRunAt: null,
      lastSuccessAt: null,
      lastError: null,
    });
    useSystemConfigMock.mockReturnValue(buildSystemConfigState({
      activeCategory: 'system',
      hasDirty: false,
      dirtyCount: 0,
      getChangedItems: () => [],
      itemsByCategory: {
        ...configState.itemsByCategory,
        system: [
          ...configState.itemsByCategory.system,
          {
            key: 'SCHEDULE_ENABLED',
            value: 'false',
            rawValueExists: true,
            isMasked: false,
            schema: {
              key: 'SCHEDULE_ENABLED',
              category: 'system',
              dataType: 'boolean',
              uiControl: 'switch',
              isSensitive: false,
              isRequired: false,
              isEditable: true,
              options: [],
              validation: {},
              displayOrder: 8,
            },
          },
          {
            key: 'SCHEDULE_TIMES',
            value: '18:00',
            rawValueExists: true,
            isMasked: false,
            schema: {
              key: 'SCHEDULE_TIMES',
              category: 'system',
              dataType: 'string',
              uiControl: 'text',
              isSensitive: false,
              isEditable: true,
              options: [],
              validation: {},
              displayOrder: 11,
            },
          },
        ],
      },
    }));

    render(<SettingsPage />);

    expect(screen.queryByRole('button', { name: /保存配置/ })).not.toBeInTheDocument();

    const enabledSwitch = await screen.findByTestId('scheduler-enabled-switch');
    await waitFor(() => expect(enabledSwitch).toBeChecked());
    fireEvent.click(enabledSwitch);

    await waitFor(() => expect(enabledSwitch).not.toBeChecked());
    await waitFor(() => expect(save).toHaveBeenCalledWith(
      [{ key: 'SCHEDULE_ENABLED', value: 'false' }],
      { silent: true },
    ), { timeout: 2000 });
  });

  it('can reconcile runtime scheduler state when runtime is disabled but saved value is enabled', async () => {
    save.mockResolvedValue({ success: true });
    getChangedItems.mockReturnValue([]);
    const configState = buildSystemConfigState();
    getSchedulerStatus.mockResolvedValueOnce({
      enabled: false,
      running: false,
      scheduleTimes: ['18:00'],
      nextRunAt: null,
      lastRunAt: null,
      lastSuccessAt: null,
      lastError: null,
    });
    useSystemConfigMock.mockReturnValue(buildSystemConfigState({
      activeCategory: 'system',
      hasDirty: false,
      dirtyCount: 0,
      getChangedItems: () => [],
      itemsByCategory: {
        ...configState.itemsByCategory,
        system: [
          ...configState.itemsByCategory.system,
          {
            key: 'SCHEDULE_ENABLED',
            value: 'true',
            rawValueExists: true,
            isMasked: false,
            schema: {
              key: 'SCHEDULE_ENABLED',
              category: 'system',
              dataType: 'boolean',
              uiControl: 'switch',
              isSensitive: false,
              isRequired: false,
              isEditable: true,
              options: [],
              validation: {},
              displayOrder: 8,
            },
          },
          {
            key: 'SCHEDULE_TIMES',
            value: '18:00',
            rawValueExists: true,
            isMasked: false,
            schema: {
              key: 'SCHEDULE_TIMES',
              category: 'system',
              dataType: 'string',
              uiControl: 'text',
              isSensitive: false,
              isEditable: true,
              options: [],
              validation: {},
              displayOrder: 11,
            },
          },
        ],
      },
    }));

    render(<SettingsPage />);

    expect(screen.queryByRole('button', { name: /保存配置/ })).not.toBeInTheDocument();

    const enabledSwitch = await screen.findByTestId('scheduler-enabled-switch');
    await waitFor(() => expect(enabledSwitch).not.toBeChecked());
    fireEvent.click(enabledSwitch);

    await waitFor(() => expect(enabledSwitch).toBeChecked());
    await waitFor(() => expect(save).toHaveBeenCalledWith(
      [{ key: 'SCHEDULE_ENABLED', value: 'true' }],
      { silent: true },
    ), { timeout: 2000 });
  });

  it('refreshes scheduler status after autosaving scheduler settings', async () => {
    const configState = buildSystemConfigState();
    getSchedulerStatus
      .mockResolvedValueOnce({
        enabled: false,
        running: false,
        scheduleTimes: [],
        nextRunAt: null,
        lastRunAt: null,
        lastSuccessAt: null,
        lastError: null,
      })
      .mockResolvedValueOnce({
        enabled: true,
        running: false,
        scheduleTimes: ['09:20', '15:10'],
        nextRunAt: '2026-06-21T09:20:00+08:00',
        lastRunAt: null,
        lastSuccessAt: null,
        lastError: null,
      });
    save.mockResolvedValue({ success: true });
    useSystemConfigMock.mockReturnValue(buildSystemConfigState({
      activeCategory: 'system',
      hasDirty: true,
      dirtyCount: 1,
      getChangedItems: () => [{ key: 'SCHEDULE_ENABLED', value: 'true' }],
      itemsByCategory: {
        ...configState.itemsByCategory,
        system: [
          ...configState.itemsByCategory.system,
          {
            key: 'SCHEDULE_ENABLED',
            value: 'false',
            rawValueExists: true,
            isMasked: false,
            schema: {
              key: 'SCHEDULE_ENABLED',
              category: 'system',
              dataType: 'boolean',
              uiControl: 'switch',
              isSensitive: false,
              isRequired: false,
              isEditable: true,
              options: [],
              validation: {},
              displayOrder: 8,
            },
          },
          {
            key: 'SCHEDULE_TIMES',
            value: '09:20,15:10',
            rawValueExists: true,
            isMasked: false,
            schema: {
              key: 'SCHEDULE_TIMES',
              category: 'system',
              dataType: 'string',
              uiControl: 'text',
              isSensitive: false,
              isRequired: false,
              isEditable: true,
              options: [],
              validation: {},
              displayOrder: 11,
            },
          },
        ],
      },
    }));

    render(<SettingsPage />);

    expect(await screen.findByText('未启用')).toBeInTheDocument();

    await waitFor(() => expect(getSchedulerStatus).toHaveBeenCalledTimes(2), { timeout: 2000 });
    expect(await screen.findByText('已启用')).toBeInTheDocument();
  });

  it('refreshes AlphaSift state when the enable flow fails', async () => {
    const configState = buildSystemConfigState();
    alphasiftEnable.mockRejectedValueOnce(new Error('config update failed'));
    useSystemConfigMock.mockReturnValue(buildSystemConfigState({
      activeCategory: 'data_source',
      activeSubCategory: 'providers',
      itemsByCategory: {
        ...configState.itemsByCategory,
        data_source: [
          {
            key: 'ALPHASIFT_ENABLED',
            value: 'false',
            rawValueExists: true,
            isMasked: false,
            schema: {
              key: 'ALPHASIFT_ENABLED',
              category: 'data_source',
              dataType: 'boolean',
              uiControl: 'switch',
              isSensitive: false,
              isRequired: false,
              isEditable: true,
              options: [],
              validation: {},
              displayOrder: 16,
            },
          },
        ],
      },
    }));

    render(<SettingsPage />);

    fireEvent.click(screen.getByRole('button', { name: '开启选股' }));

    await waitFor(() => expect(alphasiftEnable).toHaveBeenCalledTimes(1));
    expect(updateSystemConfig).not.toHaveBeenCalled();
    expect(alphasiftInstall).not.toHaveBeenCalled();
    expect(refreshAfterExternalSave).toHaveBeenCalledWith(['ALPHASIFT_ENABLED']);
  });

  it('passes LLM channel support keys to the channel editor without rendering them as generic fields', async () => {
    useSystemConfigMock.mockReturnValue(buildSystemConfigState({
      activeCategory: 'ai_model',
      itemsByCategory: {
        ...buildSystemConfigState().itemsByCategory,
        ai_model: [
          {
            key: 'LLM_CHANNELS',
            value: 'my_proxy',
            rawValueExists: true,
            isMasked: false,
            schema: {
              key: 'LLM_CHANNELS',
              category: 'ai_model',
              dataType: 'string',
              uiControl: 'textarea',
              isSensitive: false,
              isRequired: false,
              isEditable: true,
              options: [],
              validation: {},
              displayOrder: 1,
              uiPlacement: 'model_access' as const,
            },
          },
          {
            key: 'LITELLM_MODEL',
            value: 'gpt-5.0',
            rawValueExists: true,
            isMasked: false,
            schema: {
              key: 'LITELLM_MODEL',
              category: 'ai_model',
              dataType: 'string',
              uiControl: 'text',
              isSensitive: false,
              isRequired: false,
              isEditable: true,
              options: [],
              validation: {},
              displayOrder: 2,
              uiPlacement: 'task_routing' as const,
            },
          },
          {
            key: 'OPENAI_BASE_URL',
            value: 'https://api.openai.com/v1',
            rawValueExists: true,
            isMasked: false,
            schema: {
              key: 'OPENAI_BASE_URL',
              category: 'ai_model',
              dataType: 'string',
              uiControl: 'text',
              isSensitive: false,
              isRequired: false,
              isEditable: true,
              options: [],
              validation: {},
              displayOrder: 3,
              uiPlacement: 'hidden_legacy' as const,
            },
          },
          {
            key: 'OPENAI_MODEL',
            value: 'gpt-5.0',
            rawValueExists: true,
            isMasked: false,
            schema: {
              key: 'OPENAI_MODEL',
              category: 'ai_model',
              isMasked: false,
              dataType: 'string',
              uiControl: 'text',
              isRequired: false,
              isEditable: true,
              options: [],
              validation: {},
              displayOrder: 4,
              uiPlacement: 'hidden_legacy' as const,
            },
          },
          {
            key: 'LLM_MY_PROXY_API_KEY',
            value: 'sk-test',
            rawValueExists: true,
            isMasked: false,
            schema: {
              key: 'LLM_MY_PROXY_API_KEY',
              category: 'ai_model',
              dataType: 'string',
              uiControl: 'password',
              isSensitive: true,
              isRequired: false,
              isEditable: true,
              options: [],
              validation: {},
              displayOrder: 9000,
              uiPlacement: 'model_access' as const,
            },
          },
          {
            key: 'LLM_MY_PROXY_MODELS',
            value: 'gpt-5.5',
            rawValueExists: true,
            isMasked: false,
            schema: {
              key: 'LLM_MY_PROXY_MODELS',
              category: 'ai_model',
              dataType: 'string',
              uiControl: 'text',
              isSensitive: false,
              isRequired: false,
              isEditable: true,
              options: [],
              validation: {},
              displayOrder: 9000,
              uiPlacement: 'model_access' as const,
            },
          },
        ],
      },
    }));

    render(<SettingsPage />);

    const llmEditorItems = await screen.findByTestId('llm-channel-editor-items');
    expect(llmEditorItems).toHaveTextContent('LLM_CHANNELS');
    expect(llmEditorItems).toHaveTextContent('LITELLM_MODEL');
    expect(llmEditorItems).toHaveTextContent('OPENAI_BASE_URL');
    expect(llmEditorItems).toHaveTextContent('OPENAI_MODEL');
    expect(llmEditorItems).toHaveTextContent('LLM_MY_PROXY_API_KEY');
    expect(llmEditorItems).toHaveTextContent('LLM_MY_PROXY_MODELS');
    expect(screen.queryByTestId('settings-field-LITELLM_MODEL')).not.toBeInTheDocument();
    expect(screen.queryByTestId('settings-field-OPENAI_BASE_URL')).not.toBeInTheDocument();
    expect(screen.queryByTestId('settings-field-OPENAI_MODEL')).not.toBeInTheDocument();
    expect(screen.queryByTestId('settings-field-LLM_MY_PROXY_API_KEY')).not.toBeInTheDocument();
    expect(screen.queryByTestId('settings-field-LLM_MY_PROXY_MODELS')).not.toBeInTheDocument();
  });

  it.each([
    ['missing', undefined],
    ['unknown', 'future_surface'],
  ])('quarantines AI fields with %s uiPlacement in Advanced as read-only diagnostics', async (_case, uiPlacement) => {
    const configState = buildSystemConfigState();
    const unsafeItem = {
      key: 'OPENAI_API_KEY',
      value: 'saved-secret',
      rawValueExists: true,
      isMasked: false,
      schema: {
        key: 'OPENAI_API_KEY',
        category: 'ai_model' as const,
        dataType: 'string' as const,
        uiControl: 'password' as const,
        isSensitive: true,
        isRequired: false,
        isEditable: true,
        options: [],
        validation: {},
        displayOrder: 1,
        ...(uiPlacement ? { uiPlacement: uiPlacement as never } : {}),
      },
    };
    const unsafeModelAccessItem = {
      ...unsafeItem,
      key: 'LLM_CHANNELS',
      value: 'openai',
      isMasked: false,
      schema: {
        ...unsafeItem.schema,
        key: 'LLM_CHANNELS',
        uiControl: 'textarea' as const,
        isSensitive: false,
      },
    };
    const state = buildSystemConfigState({
      activeCategory: 'ai_model',
      itemsByCategory: { ...configState.itemsByCategory, ai_model: [unsafeModelAccessItem, unsafeItem] },
    });
    useSystemConfigMock.mockReturnValue(state);
    routerSearchParamsMock.params = new URLSearchParams({ section: 'ai_models', view: 'connections' });
    const { rerender } = render(<SettingsPage />);
    expect(screen.queryByTestId('settings-field-OPENAI_API_KEY')).not.toBeInTheDocument();
    expect(screen.getByTestId('llm-channel-editor-items')).toHaveAttribute('data-disabled', 'true');

    routerSearchParamsMock.params = new URLSearchParams({ section: 'advanced', view: 'raw_config' });
    rerender(<SettingsPage />);
    const field = screen.getByTestId('settings-field-OPENAI_API_KEY');
    expect(field).toHaveAttribute('data-readonly', 'true');
    expect(field).toHaveTextContent(`schema_ui_placement_${_case}`);
  });

  it('keeps an unknown schema condition visible but read-only with a diagnostic', () => {
    const configState = buildSystemConfigState();
    const conditionalItem = {
      key: 'LOG_LEVEL',
      value: 'INFO',
      rawValueExists: true,
      isMasked: false,
      schema: {
        key: 'LOG_LEVEL',
        category: 'system' as const,
        dataType: 'string' as const,
        uiControl: 'text' as const,
        isSensitive: false,
        isRequired: false,
        isEditable: true,
        options: [],
        validation: {},
        displayOrder: 1,
        contract: {
          requirement: 'optional' as const,
          visibleWhen: [{ key: 'MODE', operator: 'regex' as never, value: '^safe$' }],
        },
      },
    };
    useSystemConfigMock.mockReturnValue(buildSystemConfigState({
      activeCategory: 'system',
      itemsByCategory: { ...configState.itemsByCategory, system: [conditionalItem] },
    }));

    render(<SettingsPage />);
    const field = screen.getByTestId('settings-field-LOG_LEVEL');
    expect(field).toHaveAttribute('data-readonly', 'true');
    expect(field).toHaveTextContent('schema_condition_unknown');
  });

  it('never renders legacy provider credential fields even without configured channels', async () => {
    // Model Access is the only entry for provider credentials: legacy keys
    // like OPENAI_API_KEY stay backend-compatible but must not surface as
    // generic fields, channels configured or not.
    const legacyProviderItems = ['OPENAI_API_KEY', 'ANTHROPIC_API_KEY', 'GEMINI_API_KEY', 'AIHUBMIX_KEY'].map((key, index) => ({
      key,
      value: '',
      rawValueExists: false,
      isMasked: false,
      schema: {
        key,
        category: 'ai_model',
        dataType: 'string',
        uiControl: 'password',
        isSensitive: true,
        isRequired: false,
        isEditable: true,
        options: [],
        validation: {},
        displayOrder: index + 1,
        // Mirrors the backend registry: legacy provider keys stay
        // backend-compatible but are never rendered as generic fields.
        uiPlacement: 'hidden_legacy' as const,
      },
    }));
    useSystemConfigMock.mockReturnValue(buildSystemConfigState({
      activeCategory: 'ai_model',
      itemsByCategory: {
        ...buildSystemConfigState().itemsByCategory,
        ai_model: legacyProviderItems,
      },
    }));

    render(<SettingsPage />);

    await screen.findByTestId('llm-channel-editor-items');
    for (const item of legacyProviderItems) {
      expect(screen.queryByTestId(`settings-field-${item.key}`)).not.toBeInTheDocument();
    }
    expect(screen.queryByText('模型供应商')).not.toBeInTheDocument();
  });

  it('renders notification test panel before notification fields', () => {
    useSystemConfigMock.mockReturnValue(buildSystemConfigState({ activeCategory: 'notification' }));

    render(<SettingsPage />);

    expect(screen.getByText('通知测试面板:WECHAT_WEBHOOK_URL')).toBeInTheDocument();
    expect(screen.getByText('WECHAT_WEBHOOK_URL')).toBeInTheDocument();
    expect(settingsPanelErrorBoundary).toHaveBeenCalledWith('通知测试');
    expect(settingsPanelErrorBoundary).toHaveBeenCalledWith('通知设置');
  });

  it('uses browser and backend logs in settings panel diagnostic hints outside desktop runtime', () => {
    useSystemConfigMock.mockReturnValue(buildSystemConfigState({ activeCategory: 'notification' }));

    render(<SettingsPage />);

    expect(screen.getAllByText(/浏览器开发者工具控制台与后端日志/)).toHaveLength(2);
    expect(screen.queryByText('desktop.log')).not.toBeInTheDocument();
  });

  it('uses desktop log in settings panel diagnostic hints during desktop runtime', () => {
    useSystemConfigMock.mockReturnValue(buildSystemConfigState({ activeCategory: 'notification' }));
    (window as { dsaDesktop?: unknown }).dsaDesktop = createDesktopRuntime();

    render(<SettingsPage />);

    expect(screen.getAllByText('desktop.log')).toHaveLength(2);
    expect(screen.queryByText(/浏览器开发者工具控制台与后端日志/)).not.toBeInTheDocument();
  });

  it('keeps env backup actions in Advanced outside desktop runtime', () => {
    const { rerender } = render(<SettingsPage />);

    expect(screen.queryByRole('heading', { name: '配置备份' })).not.toBeInTheDocument();

    useAdvancedConfigState();
    rerender(<SettingsPage />);

    expect(screen.getByRole('heading', { name: '配置备份' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '导出 .env' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '导入 .env' })).toBeInTheDocument();
    expect(screen.getByText(/Docker 部署中/)).toHaveTextContent('ENV_FILE');
  });

  it('disables env backup actions when web auth is not enabled', () => {
    useAuthMock.mockReturnValue({
      authEnabled: false,
      passwordChangeable: false,
      refreshStatus,
    });
    useAdvancedConfigState();

    render(<SettingsPage />);

    expect(screen.getByText(/当前 Web 端未开启管理员鉴权/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '导出 .env' })).toBeDisabled();
    expect(screen.getByRole('button', { name: '导入 .env' })).toBeDisabled();
  });

  it('uses live auth state for env backup availability instead of loaded config items', () => {
    const configState = buildSystemConfigState();
    useAdvancedConfigState({
      itemsByCategory: {
        ...configState.itemsByCategory,
        system: configState.itemsByCategory.system.map((item) => (
          item.key === 'ADMIN_AUTH_ENABLED' ? { ...item, value: 'false' } : item
        )),
      },
    });
    useAuthMock.mockReturnValue({
      authEnabled: true,
      passwordChangeable: true,
      refreshStatus,
    });

    render(<SettingsPage />);

    expect(screen.queryByText(/当前 Web 端未开启管理员鉴权/)).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: '导出 .env' })).not.toBeDisabled();
    expect(screen.getByRole('button', { name: '导入 .env' })).not.toBeDisabled();
  });

  it('exports saved env from config backup actions', async () => {
    (window as { dsaDesktop?: unknown }).dsaDesktop = { version: '3.12.0' };
    useAdvancedConfigState();

    render(<SettingsPage />);

    vi.clearAllMocks();

    fireEvent.click(screen.getByRole('button', { name: '导出 .env' }));

    await waitFor(() => expect(exportEnv).toHaveBeenCalledTimes(1));
    expect(mockedAnchorClick).toHaveBeenCalledTimes(1);
    expect(load).not.toHaveBeenCalled();
  });

  it('asks for confirmation before importing when local drafts exist', async () => {
    (window as { dsaDesktop?: unknown }).dsaDesktop = { version: '3.12.0' };
    useAdvancedConfigState({
      hasDirty: true,
      dirtyCount: 2,
      getChangedItems: () => [{ key: 'WEBUI_PORT', value: '9000' }],
    });

    render(<SettingsPage />);

    vi.clearAllMocks();

    fireEvent.click(screen.getByRole('button', { name: '导入 .env' }));

    expect(await screen.findByText('导入会覆盖当前草稿')).toBeInTheDocument();
    expect(importEnv).not.toHaveBeenCalled();
  });

  it('reloads config after successful env import', async () => {
    (window as { dsaDesktop?: unknown }).dsaDesktop = { version: '3.12.0' };
    useAdvancedConfigState();

    const { container } = render(<SettingsPage />);

    vi.clearAllMocks();

    const input = container.querySelector('input[type="file"]');
    expect(input).not.toBeNull();

    fireEvent.change(input as HTMLInputElement, {
      target: {
        files: [new File(['STOCK_LIST=300750\n'], 'desktop-backup.env', { type: 'text/plain' })],
      },
    });

    await waitFor(() => expect(importEnv).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(load).toHaveBeenCalledTimes(1));
  });

  it('imports scheduler settings from Advanced without mounting runtime controls', async () => {
    (window as { dsaDesktop?: unknown }).dsaDesktop = { version: '3.12.0' };
    const configState = buildSystemConfigState();
    importEnv.mockResolvedValueOnce({
      success: true,
      configVersion: 'v2',
      appliedCount: 2,
      skippedMaskedCount: 0,
      reloadTriggered: true,
      updatedKeys: ['SCHEDULE_ENABLED', 'SCHEDULE_TIMES'],
      warnings: [],
    });
    useAdvancedConfigState({
      itemsByCategory: {
        ...configState.itemsByCategory,
        system: [
          ...configState.itemsByCategory.system,
          {
            key: 'SCHEDULE_ENABLED',
            value: 'false',
            rawValueExists: true,
            isMasked: false,
            schema: {
              key: 'SCHEDULE_ENABLED',
              category: 'system',
              dataType: 'boolean',
              uiControl: 'switch',
              isSensitive: false,
              isRequired: false,
              isEditable: true,
              options: [],
              validation: {},
              displayOrder: 8,
            },
          },
          {
            key: 'SCHEDULE_TIMES',
            value: '18:00',
            rawValueExists: true,
            isMasked: false,
            schema: {
              key: 'SCHEDULE_TIMES',
              category: 'system',
              dataType: 'string',
              uiControl: 'text',
              isSensitive: false,
              isRequired: false,
              isEditable: true,
              options: [],
              validation: {},
              displayOrder: 11,
            },
          },
        ],
      },
    });

    const { container } = render(<SettingsPage />);

    vi.clearAllMocks();

    const input = container.querySelector('input[type="file"]');
    expect(input).not.toBeNull();

    fireEvent.change(input as HTMLInputElement, {
      target: {
        files: [new File(['SCHEDULE_ENABLED=true\nSCHEDULE_TIMES=09:20,15:10\n'], 'desktop-backup.env', { type: 'text/plain' })],
      },
    });

    await waitFor(() => expect(importEnv).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(load).toHaveBeenCalledTimes(1));
    expect(getSchedulerStatus).not.toHaveBeenCalled();
  });

  it('shows an error when env import succeeds but reload fails', async () => {
    (window as { dsaDesktop?: unknown }).dsaDesktop = { version: '3.12.0' };
    load.mockResolvedValue(false);
    useAdvancedConfigState();

    const { container } = render(<SettingsPage />);

    vi.clearAllMocks();
    load.mockResolvedValue(false);

    const input = container.querySelector('input[type="file"]');
    expect(input).not.toBeNull();

    fireEvent.change(input as HTMLInputElement, {
      target: {
        files: [new File(['STOCK_LIST=300750\n'], 'desktop-backup.env', { type: 'text/plain' })],
      },
    });

    await waitFor(() => expect(importEnv).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(load).toHaveBeenCalledTimes(1));
    expect(screen.getByText('配置已导入但刷新失败')).toBeInTheDocument();
    expect(screen.getByText('备份已导入，但重新加载配置失败，请手动重载页面。')).toBeInTheDocument();
    expect(screen.queryByText('已导入 .env 备份并重新加载配置。')).not.toBeInTheDocument();
  });

  it('renders desktop update notice when a newer release is available', async () => {
    desktopGetUpdateState.mockResolvedValue({
      status: 'update-available',
      currentVersion: '3.12.0',
      latestVersion: '3.13.0',
      releaseUrl: 'https://github.com/SiinXu/stock-pulse-ai/releases/tag/v3.13.0',
      message: '发现新版本 3.13.0，可前往 GitHub Releases 下载更新。',
    });
    (window as { dsaDesktop?: unknown }).dsaDesktop = createDesktopRuntime();

    render(<SettingsPage />);

    expect(await screen.findByText('发现新版本')).toBeInTheDocument();
    expect(screen.getByText(/当前 3\.12\.0，最新 3\.13\.0/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '前往下载' })).toBeInTheDocument();
  });

  it('checks desktop updates on demand and renders the latest-version state', async () => {
    (window as { dsaDesktop?: unknown }).dsaDesktop = createDesktopRuntime();

    render(<SettingsPage />);

    fireEvent.click(await screen.findByRole('button', { name: '检查更新' }));

    await waitFor(() => expect(desktopCheckForUpdates).toHaveBeenCalledTimes(1));
    expect(await screen.findByText('已是最新版本')).toBeInTheDocument();
    expect(screen.getByText('当前桌面端已是最新版本。')).toBeInTheDocument();
  });

  it('opens GitHub release page from desktop update notice', async () => {
    desktopGetUpdateState.mockResolvedValue({
      status: 'update-available',
      currentVersion: '3.12.0',
      latestVersion: '3.13.0',
      releaseUrl: 'https://github.com/SiinXu/stock-pulse-ai/releases/tag/v3.13.0',
      message: '发现新版本 3.13.0，可前往 GitHub Releases 下载更新。',
    });
    (window as { dsaDesktop?: unknown }).dsaDesktop = createDesktopRuntime();

    render(<SettingsPage />);

    fireEvent.click(await screen.findByRole('button', { name: '前往下载' }));

    await waitFor(() => {
      expect(desktopOpenReleasePage).toHaveBeenCalledWith(
        'https://github.com/SiinXu/stock-pulse-ai/releases/tag/v3.13.0'
      );
    });
  });

  it('renders downloaded desktop update and starts install on demand', async () => {
    desktopGetUpdateState.mockResolvedValue({
      status: 'update-downloaded',
      updateMode: 'auto',
      currentVersion: '3.12.0',
      latestVersion: '3.13.0',
      releaseUrl: 'https://github.com/SiinXu/stock-pulse-ai/releases/tag/v3.13.0',
      message: '新版本 3.13.0 已下载，可重启应用完成安装。',
      downloadPercent: 100,
    });
    (window as { dsaDesktop?: unknown }).dsaDesktop = createDesktopRuntime();

    render(<SettingsPage />);

    expect(await screen.findByText('更新已下载')).toBeInTheDocument();
    expect(screen.getByText('新版本 3.13.0 已下载，可重启应用完成安装。')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '重启安装' }));

    await waitFor(() => expect(desktopInstallDownloadedUpdate).toHaveBeenCalledTimes(1));
  });
});
