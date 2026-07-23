import type React from 'react';
import { useCallback, useEffect, useId, useMemo, useRef, useState } from 'react';
import {
  Activity,
  Bookmark,
  Building2,
  CheckCircle2,
  ChevronDown,
  CircleAlert,
  Clock3,
  Droplet,
  Factory,
  Flame,
  Gem,
  Landmark,
  Pickaxe,
  Plane,
  Play,
  PlusCircle,
  RefreshCw,
  Search,
  Shield,
  SlidersHorizontal,
  Stethoscope,
  Trees,
  Utensils,
  Wrench,
} from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import {
  alphasiftApi,
  type AlphaSiftCandidate,
  type AlphaSiftHotspotDetail,
  type AlphaSiftHotspot,
  type AlphaSiftHotspotsResponse,
  type AlphaSiftScreenResponse,
  type AlphaSiftScreenTaskStatus,
  type AlphaSiftStrategy,
} from '../api/alphasift';
import { formatParsedApiError, getParsedApiError, toApiErrorMessage, type ParsedApiError } from '../api/error';
import { AppPage, Button, DataTable, type DataTableColumn, InlineAlert, Input, Modal, Select, Surface } from '../components/common';
import { useUiLanguage } from '../contexts/UiLanguageContext';
import { formatUiText, type UiLanguage } from '../i18n/uiText';
import { SCREENING_TEXT } from '../locales/screening';
import { formatUiDateTime, formatUiNumber, getUiListSeparator } from '../utils/uiLocale';
import { formatTaskMessage } from '../utils/taskMessage';
import { getStrategyDisplay } from '../utils/strategyDisplay';
import { SCREEN_TASK_SESSION_STORAGE_KEY } from '../utils/sessionPersistence';

const SCREEN_TASK_POLL_INTERVAL_MS = 2000;

type PersistedScreenTask = {
  taskId: string;
  market: string;
  strategy: string;
  maxResults: number;
};

type ScreeningRunParameters = Omit<PersistedScreenTask, 'taskId'>;

const DEFAULT_SCREENING_RUN_PARAMETERS: ScreeningRunParameters = {
  market: 'cn',
  strategy: 'dual_low',
  maxResults: 3,
};

const readScreeningRunParameters = (
  restoredTask: PersistedScreenTask | null,
  search = typeof window === 'undefined' ? '' : window.location.search,
): ScreeningRunParameters => {
  if (restoredTask) {
    return {
      market: restoredTask.market,
      strategy: restoredTask.strategy,
      maxResults: restoredTask.maxResults,
    };
  }
  const params = new URLSearchParams(search);
  const count = Number(params.get('count'));
  const strategy = params.get('strategy')?.trim();
  return {
    market: params.get('market') === 'cn' ? 'cn' : DEFAULT_SCREENING_RUN_PARAMETERS.market,
    strategy: strategy || DEFAULT_SCREENING_RUN_PARAMETERS.strategy,
    maxResults: Number.isInteger(count) && count >= 1 && count <= 100
      ? count
      : DEFAULT_SCREENING_RUN_PARAMETERS.maxResults,
  };
};

const getScreeningRunParametersLocation = ({ market, strategy, maxResults }: ScreeningRunParameters) => {
  if (typeof window === 'undefined') return null;
  const url = new URL(window.location.href);
  const values: Record<string, string | undefined> = {
    market: market === DEFAULT_SCREENING_RUN_PARAMETERS.market ? undefined : market,
    strategy: strategy === DEFAULT_SCREENING_RUN_PARAMETERS.strategy ? undefined : strategy,
    count: maxResults === DEFAULT_SCREENING_RUN_PARAMETERS.maxResults ? undefined : String(maxResults),
  };
  Object.entries(values).forEach(([key, value]) => {
    if (value) url.searchParams.set(key, value);
    else url.searchParams.delete(key);
  });
  return `${url.pathname}${url.search}${url.hash}`;
};

const readPersistedScreenTask = (): PersistedScreenTask | null => {
  if (typeof window === 'undefined') {
    return null;
  }
  try {
    const raw = window.sessionStorage.getItem(SCREEN_TASK_SESSION_STORAGE_KEY);
    if (!raw) {
      return null;
    }
    const parsed = JSON.parse(raw) as Partial<PersistedScreenTask>;
    if (typeof parsed.taskId !== 'string' || !parsed.taskId.trim()) {
      return null;
    }
    const restoredMaxResults = Number(parsed.maxResults);
    return {
      taskId: parsed.taskId,
      market: typeof parsed.market === 'string' && parsed.market.trim() ? parsed.market : 'cn',
      strategy: typeof parsed.strategy === 'string' && parsed.strategy.trim() ? parsed.strategy : 'dual_low',
      maxResults: Number.isFinite(restoredMaxResults) ? Math.min(100, Math.max(1, restoredMaxResults)) : 3,
    };
  } catch {
    return null;
  }
};

const persistScreenTask = (task: PersistedScreenTask) => {
  try {
    window.sessionStorage.setItem(SCREEN_TASK_SESSION_STORAGE_KEY, JSON.stringify(task));
  } catch {
    // Session storage is best-effort; polling still works while the page stays mounted.
  }
};

const clearPersistedScreenTask = () => {
  try {
    window.sessionStorage.removeItem(SCREEN_TASK_SESSION_STORAGE_KEY);
  } catch {
    // Ignore storage cleanup failures.
  }
};

const isUnrecoverableScreenTaskError = (error: ParsedApiError) =>
  error.code === 'alphasift_screen_task_not_found';

type ScreeningText = (typeof SCREENING_TEXT)[UiLanguage];

const formatRecoverableScreenTaskPollingError = (error: ParsedApiError, text: ScreeningText) => {
  if (error.category === 'upstream_timeout') {
    return text.pollingTimeout;
  }
  if (error.category === 'upstream_network' || error.category === 'local_connection_failed') {
    return text.pollingNetwork;
  }
  return formatParsedApiError(error) || text.pollingFallback;
};

const formatScore = (score: AlphaSiftCandidate['score']) => {
  if (score == null || Number.isNaN(Number(score))) {
    return '-';
  }
  return Number(score).toFixed(2);
};

const formatNumber = (value: unknown, digits = 2) => {
  if (value == null || value === '' || Number.isNaN(Number(value))) {
    return '-';
  }
  return Number(value).toFixed(digits);
};

const formatAmount = (value: unknown, language: UiLanguage, text: ScreeningText) => {
  if (value == null || value === '' || Number.isNaN(Number(value))) {
    return '-';
  }
  const amount = Number(value);
  if (Math.abs(amount) >= 100_000_000) {
    return formatUiText(text.amountHundredMillion, { value: formatUiNumber(amount / 100_000_000, language, { maximumFractionDigits: 2 }) });
  }
  if (Math.abs(amount) >= 10_000) {
    return formatUiText(text.amountTenThousand, { value: formatUiNumber(amount / 10_000, language, { maximumFractionDigits: 2 }) });
  }
  return formatUiNumber(amount, language, { maximumFractionDigits: 2 });
};

const formatPercent = (value: unknown) => {
  if (value == null || value === '' || Number.isNaN(Number(value))) {
    return '-';
  }
  return `${(Number(value) * 100).toFixed(0)}%`;
};

const getCandidateDetailId = (item: AlphaSiftCandidate) => (
  `screening-candidate-${item.rank}-${item.code.replace(/[^a-zA-Z0-9_-]/g, '-')}-details`
);

const getCandidateReason = (item: AlphaSiftCandidate, text: ScreeningText) => {
  if (item.reason) {
    return item.reason;
  }
  const summaries = item.postAnalysisSummaries || {};
  const summary = Object.values(summaries).find((value) => typeof value === 'string' && value.trim());
  if (typeof summary === 'string') {
    return summary;
  }
  return text.noCandidateSummary;
};

const getSignal = (item: AlphaSiftCandidate, text: ScreeningText) => {
  const rawSignal = item.raw.action ?? item.raw.signal ?? item.raw.recommendation;
  return typeof rawSignal === 'string' && rawSignal.trim() ? rawSignal : text.observe;
};

const getFactorEntries = (item: AlphaSiftCandidate) =>
  Object.entries(item.factorScores || {})
    .filter(([, value]) => typeof value === 'number')
    .sort((a, b) => Number(b[1]) - Number(a[1]))
    .slice(0, 6);

const toMessageList = (values: string[] | undefined) =>
  Array.isArray(values) ? values.map((value) => String(value).trim()).filter(Boolean) : [];

