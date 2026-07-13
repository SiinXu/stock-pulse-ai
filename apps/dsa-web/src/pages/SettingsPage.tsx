import type React from 'react';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useBlocker, useSearchParams } from 'react-router-dom';
import { CheckCircle2, ChevronDown, CircleAlert, CircleDashed, Clock, Play, Plus, RefreshCw, Trash2 } from 'lucide-react';
import { useAuth, useSystemConfig } from '../hooks';
import { useUiLanguage } from '../contexts/UiLanguageContext';
import { createParsedApiError, getParsedApiError, type ParsedApiError } from '../api/error';
import { analysisApi } from '../api/analysis';
import { alphasiftApi, notifyAlphaSiftConfigChanged, notifySystemConfigChanged } from '../api/alphasift';
import { systemConfigApi } from '../api/systemConfig';
import { ApiErrorAlert, Button, ConfirmDialog, EmptyState } from '../components/common';
import {
  AuthSettingsCard,
  ChangePasswordCard,
  GenerationBackendStatusPanel,
  IntelligentImport,
  LLMChannelEditor,
  LLMConfigModeBanner,
  NotificationChannelsPanel,
  ModelProvidersPanel,
  DataProvidersPanel,
  NotificationTestPanel,
  isNotificationChannelKey,
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
  FirstRunWizard,
  type WizardDraftItem,
} from '../components/settings';
import { SettingsSectionNav, SettingsViewTabs } from '../components/settings/SettingsNavigation';
import { AiOverviewMatrix } from '../components/settings/AiOverviewMatrix';
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
import { keyBelongsToSection, placementForKey } from '../components/settings/settingsFieldPlacement';
import { WEB_BUILD_INFO } from '../utils/constants';
import { parseStockListValue } from '../utils/stockList';
import { getCategoryDescription, getCategoryTitle, getFieldTitleZh } from '../utils/systemConfigI18n';
import { isFieldVisibleByContract, isFieldEnabledByContract, resolveFieldRequirement } from '../utils/configConditions';
import type {
  ConfigValidationIssue,
  LLMConfigModeStatus,
  SchedulerStatusResponse,
  SetupStatusCheck,
  SetupStatusResponse,
  SystemConfigCategory,
  SystemConfigItem,
  SystemConfigUpdateItem,
} from '../types/systemConfig';
import type { UiLanguage, UiTextKey } from '../i18n/uiText';

type DesktopWindow = Window & {
  dsaDesktop?: {
    version?: unknown;
    getUpdateState?: () => Promise<RawDesktopUpdateState>;
    checkForUpdates?: () => Promise<RawDesktopUpdateState>;
    installDownloadedUpdate?: () => Promise<boolean>;
    openReleasePage?: (releaseUrl?: string) => Promise<boolean>;
    onUpdateStateChange?: (listener: (state: RawDesktopUpdateState) => void) => (() => void) | void;
  };
};

type DesktopUpdateState = {
  status?: string;
  updateMode?: string;
  currentVersion?: string;
  latestVersion?: string;
  releaseUrl?: string;
  checkedAt?: string;
  publishedAt?: string;
  message?: string;
  releaseName?: string;
  tagName?: string;
  downloadPercent?: number | null;
  downloadedBytes?: number | null;
  totalBytes?: number | null;
};

type RawDesktopUpdateState = {
  status?: unknown;
  updateMode?: unknown;
  currentVersion?: unknown;
  latestVersion?: unknown;
  releaseUrl?: unknown;
  checkedAt?: unknown;
  publishedAt?: unknown;
  message?: unknown;
  releaseName?: unknown;
  tagName?: unknown;
  downloadPercent?: unknown;
  downloadedBytes?: unknown;
  totalBytes?: unknown;
};

type DesktopUpdateNotice = {
  title: string;
  message: string;
  variant: 'error' | 'success' | 'warning';
  actionLabel?: string;
  actionKind?: 'release' | 'install';
};

const LLM_CHANNEL_EDITOR_RUNTIME_KEYS = new Set([
  'LITELLM_MODEL',
  'LITELLM_FALLBACK_MODELS',
  'AGENT_LITELLM_MODEL',
  'VISION_MODEL',
  'LLM_TEMPERATURE',
]);
const GENERATION_BACKEND_STATUS_KEYS = new Set([
  'GENERATION_BACKEND',
  'GENERATION_FALLBACK_BACKEND',
  'GENERATION_BACKEND_TIMEOUT_SECONDS',
  'GENERATION_BACKEND_MAX_OUTPUT_BYTES',
  'GENERATION_BACKEND_MAX_CONCURRENCY',
  'LOCAL_CLI_BACKEND_MAX_CONCURRENCY',
  'OPENCODE_CLI_MODEL',
  'LITELLM_CONFIG',
  'LITELLM_MODEL',
  'LITELLM_FALLBACK_MODELS',
  'GEMINI_API_KEY',
  'GEMINI_API_KEYS',
  'GEMINI_MODEL',
  'GEMINI_MODEL_FALLBACK',
  'GEMINI_TEMPERATURE',
  'ANTHROPIC_API_KEY',
  'ANTHROPIC_API_KEYS',
  'ANTHROPIC_MODEL',
  'ANTHROPIC_TEMPERATURE',
  'ANTHROPIC_MAX_TOKENS',
  'OPENAI_API_KEY',
  'OPENAI_API_KEYS',
  'OPENAI_BASE_URL',
  'OPENAI_MODEL',
  'OPENAI_VISION_MODEL',
  'OPENAI_TEMPERATURE',
  'OLLAMA_API_BASE',
  'OLLAMA_MODEL',
  'DEEPSEEK_API_KEY',
  'DEEPSEEK_API_KEYS',
  'AIHUBMIX_KEY',
  'ANSPIRE_LLM_ENABLED',
  'ANSPIRE_LLM_BASE_URL',
  'ANSPIRE_LLM_MODEL',
  'ANSPIRE_API_KEYS',
]);
const LLM_CHANNEL_STATUS_KEY_PATTERN = /^LLM_[A-Z0-9_]+_(PROTOCOL|BASE_URL|API_KEY|API_KEYS|MODELS|EXTRA_HEADERS|ENABLED)$/;

function isLlmChannelEditorDraftKey(key: string): boolean {
  const normalized = key.trim().toUpperCase();
  return normalized.startsWith('LLM_') || LLM_CHANNEL_EDITOR_RUNTIME_KEYS.has(normalized);
}

function isGenerationBackendStatusDraftKey(key: string): boolean {
  const normalized = key.trim().toUpperCase();
  return (
    GENERATION_BACKEND_STATUS_KEYS.has(normalized)
    || normalized === 'LLM_CHANNELS'
    || LLM_CHANNEL_STATUS_KEY_PATTERN.test(normalized)
  );
}

function mergeGenerationBackendDraftItems(
  outerItems: SystemConfigUpdateItem[],
  llmChannelItems: SystemConfigUpdateItem[],
): SystemConfigUpdateItem[] {
  const merged = new Map<string, SystemConfigUpdateItem>();
  for (const item of outerItems) {
    const normalizedKey = item.key.trim().toUpperCase();
    if (isGenerationBackendStatusDraftKey(normalizedKey)) {
      merged.set(normalizedKey, item);
    }
  }
  for (const item of llmChannelItems) {
    const normalizedKey = item.key.trim().toUpperCase();
    if (isLlmChannelEditorDraftKey(normalizedKey) && isGenerationBackendStatusDraftKey(normalizedKey)) {
      merged.set(normalizedKey, item);
    }
  }
  return Array.from(merged.values());
}

const PROMPT_CACHE_ADVANCED_SETTING_KEYS = new Set([
  'LLM_PROMPT_CACHE_TELEMETRY_ENABLED',
  'LLM_PROMPT_CACHE_HINTS_ENABLED',
  'LLM_PROMPT_CACHE_DIAGNOSTICS_LEVEL',
]);

function isPromptCacheAdvancedSetting(item: { key: string }) {
  return PROMPT_CACHE_ADVANCED_SETTING_KEYS.has(item.key);
}

function trimDesktopRuntimeString(value: unknown) {
  return typeof value === 'string' ? value.trim() : '';
}

function normalizeDesktopRuntimeNumber(value: unknown) {
  if (value === null || value === undefined || value === '') {
    return null;
  }
  const numberValue = typeof value === 'number' ? value : Number(value);
  return Number.isFinite(numberValue) ? numberValue : null;
}

function getDesktopRuntimeApi() {
  if (typeof window === 'undefined') {
    return undefined;
  }

  return (window as DesktopWindow).dsaDesktop;
}

function getDesktopAppVersion() {
  return trimDesktopRuntimeString(getDesktopRuntimeApi()?.version);
}

function normalizeDesktopUpdateState(state: RawDesktopUpdateState | null | undefined) {
  if (!state || typeof state !== 'object') {
    return null;
  }

  return {
    status: trimDesktopRuntimeString(state.status) || 'idle',
    updateMode: trimDesktopRuntimeString(state.updateMode) || 'manual',
    currentVersion: trimDesktopRuntimeString(state.currentVersion),
    latestVersion: trimDesktopRuntimeString(state.latestVersion),
    releaseUrl: trimDesktopRuntimeString(state.releaseUrl),
    checkedAt: trimDesktopRuntimeString(state.checkedAt),
    publishedAt: trimDesktopRuntimeString(state.publishedAt),
    message: trimDesktopRuntimeString(state.message),
    releaseName: trimDesktopRuntimeString(state.releaseName),
    tagName: trimDesktopRuntimeString(state.tagName),
    downloadPercent: normalizeDesktopRuntimeNumber(state.downloadPercent),
    downloadedBytes: normalizeDesktopRuntimeNumber(state.downloadedBytes),
    totalBytes: normalizeDesktopRuntimeNumber(state.totalBytes),
  };
}

