import React from 'react';
import { createPortal } from 'react-dom';
import { act, fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, expect, vi } from 'vitest';
import type { LlmConnectionFieldSchema } from '../../types/systemConfig';
import { getDefaultSubCategory } from '../../components/settings/settingsSubCategories';
import { legacyToSectionView } from '../../components/settings/settingsInformationArchitecture';
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
  getUsageDashboard,
  usageNavigate,
  useAuthMock,
  useSystemConfigMock,
  webBuildInfoMock,
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
  getUsageDashboard: vi.fn(),
  usageNavigate: vi.fn(),
  useAuthMock: vi.fn(),
  useSystemConfigMock: vi.fn(),
  webBuildInfoMock: {
    version: '3.11.0',
    rawVersion: '3.11.0',
    buildId: 'build-20260329-021530Z',
    buildTime: '2026-03-29T02:15:30.000Z',
    isFallbackVersion: false,
  },
}));

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

vi.mock('../../api/usage', () => ({
  usageApi: {
    getDashboard: (...args: unknown[]) => getUsageDashboard(...args),
  },
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
  useNavigate: () => usageNavigate,
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

vi.mock('../../components/settings', async () => {
  return {
  ...(await import('../../components/settings/notificationFieldGroups')),
  ...(await import('../../components/settings/categoryFieldGroups')),
  ...(await import('../../components/settings/settingsSubCategories')),
  ...(await import('../../components/settings/notificationChannels')),
  NotificationChannelsPanel: ({ items }: { items: Array<{ key: string }> }) => (
    <div data-testid="notification-channels-panel">
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
    onViewRouting,
    routingOptions,
    initialFallbackModels,
    initialVisionModel,
  }: {
    onComplete: (items: Array<{ key: string; value: string }>) => void;
    onClose: () => void;
    onViewRouting?: () => void;
    routingOptions?: Array<{ value: string }>;
    initialFallbackModels?: string;
    initialVisionModel?: string;
  }) => createPortal((
    <div role="dialog" aria-label="first-run-wizard">
      <div data-testid="wizard-routing-props">
        {`${routingOptions?.length ?? 0}|${initialFallbackModels ?? ''}|${initialVisionModel ?? ''}`}
      </div>
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
      <button type="button" onClick={onViewRouting}>wizard view routing</button>
      <button type="button" onClick={onClose}>wizard close</button>
    </div>
  ), document.body),
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
  };
});

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
  // Env backup lives on the Advanced Config Backup tab.
  routerSearchParamsMock.params = new URLSearchParams({ section: 'advanced', view: 'backup' });
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

  vi.useFakeTimers();
  try {
    render(<SettingsPage />);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(screen.getByTestId('llm-channel-editor-items')).toHaveAttribute('data-disabled', 'true');
    fireEvent.click(screen.getByRole('button', { name: 'emit connection draft' }));

    await act(async () => {
      await vi.advanceTimersByTimeAsync(850);
    });
    expect(save).not.toHaveBeenCalled();
  } finally {
    vi.useRealTimers();
  }
}

function registerSettingsPageBeforeEach(): void {
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
    getUsageDashboard.mockResolvedValue({
      period: 'month',
      fromDate: '2026-07-01',
      toDate: '2026-07-22',
      totalCalls: 0,
      totalPromptTokens: 0,
      totalCompletionTokens: 0,
      totalTokens: 0,
      byCallType: [],
      byModel: [],
      recentCalls: [],
    });
    delete (window as { dsaDesktop?: unknown }).dsaDesktop;
    vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:mock');
    vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => undefined);
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(mockedAnchorClick);
  });
}

const SettingsPageTestHarness = {
  registerSettingsPageBeforeEach,
  SettingsPage,
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
  desktopOpenReleasePage,
  load,
  save,
  resetDraft,
  resetDraftKeys,
  setDraftValue,
  getChangedItems,
  refreshAfterExternalSave,
  refreshStatus,
  settingsPanelErrorBoundary,
  useAuthMock,
  useSystemConfigMock,
  webBuildInfoMock,
  mockedAnchorClick,
  TEST_CONNECTION_NAME_FIELD,
  TEST_PROVIDER_ID_FIELD,
  TEST_MODELS_FIELD,
  withTestConnectionCoreFields,
  routerBlockerMock,
  routerSearchParamsMock,
  createDesktopRuntime,
  defaultItemsByCategory,
  buildSystemConfigState,
  useAdvancedConfigState,
  createDeferred,
  expectConnectionDraftAutosaveBlockedBySchema,
};

export default SettingsPageTestHarness;
export type { BlockerArgs };