const KNOWN_SNAPSHOT_SOURCES = new Set(['tushare', 'efinance', 'akshare_em', 'em_datacenter', 'baostock']);
const MAX_MESSAGE_DETAIL_LENGTH = 96;

const truncateMessageDetail = (value: string, maxLength = MAX_MESSAGE_DETAIL_LENGTH) => {
  const text = value.replace(/\s+/g, ' ').trim();
  if (text.length <= maxLength) {
    return text;
  }
  return `${text.slice(0, maxLength - 1)}…`;
};

const formatStableAlphaSiftDiagnostic = (value: string, text: ScreeningText) => {
  const messages: Record<string, string> = {
    alphasift_warning: text.diagnosticWarning,
    alphasift_error: text.diagnosticInternal,
    alphasift_source_error: text.diagnosticSourceUnavailable,
    alphasift_llm_parse_error: text.diagnosticLlmParse,
    alphasift_internal_error: text.diagnosticInternal,
    alphasift_hotspot_refresh_failed: text.hotspotLoadFailed,
    alphasift_hotspot_source_error: text.diagnosticSourceUnavailable,
    alphasift_hotspot_direct_fallback_failed: text.hotspotLoadFailed,
    alphasift_hotspot_direct_fallback_used: text.cacheFallback,
    alphasift_hotspot_detail_prefetch_failed: text.hotspotDetailLoadFailed,
    alphasift_hotspot_detail_stale_cache: text.cacheFallback,
    alphasift_hotspot_detail_fallback: text.cacheFallback,
    alphasift_hotspot_detail_source_error: text.diagnosticSourceUnavailable,
    eastmoney_hotspot_unavailable: text.diagnosticNetwork,
    dsa_candidate_enrichment_failed: text.diagnosticWarning,
    dsa_stock_name_failed: text.diagnosticSourceUnavailable,
    dsa_realtime_quote_missing: text.diagnosticEmpty,
    dsa_realtime_quote_failed: text.diagnosticSourceUnavailable,
    dsa_fundamental_context_failed: text.diagnosticSourceUnavailable,
    dsa_search_unavailable: text.diagnosticSourceUnavailable,
    stock_news_unavailable: text.diagnosticSourceUnavailable,
    stock_news_failed: text.diagnosticSourceUnavailable,
  };
  return messages[value] || '';
};

const summarizeAlphaSiftDiagnostic = (detail: string, text: ScreeningText) => {
  const stableMessage = formatStableAlphaSiftDiagnostic(detail, text);
  if (stableMessage) {
    return stableMessage;
  }
  if (/trade_cal returned no open trading days/i.test(detail)) {
    return text.diagnosticCalendar;
  }
  if (/too many requests|rate limit|http\s*429/i.test(detail)) {
    return text.diagnosticRateLimit;
  }
  if (/403 forbidden|forbidden|access denied/i.test(detail)) {
    return text.diagnosticForbidden;
  }
  if (/timeout|timed out/i.test(detail)) {
    return text.diagnosticTimeout;
  }
  if (/RemoteDisconnected|Connection aborted|ProtocolError|ConnectionPool|Max retries exceeded|ProxyError|NameResolutionError/i.test(detail)) {
    return text.diagnosticNetwork;
  }
  if (/missing .*api key|GEMINI_API_KEY|GOOGLE_API_KEY|gemini_api_key/i.test(detail)) {
    return text.diagnosticMissingKey;
  }
  if (/returned no data|empty/i.test(detail)) {
    return text.diagnosticEmpty;
  }

  const withoutUrl = detail
    .replace(/https?:\/\/\S+/gi, 'URL')
    .replace(/\bwith url:\s*\S+/gi, 'with url: URL')
    .replace(/\burl:\s*\S+/gi, 'url: URL');
  return truncateMessageDetail(withoutUrl);
};

const parseSourceDiagnostic = (value: string) => {
  const match = value.match(/^([a-zA-Z0-9_-]+)\s*[:：]\s*(.+)$/);
  if (!match) {
    return null;
  }
  return {
    source: match[1],
    detail: match[2],
  };
};

const normalizeScreenMessageKey = (value: string, text: ScreeningText) => {
  const formatted = formatScreenMessage(value, text);
  return formatted ? formatted.trim().toLowerCase() : value.trim().toLowerCase();
};

const formatScreenMessage = (value: string, text: ScreeningText) => {
  const stableMessage = formatStableAlphaSiftDiagnostic(value, text);
  if (stableMessage) {
    return stableMessage;
  }
  if (/^DSA provider context applied \d+ of \d+ candidates/i.test(value)) {
    return '';
  }
  if (/^LLM ranking failed/i.test(value)) {
    return formatUiText(text.llmRankingFallback, { detail: summarizeAlphaSiftDiagnostic(value, text) });
  }

  const snapshotFallback = value.match(/^Snapshot source fallback:\s*(.+)$/i);
  if (snapshotFallback) {
    const parsed = parseSourceDiagnostic(snapshotFallback[1]);
    if (parsed) {
      return formatUiText(text.sourceFallbackNamed, { source: parsed.source, detail: summarizeAlphaSiftDiagnostic(parsed.detail, text) });
    }
    return formatUiText(text.sourceFallback, { detail: summarizeAlphaSiftDiagnostic(snapshotFallback[1], text) });
  }

  const parsed = parseSourceDiagnostic(value);
  if (parsed && KNOWN_SNAPSHOT_SOURCES.has(parsed.source.toLowerCase())) {
    return formatUiText(text.sourceFallbackNamed, { source: parsed.source, detail: summarizeAlphaSiftDiagnostic(parsed.detail, text) });
  }
  return truncateMessageDetail(value);
};

const getScreenMessages = (meta: AlphaSiftScreenResponse | null, text: ScreeningText) => {
  if (!meta) {
    return [];
  }
  const messages: string[] = [];
  const seen = new Set<string>();
  [...toMessageList(meta.warnings), ...toMessageList(meta.sourceErrors), ...toMessageList(meta.llmParseErrors)].forEach(
    (value) => {
      const key = normalizeScreenMessageKey(value, text);
      if (seen.has(key)) {
        return;
      }
      const message = formatScreenMessage(value, text);
      if (!message) {
        return;
      }
      seen.add(key);
      messages.push(message);
    },
  );
  return messages;
};

const isRunningScreenTask = (status: string | undefined | null) => status === 'pending' || status === 'processing';

const ALPHASIFT_HOTSPOT_NO_CACHE_HINT = 'No cached AlphaSift hotspot snapshot. Click refresh to fetch live hotspots.';
const ALPHASIFT_HOTSPOT_UNAVAILABLE_CODE = 'eastmoney_hotspot_unavailable';

const formatHotspotEmptyMessage = (result: AlphaSiftHotspotsResponse, text: ScreeningText) => {
  const message = String(result.message || '').trim();
  const sourceErrors = result.sourceErrors || [];
  if (message && sourceErrors.includes(ALPHASIFT_HOTSPOT_UNAVAILABLE_CODE)) {
    return message;
  }
  if (message === ALPHASIFT_HOTSPOT_NO_CACHE_HINT) {
    return text.noCachedHotspots;
  }
  const sourceError = sourceErrors[0];
  if (sourceError) {
    return formatUiText(text.hotspotUnavailableDetail, { detail: summarizeAlphaSiftDiagnostic(sourceError, text) });
  }
  return text.hotspotUnavailable;
};

const ScreenAlertMessage: React.FC<{ messages: string[] }> = ({ messages }) => {
  if (messages.length <= 1) {
    return <span>{messages[0]}</span>;
  }
  return (
    <ul className="list-disc space-y-1 pl-4">
      {messages.map((message) => (
        <li key={message}>{message}</li>
      ))}
    </ul>
  );
};

const hasLlmInsight = (item: AlphaSiftCandidate) =>
  Boolean(
    item.llmThesis ||
      item.llmSector ||
      item.llmTheme ||
      item.llmConfidence != null ||
      item.llmWatchItems?.length ||
      item.llmCatalysts?.length,
  );

const getRouteTimeLabel = (item: AlphaSiftHotspotDetail['route'][number], language: UiLanguage, text: ScreeningText) => {
  const rawTime = item.publishedAt || item.date || item.time || '';
  if (!rawTime) {
    return item.source || text.pendingConfirmation;
  }
  if (/^\d{4}-\d{2}-\d{2}$/.test(rawTime)) {
    return rawTime;
  }
  const parsed = new Date(rawTime);
  if (!Number.isNaN(parsed.getTime())) {
    return formatUiDateTime(parsed, language, {
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      hour12: false,
    });
  }
  return rawTime;
};