function getDesktopUpdateNotice(
  state: DesktopUpdateState | null,
  t: (key: UiTextKey, params?: Record<string, string | number>) => string,
): DesktopUpdateNotice | null {
  if (!state) {
    return null;
  }

  if (state.status === 'update-available') {
    const latestLabel = state.latestVersion || state.tagName || t('settings.desktopLatest');
    const currentLabel = state.currentVersion || getDesktopAppVersion() || WEB_BUILD_INFO.version;
    return {
      title: t('settings.desktopUpdateAvailable'),
      message: t('settings.desktopUpdateMessage', {
        current: currentLabel,
        latest: latestLabel,
        message: state.message || t('settings.desktopUpdateReleaseMessage'),
      }),
      variant: 'warning' as const,
      actionLabel: state.updateMode === 'auto' ? undefined : t('settings.desktopDownload'),
      actionKind: state.updateMode === 'auto' ? undefined : 'release',
    };
  }

  if (state.status === 'downloading') {
    const percentText = typeof state.downloadPercent === 'number' ? `（${state.downloadPercent}%）` : '';
    return {
      title: t('settings.desktopDownloading'),
      message: state.message || t('settings.desktopUpdateDownloadingMessage', { percent: percentText }),
      variant: 'warning' as const,
    };
  }

  if (state.status === 'update-downloaded') {
    return {
      title: t('settings.desktopDownloaded'),
      message: state.message || t('settings.desktopUpdateDownloadedMessage'),
      variant: 'success' as const,
      actionLabel: t('settings.desktopInstall'),
      actionKind: 'install',
    };
  }

  if (state.status === 'installing') {
    return {
      title: t('settings.desktopInstalling'),
      message: state.message || t('settings.desktopUpdateInstallingMessage'),
      variant: 'warning' as const,
    };
  }

  if (state.status === 'up-to-date') {
    return {
      title: t('settings.desktopUpToDate'),
      message: state.message || t('settings.desktopUpToDateMessage'),
      variant: 'success' as const,
    };
  }

  if (state.status === 'checking') {
    return {
      title: t('settings.desktopChecking'),
      message: state.message || t('settings.desktopUpdateCheckingMessage'),
      variant: 'warning' as const,
    };
  }

  if (state.status === 'error') {
    return {
      title: t('settings.desktopCheckError'),
      message: state.message || t('settings.desktopUpdateErrorMessage'),
      variant: 'error' as const,
      actionLabel: state.updateMode === 'auto' && state.releaseUrl ? t('settings.desktopDownload') : undefined,
      actionKind: state.updateMode === 'auto' && state.releaseUrl ? 'release' : undefined,
    };
  }

  return null;
}

function formatEnvBackupFilename(isDesktopRuntime: boolean) {
  const now = new Date();
  const pad = (value: number) => value.toString().padStart(2, '0');
  const date = `${now.getFullYear()}${pad(now.getMonth() + 1)}${pad(now.getDate())}`;
  const time = `${pad(now.getHours())}${pad(now.getMinutes())}`;
  return `${isDesktopRuntime ? 'dsa-desktop-env' : 'dsa-env'}_${date}_${time}.env`;
}

const SCHEDULE_TIME_PATTERN = /^(?:[01]\d|2[0-3]):[0-5]\d$/;
const SCHEDULER_DEFAULT_TIME = '18:00';
const SCHEDULER_SETTING_KEYS = new Set([
  'SCHEDULE_ENABLED',
  'SCHEDULE_TIME',
  'SCHEDULE_TIMES',
  'SCHEDULE_RUN_IMMEDIATELY',
]);

function getConfigItem(items: SystemConfigItem[], key: string) {
  return items.find((item) => item.key === key);
}

function parseSetupStockList(value: unknown) {
  return parseStockListValue(String(value ?? ''));
}

function isEnabledConfigValue(value: unknown) {
  return String(value ?? '').trim().toLowerCase() === 'true';
}

function getSetupCheckIcon(check: SetupStatusCheck) {
  if (check.status === 'configured' || check.status === 'inherited') {
    return <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-success" aria-hidden="true" />;
  }
  if (check.status === 'needs_action') {
    return <CircleAlert className="mt-0.5 h-4 w-4 shrink-0 text-warning" aria-hidden="true" />;
  }
  return <CircleDashed className="mt-0.5 h-4 w-4 shrink-0 text-muted-text" aria-hidden="true" />;
}

function getSetupCheckStatusLabel(
  check: SetupStatusCheck,
  t: (key: UiTextKey, params?: Record<string, string | number>) => string,
) {
  if (check.status === 'configured') return t('settings.setupStatusConfigured');
  if (check.status === 'inherited') return t('settings.setupStatusInherited');
  if (check.status === 'needs_action') return t('settings.setupStatusNeedsAction');
  return t('settings.setupStatusOptional');
}

type FirstRunSetupCardProps = {
  status: SetupStatusResponse | null;
  isLoading: boolean;
  error: ParsedApiError | null;
  firstStockCode: string;
  isSaving: boolean;
  isRunningSmoke: boolean;
  smokeError: ParsedApiError | null;
  smokeSuccess: string;
  onRefresh: () => void | Promise<void>;
  onSelectCategory: (category: SystemConfigCategory) => void;
  onRunSmoke: () => void | Promise<void>;
  listSeparator: string;
  t: (key: UiTextKey, params?: Record<string, string | number>) => string;
};

const FirstRunSetupCard: React.FC<FirstRunSetupCardProps> = ({
  status,
  isLoading,
  error,
  firstStockCode,
  isSaving,
  isRunningSmoke,
  smokeError,
  smokeSuccess,
  onRefresh,
  onSelectCategory,
  onRunSmoke,
  listSeparator,
  t,
}) => {
  const [isHidden, setIsHidden] = useState(false);
  const requiredMissing = status?.checks.filter((check) => check.required && check.status === 'needs_action') || [];
  const isComplete = Boolean(status?.isComplete);
  const canRunSmoke = Boolean(status?.readyForSmoke && firstStockCode);
  const summaryTitle = !status
    ? error
      ? t('settings.setupGuideUnknownTitle')
      : t('settings.setupGuideCheckingTitle')
    : isComplete
      ? t('settings.setupGuideCompleteTitle')
      : t('settings.setupGuideIncompleteTitle');
  const summaryMessage = !status
    ? error
      ? t('settings.setupGuideUnknownSummary')
      : t('settings.setupGuideCheckingSummary')
    : requiredMissing.length
      ? t('settings.setupGuideMissingSummary', {
        count: requiredMissing.length,
        labels: requiredMissing.slice(0, 3).map((check) => check.title).join(listSeparator),
      })
      : t('settings.setupGuideReadySummary');

  if (isHidden) {
    return (
      <div className="rounded-2xl border settings-border bg-card/90 px-4 py-3 shadow-soft-card">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <p className="text-sm font-semibold text-foreground">{t('settings.setupGuideHiddenTitle')}</p>
            <p className="mt-1 text-xs leading-5 text-muted-text">{t('settings.setupGuideHiddenDescription')}</p>
          </div>
          <Button type="button" variant="settings-secondary" size="sm" onClick={() => setIsHidden(false)}>
            {t('settings.setupGuideOpen')}
          </Button>
        </div>
      </div>
    );
  }

  return (
    <SettingsSectionCard
      title={t('settings.setupGuideTitle')}
      description={t('settings.setupGuideDescription')}
      contentBordered
    >
      <div data-testid="first-run-setup-card" className="space-y-4">
        <div className="flex flex-col gap-3 rounded-2xl border settings-border bg-background/35 px-4 py-4 md:flex-row md:items-start md:justify-between">
          <div className="min-w-0">
            <p className="text-sm font-semibold text-foreground">
              {summaryTitle}
            </p>
            <p className="mt-1 text-xs leading-6 text-muted-text">
              {summaryMessage}
            </p>
          </div>
          <div className="flex shrink-0 flex-wrap items-center gap-2">
            <Button
              type="button"
              variant="settings-secondary"
              size="sm"
              disabled={isLoading}
              isLoading={isLoading}
              loadingText={t('settings.setupGuideRefreshing')}
              onClick={() => void onRefresh()}
            >
              <RefreshCw className="h-4 w-4" aria-hidden="true" />
              {t('settings.setupGuideRefresh')}
            </Button>
            <Button type="button" variant="settings-secondary" size="sm" onClick={() => setIsHidden(true)}>
              {t('settings.setupGuideHide')}
            </Button>
          </div>
        </div>

        {error ? <ApiErrorAlert error={error} /> : null}

        {isLoading && !status ? (
          <p className="text-sm text-muted-text">{t('common.loading')}</p>
        ) : null}

        {status ? (
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
            {status.checks.map((check) => (
              <div
                key={check.key}
                className="rounded-2xl border settings-border bg-card/65 px-4 py-3"
              >
                <div className="flex items-start gap-3">
                  {getSetupCheckIcon(check)}
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <p className="text-sm font-semibold text-foreground">{check.title}</p>
                      <span className="rounded-full border settings-border bg-background/60 px-2 py-0.5 text-[11px] font-medium text-muted-text">
                        {getSetupCheckStatusLabel(check, t)}
                      </span>
                    </div>
                    <p className="mt-1 text-xs leading-5 text-muted-text">{check.message}</p>
                    {check.nextStep ? (
                      <p className="mt-2 text-xs leading-5 text-secondary-text">{check.nextStep}</p>
                    ) : null}
                  </div>
                </div>
              </div>
            ))}
          </div>
        ) : null}

        <div className="flex flex-wrap items-center gap-2">
          <Button type="button" variant="settings-secondary" size="sm" onClick={() => onSelectCategory('ai_model')}>
            {t('settings.setupGuideConfigureLlm')}
          </Button>
          <Button type="button" variant="settings-secondary" size="sm" onClick={() => onSelectCategory('base')}>
            {t('settings.setupGuideAddStocks')}
          </Button>
          <Button type="button" variant="settings-secondary" size="sm" onClick={() => onSelectCategory('notification')}>
            {t('settings.setupGuideConfigureNotification')}
          </Button>
          <Button
            type="button"
            variant="settings-primary"
            size="sm"
            disabled={!canRunSmoke || isSaving || isRunningSmoke}
            isLoading={isRunningSmoke}
            loadingText={t('settings.setupGuideSmokeRunning')}
            title={!firstStockCode ? t('settings.setupGuideSmokeNeedsStock') : undefined}
            onClick={() => void onRunSmoke()}
          >
            <Play className="h-4 w-4" aria-hidden="true" />
            {t('settings.setupGuideRunSmoke')}
          </Button>
        </div>

        {!canRunSmoke && status ? (
          <p className="text-xs leading-6 text-muted-text">
            {firstStockCode ? t('settings.setupGuideSmokeNotReady') : t('settings.setupGuideSmokeNeedsStock')}
          </p>
        ) : null}
        {smokeError ? <ApiErrorAlert error={smokeError} /> : null}
        {!smokeError && smokeSuccess ? (
          <SettingsAlert title={t('settings.actionSuccess')} message={smokeSuccess} variant="success" />
        ) : null}
      </div>
    </SettingsSectionCard>
  );
};

function parseScheduleTimes(scheduleTimesValue?: string, fallbackValue?: string) {
  const values = String(scheduleTimesValue ?? '')
    .split(',')
    .map((value) => value.trim())
    .filter(Boolean);

  if (values.length > 0) {
    return values;
  }

  const fallback = String(fallbackValue ?? '').trim();
  return fallback ? [fallback] : [SCHEDULER_DEFAULT_TIME];
}

function serializeScheduleTimes(times: string[]) {
  return times.map((time) => time.trim()).filter(Boolean).join(',');
}