const getHotspotRouteItems = (detail: AlphaSiftHotspotDetail) => {
  const route = detail.route || [];
  if (route.length > 0) {
    return route;
  }
  return detail.timeline || [];
};

const formatHotspotMetric = (value: unknown, text: ScreeningText, digits = 1) => {
  const formatted = formatNumber(value, digits);
  return formatted === '-' ? text.observing : formatted;
};

const getHotspotLeadersText = (item: AlphaSiftHotspot, language: UiLanguage, text: ScreeningText) => {
  const leaders = (item.leaders || []).map((value) => String(value).trim()).filter(Boolean);
  if (leaders.length > 0) {
    return leaders.slice(0, 2).join(getUiListSeparator(language));
  }
  return text.observing;
};

const getHotspotSampleText = (item: AlphaSiftHotspot, text: ScreeningText) => {
  if (item.sampleStockCount == null || Number.isNaN(Number(item.sampleStockCount))) {
    return text.activeStocksObserving;
  }
  return formatUiText(text.stockCoverage, { count: item.sampleStockCount });
};

const formatStockChangeText = (value: unknown, text: ScreeningText) => {
  const formatted = formatNumber(value);
  return formatted === '-' ? text.quotePending : `${formatted}%`;
};

const formatHotspotUpdatedAt = (value: string | null, language: UiLanguage, text: ScreeningText) => {
  if (!value) {
    return text.refreshPending;
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  return formatUiDateTime(parsed, language, {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  });
};

const getHotspotStrength = (item: AlphaSiftHotspot, index: number, text: ScreeningText) => {
  const heat = Number(item.heatScore ?? 0);
  const changePct = Number(item.changePct ?? 0);
  if (index === 0 || heat >= 90 || changePct >= 8) {
    return { label: text.strengthLeading, className: 'bg-red-500/10 text-red-500' };
  }
  if (heat >= 80 || changePct >= 5) {
    return { label: text.strengthStrong, className: 'bg-blue-500/10 text-blue-500' };
  }
  return { label: text.strengthFirm, className: 'bg-primary/10 text-primary' };
};

const HOTSPOT_ICON_RULES: Array<{
  pattern: RegExp;
  icon: React.ComponentType<{ className?: string }>;
  className: string;
}> = [
  { pattern: /金|银|铜|铝|铅|锌|钼|钴|镍|贵金属|矿|有色/, icon: Pickaxe, className: 'bg-orange-500/10 text-orange-500' },
  { pattern: /黄金|珠宝/, icon: Gem, className: 'bg-amber-500/10 text-amber-500' },
  { pattern: /油|气|能源|煤/, icon: Droplet, className: 'bg-yellow-700/10 text-yellow-700' },
  { pattern: /金融|券商|银行|保险|资本/, icon: Landmark, className: 'bg-orange-500/10 text-orange-500' },
  { pattern: /航空|机场|航天|运输/, icon: Plane, className: 'bg-blue-500/10 text-blue-500' },
  { pattern: /林业|农业|种植/, icon: Trees, className: 'bg-emerald-500/10 text-emerald-500' },
  { pattern: /医疗|诊断|卫生|医药/, icon: Stethoscope, className: 'bg-teal-500/10 text-teal-500' },
  { pattern: /食品|餐饮|酒/, icon: Utensils, className: 'bg-violet-500/10 text-violet-500' },
  { pattern: /工业|制造|修理|机械|设备/, icon: Wrench, className: 'bg-blue-500/10 text-blue-500' },
  { pattern: /租赁|地产|建筑/, icon: Building2, className: 'bg-emerald-500/10 text-emerald-500' },
  { pattern: /电|芯片|算力|AI|机器人/, icon: Factory, className: 'bg-indigo-500/10 text-indigo-500' },
  { pattern: /保险|安全/, icon: Shield, className: 'bg-blue-500/10 text-blue-500' },
];

const getHotspotIcon = (topic: string) => {
  const match = HOTSPOT_ICON_RULES.find((rule) => rule.pattern.test(topic));
  return match || { icon: Activity, className: 'bg-primary/10 text-primary' };
};

const MiniSparkline: React.FC<{ score?: number | null; selected?: boolean }> = ({ score, selected }) => {
  const normalizedScore = Number.isFinite(Number(score)) ? Math.max(0, Math.min(100, Number(score))) : 65;
  const lift = Math.max(0, Math.min(16, normalizedScore / 7));
  const path = `M2 35 C12 ${32 - lift / 4}, 16 ${34 - lift / 2}, 24 ${28 - lift / 3} S38 ${29 - lift}, 46 ${23 - lift / 2} S62 ${24 - lift}, 72 ${16 - lift / 3} S86 ${15 - lift}, 94 ${7}`;
  return (
    <svg className="h-8 w-20" viewBox="0 0 96 40" aria-hidden="true">
      <path d={`${path} L94 40 L2 40 Z`} fill={selected ? 'hsl(var(--warning) / 0.14)' : 'hsl(var(--primary) / 0.12)'} />
      <path d={path} fill="none" stroke={selected ? 'hsl(var(--warning))' : 'hsl(var(--primary))'} strokeLinecap="round" strokeWidth="2" />
    </svg>
  );
};

const StockScreeningPage: React.FC = () => {
  const navigate = useNavigate();
  const syncScreeningRunParameters = useCallback((parameters: ScreeningRunParameters) => {
    const location = getScreeningRunParametersLocation(parameters);
    if (location) navigate(location, { replace: true });
  }, [navigate]);
  const { language, t } = useUiLanguage();
  const configurationFormId = useId();
  const text = SCREENING_TEXT[language];
  const markets = useMemo(() => [{ id: 'cn', label: text.marketCn }], [text.marketCn]);
  const [restoredTask] = useState<PersistedScreenTask | null>(() => readPersistedScreenTask());
  const [initialRunParameters] = useState<ScreeningRunParameters>(() => readScreeningRunParameters(restoredTask));
  const [statusLoading, setStatusLoading] = useState(true);
  const [enabled, setEnabled] = useState(false);
  const [available, setAvailable] = useState(false);
  const [market, setMarket] = useState(initialRunParameters.market);
  const [strategy, setStrategy] = useState(initialRunParameters.strategy);
  const [strategies, setStrategies] = useState<AlphaSiftStrategy[]>([]);
  const [maxResults, setMaxResults] = useState(initialRunParameters.maxResults);
  const [maxResultsDraft, setMaxResultsDraft] = useState(String(initialRunParameters.maxResults));
  const [maxResultsError, setMaxResultsError] = useState('');
  const [configurationOpen, setConfigurationOpen] = useState(false);
  const [configurationError, setConfigurationError] = useState('');
  const [candidates, setCandidates] = useState<AlphaSiftCandidate[]>([]);
  const [hotspots, setHotspots] = useState<AlphaSiftHotspot[]>([]);
  const [hotspotsUpdatedAt, setHotspotsUpdatedAt] = useState<string | null>(null);
  const [hotspotsExpanded, setHotspotsExpanded] = useState(false);
  const [selectedHotspotTopic, setSelectedHotspotTopic] = useState<string | null>(null);
  const selectedHotspotTopicRef = useRef<string | null>(null);
  const strategiesRequestIdRef = useRef(0);
  const hotspotsRequestIdRef = useRef(0);
  const hotspotDetailRequestIdRef = useRef(0);
  const mountedRef = useRef(true);
  const hotspotDetailsByTopicRef = useRef<Record<string, AlphaSiftHotspotDetail>>({});
  const [hotspotDetail, setHotspotDetail] = useState<AlphaSiftHotspotDetail | null>(null);
  const [loadingHotspotDetail, setLoadingHotspotDetail] = useState(false);
  const [hotspotDetailError, setHotspotDetailError] = useState('');
  const [loadingHotspots, setLoadingHotspots] = useState(false);
  const [hotspotError, setHotspotError] = useState('');
  const [screenMeta, setScreenMeta] = useState<AlphaSiftScreenResponse | null>(null);
  const [expandedCode, setExpandedCode] = useState<string | null>(null);
  const [loading, setLoading] = useState(Boolean(restoredTask?.taskId));
  const [enabling, setEnabling] = useState(false);
  const [loadingStrategies, setLoadingStrategies] = useState(false);
  const [error, setError] = useState('');
  const [strategyLoadError, setStrategyLoadError] = useState('');
  const [activeTaskId, setActiveTaskId] = useState<string | null>(restoredTask?.taskId ?? null);
  const [taskProgress, setTaskProgress] = useState(restoredTask?.taskId ? 10 : 0);
  const [taskMessage, setTaskMessage] = useState(restoredTask?.taskId ? text.restoringTask : '');

  const selectedStrategy = useMemo(() => strategies.find((item) => item.id === strategy), [strategies, strategy]);
  const selectedStrategyDisplay = useMemo(
    () => selectedStrategy ? getStrategyDisplay(selectedStrategy, language) : null,
    [language, selectedStrategy],
  );
  const selectedStrategyTag = selectedStrategyDisplay?.category || text.custom;
  const displayedStrategy = selectedStrategyDisplay?.name ?? `${text.customStrategy} (${strategy})`;
  const screenMessages = useMemo(() => getScreenMessages(screenMeta, text), [screenMeta, text]);
  const llmDegraded = screenMeta?.llmRanked === false;
  const alertMessages = llmDegraded
    ? screenMessages.length > 0
      ? screenMessages
      : [text.localRankingNotice]
    : screenMessages;
  const isScreeningEnabled = enabled && available;
  const statusText = statusLoading ? text.statusLoading : isScreeningEnabled ? text.enabled : text.disabled;

  useEffect(() => {
    document.title = text.documentTitle;
  }, [text.documentTitle]);

  useEffect(() => {
    syncScreeningRunParameters({ market, strategy, maxResults });
  }, [market, maxResults, strategy, syncScreeningRunParameters]);

  const applyScreenResult = useCallback((result: AlphaSiftScreenResponse) => {
    const nextCandidates = result.candidates || [];
    setScreenMeta(result);
    setCandidates(nextCandidates);
    setExpandedCode(nextCandidates[0]?.code ?? null);
  }, []);

  const clearScreeningResults = () => {
    setCandidates([]);
    setScreenMeta(null);
    setExpandedCode(null);
  };

  const loadHotspotDetail = useCallback(async (topic: string, options: { refresh?: boolean } = {}) => {
    if (!topic) {
      return;
    }
    const cachedDetail = !options.refresh ? hotspotDetailsByTopicRef.current[topic] : null;
    if (cachedDetail) {
      setHotspotDetail(cachedDetail);
      setHotspotDetailError('');
      setLoadingHotspotDetail(false);
      return;
    }
    const requestId = hotspotDetailRequestIdRef.current + 1;
    hotspotDetailRequestIdRef.current = requestId;
    const isCurrentRequest = () => hotspotDetailRequestIdRef.current === requestId;
    const canApplyRequest = () => isCurrentRequest() && selectedHotspotTopicRef.current === topic;
    setLoadingHotspotDetail(true);
    setHotspotDetail((currentDetail) => (currentDetail?.topic === topic ? currentDetail : null));
    setHotspotDetailError('');
    try {
      const detail = await alphasiftApi.getHotspotDetail({ topic, provider: 'akshare', refresh: options.refresh ?? false });
      if (!canApplyRequest()) {
        return;
      }
      hotspotDetailsByTopicRef.current = {
        ...hotspotDetailsByTopicRef.current,
        [topic]: detail,
      };
      setHotspotDetail(detail);
    } catch (err) {
      if (!canApplyRequest()) {
        return;
      }
      setHotspotDetail(null);
      setHotspotDetailError(toApiErrorMessage(err, text.hotspotDetailLoadFailed, language));
    } finally {
      if (isCurrentRequest()) {
        setLoadingHotspotDetail(false);
      }
    }
  }, [language, text.hotspotDetailLoadFailed]);

  const loadStrategies = useCallback(async () => {
    const requestId = strategiesRequestIdRef.current + 1;
    strategiesRequestIdRef.current = requestId;
    const isLatestRequest = () => strategiesRequestIdRef.current === requestId;
    setLoadingStrategies(true);
    setStrategyLoadError('');
    try {
      const result = await alphasiftApi.getStrategies();
      if (!isLatestRequest()) return;
      const loadedStrategies = result.strategies || [];
      setStrategies(loadedStrategies);
      if (loadedStrategies.length > 0) {
        setStrategy((currentStrategy) =>
          loadedStrategies.some((item) => item.id === currentStrategy) ? currentStrategy : loadedStrategies[0].id,
        );
      }
    } catch (err) {
      if (!isLatestRequest()) return;
      setStrategyLoadError(getParsedApiError(err, language).message || text.strategyLoadFailed);
    } finally {
      if (isLatestRequest()) setLoadingStrategies(false);
    }
  }, [language, text.strategyLoadFailed]);

  const loadHotspots = useCallback(async (refresh = false) => {
    const requestId = hotspotsRequestIdRef.current + 1;
    hotspotsRequestIdRef.current = requestId;
    const isLatestRequest = () => hotspotsRequestIdRef.current === requestId;
    setLoadingHotspots(true);
    setHotspotError('');
    try {
      const result = await alphasiftApi.getHotspots({ provider: 'akshare', top: 12, refresh });
      if (!isLatestRequest()) return;
      const nextHotspots = result.hotspots || [];
      const nextDetails = result.details || {};
      hotspotDetailsByTopicRef.current = {
        ...hotspotDetailsByTopicRef.current,
        ...nextDetails,
      };
      const currentTopic = selectedHotspotTopicRef.current;
      const retainedTopic = Boolean(currentTopic && nextHotspots.some((item) => item.topic === currentTopic));
      const nextTopic = retainedTopic ? currentTopic : null;
      setHotspots(nextHotspots);
      setHotspotsUpdatedAt(result.cachedAt || (nextHotspots.length > 0 ? new Date().toISOString() : null));
      setSelectedHotspotTopic(nextTopic);
      selectedHotspotTopicRef.current = nextTopic;
      if (nextTopic && nextDetails[nextTopic]) {
        setHotspotDetail(nextDetails[nextTopic]);
        setLoadingHotspotDetail(false);
      } else if (retainedTopic && refresh && nextTopic) {
        void loadHotspotDetail(nextTopic, { refresh: true });
      } else if (!retainedTopic) {
        setHotspotDetail(null);
      }
      setHotspotDetailError('');
      if (nextHotspots.length === 0) {
        setHotspotError(formatHotspotEmptyMessage(result, text));
      }
    } catch (err) {
      if (!isLatestRequest()) return;
      setHotspotError(toApiErrorMessage(err, text.hotspotLoadFailed, language));
    } finally {
      if (isLatestRequest()) setLoadingHotspots(false);
    }
  }, [language, loadHotspotDetail, text]);

  const handleHotspotSelect = useCallback((topic: string) => {
    selectedHotspotTopicRef.current = topic;
    setSelectedHotspotTopic(topic);
    const cachedDetail = hotspotDetailsByTopicRef.current[topic];
    if (cachedDetail) {
      setHotspotDetail(cachedDetail);
      setHotspotDetailError('');
      setLoadingHotspotDetail(false);
    } else {
      setHotspotDetail((currentDetail) => (currentDetail?.topic === topic ? currentDetail : null));
    }
  }, []);

  const toggleHotspotsExpanded = useCallback(() => {
    setHotspotsExpanded((expanded) => {
      const nextExpanded = !expanded;
      if (!nextExpanded) {
        selectedHotspotTopicRef.current = null;
        setSelectedHotspotTopic(null);
        setHotspotDetail(null);
        setHotspotDetailError('');
      }
      return nextExpanded;
    });
  }, []);

  const handleAnalyzeHotspotStock = useCallback((stock: AlphaSiftHotspotDetail['stocks'][number]) => {
    const stockCode = String(stock.code || '').trim();
    if (!stockCode) {
      return;
    }
    const stockName = String(stock.name || stockCode).trim();
    navigate('/', {
      state: {
        stockCode,
        stockName,
        autoAnalyze: true,
        selectionSource: 'alphasift_hotspot',
      },
    });
  }, [navigate]);

  useEffect(() => {
    selectedHotspotTopicRef.current = selectedHotspotTopic;
  }, [selectedHotspotTopic]);

  useEffect(() => {
    if (!selectedHotspotTopic) {
      return;
    }
    void loadHotspotDetail(selectedHotspotTopic);
  }, [loadHotspotDetail, selectedHotspotTopic]);

  useEffect(() => {
    let active = true;
    alphasiftApi
      .getStatus()
      .then((status) => {
        if (!active) {
          return;
        }
        setEnabled(status.enabled);
        setAvailable(status.available);
        setStatusLoading(false);
        if (status.enabled && status.available) {
          void loadStrategies();
          void loadHotspots(false);
        }
      })
      .catch(() => {
        if (active) {
          setEnabled(false);
          setAvailable(false);
          setStatusLoading(false);
        }
      });
    return () => {
      active = false;
    };
  }, [loadHotspots, loadStrategies]);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      strategiesRequestIdRef.current += 1;
      hotspotsRequestIdRef.current += 1;
      hotspotDetailRequestIdRef.current += 1;
    };
  }, []);

  useEffect(() => {
    if (!activeTaskId) {
      return undefined;
    }

    const pollingTaskId = activeTaskId;
    let active = true;
    let timer: number | undefined;

    function finishTask() {
      clearPersistedScreenTask();
      setActiveTaskId(null);
      setLoading(false);
    }

    function applyTaskStatus(task: AlphaSiftScreenTaskStatus) {
      const nextProgress = Number(task.progress ?? 0);
      setTaskProgress(Number.isFinite(nextProgress) ? nextProgress : 0);
      setTaskMessage(formatTaskMessage(task, language));

      if (task.status === 'completed') {
        if (task.result) {
          applyScreenResult(task.result);
          setError('');
        } else {
          setError(text.noTaskResults);
          setCandidates([]);
          setScreenMeta(null);
        }
        finishTask();
        return;
      }

      if (task.status === 'failed') {
        setCandidates([]);
        setScreenMeta(null);
        setExpandedCode(null);
        setError(getParsedApiError({
          error: 'alphasift_screen_failed',
          message: task.error || task.message || 'Screening failed',
          trace_id: task.traceId,
        }, language).message);
        finishTask();
        return;
      }

      if (isRunningScreenTask(task.status)) {
        setLoading(true);
        timer = window.setTimeout(pollTask, SCREEN_TASK_POLL_INTERVAL_MS);
        return;
      }

      setError(formatUiText(text.unknownTaskStatus, { status: task.status || 'unknown' }));
      finishTask();
    }

    async function pollTask() {
      try {
        const task = await alphasiftApi.getScreenTask(pollingTaskId);
        if (!active) {
          return;
        }
        applyTaskStatus(task);
      } catch (err) {
        if (!active) {
          return;
        }
        const parsedError = getParsedApiError(err, language);
        if (isUnrecoverableScreenTaskError(parsedError)) {
          setError(formatParsedApiError(parsedError) || text.taskUnrecoverable);
          setCandidates([]);
          setScreenMeta(null);
          finishTask();
          return;
        }
        setError(formatRecoverableScreenTaskPollingError(parsedError, text));
        setLoading(true);
        timer = window.setTimeout(pollTask, SCREEN_TASK_POLL_INTERVAL_MS);
      }
    }

    void pollTask();

    return () => {
      active = false;
      if (timer) {
        window.clearTimeout(timer);
      }
    };
  }, [activeTaskId, applyScreenResult, language, text]);

  const handleEnable = async () => {
    setEnabling(true);
    setError('');
    try {
      await alphasiftApi.enable();
      if (!mountedRef.current) return;
      setEnabled(true);
      setAvailable(true);
      setStatusLoading(false);
      await loadStrategies();
    } catch (err) {
      try {
        const status = await alphasiftApi.getStatus();
        if (!mountedRef.current) return;
        setEnabled(status.enabled);
        setAvailable(status.available);
        setStatusLoading(false);
      } catch {
        if (!mountedRef.current) return;
        setEnabled(false);
        setAvailable(false);
        setStatusLoading(false);
      }
      if (mountedRef.current) setError(getParsedApiError(err, language).message || text.enableFailed);
    } finally {
      if (mountedRef.current) setEnabling(false);
    }
  };

  const handleStrategyChange = (nextStrategy: string) => {
    if (nextStrategy !== strategy) {
      clearScreeningResults();
    }
    setStrategy(nextStrategy);
  };

  const handleMarketChange = (nextMarket: string) => {
    if (nextMarket !== market) {
      clearScreeningResults();
    }
    setMarket(nextMarket);
  };

  const handleMaxResultsChange = (nextMaxResults: string) => {
    if (nextMaxResults !== String(maxResults)) {
      clearScreeningResults();
    }
    setMaxResultsDraft(nextMaxResults);
    setMaxResultsError('');
  };

  const handleOpenConfiguration = () => {
    setConfigurationError('');
    setConfigurationOpen(true);
  };

  const handleSubmit = async (): Promise<boolean> => {
    const parsedMaxResults = Number(maxResultsDraft);
    if (!Number.isInteger(parsedMaxResults) || parsedMaxResults < 1 || parsedMaxResults > 100) {
      setMaxResultsError(text.resultCountError);
      document.getElementById('screening-max-results')?.focus();
      return false;
    }
    setMaxResults(parsedMaxResults);
    setMaxResultsError('');
    setConfigurationError('');
    setLoading(true);
    setError('');
    setScreenMeta(null);
    setTaskProgress(0);
    setTaskMessage(text.submittingTask);
    try {
      const task = await alphasiftApi.startScreen({ market, strategy, maxResults: parsedMaxResults });
      if (!mountedRef.current) return false;
      persistScreenTask({
        taskId: task.taskId,
        market,
        strategy,
        maxResults: parsedMaxResults,
      });
      setActiveTaskId(task.taskId);
      setTaskProgress(0);
      setTaskMessage(formatTaskMessage(task, language));
      return true;
    } catch (err) {
      if (mountedRef.current) {
        const message = toApiErrorMessage(err, text.taskSubmitFailed, language);
        setCandidates([]);
        setLoading(false);
        setConfigurationError(message);
        setError(message);
      }
      return false;
    }
  };

  const handleConfigurationSubmit = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    event.stopPropagation();
    if (!isScreeningEnabled || loading) return;
    void handleSubmit().then((started) => {
      if (started) setConfigurationOpen(false);
    });
  };

  const candidateColumns = useMemo<DataTableColumn<AlphaSiftCandidate>[]>(() => [
    {
      id: 'rank',
      header: '#',
      width: 'compact',
      nowrap: true,
      cell: (item) => item.rank,
    },
    {
      id: 'code',
      header: text.code,
      rowHeader: true,
      nowrap: true,
      cell: (item) => <span className="font-mono font-semibold text-foreground">{item.code}</span>,
    },
    {
      id: 'name',
      header: text.name,
      cell: (item) => <span className="font-semibold text-foreground">{item.name || '-'}</span>,
    },
    {
      id: 'industry',
      header: text.industry,
      cell: (item) => item.industry || '-',
    },
    {
      id: 'price',
      header: text.price,
      nowrap: true,
      cell: (item) => formatNumber(item.price),
    },
    {
      id: 'change',
      header: text.change,
      nowrap: true,
      cell: (item) => `${formatNumber(item.changePct)}%`,
    },
    {
      id: 'score',
      header: text.score,
      nowrap: true,
      cell: (item) => <span className="font-bold text-primary">{formatScore(item.score)}</span>,
    },
    {
      id: 'llm',
      header: <span>LLM</span>,
      nowrap: true,
      cell: (item) => llmDegraded ? text.notReranked : formatScore(item.llmScore),
    },
    {
      id: 'risk',
      header: text.risk,
      nowrap: true,
      cell: (item) => (
        <span className="rounded-lg bg-success/10 px-2.5 py-1 text-xs font-semibold text-success">
          {item.riskLevel || text.unknown}
        </span>
      ),
    },
    {
      id: 'details',
      header: text.details,
      nowrap: true,
      cell: (item) => {
        const expanded = expandedCode === item.code;
        return (
          <Button
            type="button"
            variant="ghost"
            size="default"
            aria-expanded={expanded}
            aria-controls={getCandidateDetailId(item)}
            onClick={() => setExpandedCode(expanded ? null : item.code)}
          >
            {expanded ? text.collapse : text.expand}
          </Button>
        );
      },
    },
  ], [expandedCode, llmDegraded, text]);

  const renderCandidateDetail = useCallback((item: AlphaSiftCandidate) => {
    const factors = getFactorEntries(item);
    const llmInsightAvailable = hasLlmInsight(item);
    const llmFallbackText = llmDegraded && !llmInsightAvailable
      ? text.llmFallbackRow
      : text.noLlmJudgement;
    const dsaWarnings = item.dsaContext?.warnings || [];
    const dsaNews = item.dsaNews || [];
    return (
      <div className="grid gap-4 lg:grid-cols-[1.1fr_1fr]">
        <div className="space-y-3">
          <div>
            <p className="text-xs font-semibold text-secondary-text">{text.summary}</p>
            <p className="mt-1 text-sm leading-6 text-foreground">{getCandidateReason(item, text)}</p>
          </div>
          <div>
            <p className="text-xs font-semibold text-secondary-text">{text.signal}</p>
            <p className="mt-1 text-sm text-foreground">{getSignal(item, text)}</p>
          </div>
          {item.dsaAnalysisSummary ? (
            <div>
              <p className="text-xs font-semibold text-secondary-text">{text.dsaSummary}</p>
              <p className="mt-1 text-sm leading-6 text-foreground">{item.dsaAnalysisSummary}</p>
            </div>
          ) : null}
          <div>
            <p className="text-xs font-semibold text-secondary-text">{text.llmJudgement}</p>
            <p className="mt-1 text-sm leading-6 text-foreground">
              {item.llmThesis || llmFallbackText}
            </p>
            {llmInsightAvailable ? (
              <p className="mt-1 text-xs text-secondary-text">
                {formatUiText(text.sectorThemeConfidence, { sector: item.llmSector || '-', theme: item.llmTheme || '-', confidence: formatPercent(item.llmConfidence) })}
              </p>
            ) : (
              <p className="mt-1 text-xs text-secondary-text">{text.noLlmMetadata}</p>
            )}
          </div>
          <div>
            <p className="text-xs font-semibold text-secondary-text">{text.riskTags}</p>
            <p className="mt-1 text-sm text-foreground">
              {[...(item.riskFlags || []), ...(item.llmRisks || [])].length
                ? [...(item.riskFlags || []), ...(item.llmRisks || [])].join('，')
                : text.none}
            </p>
          </div>
        </div>
        <div className="space-y-3">
          <div>
            <p className="text-xs font-semibold text-secondary-text">{text.mainFactors}</p>
            <div className="mt-2 grid grid-cols-2 gap-2">
              {factors.length > 0 ? (
                factors.map(([key, value]) => (
                  <Surface key={key} level="interactive" padding="sm">
                    <span className="block text-xs text-secondary-text">{key}</span>
                    <span className="text-sm font-semibold text-foreground">{formatNumber(value)}</span>
                  </Surface>
                ))
              ) : (
                <span className="text-sm text-secondary-text">{text.noFactors}</span>
              )}
            </div>
          </div>
          <div>
            <p className="text-xs font-semibold text-secondary-text">{text.turnover}</p>
            <p className="mt-1 text-sm text-foreground">{formatAmount(item.amount, language, text)}</p>
          </div>
          <div>
            <p className="text-xs font-semibold text-secondary-text">{text.watchItems}</p>
            <p className="mt-1 text-sm text-foreground">
              {item.llmWatchItems?.length ? item.llmWatchItems.join(getUiListSeparator(language)) : llmDegraded ? text.degradedNoValue : text.none}
            </p>
          </div>
          <div>
            <p className="text-xs font-semibold text-secondary-text">{text.catalysts}</p>
            <p className="mt-1 text-sm text-foreground">
              {item.llmCatalysts?.length ? item.llmCatalysts.join(getUiListSeparator(language)) : llmDegraded ? text.degradedNoValue : text.none}
            </p>
          </div>
          <div>
            <p className="text-xs font-semibold text-secondary-text">{text.dsaNews}</p>
            {dsaNews.length > 0 ? (
              <ul className="mt-1 space-y-1 text-sm text-foreground">
                {dsaNews.slice(0, 3).map((newsItem, newsIndex) => (
                  <li key={`${item.code}-dsa-news-${newsIndex}`}>
                    {newsItem.title || newsItem.snippet || '-'}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="mt-1 text-sm text-secondary-text">{text.none}</p>
            )}
          </div>
          {dsaWarnings.length > 0 ? (
            <div>
              <p className="text-xs font-semibold text-secondary-text">{text.dsaHints}</p>
              <p className="mt-1 text-sm text-secondary-text">
                {dsaWarnings.map((warning) => summarizeAlphaSiftDiagnostic(warning, text)).join('，')}
              </p>
            </div>
          ) : null}
        </div>
      </div>
    );
  }, [language, llmDegraded, text]);

  return (
    <AppPage className="space-y-6 pb-12 pt-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="flex items-center gap-3">
          <span className="grid h-7 w-7 place-items-center rounded-full border-2 border-primary text-primary shadow-soft-card">
            <PlusCircle className="h-4 w-4" />
          </span>
          <div>
            <h1 className="text-2xl font-bold tracking-normal text-foreground">{text.title}</h1>
            <p className="mt-1 text-sm text-secondary-text">{text.description}</p>
          </div>
        </div>

        <Surface level="interactive" padding="sm" className="inline-flex w-fit items-center gap-2 text-sm">
          <span className={`h-2.5 w-2.5 rounded-full ${isScreeningEnabled ? 'bg-success' : 'bg-warning'}`} />
          <span className="font-medium text-secondary-text">{statusText}</span>
        </Surface>
      </div>

      {!statusLoading && !enabled ? (
        <InlineAlert
          variant="info"
          title={text.notEnabledTitle}
          message={text.notEnabledMessage}
          action={
            <Button variant="primary" size="default" isLoading={enabling} loadingText={text.enabling} onClick={() => void handleEnable()}>
              {text.enable}
            </Button>
          }
        />
      ) : null}

      {!statusLoading && enabled && !available ? (
        <InlineAlert
          variant="warning"
          title={text.unavailableTitle}
          message={text.unavailableMessage}
        />
      ) : null}

      <InlineAlert
        variant="warning"
        title={text.riskTitle}
        message={text.riskMessage}
      />

      {loading ? (
        <InlineAlert
          variant="info"
          title={text.taskRunningTitle}
          message={`${taskMessage || text.runningTask}. ${text.taskId}: ${activeTaskId ? activeTaskId.slice(0, 12) : '-'}`}
        />
      ) : null}

      {error ? <InlineAlert variant="danger" title={text.callFailed} message={error} /> : null}

      <Surface as="section" level="interactive" padding="md">
        <div className="mb-4 flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
          <div className="flex items-start gap-3">
            <span className="grid h-10 w-10 shrink-0 place-items-center rounded-full bg-warning/10 text-warning shadow-soft-card">
              <Flame className="h-5 w-5" />
            </span>
            <div>
              <h2 className="text-lg font-bold tracking-normal text-foreground">{text.hotspots}</h2>
              <p className="mt-1 text-xs leading-5 text-secondary-text">
                {text.hotspotsDescription}
              </p>
            </div>
          </div>
          <div className="flex flex-col items-start gap-2 lg:items-end">
            <div className="flex flex-wrap items-center gap-2">
              <Button
                size="default"
                variant="secondary"
                disabled={!isScreeningEnabled}
                onClick={toggleHotspotsExpanded}
              >
                <Bookmark className="h-4 w-4" />
                {hotspotsExpanded ? text.collapseHotspots : `${text.expandHotspots}${hotspots.length ? ` (${hotspots.length})` : ''}`}
                <ChevronDown className={`h-4 w-4 transition-transform ${hotspotsExpanded ? 'rotate-180' : ''}`} />
              </Button>
              {hotspotsExpanded ? (
              <Button
                size="default"
                variant="secondary"
                isLoading={loadingHotspots}
                loadingText={text.refreshing}
                disabled={!isScreeningEnabled || loadingHotspots}
                onClick={() => void loadHotspots(true)}
              >
                <RefreshCw className="h-4 w-4" />
                {text.refreshHotspots}
              </Button>
              ) : null}
            </div>
            <p className="text-xs text-secondary-text">{formatUiText(text.updatedAt, { time: formatHotspotUpdatedAt(hotspotsUpdatedAt, language, text) })}</p>
          </div>
        </div>

        {hotspotError ? (
          <InlineAlert variant="warning" className="mb-3" message={hotspotError} />
        ) : null}

        {!hotspotsExpanded ? (
          <Surface level="interactive" padding="sm" className="flex flex-col gap-2 text-sm text-secondary-text sm:flex-row sm:items-center sm:justify-between">
            <span>
              {hotspots.length > 0
                ? formatUiText(text.cachedHotspots, { count: hotspots.length })
                : text.hotspotsCollapsed}
            </span>
            <span className="text-xs">{text.liveDetailHint}</span>
          </Surface>
        ) : hotspots.length === 0 ? (
          <Surface level="interactive" padding="sm" className="text-sm text-secondary-text">
            {text.refreshDescription}
          </Surface>
        ) : (
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
            {hotspots.map((item, index) => {
              const selected = selectedHotspotTopic === item.topic;
              const strength = getHotspotStrength(item, index, text);
              const iconMeta = getHotspotIcon(item.name || item.topic);
              const Icon = iconMeta.icon;
              return (
              <button
                key={`${item.topic}-${item.rank ?? ''}`}
                className={`group relative min-h-28 overflow-hidden rounded-lg border px-3 py-3 text-left transition-all ${
                  selected
                    ? 'border-warning/50 bg-gradient-to-br from-warning/10 via-card to-card shadow-soft-card ring-1 ring-warning/20'
                    : 'border-border/80 bg-card hover:-translate-y-0.5 hover:border-warning/40 hover:shadow-soft-card'
                }`}
                type="button"
                onClick={() => handleHotspotSelect(item.topic)}
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="flex min-w-0 items-start gap-3">
                    <span
                      className={`grid h-6 w-6 shrink-0 place-items-center rounded-full text-xs font-bold ${
                        index < 3 ? 'bg-warning/15 text-warning shadow-soft-card' : 'bg-subtle-soft text-secondary-text'
                      }`}
                    >
                      {index + 1}
                    </span>
                    <span className={`grid h-9 w-9 shrink-0 place-items-center rounded-full ${iconMeta.className}`}>
                      <Icon className="h-5 w-5" />
                    </span>
                    <div className="min-w-0">
                      <p className="truncate text-sm font-bold text-foreground">{item.name || item.topic}</p>
                      <span className={`mt-1 inline-flex rounded-md px-1.5 py-0.5 text-xs font-semibold ${strength.className}`}>
                        {strength.label}
                      </span>
                    </div>
                  </div>
                  <span className="shrink-0 text-2xl font-black leading-none text-orange-500">
                    {formatNumber(item.heatScore, 0)}
                  </span>
                </div>
                <div className="mt-4 grid max-w-[72%] gap-1 text-xs text-secondary-text">
                  <span>{text.change} <strong className="font-semibold text-foreground">{formatHotspotMetric(item.changePct, text)}%</strong></span>
                  <span>{text.trend} <strong className="font-semibold text-foreground">{formatHotspotMetric(item.trendScore, text)}</strong> · {text.persistence} <strong className="font-semibold text-foreground">{formatHotspotMetric(item.persistenceScore, text)}</strong></span>
                  <span>{getHotspotSampleText(item, text)} · {text.leader} {getHotspotLeadersText(item, language, text)}</span>
                </div>
                <div className="absolute bottom-3 right-3 opacity-95 transition-transform group-hover:scale-105">
                  <MiniSparkline score={item.heatScore} selected={selected} />
                </div>
              </button>
              );
            })}
          </div>
        )}

        {hotspotsExpanded && selectedHotspotTopic ? (
          <Surface level="interactive" padding="sm" className="mt-4">
            <div className="mb-3 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <h3 className="text-sm font-semibold text-foreground">
                  {hotspotDetail?.name || selectedHotspotTopic}
                </h3>
                <p className="mt-1 text-xs leading-5 text-secondary-text">
                  {loadingHotspotDetail ? text.loadingHotspotDetail : hotspotDetail?.summary || text.selectHotspot}
                </p>
                {hotspotDetail?.canonicalTopic && hotspotDetail.canonicalTopic !== selectedHotspotTopic ? (
                  <p className="mt-1 text-xs text-secondary-text">{formatUiText(text.canonicalTopic, { topic: hotspotDetail.canonicalTopic })}</p>
                ) : null}
              </div>
              <div className="flex flex-wrap items-center gap-2">
                {hotspotDetail?.qualityStatus ? (
                  <span className="w-fit rounded-full bg-warning/10 px-3 py-1 text-xs font-semibold text-warning">
                    {formatUiText(text.quality, { status: hotspotDetail.qualityStatus })}
                  </span>
                ) : null}
                {hotspotDetail?.fallbackUsed || hotspotDetail?.stale ? (
                  <span className="w-fit rounded-full bg-warning/10 px-3 py-1 text-xs font-semibold text-warning">
                    {hotspotDetail.staleAgeHours != null ? formatUiText(text.cacheFallbackHours, { hours: formatNumber(hotspotDetail.staleAgeHours, 1) }) : text.cacheFallback}
                  </span>
                ) : null}
                {hotspotDetail?.stockCount != null ? (
                  <span className="w-fit rounded-full bg-orange-500/10 px-3 py-1 text-xs font-semibold text-orange-500">
                    {formatUiText(text.conceptStocksCount, { count: hotspotDetail.stockCount })}
                  </span>
                ) : null}
              </div>
            </div>

            {hotspotDetailError ? (
              <InlineAlert variant="warning" className="mb-3" message={hotspotDetailError} />
            ) : null}

            {hotspotDetail && ((hotspotDetail.missingFields || []).length > 0 || (hotspotDetail.sourceErrors || []).length > 0) ? (
              <details className="mb-3 rounded-xl border border-warning/30 bg-warning/10 px-3 py-2 text-xs text-warning">
                <summary className="min-h-11 cursor-pointer font-semibold">
                  <span className="inline-flex min-h-11 items-center">{text.degradedDetail}</span>
                </summary>
                <div className="mt-2 space-y-1 leading-5">
                  {(hotspotDetail.missingFields || []).length > 0 ? (
                    <p>{formatUiText(text.missingFields, { fields: (hotspotDetail.missingFields || []).join(getUiListSeparator(language)) })}</p>
                  ) : null}
                  {(hotspotDetail.sourceErrors || []).slice(0, 4).map((message, index) => (
                    <p key={`${message}-${index}`}>{summarizeAlphaSiftDiagnostic(message, text)}</p>
                  ))}
                </div>
              </details>
            ) : null}

            {hotspotDetail ? (
              <div className="grid gap-4 lg:grid-cols-[1fr_1.3fr]">
                <div>
                  <p className="mb-3 flex items-center gap-1.5 text-xs font-semibold text-secondary-text">
                    <Clock3 className="h-3.5 w-3.5 text-orange-500" />
                    {text.routeTimeline}
                  </p>
                  <div className="relative space-y-0 pl-4 before:absolute before:bottom-3 before:left-[5px] before:top-2 before:w-px before:bg-border">
                    {getHotspotRouteItems(hotspotDetail).map((item, index) => (
                      <div key={`${item.title}-${index}`} className="relative pb-4 last:pb-0">
                        <span className="absolute -left-4 top-1 h-2.5 w-2.5 rounded-full border border-orange-400 bg-card" />
                        <Surface level="interactive" padding="sm">
                          <p className="text-xs font-semibold text-orange-500">{getRouteTimeLabel(item, language, text)}</p>
                          <p className="mt-1 text-xs font-semibold text-foreground">{item.title}</p>
                          <p className="mt-1 text-xs leading-5 text-secondary-text">{item.description}</p>
                          {item.source ? <p className="mt-2 text-xs text-secondary-text">{formatUiText(text.source, { source: item.source })}</p> : null}
                        </Surface>
                      </div>
                    ))}
                  </div>
                </div>
                <div>
                  <p className="mb-2 text-xs font-semibold text-secondary-text">{text.conceptStocks}</p>
                  <div className="grid gap-2 sm:grid-cols-2">
                    {(hotspotDetail.stocks || []).slice(0, 10).map((stock) => (
                      <Surface key={`${stock.code || stock.name}`} level="interactive" padding="sm">
                        <div className="flex items-start justify-between gap-2">
                          <div className="min-w-0">
                            <p className="truncate text-xs font-semibold text-foreground">{stock.name || stock.code || '-'}</p>
                            <p className="mt-1 text-xs text-secondary-text">{stock.code || '-'}</p>
                          </div>
                          <div className="flex shrink-0 items-center gap-1">
                            <span className="rounded-full bg-primary/10 px-2 py-1 text-xs font-semibold text-primary">
                              {stock.role || text.conceptStock}
                            </span>
                            {stock.code ? (
                              <button
                                type="button"
                                aria-label={formatUiText(text.analyzeStock, { stock: stock.name || stock.code })}
                                className="inline-flex min-h-11 min-w-11 items-center justify-center text-xs font-semibold text-primary"
                                onClick={() => handleAnalyzeHotspotStock(stock)}
                              >
                                <span className="inline-flex h-7 items-center gap-1 rounded-full border border-primary/30 bg-primary/10 px-2 transition-colors hover:border-primary hover:bg-primary/15 hover:text-foreground">
                                  <Play className="h-3 w-3" />
                                  {text.analyze}
                                </span>
                              </button>
                            ) : null}
                          </div>
                        </div>
                        <p className="mt-2 text-xs text-secondary-text">
                          {text.change} {formatStockChangeText(stock.changePct, text)} · {text.heat} {formatNumber(stock.hotStockScore, 0)}
                        </p>
                        {stock.source || stock.sourceConfidence != null || stock.fallbackUsed ? (
                          <p className="mt-1 text-xs text-secondary-text">
                            {formatUiText(text.source, { source: stock.source || '-' })}
                            {stock.sourceConfidence != null ? ` · ${formatUiText(text.confidence, { value: formatPercent(stock.sourceConfidence) })}` : ''}
                            {stock.fallbackUsed ? ` · ${text.fallback}` : ''}
                          </p>
                        ) : null}
                      </Surface>
                    ))}
                  </div>
                </div>
              </div>
            ) : null}
          </Surface>
        ) : null}
      </Surface>

      <Surface as="section" level="interactive" padding="none" className="p-3">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <h2 className="text-sm font-semibold text-foreground">{text.selectStrategy}</h2>
            <p className="mt-1 text-xs text-secondary-text">
              {selectedStrategyDisplay?.description || text.strategyDescription}
            </p>
          </div>
          <div className="flex w-full flex-wrap items-center gap-2 sm:w-auto sm:flex-nowrap">
            <Select
              value={strategy}
              onChange={handleStrategyChange}
              options={strategies.map((item) => ({
                value: item.id,
                label: getStrategyDisplay(item, language).name,
              }))}
              ariaLabel={text.selectStrategy}
              placeholder={loadingStrategies ? text.loadingStrategies : text.strategiesUnavailable}
              disabled={loading || loadingStrategies || strategies.length === 0}
              className="w-full sm:w-72 [&>div]:w-full"
            />
            <span className="shrink-0 rounded-lg border border-primary/30 bg-primary/10 px-2 py-1 text-xs font-semibold text-primary">
              {selectedStrategyTag}
            </span>
            <Button
              type="button"
              variant="secondary"
              size="compact"
              onClick={handleOpenConfiguration}
            >
              <SlidersHorizontal className="h-3.5 w-3.5" aria-hidden="true" />
              {text.parameters}
            </Button>
          </div>
        </div>
        {strategyLoadError ? <p role="alert" className="mt-2 text-xs text-danger">{strategyLoadError}</p> : null}
      </Surface>

      <Modal
        isOpen={configurationOpen}
        onClose={() => setConfigurationOpen(false)}
        title={text.parameters}
        description={selectedStrategyDisplay?.description || text.strategyDescription}
        closeDisabled={loading}
        footer={(
          <>
            <Button
              type="button"
              variant="ghost"
              size="compact"
              disabled={loading}
              onClick={() => setConfigurationOpen(false)}
            >
              {t('common.cancel')}
            </Button>
            <Button
              type="submit"
              form={configurationFormId}
              variant="primary"
              size="compact"
              disabled={!isScreeningEnabled || loading}
              isLoading={loading}
              loadingText={text.screening}
            >
              <Play className="h-3.5 w-3.5" aria-hidden="true" />
              {text.run}
            </Button>
          </>
        )}
      >
        {configurationError ? (
          <InlineAlert
            variant="danger"
            title={text.callFailed}
            message={configurationError}
            className="mb-3"
          />
        ) : null}
        <form id={configurationFormId} onSubmit={handleConfigurationSubmit} noValidate>
          <div className="grid gap-3 sm:grid-cols-2">
            <Select
              label={text.market}
              value={market}
              disabled={loading}
              onChange={handleMarketChange}
              options={markets.map((item) => ({ value: item.id, label: item.label }))}
              className="w-full flex-row items-center gap-3 [&>label]:mb-0 [&>label]:shrink-0 [&>div]:min-w-0 [&>div]:flex-1"
            />

            <Input
              label={text.strategyParameter}
              value={strategy}
              disabled={loading}
              onChange={(event) => handleStrategyChange(event.target.value)}
              fieldClassName="w-full flex-row flex-wrap items-center gap-x-3 gap-y-1 [&>label]:mb-0 [&>label]:shrink-0 [&>.control-input-target]:min-w-0 [&>.control-input-target]:flex-1 [&>p]:basis-full"
            />

            <Input
              id="screening-max-results"
              label={text.resultCount}
              type="number"
              min={1}
              max={100}
              step={1}
              value={maxResultsDraft}
              error={maxResultsError}
              disabled={loading}
              onChange={(event) => handleMaxResultsChange(event.target.value)}
              fieldClassName="w-full flex-row flex-wrap items-center gap-x-3 gap-y-1 [&>label]:mb-0 [&>label]:shrink-0 [&>.control-input-target]:min-w-0 [&>.control-input-target]:flex-1 [&>p]:basis-full"
            />
          </div>
        </form>
      </Modal>

      <Surface as="section" level="interactive" padding="md">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-3">
            <span
              className={`grid h-7 w-7 place-items-center rounded-full ${
                candidates.length > 0 ? 'text-success' : isScreeningEnabled ? 'text-primary' : 'text-warning'
              }`}
            >
              {candidates.length > 0 ? <CheckCircle2 className="h-5 w-5" /> : <CircleAlert className="h-5 w-5" />}
            </span>
            <div>
              <h2 className="text-sm font-semibold text-foreground">
                {loading ? text.running : candidates.length > 0 ? text.completed : isScreeningEnabled ? text.waitingRun : text.waitingEnable}
              </h2>
              <p className="mt-1 text-xs text-secondary-text">
                {loading
                  ? `${taskMessage || text.runningTask} · ${taskProgress}%`
                  : formatUiText(text.currentStrategy, { strategy: displayedStrategy, market: markets.find((item) => item.id === market)?.label || market })}
              </p>
            </div>
          </div>
          <div className="grid gap-1 text-xs text-secondary-text sm:text-right">
            <span>{formatUiText(text.task, { id: activeTaskId ? activeTaskId.slice(0, 12) : '-' })}</span>
            <span>{formatUiText(text.runId, { id: screenMeta?.runId || '-' })}</span>
            <span>
              {formatUiText(text.taskStats, { snapshot: screenMeta?.snapshotCount ?? '-', filtered: screenMeta?.afterFilterCount ?? '-', candidates: screenMeta?.candidateCount ?? candidates.length })}
            </span>
            <span>
              {text.llm}: {screenMeta?.llmRanked ? text.reranked : screenMeta ? text.notReranked : '-'}
              {screenMeta?.llmCoverage != null ? ` · ${formatUiText(text.coverage, { value: formatPercent(screenMeta.llmCoverage) })}` : ''}
            </span>
            <span>
              {formatUiText(text.dsaEnrichment, { enriched: screenMeta?.dsaEnrichment?.enrichedCount ?? '-', requested: screenMeta?.dsaEnrichment?.requestedCount ?? '-' })}
            </span>
          </div>
        </div>
      </Surface>

      {screenMeta && alertMessages.length > 0 ? (
        <InlineAlert
          variant={llmDegraded ? 'warning' : 'info'}
          title={llmDegraded ? text.llmDegraded : text.alphaSiftNotice}
          message={<ScreenAlertMessage messages={alertMessages} />}
        />
      ) : null}

      <Surface as="section" level="interactive" padding="md">
        <div className="mb-5 flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <h2 className="text-base font-semibold text-foreground">{text.results}</h2>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-secondary-text">
              {text.resultsDescription}
            </p>
          </div>
          <div className="flex items-center gap-2 rounded-full border border-border bg-subtle-soft px-3 py-2 text-xs text-secondary-text">
            <Search className="h-4 w-4 text-primary" />
            {formatUiText(text.candidateCount, { count: candidates.length })}
          </div>
        </div>

        <DataTable
          caption={text.results}
          scrollAreaLabel={text.results}
          columns={candidateColumns}
          rows={candidates}
          getRowKey={(item) => `${item.rank}-${item.code}`}
          emptyState={{
            title: text.noResults,
            description: text.noResultsDescription,
            action: (
              <Button
                type="button"
                variant="primary"
                size="default"
                disabled={loading}
                aria-label={text.waitingRun}
                onClick={handleOpenConfiguration}
              >
                <Play className="h-4 w-4" aria-hidden="true" />
                {text.run}
              </Button>
            ),
          }}
          minWidth="wide"
          isRowDetailVisible={(item) => expandedCode === item.code}
          renderRowDetail={renderCandidateDetail}
          getRowDetailId={getCandidateDetailId}
          getRowDetailAriaLabel={(item) => `${item.name || item.code} ${text.details}`}
        />
      </Surface>
    </AppPage>
  );
};

export default StockScreeningPage;