function formatSchedulerTimestamp(value: string | null | undefined, language: UiLanguage) {
  if (!value) {
    return '-';
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }

  return new Intl.DateTimeFormat(language === 'en' ? 'en-US' : 'zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).format(date);
}

type SchedulerSettingsCardProps = {
  items: SystemConfigItem[];
  disabled: boolean;
  issueByKey: Record<string, ConfigValidationIssue[]>;
  statusRefreshToken: number;
  onChange: (key: string, value: string) => void;
  onSchedulerStateChange?: (payload: {
    runtimeEnabled: boolean | null;
    overrideEnabled: boolean | null;
  }) => void;
  t: (key: UiTextKey, params?: Record<string, string | number>) => string;
  language: UiLanguage;
};

const SchedulerSettingsCard: React.FC<SchedulerSettingsCardProps> = ({
  items,
  disabled,
  issueByKey,
  statusRefreshToken,
  onChange,
  onSchedulerStateChange,
  t,
  language,
}) => {
  const scheduleEnabledItem = getConfigItem(items, 'SCHEDULE_ENABLED');
  const scheduleTimesItem = getConfigItem(items, 'SCHEDULE_TIMES');
  const scheduleTimeItem = getConfigItem(items, 'SCHEDULE_TIME');
  const hasSchedulerSettings = Boolean(scheduleEnabledItem || scheduleTimesItem || scheduleTimeItem);
  const [status, setStatus] = useState<SchedulerStatusResponse | null>(null);
  const [isRefreshingStatus, setIsRefreshingStatus] = useState(false);
  const [isRunningNow, setIsRunningNow] = useState(false);
  const [statusError, setStatusError] = useState<ParsedApiError | null>(null);
  const [runNowError, setRunNowError] = useState<ParsedApiError | null>(null);
  const [runNowSuccess, setRunNowSuccess] = useState('');
  const [scheduleEnabledOverride, setScheduleEnabledOverride] = useState<boolean | null>(null);

  const refreshSchedulerStatus = useCallback(async () => {
    setStatusError(null);
    setIsRefreshingStatus(true);
    try {
      const payload = await systemConfigApi.getSchedulerStatus();
      setStatus(payload);
    } catch (error: unknown) {
      setStatusError(getParsedApiError(error));
    } finally {
      setIsRefreshingStatus(false);
    }
  }, []);

  useEffect(() => {
    if (!hasSchedulerSettings) {
      return;
    }
    void refreshSchedulerStatus();
  }, [hasSchedulerSettings, refreshSchedulerStatus, statusRefreshToken]);

  useEffect(() => {
    if (!onSchedulerStateChange) {
      return;
    }

    const runtimeEnabled = status?.enabled ?? null;
    onSchedulerStateChange({
      runtimeEnabled,
      overrideEnabled: scheduleEnabledOverride,
    });
  }, [onSchedulerStateChange, status?.enabled, scheduleEnabledOverride]);

  if (!hasSchedulerSettings) {
    return null;
  }

  const scheduleEnabled = isEnabledConfigValue(scheduleEnabledItem?.value);
  const scheduleTimes = parseScheduleTimes(
    String(scheduleTimesItem?.value ?? ''),
    String(scheduleTimeItem?.value ?? ''),
  );
  const timeTargetKey = scheduleTimesItem ? 'SCHEDULE_TIMES' : 'SCHEDULE_TIME';
  const statusEnabled = status?.enabled ?? scheduleEnabled;
  const displayedScheduleEnabled = scheduleEnabledOverride ?? statusEnabled;
  const effectiveStatusTimes = status?.scheduleTimes?.length ? status.scheduleTimes : scheduleTimes.filter(Boolean);
  const validationIssues = [
    ...(issueByKey.SCHEDULE_ENABLED || []),
    ...(issueByKey.SCHEDULE_TIMES || []),
    ...(issueByKey.SCHEDULE_TIME || []),
  ];

  const updateScheduleTimes = (nextTimes: string[]) => {
    if (timeTargetKey === 'SCHEDULE_TIME') {
      onChange(timeTargetKey, nextTimes[0] || '');
      return;
    }
    onChange(timeTargetKey, serializeScheduleTimes(nextTimes));
  };

  const runSchedulerNow = async () => {
    setRunNowError(null);
    setRunNowSuccess('');
    setIsRunningNow(true);
    try {
      await systemConfigApi.runSchedulerNow();
      setRunNowSuccess(t('settings.schedulerRunAccepted'));
      await refreshSchedulerStatus();
    } catch (error: unknown) {
      setRunNowError(getParsedApiError(error));
    } finally {
      setIsRunningNow(false);
    }
  };

  return (
    <SettingsSectionCard
      title={t('settings.schedulerTitle')}
      description={t('settings.schedulerDescription')}
      contentBordered
    >
      <div data-testid="scheduler-settings-card" className="space-y-4">
        <div className="grid grid-cols-1 gap-3">
          <div className="space-y-4 rounded-2xl border settings-border bg-background/35 px-4 py-4">
                <label className="flex items-start gap-3">
                  <input
                    type="checkbox"
                    className="mt-1 h-4 w-4 rounded border-border text-cyan focus:ring-cyan/20"
                    checked={displayedScheduleEnabled}
                    data-testid="scheduler-enabled-checkbox"
                    disabled={disabled || !scheduleEnabledItem?.schema?.isEditable}
                    onChange={(event) => {
                      const nextEnabled = Boolean(event.target.checked);
                      setScheduleEnabledOverride(nextEnabled);
                      onChange('SCHEDULE_ENABLED', nextEnabled ? 'true' : 'false');
                    }}
                  />
              <span>
                <span className="block text-sm font-semibold text-foreground">{t('settings.schedulerEnable')}</span>
                <span className="block text-xs leading-6 text-muted-text">{t('settings.schedulerEnableDescription')}</span>
              </span>
            </label>

            <div className="space-y-3">
              <div className="flex items-center gap-2 text-sm font-semibold text-foreground">
                <Clock className="h-4 w-4" aria-hidden="true" />
                {t('settings.schedulerTimes')}
              </div>
              <div className="flex flex-wrap items-center gap-2">
                {scheduleTimes.map((time, index) => (
                  <div
                    key={index}
                    className="inline-flex h-11 shrink-0 items-center gap-1 rounded-xl border settings-border bg-card/90 p-1 shadow-inner"
                  >
                    <input
                      data-testid={`scheduler-time-input-${index}`}
                      type="time"
                      value={SCHEDULE_TIME_PATTERN.test(time) ? time : ''}
                      aria-label={t('settings.schedulerTimeInputAria', { index: index + 1 })}
                      className="h-9 w-[8.75rem] rounded-lg border-none bg-transparent px-2 text-sm font-medium text-foreground outline-none transition focus:bg-background/60 focus:ring-2 focus:ring-cyan/20"
                      disabled={disabled}
                      onChange={(event) => {
                        const nextTimes = scheduleTimes.map((currentTime, currentIndex) => (
                          currentIndex === index ? event.target.value : currentTime
                        ));
                        updateScheduleTimes(nextTimes);
                      }}
                    />
                    {scheduleTimes.length > 1 ? (
                      <Button
                        type="button"
                        variant="settings-secondary"
                        size="sm"
                        className="h-8 w-8 rounded-lg px-0"
                        aria-label={t('settings.schedulerRemoveTime')}
                        title={t('settings.schedulerRemoveTime')}
                        disabled={disabled}
                        onClick={() => {
                          updateScheduleTimes(scheduleTimes.filter((_, currentIndex) => currentIndex !== index));
                        }}
                      >
                        <Trash2 className="h-4 w-4" aria-hidden="true" />
                      </Button>
                    ) : null}
                  </div>
                ))}
                <Button
                  type="button"
                  variant="settings-secondary"
                  size="sm"
                  className="h-11 shrink-0"
                  data-testid="scheduler-add-time-button"
                  disabled={disabled}
                  onClick={() => updateScheduleTimes([...scheduleTimes, SCHEDULER_DEFAULT_TIME])}
                >
                  <Plus className="h-4 w-4" aria-hidden="true" />
                  {t('settings.schedulerAddTime')}
                </Button>
              </div>
            </div>
          </div>

          <div className="space-y-3 rounded-2xl border settings-border bg-background/35 px-4 py-4">
            <div>
              <p className="text-sm font-semibold text-foreground">{t('settings.schedulerStatus')}</p>
              <p className="mt-1 text-xs leading-6 text-muted-text">
                {status?.running
                  ? t('settings.schedulerRunning')
                  : statusEnabled
                    ? t('settings.schedulerEnabled')
                    : t('settings.schedulerDisabled')}
              </p>
            </div>
            <dl className="grid grid-cols-1 gap-2 text-xs">
              <div className="rounded-xl border settings-border bg-card/60 px-3 py-2">
                <dt className="text-muted-text">{t('settings.schedulerEffectiveTimes')}</dt>
                <dd className="mt-1 font-medium text-foreground">{effectiveStatusTimes.join(', ') || '-'}</dd>
              </div>
              <div className="rounded-xl border settings-border bg-card/60 px-3 py-2">
                <dt className="text-muted-text">{t('settings.schedulerNextRun')}</dt>
                <dd className="mt-1 font-medium text-foreground">
                  {formatSchedulerTimestamp(status?.nextRunAt, language)}
                </dd>
              </div>
              <div className="rounded-xl border settings-border bg-card/60 px-3 py-2">
                <dt className="text-muted-text">{t('settings.schedulerLastSuccess')}</dt>
                <dd data-testid="scheduler-last-success" className="mt-1 font-medium text-foreground">
                  {formatSchedulerTimestamp(status?.lastSuccessAt, language)}
                </dd>
              </div>
              {status?.lastError ? (
                <div className="rounded-xl border border-danger/40 bg-danger/10 px-3 py-2">
                  <dt className="text-danger">{t('settings.schedulerLastError')}</dt>
                  <dd data-testid="scheduler-last-error" className="mt-1 break-words text-danger">{status.lastError}</dd>
                </div>
              ) : null}
            </dl>
            <div className="flex flex-wrap items-center gap-2">
              <Button
                type="button"
                variant="settings-secondary"
                size="sm"
                data-testid="scheduler-refresh-status-button"
                disabled={disabled || isRefreshingStatus}
                isLoading={isRefreshingStatus}
                loadingText={t('settings.schedulerRefreshing')}
                onClick={() => void refreshSchedulerStatus()}
              >
                <RefreshCw className="h-4 w-4" aria-hidden="true" />
                {t('settings.schedulerRefresh')}
              </Button>
              <Button
                type="button"
                variant="settings-primary"
                size="sm"
                data-testid="scheduler-run-now-button"
                disabled={disabled || isRunningNow}
                isLoading={isRunningNow}
                loadingText={t('settings.schedulerRunningNow')}
                onClick={() => void runSchedulerNow()}
              >
                <Play className="h-4 w-4" aria-hidden="true" />
                {t('settings.schedulerRunNow')}
              </Button>
            </div>
          </div>
        </div>

        {validationIssues.length ? (
          <div className="space-y-1 text-xs text-danger">
            {validationIssues.map((issue) => (
              <p key={`${issue.key}-${issue.code}`}>{issue.message}</p>
            ))}
          </div>
        ) : null}
        {statusError ? <ApiErrorAlert error={statusError} /> : null}
        {runNowError ? <ApiErrorAlert error={runNowError} /> : null}
        {!runNowError && runNowSuccess ? (
          <SettingsAlert title={t('settings.actionSuccess')} message={runNowSuccess} variant="success" />
        ) : null}
      </div>
    </SettingsSectionCard>
  );
};

const SettingsPage: React.FC = () => {
  const { authEnabled, passwordChangeable } = useAuth();
  const { language: uiLanguage, t } = useUiLanguage();
  const [envBackupActionError, setEnvBackupActionError] = useState<ParsedApiError | null>(null);
  const [envBackupActionSuccess, setEnvBackupActionSuccess] = useState<string>('');
  const [alphaSiftActionError, setAlphaSiftActionError] = useState<ParsedApiError | null>(null);
  const [alphaSiftActionSuccess, setAlphaSiftActionSuccess] = useState<string>('');
  const [isExportingEnv, setIsExportingEnv] = useState(false);
  const [isImportingEnv, setIsImportingEnv] = useState(false);
  const [isUpdatingAlphaSift, setIsUpdatingAlphaSift] = useState(false);
  const [showImportConfirm, setShowImportConfirm] = useState(false);
  const [showResetConfirm, setShowResetConfirm] = useState(false);
  const [desktopUpdateState, setDesktopUpdateState] = useState<DesktopUpdateState | null>(null);
  const [isCheckingDesktopUpdate, setIsCheckingDesktopUpdate] = useState(false);
  const [schedulerStatusRefreshToken, setSchedulerStatusRefreshToken] = useState(0);
  const [schedulerRuntimeEnabled, setSchedulerRuntimeEnabled] = useState<boolean | null>(null);
  const [schedulerOverrideFromUi, setSchedulerOverrideFromUi] = useState<boolean | null>(null);
  const [setupStatus, setSetupStatus] = useState<SetupStatusResponse | null>(null);
  const [isWizardOpen, setIsWizardOpen] = useState(false);
  const [isRefreshingSetupStatus, setIsRefreshingSetupStatus] = useState(false);
  const [setupStatusError, setSetupStatusError] = useState<ParsedApiError | null>(null);
  const [isRunningSetupSmoke, setIsRunningSetupSmoke] = useState(false);
  const [setupSmokeError, setSetupSmokeError] = useState<ParsedApiError | null>(null);
  const [setupSmokeSuccess, setSetupSmokeSuccess] = useState('');
  const [llmChannelDraftItems, setLlmChannelDraftItems] = useState<SystemConfigUpdateItem[]>([]);
  // Structural completeness gate reported by the LLM channel editor; blocks the
  // unified Save & Apply while an enabled channel is incomplete.
  const [llmChannelDraftValid, setLlmChannelDraftValid] = useState(true);
  // Bumped to tell the mounted channel editor to discard its draft on Reset.
  const [llmChannelResetSignal, setLlmChannelResetSignal] = useState(0);
  const envBackupImportRef = useRef<HTMLInputElement | null>(null);
  const setupStatusRequestIdRef = useRef(0);
  const desktopRuntimeApi = getDesktopRuntimeApi();
  const isDesktopRuntime = Boolean(desktopRuntimeApi);
  const canCheckDesktopUpdate = Boolean(
    desktopRuntimeApi?.getUpdateState && desktopRuntimeApi?.checkForUpdates && desktopRuntimeApi?.openReleasePage
  );
  const desktopAppVersion = getDesktopAppVersion();
  const shouldShowDesktopVersionCard = Boolean(desktopAppVersion);

  // Set page title
  useEffect(() => {
    document.title = t('settings.pageTitleDocument');
  }, [t]);

  const [searchParams, setSearchParams] = useSearchParams();
  // Seed the active tab from the URL once so deep links / refresh restore it.
  // Prefer the new section/view scheme; fall back to (and migrate from) the
  // legacy category/sub params below.
  const [initialTab] = useState(() => {
    const section = searchParams.get('section');
    if (section) {
      const legacy = sectionViewToLegacy(section, searchParams.get('view'));
      return { category: legacy.category, subCategory: legacy.sub };
    }
    const category = searchParams.get('category');
    return category ? { category, subCategory: searchParams.get('sub') } : undefined;
  });

  const {
    itemsByCategory,
    issueByKey,
    selectTab,
    hasDirty,
    dirtyKeys,
    dirtyCount,
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
    resetDraft,
    setDraftValue,
    getChangedItems,
    refreshAfterExternalSave,
    configVersion,
    maskToken,
  } = useSystemConfig(initialTab);

  // section/view is the single source of truth for navigation, driven by the
  // URL so Back/Forward/refresh/deep-links all work. Legacy category/sub only
  // seeds the initial state and is migrated away; it never decides the section
  // (which is why Reports vs Alerts, or Conversation vs Agent, no longer jump).
  const activeSection = useMemo<SettingsSectionId>(() => {
    const section = searchParams.get('section');
    if (section && isSettingsSectionId(section)) {
      return section;
    }
    const category = searchParams.get('category');
    if (category) {
      return legacyToSectionView(category, searchParams.get('sub')).section;
    }
    return SETTINGS_SECTIONS[0].id;
  }, [searchParams]);
  const activeView = useMemo<string>(() => {
    const view = searchParams.get('view');
    if (getSectionViews(activeSection).some((entry) => entry.id === view)) {
      return view as string;
    }
    const category = searchParams.get('category');
    if (category && !searchParams.get('section')) {
      const legacy = legacyToSectionView(category, searchParams.get('sub'));
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
    next.delete('category');
    next.delete('sub');
    next.set('section', section);
    const resolvedView = getSectionViews(section).some((entry) => entry.id === view)
      ? view
      : getDefaultView(section);
    if (resolvedView) {
      next.set('view', resolvedView);
    } else {
      next.delete('view');
    }
    // Normal navigation pushes a history entry so Back/Forward return here.
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
    const hasLegacy = searchParams.has('category') || searchParams.has('sub');
    const canonical = !hasLegacy
      && searchParams.get('section') === activeSection
      && searchParams.get('view') === activeView;
    if (canonical) {
      return;
    }
    const next = new URLSearchParams(searchParams);
    next.delete('category');
    next.delete('sub');
    next.set('section', activeSection);
    if (activeView) {
      next.set('view', activeView);
    } else {
      next.delete('view');
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
  // The LLM channel draft feeds the same unified Save & Apply as normal fields;
  // switching tabs keeps it in this parent state and rehydrates on remount.
  const hasLlmChannelDraft = llmChannelDraftItems.length > 0;
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
  // Discard reverts both the useSystemConfig draft and the LLM channel draft; the
  // reset signal tells a mounted channel editor to re-sync to the saved snapshot.
  const discardDraft = useCallback(() => {
    resetDraft();
    setLlmChannelDraftItems([]);
    setLlmChannelDraftValid(true);
    setLlmChannelResetSignal((current) => current + 1);
  }, [resetDraft]);

  const resolveSettingsConflict = useCallback((key: string, choice: 'server' | 'local') => {
    if (choice === 'server' && llmChannelDraftItems.some((item) => item.key === key)) {
      setLlmChannelDraftItems((current) => current.filter((item) => item.key !== key));
      setLlmChannelResetSignal((current) => current + 1);
    }
    resolveConflictField(key, choice);
  }, [llmChannelDraftItems, resolveConflictField]);

  const resolveAllSettingsConflicts = useCallback((choice: 'server' | 'local') => {
    if (choice === 'server' && conflictState) {
      const conflictKeys = new Set(conflictState.fields.map((field) => field.key));
      setLlmChannelDraftItems((current) => current.filter((item) => !conflictKeys.has(item.key)));
      setLlmChannelResetSignal((current) => current + 1);
    }
    resolveAllConflicts(choice);
  }, [conflictState, resolveAllConflicts]);

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

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    void refreshSetupStatus();
  }, [refreshSetupStatus]);

  useEffect(() => {
    if (!toast) {
      return;
    }

    const timer = window.setTimeout(() => {
      clearToast();
    }, 3200);

    return () => {
      window.clearTimeout(timer);
    };
  }, [clearToast, toast]);

  useEffect(() => {
    if (!canCheckDesktopUpdate) {
      setDesktopUpdateState(null);
      setIsCheckingDesktopUpdate(false);
      return;
    }

    let active = true;

    const syncDesktopUpdateState = async () => {
      try {
        const state = await desktopRuntimeApi?.getUpdateState?.();
        if (active) {
          setDesktopUpdateState(normalizeDesktopUpdateState(state));
        }
      } catch (error: unknown) {
        if (!active) {
          return;
        }
        setDesktopUpdateState({
          status: 'error',
          message: error instanceof Error ? error.message : t('settings.desktopUpdateErrorMessage'),
        });
      }
    };

    void syncDesktopUpdateState();

    const unsubscribe = desktopRuntimeApi?.onUpdateStateChange?.((state) => {
      if (!active) {
        return;
      }
      setDesktopUpdateState(normalizeDesktopUpdateState(state));
      setIsCheckingDesktopUpdate(false);
    });

    return () => {
      active = false;
      if (typeof unsubscribe === 'function') {
        unsubscribe();
      }
    };
  }, [canCheckDesktopUpdate, desktopRuntimeApi, t]);

  const rawActiveItems = itemsByCategory[activeCategory] || [];
  const rawActiveItemMap = new Map(rawActiveItems.map((item) => [item.key, String(item.value ?? '')]));
  const firstSetupStockCode = parseSetupStockList(getConfigItem(itemsByCategory.base || [], 'STOCK_LIST')?.value)[0] || '';
  const alphasiftItem = (itemsByCategory.data_source || []).find((item) => item.key === 'ALPHASIFT_ENABLED');
  const alphasiftEnabled = String(alphasiftItem?.value ?? '').trim().toLowerCase() === 'true';
  const shouldShowFirstRunSetup = activeCategory === 'base';
  const shouldShowAlphaSiftSettings =
    activeCategory === 'data_source' && activeSubCategory === 'providers' && Boolean(alphasiftItem);
  const hasConfiguredChannels = Boolean((rawActiveItemMap.get('LLM_CHANNELS') || '').trim());
  const hasLitellmConfig = Boolean((rawActiveItemMap.get('LITELLM_CONFIG') || '').trim());
  const hasRuntimeSchedulerMismatch =
    schedulerRuntimeEnabled !== null
    && schedulerOverrideFromUi !== null
    && schedulerOverrideFromUi !== schedulerRuntimeEnabled;
  const hasRuntimeSchedulerMismatchInDraft = hasRuntimeSchedulerMismatch
    && !currentChangedItems.some((item) => item.key === 'SCHEDULE_ENABLED');
  // The LLM channel draft is committed by the same Save & Apply, so it counts
  // toward dirty state; an enabled-incomplete channel keeps Save disabled.
  const effectiveHasDirty = hasDirty || hasRuntimeSchedulerMismatchInDraft || hasLlmChannelDraft;
  const canSaveConfig = effectiveHasDirty
    && (!hasLlmChannelDraft || llmChannelDraftValid)
    && !conflictState;
  const effectiveDirtyCount = dirtyCount
    + (hasRuntimeSchedulerMismatchInDraft ? 1 : 0)
    + llmChannelDraftItems.length;
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

  // UI rendering rule only: hide channel-managed and legacy provider-specific
  // LLM keys from generic fields when channel mode is active. This does not
  // alter save/refresh payloads or config migration/rollback behavior.
  const LLM_CHANNEL_KEY_RE = /^LLM_[A-Z0-9_]+_(PROTOCOL|BASE_URL|API_KEY|API_KEYS|MODELS|EXTRA_HEADERS|ENABLED)$/;
  // Legacy LiteLLM keys decluttered from the "model" sub-tab once channels are
  // configured. Provider API-key fields are intentionally excluded so the
  // "providers" sub-tab always lists every provider.
  const AI_MODEL_HIDDEN_KEYS = new Set([
    'LLM_CHANNELS',
    'LLM_TEMPERATURE',
    'LITELLM_MODEL',
    'AGENT_LITELLM_MODEL',
    'LITELLM_FALLBACK_MODELS',
    'VISION_MODEL',
  ]);
  const SYSTEM_HIDDEN_KEYS = new Set([
    'ADMIN_AUTH_ENABLED',
    ...SCHEDULER_SETTING_KEYS,
  ]);
  const DATA_SOURCE_HIDDEN_KEYS = new Set([
    'ALPHASIFT_ENABLED',
  ]);
  const AGENT_HIDDEN_KEYS = new Set<string>();
  const activeItems =
    activeCategory === 'ai_model'
      ? rawActiveItems.filter((item) => {
        if (hasConfiguredChannels && LLM_CHANNEL_KEY_RE.test(item.key)) {
          return false;
        }
        if (hasConfiguredChannels && !hasLitellmConfig && AI_MODEL_HIDDEN_KEYS.has(item.key)) {
          return false;
        }
        return true;
      })
      : activeCategory === 'system'
        ? rawActiveItems.filter((item) => !SYSTEM_HIDDEN_KEYS.has(item.key))
      : activeCategory === 'data_source'
        ? rawActiveItems.filter((item) => !DATA_SOURCE_HIDDEN_KEYS.has(item.key))
      : activeCategory === 'agent'
        ? rawActiveItems.filter((item) => !AGENT_HIDDEN_KEYS.has(item.key))
      : rawActiveItems;
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
      const { section, view } = placementForKey(categoryByKey[key] ?? '', key);
      entries.push({
        key,
        label: uiLanguage === 'en' ? key : getFieldTitleZh(key, key),
        message: firstError.message,
        section,
        view,
      });
    }
    return entries;
  }, [issueByKey, categoryByKey, uiLanguage]);
  const jumpToErrorField = useCallback((entry: ErrorSummaryEntry) => {
    selectSectionView(entry.section as SettingsSectionId, entry.view);
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
  const isAiOverview = activeSection === 'ai_models' && activeView === 'overview';
  // Task Routing view: the single place to edit which model each task uses.
  const isAiTaskRouting = activeSection === 'ai_models' && activeView === 'task_routing';
  const aiModelItemByKey = useMemo(
    () => new Map((itemsByCategory.ai_model || []).map((item) => [item.key, item])),
    [itemsByCategory],
  );
  const pickAiModelItems = useCallback(
    (keys: string[]) => keys
      .map((key) => aiModelItemByKey.get(key))
      .filter((item): item is NonNullable<typeof item> => Boolean(item)),
    [aiModelItemByKey],
  );
  // Task Routing is the single canonical editor for per-task models and the
  // generation temperature. Fallback order is edited under Reliability only, so
  // here it is a read-only summary with a jump link (no duplicate editor).
  const taskRoutingItems = useMemo(
    () => pickAiModelItems(['LITELLM_MODEL', 'AGENT_LITELLM_MODEL', 'VISION_MODEL', 'LLM_TEMPERATURE']),
    [pickAiModelItems],
  );
  // Reliability view: two distinct mechanisms — execution-backend failover and
  // in-LiteLLM model fallback order (MC-05, must not both read "Fallback").
  const isAiReliability = activeSection === 'ai_models' && activeView === 'reliability';
  const executionFailoverItems = useMemo(
    () => pickAiModelItems(['GENERATION_BACKEND', 'GENERATION_FALLBACK_BACKEND']),
    [pickAiModelItems],
  );
  const modelFallbackItems = useMemo(
    () => pickAiModelItems(['LITELLM_FALLBACK_MODELS']),
    [pickAiModelItems],
  );
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
  // categories via the placement map (e.g. HMAC usage secrets), instead of the
  // legacy Model Providers panel (which stays under the AI & Models → Advanced
  // view). This keeps everyday views uncluttered (MC-18).
  const isTopLevelAdvanced = activeSection === 'advanced';
  const advancedSectionItems = useMemo(
    () => Object.entries(itemsByCategory)
      .flatMap(([category, categoryItems]) =>
        categoryItems.filter((item) => placementForKey(category, item.key).section === 'advanced'))
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
  ).filter((item) => belongsToActiveSection(item.key));
  const activeSubPromptCacheItems =
    activeCategory === 'ai_model' && activeSubCategory === 'model' ? promptCacheAdvancedItems : [];
  const isNotificationChannelsSub = activeCategory === 'notification' && activeSubCategory === 'channels';
  const isModelProvidersSub = activeCategory === 'ai_model' && activeSubCategory === 'providers';
  const isDataProvidersSub = activeCategory === 'data_source' && activeSubCategory === 'providers';
  const activeSubTitle = hasSubNav && activeSubCategory
    ? t((activeSubCategoriesList?.find((sub) => sub.id === activeSubCategory)?.titleKey) ?? 'settings.activePanelTitle')
    : '';
  // Whether the field panel (SettingsSectionCard with fields) has any content for the active tab.
  const hasSubFieldContent =
    isNotificationChannelsSub ||
    isModelProvidersSub ||
    isDataProvidersSub ||
    subFilteredItems.length > 0 ||
    activeSubPromptCacheItems.length > 0;
  const isEnvBackupAllowed = isDesktopRuntime || authEnabled;
  const envBackupActionDisabled = isLoading || isSaving || isExportingEnv || isImportingEnv || !isEnvBackupAllowed;

  const downloadEnvBackup = async () => {
    setEnvBackupActionError(null);
    setEnvBackupActionSuccess('');
    setIsExportingEnv(true);
    try {
      const payload = await systemConfigApi.exportEnv();
      const blob = new Blob([payload.content], { type: 'text/plain;charset=utf-8' });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = formatEnvBackupFilename(isDesktopRuntime);
      document.body.appendChild(anchor);
      anchor.click();
      document.body.removeChild(anchor);
      URL.revokeObjectURL(url);
      setEnvBackupActionSuccess(t('settings.envExported'));
    } catch (error: unknown) {
      setEnvBackupActionError(getParsedApiError(error));
    } finally {
      setIsExportingEnv(false);
    }
  };

  const beginEnvBackupImport = () => {
    setEnvBackupActionError(null);
    setEnvBackupActionSuccess('');
    if (hasDirty) {
      setShowImportConfirm(true);
      return;
    }
    envBackupImportRef.current?.click();
  };

  const handleEnvBackupImportFile = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = '';
    setShowImportConfirm(false);
    if (!file) {
      return;
    }

    setEnvBackupActionError(null);
    setEnvBackupActionSuccess('');
    setIsImportingEnv(true);
    try {
      const content = await file.text();
      const importResult = await systemConfigApi.importEnv({
        configVersion,
        content,
        reloadNow: true,
      });
      const reloaded = await load();
      if (!reloaded) {
        setEnvBackupActionError(createParsedApiError({
          title: t('settings.envImportedRefreshFailedTitle'),
          message: t('settings.envImportedRefreshFailedMessage'),
          rawMessage: t('settings.envImportedRefreshFailedRaw'),
          category: 'http_error',
        }));
        return;
      }
      if (importResult.updatedKeys.some((key) => SCHEDULER_SETTING_KEYS.has(key))) {
        setSchedulerStatusRefreshToken((current) => current + 1);
      }
      notifySystemConfigChanged();
      void refreshSetupStatus();
      setEnvBackupActionSuccess(t('settings.envImported'));
    } catch (error: unknown) {
      setEnvBackupActionError(getParsedApiError(error));
    } finally {
      setIsImportingEnv(false);
    }
  };

  const handleDesktopUpdateCheck = async () => {
    if (!desktopRuntimeApi?.checkForUpdates) {
      return;
    }

    setIsCheckingDesktopUpdate(true);
    setDesktopUpdateState((current) => ({
      ...(current || {}),
      status: 'checking',
      message: t('settings.desktopUpdateCheckingMessage'),
    }));

    try {
      const state = await desktopRuntimeApi.checkForUpdates();
      setDesktopUpdateState(normalizeDesktopUpdateState(state));
    } catch (error: unknown) {
      setDesktopUpdateState({
        status: 'error',
        message: error instanceof Error ? error.message : t('settings.desktopUpdateErrorMessage'),
      });
    } finally {
      setIsCheckingDesktopUpdate(false);
    }
  };

  const updateAlphaSiftEnabled = async (nextEnabled: boolean) => {
    setAlphaSiftActionError(null);
    setAlphaSiftActionSuccess('');
    setIsUpdatingAlphaSift(true);
    try {
      if (nextEnabled) {
        await alphasiftApi.enable();
        await refreshAfterExternalSave(['ALPHASIFT_ENABLED']);
        setAlphaSiftActionSuccess(t('settings.enabledAlphaSiftSuccess'));
        return;
      }

      await systemConfigApi.update({
        configVersion,
        maskToken,
        reloadNow: true,
        items: [{ key: 'ALPHASIFT_ENABLED', value: 'false' }],
      });
      notifyAlphaSiftConfigChanged();
      await refreshAfterExternalSave(['ALPHASIFT_ENABLED']);
      setAlphaSiftActionSuccess(t('settings.disabledAlphaSiftSuccess'));
    } catch (error: unknown) {
      setAlphaSiftActionError(getParsedApiError(error));
      await refreshAfterExternalSave(['ALPHASIFT_ENABLED']);
    } finally {
      setIsUpdatingAlphaSift(false);
    }
  };

  const handleSaveConfig = async () => {
    const changedItems = getChangedItems();
    const syncRuntimeSchedulerState =
      schedulerOverrideFromUi !== null
      && schedulerRuntimeEnabled !== null
      && schedulerOverrideFromUi !== schedulerRuntimeEnabled
      && !changedItems.some((item) => item.key === 'SCHEDULE_ENABLED');
    const schedulerSyncItem: SystemConfigUpdateItem[] = syncRuntimeSchedulerState
      ? [{ key: 'SCHEDULE_ENABLED', value: schedulerOverrideFromUi ? 'true' : 'false' }]
      : [];
    // Commit the LLM channel draft through the same transaction so channel and
    // normal field edits are persisted atomically. Channel entries win on key
    // collisions since the editor owns those keys.
    const mergedByKey = new Map<string, SystemConfigUpdateItem>();
    for (const item of [...changedItems, ...schedulerSyncItem]) {
      mergedByKey.set(item.key.toUpperCase(), item);
    }
    for (const item of llmChannelDraftItems) {
      mergedByKey.set(item.key.toUpperCase(), item);
    }
    const changedItemsToSave = Array.from(mergedByKey.values());
    const changedAlphaSiftItem = changedItems.find((item) => item.key === 'ALPHASIFT_ENABLED');
    const result = await save(changedItemsToSave);
    if (!result.success) {
      return;
    }
    const submittedLlmValues = new Map(
      llmChannelDraftItems.map((item) => [item.key.toUpperCase(), item.value]),
    );
    // Clear only the exact channel values included in this transaction. If the
    // user edited a channel again while Save was in flight, keep that newer
    // draft for the next transaction.
    setLlmChannelDraftItems((current) => current.filter((item) => (
      submittedLlmValues.get(item.key.toUpperCase()) !== item.value
    )));
    setLlmChannelDraftValid(true);
    applyPostSaveEffects();
    if (!changedAlphaSiftItem) {
      return;
    }

    setAlphaSiftActionError(null);
    setAlphaSiftActionSuccess('');
    try {
      const isAlphaSiftEnabled = changedAlphaSiftItem.value.trim().toLowerCase() === 'true';
      if (isAlphaSiftEnabled) {
        await alphasiftApi.enable();
        await refreshAfterExternalSave(['ALPHASIFT_ENABLED']);
        setAlphaSiftActionSuccess(t('settings.enabledAlphaSiftSuccess'));
        return;
      }

      notifyAlphaSiftConfigChanged();
      setAlphaSiftActionSuccess(t('settings.disabledAlphaSiftSuccess'));
    } catch (error: unknown) {
      setAlphaSiftActionError(getParsedApiError(error));
      await refreshAfterExternalSave(['ALPHASIFT_ENABLED']);
    }
  };

  // First-run wizard commits its minimal config through the same save
  // transaction (validate + update + apply server payload), so channel keys are
  // persisted atomically and the normal post-save effects run.
  const handleWizardComplete = async (items: WizardDraftItem[]) => {
    const result = await save(items);
    if (!result.success) {
      return;
    }
    applyPostSaveEffects();
    setIsWizardOpen(false);
  };

  const openDesktopReleasePage = async () => {
    if (!desktopRuntimeApi?.openReleasePage) {
      return;
    }

    await desktopRuntimeApi.openReleasePage(desktopUpdateState?.releaseUrl);
  };

  const installDesktopUpdate = async () => {
    if (!desktopRuntimeApi?.installDownloadedUpdate) {
      setDesktopUpdateState((current) => ({
        ...(current || {}),
        status: 'error',
        message: t('settings.desktopManualUnsupported'),
      }));
      return;
    }

    try {
      setDesktopUpdateState((current) => ({
        ...(current || {}),
        status: 'installing',
        message: t('settings.desktopUpdateInstallingMessage'),
      }));
      await desktopRuntimeApi.installDownloadedUpdate();
    } catch (error: unknown) {
      setDesktopUpdateState((current) => ({
        ...(current || {}),
        status: 'error',
        message: error instanceof Error ? error.message : t('settings.desktopManualUnsupported'),
      }));
    }
  };

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

  const desktopUpdateNotice = getDesktopUpdateNotice(desktopUpdateState, t);
  const shouldGuardActiveConfigPanel = activeCategory === 'notification' || activeCategory === 'agent';
  const activeConfigPanelErrorTitle = activeCategory === 'agent' ? t('settings.agentSettings') : t('settings.notificationSettings');
  const settingsPanelDiagnosticHint = isDesktopRuntime
    ? uiLanguage === 'en'
      ? <>Check and provide the desktop log <code>desktop.log</code>, plus the release version, Windows version, and trigger path.</>
      : <>请查看并提供桌面端日志 <code>desktop.log</code>，同时补充 release 版本、Windows 版本和触发入口。</>
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
  // the panel doesn't reuse the sibling category's heading (e.g. Reports must
  // not read "通知规则", Conversation must not read the Agent heading).
  const splitSectionCopy: Partial<Record<SettingsSectionId, { title: string; description: string }>> = {
    reports: {
      title: sectionLabel('reports', uiLanguage),
      description: uiLanguage === 'en'
        ? 'Report output format, language, templates and rendering.'
        : '报告输出的格式、语言、模板与渲染。',
    },
    conversation: {
      title: sectionLabel('conversation', uiLanguage),
      description: uiLanguage === 'en'
        ? 'Conversation context handling and compression.'
        : '对话上下文的处理与压缩策略。',
    },
  };
  const sectionScopedCopy = splitSectionCopy[activeSection];
  const activeConfigPanelTitle = sectionScopedCopy?.title
    ?? (hasSubNav && activeSubTitle ? activeSubTitle : activeCategoryTitle);
  const activeConfigPanelDescription = sectionScopedCopy?.description ?? activeCategoryDescription;
  // For single-tab categories that a section split can narrow (agent →
  // Conversation / Agent Behavior), gate on the section-filtered content so an
  // empty section never renders a bare card.
  const hasSectionFieldContent = subFilteredItems.length > 0 || activeSubPromptCacheItems.length > 0;
  const shouldRenderFieldPanel = (hasSubNav ? hasSubFieldContent : hasSectionFieldContent)
    && !isAiOverview
    && !isAiTaskRouting
    && !isAiReliability
    && !isTopLevelAdvanced;
  const activeConfigPanel = shouldRenderFieldPanel ? (
    <SettingsSectionCard
      title={activeConfigPanelTitle}
      description={activeConfigPanelDescription || t('settings.activePanelDescription')}
    >
      {isNotificationChannelsSub ? (
        <NotificationChannelsPanel
          items={visibleActiveItems.filter((item) => isNotificationChannelKey(item.key))}
          disabled={isSaving}
          onChange={setDraftValue}
          issueByKey={issueByKey}
        />
      ) : isModelProvidersSub ? (
        <ModelProvidersPanel
          items={subFilteredItems}
          disabled={isSaving}
          onChange={setDraftValue}
          issueByKey={issueByKey}
        />
      ) : isDataProvidersSub ? (
        <DataProvidersPanel
          items={subFilteredItems}
          disabled={isSaving}
          onChange={setDraftValue}
          issueByKey={issueByKey}
          configuredOverrides={{ alphasift: alphasiftEnabled }}
        />
      ) : activeFieldGroupOrder ? (
        <div className="space-y-4">
          {activeFieldGroupOrder.map((group) => {
            const groupItems = subFilteredItems
              .filter((item) => fieldGroupIdOf(item.key) === group.id)
              .sort((a, b) => fieldGroupOrderOf(a.key) - fieldGroupOrderOf(b.key));
            if (!groupItems.length) {
              return null;
            }
            return (
              <div key={group.id} className="space-y-2">
                <h3 className="px-1 text-sm font-medium text-secondary-text">{t(group.titleKey)}</h3>
                <div className="overflow-hidden rounded-lg border border-[var(--settings-border)] bg-[var(--settings-surface)]">
                  {groupItems.map((item) => (
                    <SettingsField
                      key={item.key}
                      item={item}
                      value={item.value}
                      disabled={isSaving}
                      onChange={setDraftValue}
                      issues={issueByKey[item.key] || []}
                      requirement={resolveFieldRequirement(item.schema?.contract, allValuesByKey)}
                      dependencyLocked={!isFieldEnabledByContract(item.schema?.contract, allValuesByKey)}
                    />
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      ) : subFilteredItems.length ? (
        <div className="overflow-hidden rounded-lg border border-[var(--settings-border)] bg-[var(--settings-surface)]">
          {subFilteredItems.map((item) => (
            <SettingsField
              key={item.key}
              item={item}
              value={item.value}
              disabled={isSaving}
              onChange={setDraftValue}
              issues={issueByKey[item.key] || []}
            />
          ))}
        </div>
      ) : null}
      {activeSubPromptCacheItems.length ? (
        <details className="group/prompt-cache overflow-hidden rounded-lg border border-[var(--settings-border)] bg-[var(--settings-surface)] transition-colors duration-200 hover:bg-[var(--settings-surface-hover)]">
          <summary className="flex cursor-pointer list-none items-start justify-between gap-3 px-4 py-4 [&::-webkit-details-marker]:hidden">
            <div className="min-w-0 space-y-1">
              <p className="text-sm font-semibold text-foreground">
                {t('settings.promptCacheAdvancedTitle')}
              </p>
              <p className="text-xs leading-5 text-muted-text">
                {t('settings.promptCacheAdvancedDescription')}
              </p>
            </div>
            <ChevronDown className="mt-0.5 h-4 w-4 shrink-0 text-muted-text transition-transform group-open/prompt-cache:rotate-180" aria-hidden="true" />
          </summary>
          <div className="border-t border-[var(--settings-border-soft)]">
            {activeSubPromptCacheItems.map((item) => (
              <SettingsField
                key={item.key}
                item={item}
                value={item.value}
                disabled={isSaving}
                onChange={setDraftValue}
                issues={issueByKey[item.key] || []}
              />
            ))}
          </div>
        </details>
      ) : null}
    </SettingsSectionCard>
  ) : hasSubNav || hasActiveConfigItems ? null : (
    <EmptyState
      title={t('settings.currentCategoryEmptyTitle')}
      description={t('settings.currentCategoryEmptyDescription')}
      className="settings-surface-panel settings-border-strong border-none bg-transparent shadow-none"
    />
  );

  return (
    <div className="settings-page min-h-full px-4 pb-6 pt-4 md:px-6">
      <div className="mb-4 px-1 py-1">
        <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
          <div className="min-w-0">
            <h1 className="text-xl font-semibold tracking-tight text-foreground">{t('settings.pageTitle')}</h1>
            <p className="max-w-3xl text-xs leading-5 text-muted-text sm:text-sm sm:leading-6">
              {t('settings.pageDescription')}
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <Button
              type="button"
              variant="settings-secondary"
              size="sm"
              className="px-2.5"
              onClick={() => {
                if (effectiveHasDirty) {
                  setShowResetConfirm(true);
                } else {
                  discardDraft();
                }
              }}
              disabled={isLoading || isSaving}
            >
              <RefreshCw className="h-4 w-4" aria-hidden="true" />
              {t('settings.reset')}
            </Button>
            <Button
              type="button"
              variant="settings-primary"
              size="sm"
              className="px-2.5"
              onClick={() => void handleSaveConfig()}
              disabled={!canSaveConfig || isSaving || isLoading}
              isLoading={isSaving}
              loadingText={t('settings.saving')}
            >
              <CheckCircle2 className="h-4 w-4" aria-hidden="true" />
              {isSaving
                ? t('settings.saving')
                : effectiveDirtyCount
                  ? t('settings.saveConfigWithCount', { count: effectiveDirtyCount })
                  : t('settings.saveConfig')}
            </Button>
          </div>
        </div>

        {saveError ? (
          <ApiErrorAlert
            className="mt-3"
            error={saveError}
            actionLabel={retryAction === 'save' ? t('settings.saveRetry') : undefined}
            onAction={retryAction === 'save' ? () => void handleSaveConfig() : undefined}
          />
        ) : null}

        {conflictState ? (
          <section
            className="mt-3 space-y-3 rounded-xl border border-warning/40 bg-warning/5 p-4"
            aria-labelledby="settings-conflict-title"
          >
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="space-y-1">
                <h2 id="settings-conflict-title" className="text-sm font-semibold text-foreground">
                  配置同时被其他会话修改
                </h2>
                <p className="text-xs leading-5 text-secondary-text">
                  逐项选择采用服务器值或保留本地草稿。未选择前不会覆盖任何一方，也不能继续保存。
                </p>
              </div>
              <div className="flex flex-wrap gap-2">
                <Button
                  type="button"
                  variant="settings-secondary"
                  size="xsm"
                  onClick={() => resolveAllSettingsConflicts('server')}
                >
                  全部采用服务器值
                </Button>
                <Button
                  type="button"
                  variant="settings-secondary"
                  size="xsm"
                  onClick={() => resolveAllSettingsConflicts('local')}
                >
                  全部保留本地草稿
                </Button>
              </div>
            </div>

            <div className="space-y-2">
              {conflictState.fields.map((field) => (
                <div key={field.key} className="rounded-lg border border-[var(--settings-border)] bg-background/70 p-3">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div>
                      <p className="text-sm font-medium text-foreground">{field.title || field.key}</p>
                      <p className="text-[11px] text-muted-text">{field.key}</p>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      <Button
                        type="button"
                        variant="settings-secondary"
                        size="xsm"
                        onClick={() => resolveSettingsConflict(field.key, 'server')}
                      >
                        采用服务器值
                      </Button>
                      <Button
                        type="button"
                        variant="settings-primary"
                        size="xsm"
                        onClick={() => resolveSettingsConflict(field.key, 'local')}
                      >
                        保留本地草稿
                      </Button>
                    </div>
                  </div>
                  <div className="mt-3 grid gap-2 sm:grid-cols-2">
                    <div className="rounded-md bg-[var(--settings-surface)] px-3 py-2">
                      <p className="text-[11px] font-medium text-muted-text">服务器当前值</p>
                      <p className="mt-1 break-all text-xs text-secondary-text">
                        {field.isSensitive ? '敏感值已更新（内容隐藏）' : field.server || '（空）'}
                      </p>
                    </div>
                    <div className="rounded-md bg-[var(--settings-surface)] px-3 py-2">
                      <p className="text-[11px] font-medium text-muted-text">你的本地草稿</p>
                      <p className="mt-1 break-all text-xs text-secondary-text">
                        {field.isSensitive ? '本地敏感值已修改（内容隐藏）' : field.local || '（空）'}
                      </p>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </section>
        ) : null}
      </div>

      {loadError ? (
        <ApiErrorAlert
          error={loadError}
          actionLabel={retryAction === 'load' ? t('common.retry') : t('settings.reload')}
          onAction={() => void retry()}
          className="mb-4"
        />
      ) : null}

      {isLoading ? (
        <SettingsLoading />
      ) : (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-[260px_minmax(0,1fr)]">
          <aside className="lg:sticky lg:top-4 lg:self-start">
            <SettingsSectionNav
              activeSection={activeSection}
              onSelectSection={(section) => selectSectionView(section, getDefaultView(section))}
              onMobileSelectSection={selectSectionFromMobile}
              sectionStatus={settingsSectionStatus}
              language={uiLanguage}
              navLabel={t('settings.categoryNavTitle')}
            />
          </aside>

          <section ref={contentRegionRef} tabIndex={-1} className="space-y-4 outline-none">
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
            {shouldShowFirstRunSetup ? (
              <div className="flex flex-col gap-2 rounded-2xl border settings-border bg-card/60 px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
                <div className="min-w-0">
                  <p className="text-sm font-semibold text-foreground">
                    {uiLanguage === 'en' ? 'Quick setup' : '快速配置'}
                  </p>
                  <p className="mt-0.5 text-xs text-muted-text">
                    {uiLanguage === 'en'
                      ? 'Get a runnable model config in a few guided steps.'
                      : '几步引导，快速得到一个可运行的模型配置。'}
                  </p>
                </div>
                <Button
                  type="button"
                  variant="settings-primary"
                  size="sm"
                  className="shrink-0"
                  onClick={() => setIsWizardOpen(true)}
                >
                  {uiLanguage === 'en' ? 'Start wizard' : '启动向导'}
                </Button>
              </div>
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
                listSeparator={uiLanguage === 'en' ? ', ' : '、'}
                t={t}
              />
            ) : null}
            {shouldShowAlphaSiftSettings ? (
              <SettingsSectionCard
                title={t('settings.alphaSift')}
                description={t('settings.alphaSiftDescription')}
              >
                <div className="flex flex-col gap-4 rounded-2xl border settings-border bg-background/35 px-4 py-4 md:flex-row md:items-center md:justify-between">
                  <div>
                    <p className="text-sm font-semibold text-foreground">
                      {alphasiftEnabled ? t('settings.alphaSiftEnabled') : t('settings.alphaSiftDisabled')}
                    </p>
                    <p className="mt-1 text-xs leading-6 text-muted-text">
                      {t('settings.alphaSiftSummary')}
                    </p>
                    <p className="mt-2 text-xs leading-6 text-amber-700 dark:text-amber-300">
                      {t('settings.alphaSiftRisk')}
                    </p>
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    <Button
                      type="button"
                      variant="settings-secondary"
                      onClick={() => selectSectionView('data_sources', 'providers')}
                    >
                      {t('settings.viewConfigItems')}
                    </Button>
                    <Button
                      type="button"
                      variant={alphasiftEnabled ? 'settings-secondary' : 'settings-primary'}
                      onClick={() => void updateAlphaSiftEnabled(!alphasiftEnabled)}
                      disabled={isSaving || isLoading || isUpdatingAlphaSift}
                      isLoading={isUpdatingAlphaSift}
                      loadingText={alphasiftEnabled ? t('settings.disablingAlphaSift') : t('settings.enablingAlphaSift')}
                    >
                      {alphasiftEnabled ? t('settings.disableAlphaSift') : t('settings.enableAlphaSift')}
                    </Button>
                  </div>
                </div>
                {alphaSiftActionError ? (
                  <div className="mt-3">
                    <ApiErrorAlert error={alphaSiftActionError} />
                  </div>
                ) : null}
                {!alphaSiftActionError && alphaSiftActionSuccess ? (
                  <div className="mt-3">
                    <SettingsAlert title={t('settings.actionSuccess')} message={alphaSiftActionSuccess} variant="success" />
                  </div>
                ) : null}
              </SettingsSectionCard>
            ) : null}
            {activeCategory === 'system' ? <AuthSettingsCard /> : null}
            {activeCategory === 'system' ? (
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
            ) : null}
            {activeCategory === 'system' ? (
              <SettingsSectionCard
                title={t('settings.versionInfo')}
                description={t('settings.versionInfoDescription')}
                contentBordered
              >
                <div
                  className={`grid grid-cols-1 gap-3 ${shouldShowDesktopVersionCard ? 'md:grid-cols-4' : 'md:grid-cols-3'}`}
                >
                  <div className="rounded-2xl border settings-border bg-background/40 px-4 py-3">
                    <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-text">
                      {t('settings.versionWebui')}
                    </p>
                    <p className="mt-2 break-all font-mono text-sm text-foreground">
                      {WEB_BUILD_INFO.version}
                    </p>
                  </div>
                  <div className="rounded-2xl border settings-border bg-background/40 px-4 py-3">
                    <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-text">
                      {t('settings.versionBuildId')}
                    </p>
                    <p className="mt-2 break-all font-mono text-sm text-foreground">
                      {WEB_BUILD_INFO.buildId}
                    </p>
                  </div>
                  <div className="rounded-2xl border settings-border bg-background/40 px-4 py-3">
                    <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-text">
                      {t('settings.versionBuildTime')}
                    </p>
                    <p className="mt-2 break-all font-mono text-sm text-foreground">
                      {WEB_BUILD_INFO.buildTime}
                    </p>
                  </div>
                  {shouldShowDesktopVersionCard ? (
                    <div className="rounded-2xl border settings-border bg-background/40 px-4 py-3">
                      <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-text">
                        {t('settings.versionDesktop')}
                      </p>
                      <p className="mt-2 break-all font-mono text-sm text-foreground">
                        {desktopAppVersion}
                      </p>
                    </div>
                  ) : null}
                </div>
                <p className="text-xs leading-6 text-muted-text">
                  {t('settings.updateBuildDescription')}
                </p>
                {canCheckDesktopUpdate ? (
                  <div className="mt-4 space-y-3 rounded-2xl border settings-border bg-background/30 px-4 py-4">
                    <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
                      <div>
                        <p className="text-sm font-medium text-foreground">{t('settings.desktopUpdate')}</p>
                        <p className="text-xs leading-6 text-muted-text">
                          {t('settings.desktopUpdateDescription')}
                        </p>
                      </div>
                      <Button
                        type="button"
                        variant="settings-secondary"
                        onClick={() => void handleDesktopUpdateCheck()}
                        disabled={isCheckingDesktopUpdate}
                        isLoading={isCheckingDesktopUpdate}
                        loadingText={t('settings.checkingDesktopUpdate')}
                      >
                        {t('settings.checkDesktopUpdate')}
                      </Button>
                    </div>
                    {desktopUpdateNotice ? (
                      <SettingsAlert
                        title={desktopUpdateNotice.title}
                        message={desktopUpdateNotice.message}
                        variant={desktopUpdateNotice.variant}
                        actionLabel={desktopUpdateNotice.actionLabel}
                        onAction={desktopUpdateNotice.actionLabel ? () => {
                          if (desktopUpdateNotice.actionKind === 'install') {
                            void installDesktopUpdate();
                            return;
                          }
                          void openDesktopReleasePage();
                        } : undefined}
                      />
                    ) : (
                      <p className="text-xs leading-6 text-muted-text">
                        {t('settings.desktopCurrentNoStatus')}
                      </p>
                    )}
                  </div>
                ) : null}
                {WEB_BUILD_INFO.isFallbackVersion ? (
                  <p className="text-xs leading-6 text-amber-700 dark:text-amber-300">
                    {t('settings.fallbackVersionWarning')}
                  </p>
                ) : null}
              </SettingsSectionCard>
            ) : null}
            {activeCategory === 'system' ? (
              <SettingsSectionCard
                title={t('settings.configBackup')}
                description={t('settings.configBackupDescription')}
              >
                <div className="space-y-4 rounded-xl border settings-border p-4">
                  {!isEnvBackupAllowed ? (
                    <p className="text-xs leading-6 text-amber-700 dark:text-amber-300">
                      {t('settings.disabledAuthBackupWarning')}
                    </p>
                  ) : null}
                  <div className="flex flex-wrap items-center gap-3">
                    <Button
                      type="button"
                      variant="settings-secondary"
                      onClick={() => void downloadEnvBackup()}
                      disabled={envBackupActionDisabled}
                      isLoading={isExportingEnv}
                      loadingText={t('settings.exportingEnv')}
                    >
                      {t('settings.exportEnv')}
                    </Button>
                    <Button
                      type="button"
                      variant="settings-primary"
                      onClick={beginEnvBackupImport}
                      disabled={envBackupActionDisabled}
                      isLoading={isImportingEnv}
                      loadingText={t('settings.importingEnv')}
                    >
                      {t('settings.importEnv')}
                    </Button>
                    <input
                      ref={envBackupImportRef}
                      type="file"
                      accept=".env,.txt"
                      className="hidden"
                      onChange={(event) => {
                        void handleEnvBackupImportFile(event);
                      }}
                    />
                  </div>
                  <p className="text-xs leading-6 text-muted-text">
                    {t('settings.envExportNote')}
                  </p>
                  <p className="text-xs leading-6 text-muted-text">
                    {t('settings.envDockerNote')}
                  </p>
                  {envBackupActionError ? (
                    <ApiErrorAlert
                      error={envBackupActionError}
                      actionLabel={envBackupActionError.status === 409 ? t('settings.reload') : undefined}
                      onAction={envBackupActionError.status === 409 ? () => void load() : undefined}
                    />
                  ) : null}
                  {!envBackupActionError && envBackupActionSuccess ? (
                    <SettingsAlert title={t('settings.actionSuccess')} message={envBackupActionSuccess} variant="success" />
                  ) : null}
                </div>
              </SettingsSectionCard>
            ) : null}
            {activeCategory === 'base' ? (
              <SettingsSectionCard
                title={t('settings.intelligentImport')}
                description={t('settings.intelligentImportDescription')}
                contentBordered
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
              </SettingsSectionCard>
            ) : null}
            {isAiOverview ? (
              <SettingsSectionCard
                title={t('settings.llmAccess')}
                description={t('settings.llmAccessDescription')}
                contentBordered
              >
                <AiOverviewMatrix
                  getValue={(key) => allValuesByKey[key.toUpperCase()] ?? ''}
                  language={uiLanguage}
                  onEditRouting={() => selectSectionView('ai_models', 'task_routing')}
                />
              </SettingsSectionCard>
            ) : null}
            {isAiTaskRouting ? (
              <SettingsSectionCard
                title={uiLanguage === 'en' ? 'Task routing' : '任务路由'}
                description={uiLanguage === 'en'
                  ? 'Choose the model for each task. Market review inherits the report model unless overridden.'
                  : '为每个任务选择模型。大盘复盘默认继承报告主模型，除非在此覆盖。'}
              >
                {taskRoutingItems.length > 0 ? (
                  <div className="overflow-hidden rounded-lg border border-[var(--settings-border)] bg-[var(--settings-surface)]">
                    {taskRoutingItems.map((item) => (
                      <SettingsField
                        key={item.key}
                        item={item}
                        value={item.value}
                        disabled={isSaving}
                        onChange={setDraftValue}
                        issues={issueByKey[item.key] || []}
                        requirement={resolveFieldRequirement(item.schema?.contract, allValuesByKey)}
                        dependencyLocked={!isFieldEnabledByContract(item.schema?.contract, allValuesByKey)}
                      />
                    ))}
                  </div>
                ) : (
                  <p className="text-xs text-muted-text">
                    {uiLanguage === 'en' ? 'No routing fields available.' : '暂无可配置的任务路由字段。'}
                  </p>
                )}
                <div className="mt-3 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-secondary-text">
                  <span>{uiLanguage === 'en' ? 'Fallback order: ' : '备选顺序：'}</span>
                  <span className="font-medium text-foreground">
                    {allValuesByKey.LITELLM_FALLBACK_MODELS
                      || (uiLanguage === 'en' ? 'none set' : '未设置')}
                  </span>
                  <button
                    type="button"
                    className="settings-accent-text underline-offset-2 hover:underline"
                    onClick={() => selectSectionView('ai_models', 'reliability')}
                  >
                    {uiLanguage === 'en' ? 'Edit in Reliability →' : '前往可靠性设置 →'}
                  </button>
                </div>
              </SettingsSectionCard>
            ) : null}
            {isAiReliability ? (
              <div className="space-y-4">
                <SettingsSectionCard
                  title={uiLanguage === 'en' ? 'Execution failover' : '执行后端故障切换'}
                  description={uiLanguage === 'en'
                    ? 'When the primary execution backend fails, requests switch to the failover backend. This is separate from model fallback.'
                    : '主执行后端失败时切换到备用执行后端。这与模型备选顺序是两个独立机制。'}
                >
                  <p className="mb-3 text-xs text-secondary-text">
                    {uiLanguage === 'en' ? 'Current path: ' : '当前路径：'}
                    <span className="font-medium text-foreground">{allValuesByKey.GENERATION_BACKEND || 'litellm'}</span>
                    {' → '}
                    <span className="font-medium text-foreground">
                      {allValuesByKey.GENERATION_FALLBACK_BACKEND
                        || (uiLanguage === 'en' ? 'none (no failover)' : '无（未配置切换）')}
                    </span>
                  </p>
                  {executionFailoverItems.length > 0 ? (
                    <div className="overflow-hidden rounded-lg border border-[var(--settings-border)] bg-[var(--settings-surface)]">
                      {executionFailoverItems.map((item) => (
                        <SettingsField
                          key={item.key}
                          item={item}
                          value={item.value}
                          disabled={isSaving}
                          onChange={setDraftValue}
                          issues={issueByKey[item.key] || []}
                          requirement={resolveFieldRequirement(item.schema?.contract, allValuesByKey)}
                          dependencyLocked={!isFieldEnabledByContract(item.schema?.contract, allValuesByKey)}
                        />
                      ))}
                    </div>
                  ) : null}
                </SettingsSectionCard>
                <SettingsSectionCard
                  title={uiLanguage === 'en' ? 'Model fallback order' : '模型备选顺序'}
                  description={uiLanguage === 'en'
                    ? 'Within LiteLLM, when the primary model call fails these models are tried in order. This is separate from execution failover.'
                    : '在 LiteLLM 内，主模型调用失败时按顺序尝试这些备选模型。这与执行后端切换是两个独立机制。'}
                >
                  <p className="mb-3 text-xs text-secondary-text">
                    {uiLanguage === 'en' ? 'Current order: ' : '当前顺序：'}
                    <span className="font-medium text-foreground">
                      {allValuesByKey.LITELLM_FALLBACK_MODELS
                        || (uiLanguage === 'en' ? 'none set' : '未设置')}
                    </span>
                  </p>
                  {modelFallbackItems.length > 0 ? (
                    <div className="overflow-hidden rounded-lg border border-[var(--settings-border)] bg-[var(--settings-surface)]">
                      {modelFallbackItems.map((item) => (
                        <SettingsField
                          key={item.key}
                          item={item}
                          value={item.value}
                          disabled={isSaving}
                          onChange={setDraftValue}
                          issues={issueByKey[item.key] || []}
                          requirement={resolveFieldRequirement(item.schema?.contract, allValuesByKey)}
                          dependencyLocked={!isFieldEnabledByContract(item.schema?.contract, allValuesByKey)}
                        />
                      ))}
                    </div>
                  ) : null}
                </SettingsSectionCard>
              </div>
            ) : null}
            {isTopLevelAdvanced ? (
              <SettingsSectionCard
                title={sectionLabel('advanced', uiLanguage)}
                description={uiLanguage === 'en'
                  ? 'Internal, low-level settings such as usage-signing secrets. Most users never need to change these.'
                  : '内部与底层配置，例如用量签名密钥。大多数用户无需改动。'}
              >
                {advancedSectionItems.length > 0 ? (
                  <div className="overflow-hidden rounded-lg border border-[var(--settings-border)] bg-[var(--settings-surface)]">
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
                      />
                    ))}
                  </div>
                ) : (
                  <p className="text-xs text-muted-text">
                    {uiLanguage === 'en' ? 'No advanced settings to configure.' : '暂无需要配置的高级项。'}
                  </p>
                )}
              </SettingsSectionCard>
            ) : null}
            {activeCategory === 'ai_model' && activeSubCategory === 'model' && !isAiOverview && !isAiTaskRouting && !isAiReliability ? (
              <SettingsSectionCard
                title={t('settings.llmAccess')}
                description={t('settings.llmAccessDescription')}
                contentBordered
              >
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
                <LLMChannelEditor
                  items={rawActiveItems}
                  maskToken={maskToken}
                  persistedDraftItems={llmChannelDraftItems}
                  onDraftItemsChange={handleLlmChannelDraftItemsChange}
                  onValidityChange={handleLlmChannelValidityChange}
                  resetSignal={llmChannelResetSignal}
                  disabled={isSaving || isLoading}
                  overriddenByMode={channelsOverriddenByMode}
                  showRuntimeConfig={false}
                />
              </SettingsSectionCard>
            ) : null}
            {activeCategory === 'system' && passwordChangeable ? (
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
            {isAlertsSection && eventMonitorItems.length > 0 ? (
              <SettingsSectionCard
                title={uiLanguage === 'en' ? 'Event Monitor' : '事件监控'}
                description={uiLanguage === 'en'
                  ? 'Poll for market events on a schedule and route alerts by rule. Lives here with the other alerting settings.'
                  : '按计划轮询市场事件并按规则触发告警。与其他告警设置一起集中在此。'}
              >
                <div className="overflow-hidden rounded-lg border border-[var(--settings-border)] bg-[var(--settings-surface)]">
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
                    />
                  ))}
                </div>
              </SettingsSectionCard>
            ) : null}
          </section>
        </div>
      )}

      {toast ? (
        <div className="fixed bottom-5 right-5 z-50 w-[320px] max-w-[calc(100vw-24px)]">
          {toast.type === 'success'
            ? (
                <SettingsAlert
                  title={t('settings.actionSuccess')}
                  message={toast.message}
                  variant="success"
                  presentation="toast"
                />
              )
            : <ApiErrorAlert error={toast.error} />}
        </div>
      ) : null}
      <ConfirmDialog
        isOpen={showImportConfirm}
        title={t('settings.importConfirmTitle')}
        message={t('settings.importConfirmMessage')}
        confirmText={t('settings.importConfirmContinue')}
        cancelText={t('common.cancel')}
        onConfirm={() => {
          setShowImportConfirm(false);
          envBackupImportRef.current?.click();
        }}
        onCancel={() => {
          setShowImportConfirm(false);
        }}
      />
      <ConfirmDialog
        isOpen={showResetConfirm}
        title={t('settings.resetConfirmTitle')}
        message={t('settings.resetConfirmMessage', { count: effectiveDirtyCount })}
        confirmText={t('settings.resetConfirmContinue')}
        cancelText={t('common.cancel')}
        onConfirm={() => {
          setShowResetConfirm(false);
          discardDraft();
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
      {isWizardOpen ? (
        <FirstRunWizard
          onComplete={handleWizardComplete}
          onClose={() => setIsWizardOpen(false)}
          isSaving={isSaving}
          language={uiLanguage}
        />
      ) : null}
    </div>
  );
};

export default SettingsPage;
