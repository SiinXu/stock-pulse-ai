import type React from 'react';
import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from 'react';
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
import { AppPage, Button, InlineAlert, Select } from '../components/common';
import { useUiLanguage } from '../contexts/UiLanguageContext';
import { formatUiText, type UiLanguage } from '../i18n/uiText';
import { SCREENING_TEXT } from '../locales/screening';
import { formatUiDateTime, formatUiNumber } from '../utils/uiLocale';
import { createRequestKey, useAsyncResource } from '../hooks/useAsyncResource';
import { localizeTaskMessage } from '../utils/taskMessage';
import { getStrategyDisplay } from '../utils/strategyDisplay';

const SCREEN_TASK_STORAGE_KEY = 'dsa.alphasift.activeScreenTask.v1';
const SCREEN_TASK_POLL_INTERVAL_MS = 2000;

interface HotspotResourceData {
  items: AlphaSiftHotspot[];
  updatedAt: string | null;
  emptyMessage: string;
}

const EMPTY_HOTSPOTS: HotspotResourceData = {
  items: [],
  updatedAt: null,
  emptyMessage: '',
};

type PersistedScreenTask = {
  taskId: string;
  market: string;
  strategy: string;
  maxResults: number;
};

const readPersistedScreenTask = (): PersistedScreenTask | null => {
  if (typeof window === 'undefined') {
    return null;
  }
  try {
    const raw = window.sessionStorage.getItem(SCREEN_TASK_STORAGE_KEY);
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
    window.sessionStorage.setItem(SCREEN_TASK_STORAGE_KEY, JSON.stringify(task));
  } catch {
    // Session storage is best-effort; polling still works while the page stays mounted.
  }
};

const clearPersistedScreenTask = () => {
  try {
    window.sessionStorage.removeItem(SCREEN_TASK_STORAGE_KEY);
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

const summarizeAlphaSiftDiagnostic = (detail: string, text: ScreeningText) => {
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

const normalizeScreenTaskStatus = (status: string | undefined | null) => {
  switch (status) {
    case 'pending':
    case 'processing':
    case 'completed':
    case 'failed':
    case 'cancel_requested':
    case 'cancelled':
      return status;
    default:
      return 'processing';
  }
};

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
    return leaders.slice(0, 2).join(language === 'en' ? ', ' : '、');
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
  return { label: text.strengthFirm, className: 'bg-cyan/10 text-cyan' };
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
  return match || { icon: Activity, className: 'bg-cyan/10 text-cyan' };
};

const MiniSparkline: React.FC<{ score?: number | null; selected?: boolean }> = ({ score, selected }) => {
  const normalizedScore = Number.isFinite(Number(score)) ? Math.max(0, Math.min(100, Number(score))) : 65;
  const lift = Math.max(0, Math.min(16, normalizedScore / 7));
  const path = `M2 35 C12 ${32 - lift / 4}, 16 ${34 - lift / 2}, 24 ${28 - lift / 3} S38 ${29 - lift}, 46 ${23 - lift / 2} S62 ${24 - lift}, 72 ${16 - lift / 3} S86 ${15 - lift}, 94 ${7}`;
  return (
    <svg className="h-8 w-20" viewBox="0 0 96 40" aria-hidden="true">
      <path d={`${path} L94 40 L2 40 Z`} fill={selected ? 'rgba(249,115,22,0.14)' : 'rgba(59,130,246,0.12)'} />
      <path d={path} fill="none" stroke={selected ? '#f97316' : '#3b82f6'} strokeLinecap="round" strokeWidth="2" />
    </svg>
  );
};

const StockScreeningPage: React.FC = () => {
  const navigate = useNavigate();
  const { language, t } = useUiLanguage();
  const text = SCREENING_TEXT[language];
  const markets = useMemo(() => [{ id: 'cn', label: text.marketCn }], [text.marketCn]);
  const [restoredTask] = useState<PersistedScreenTask | null>(() => readPersistedScreenTask());
  const [enabled, setEnabled] = useState(false);
  const [available, setAvailable] = useState(false);
  const [market, setMarket] = useState(restoredTask?.market || 'cn');
  const [strategy, setStrategy] = useState(restoredTask?.strategy || 'dual_low');
  const [strategiesResource, strategyRequests] = useAsyncResource<AlphaSiftStrategy[], string>({
    initialData: [],
    isEmpty: (items) => items.length === 0,
  });
  const strategies = strategiesResource.data;
  const [maxResults, setMaxResults] = useState(restoredTask?.maxResults || 3);
  const [candidates, setCandidates] = useState<AlphaSiftCandidate[]>([]);
  const [hotspotsResource, hotspotRequests] = useAsyncResource<HotspotResourceData, string>({
    initialData: EMPTY_HOTSPOTS,
    isEmpty: (data) => data.items.length === 0,
  });
  const hotspots = hotspotsResource.data.items;
  const hotspotsUpdatedAt = hotspotsResource.data.updatedAt;
  const [hotspotsExpanded, setHotspotsExpanded] = useState(false);
  const [selectedHotspotTopic, setSelectedHotspotTopic] = useState<string | null>(null);
  const componentMountedRef = useRef(true);
  const selectedHotspotTopicRef = useRef<string | null>(null);
  const hotspotDetailRequestIdRef = useRef(0);
  const hotspotDetailsByTopicRef = useRef<Record<string, AlphaSiftHotspotDetail>>({});
  const [hotspotDetail, setHotspotDetail] = useState<AlphaSiftHotspotDetail | null>(null);
  const [loadingHotspotDetail, setLoadingHotspotDetail] = useState(false);
  const [hotspotDetailError, setHotspotDetailError] = useState('');
  const loadingHotspots = hotspotsResource.status === 'loading' || hotspotsResource.status === 'refreshing';
  const hotspotError = hotspotsResource.error || '';
  const [screenMeta, setScreenMeta] = useState<AlphaSiftScreenResponse | null>(null);
  const [expandedCode, setExpandedCode] = useState<string | null>(null);
  const [loading, setLoading] = useState(Boolean(restoredTask?.taskId));
  const [enabling, setEnabling] = useState(false);
  const loadingStrategies = strategiesResource.status === 'loading';
  const [error, setError] = useState('');
  const strategyLoadError = strategiesResource.error || '';
  const [activeTaskId, setActiveTaskId] = useState<string | null>(restoredTask?.taskId ?? null);
  const [taskProgress, setTaskProgress] = useState(restoredTask?.taskId ? 10 : 0);
  const [taskMessageFallback, setTaskMessageFallback] = useState(restoredTask?.taskId ? text.restoringTask : '');
  const [taskSnapshot, setTaskSnapshot] = useState<AlphaSiftScreenTaskStatus | null>(null);

  const taskMessage = taskSnapshot
    ? localizeTaskMessage({
        status: normalizeScreenTaskStatus(taskSnapshot.status),
        messageCode: taskSnapshot.messageCode || undefined,
        messageParams: taskSnapshot.messageParams,
      }, t)
    : taskMessageFallback;
  const taskRawMessage = String(taskSnapshot?.message || '').trim();
  const taskRawError = String(taskSnapshot?.error || '').trim();
  const taskErrorCode = String(taskSnapshot?.errorCode || '').trim();
  const hasTaskDiagnostics = Boolean(taskSnapshot?.traceId || taskRawMessage || taskRawError || taskErrorCode);
  const taskFailureMessage = taskSnapshot?.status === 'failed'
    ? localizeTaskMessage({
        status: 'failed',
        messageCode: taskSnapshot.messageCode || undefined,
        messageParams: taskSnapshot.messageParams,
      }, t)
    : '';
  const displayedError = taskFailureMessage || error;

  const selectedStrategy = useMemo(() => strategies.find((item) => item.id === strategy), [strategies, strategy]);
  const selectedStrategyDisplay = useMemo(
    () => (selectedStrategy ? getStrategyDisplay(selectedStrategy, language) : null),
    [language, selectedStrategy],
  );
  const selectedStrategyTitle = selectedStrategyDisplay?.name || text.customStrategy;
  const selectedStrategyTag = selectedStrategyDisplay?.category || text.custom;
  const displayedStrategy = selectedStrategy ? selectedStrategyTitle : `${text.customStrategy} (${strategy})`;
  const screenMessages = useMemo(() => getScreenMessages(screenMeta, text), [screenMeta, text]);
  const llmDegraded = screenMeta?.llmRanked === false;
  const alertMessages = llmDegraded
    ? screenMessages.length > 0
      ? screenMessages
      : [text.localRankingNotice]
    : screenMessages;
  const isScreeningEnabled = enabled && available;
  const statusText = isScreeningEnabled ? text.enabled : text.disabled;

  useEffect(() => {
    document.title = text.documentTitle;
  }, [text.documentTitle]);

  useEffect(() => {
    componentMountedRef.current = true;
    return () => {
      componentMountedRef.current = false;
      hotspotDetailRequestIdRef.current += 1;
    };
  }, []);

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
    const canApplyRequest = () => (
      componentMountedRef.current
      && isCurrentRequest()
      && selectedHotspotTopicRef.current === topic
    );
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
      if (componentMountedRef.current && isCurrentRequest()) {
        setLoadingHotspotDetail(false);
      }
    }
  }, [language, text.hotspotDetailLoadFailed]);

  const loadStrategies = useCallback(async () => {
    const request = strategyRequests.begin(
      createRequestKey('screening-strategies', ['alphasift']),
      { retainData: true },
    );
    try {
      const result = await alphasiftApi.getStrategies();
      const loadedStrategies = result.strategies || [];
      if (strategyRequests.resolve(request, loadedStrategies) && loadedStrategies.length > 0) {
        setStrategy((currentStrategy) =>
          loadedStrategies.some((item) => item.id === currentStrategy) ? currentStrategy : loadedStrategies[0].id,
        );
      }
    } catch (err) {
      strategyRequests.reject(request, getParsedApiError(err, language).message || text.strategyLoadFailed);
    }
  }, [language, strategyRequests, text.strategyLoadFailed]);

  const loadHotspots = useCallback(async (refresh = false) => {
    const request = hotspotRequests.begin(
      createRequestKey('screening-hotspots', ['akshare', 12, refresh]),
      { retainData: refresh },
    );
    try {
      const result = await alphasiftApi.getHotspots({ provider: 'akshare', top: 12, refresh });
      const nextHotspots = result.hotspots || [];
      const nextDetails = result.details || {};
      const nextResource = {
        items: nextHotspots,
        updatedAt: result.cachedAt || (nextHotspots.length > 0 ? new Date().toISOString() : null),
        emptyMessage: nextHotspots.length === 0 ? formatHotspotEmptyMessage(result, text) : '',
      };
      if (!hotspotRequests.resolve(request, nextResource)) {
        return;
      }
      hotspotDetailsByTopicRef.current = {
        ...hotspotDetailsByTopicRef.current,
        ...nextDetails,
      };
      const currentTopic = selectedHotspotTopicRef.current;
      const retainedTopic = Boolean(currentTopic && nextHotspots.some((item) => item.topic === currentTopic));
      const nextTopic = retainedTopic ? currentTopic : null;
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
    } catch (err) {
      hotspotRequests.reject(request, toApiErrorMessage(err, text.hotspotLoadFailed, language));
    }
  }, [hotspotRequests, language, loadHotspotDetail, text]);

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
        if (status.enabled && status.available) {
          void loadStrategies();
          void loadHotspots(false);
        }
      })
      .catch(() => {
        if (active) {
          setEnabled(false);
          setAvailable(false);
        }
      });
    return () => {
      active = false;
    };
  }, [loadHotspots, loadStrategies]);

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
      setTaskSnapshot(task);

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
        setError('');
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
      setEnabled(true);
      setAvailable(true);
      await loadStrategies();
    } catch (err) {
      try {
        const status = await alphasiftApi.getStatus();
        setEnabled(status.enabled);
        setAvailable(status.available);
      } catch {
        setEnabled(false);
        setAvailable(false);
      }
      setError(getParsedApiError(err, language).message || text.enableFailed);
    } finally {
      setEnabling(false);
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

  const handleMaxResultsChange = (nextMaxResults: number) => {
    if (nextMaxResults !== maxResults) {
      clearScreeningResults();
    }
    setMaxResults(nextMaxResults);
  };

  const handleSubmit = async () => {
    setLoading(true);
    setError('');
    setScreenMeta(null);
    setTaskProgress(0);
    setTaskSnapshot(null);
    setTaskMessageFallback(text.submittingTask);
    try {
      const task = await alphasiftApi.startScreen({ market, strategy, maxResults });
      persistScreenTask({
        taskId: task.taskId,
        market,
        strategy,
        maxResults,
      });
      setActiveTaskId(task.taskId);
      setTaskProgress(0);
      setTaskSnapshot({
        taskId: task.taskId,
        traceId: task.traceId,
        status: task.status,
        progress: 0,
        message: task.message,
        messageCode: task.messageCode,
        messageParams: task.messageParams,
        revision: task.revision,
        updatedAt: task.updatedAt,
      });
      setTaskMessageFallback(text.taskSubmitted);
    } catch (err) {
      setCandidates([]);
      setLoading(false);
      setError(toApiErrorMessage(err, text.taskSubmitFailed, language));
    }
  };

  return (
    <AppPage className="max-w-6xl space-y-6 pb-12 pt-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="flex items-center gap-3">
          <span className="grid h-7 w-7 place-items-center rounded-full border-2 border-cyan text-cyan shadow-[0_0_24px_hsl(var(--primary)/0.18)]">
            <PlusCircle className="h-4 w-4" />
          </span>
          <div>
            <h1 className="text-2xl font-bold tracking-normal text-foreground">{text.title}</h1>
            <p className="mt-1 text-sm text-secondary-text">{text.description}</p>
          </div>
        </div>

        <div className="inline-flex w-fit items-center gap-2 rounded-2xl border border-border/70 bg-card/80 px-4 py-2 text-sm shadow-soft-card">
          <span className={`h-2.5 w-2.5 rounded-full ${isScreeningEnabled ? 'bg-success' : 'bg-warning'}`} />
          <span className="font-medium text-secondary-text">{statusText}</span>
        </div>
      </div>

      {!enabled ? (
        <InlineAlert
          variant="info"
          title={text.notEnabledTitle}
          message={text.notEnabledMessage}
          action={
            <Button size="sm" isLoading={enabling} loadingText={text.enabling} onClick={() => void handleEnable()}>
              {text.enable}
            </Button>
          }
        />
      ) : null}

      {enabled && !available ? (
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

      {displayedError ? <InlineAlert variant="danger" title={text.callFailed} message={displayedError} /> : null}

      {(loading || displayedError) && hasTaskDiagnostics ? (
        <details className="rounded-lg border border-border/70 bg-surface/70 px-3 py-2 text-xs text-muted-text">
          <summary className="cursor-pointer font-medium text-secondary-text">{t('taskPanel.diagnostics')}</summary>
          <div className="mt-2 grid gap-1">
            {taskSnapshot?.traceId ? <div>{text.traceId}: <code>{taskSnapshot.traceId}</code></div> : null}
            {taskErrorCode ? <div>{t('taskPanel.errorCode')}: <code>{taskErrorCode}</code></div> : null}
            {taskRawMessage ? <div>{t('taskPanel.rawMessage')}: <span>{taskRawMessage}</span></div> : null}
            {taskRawError ? <div>{t('taskPanel.rawError')}: <span>{taskRawError}</span></div> : null}
          </div>
        </details>
      ) : null}

      <section className="rounded-2xl border border-border/80 bg-card/95 p-4 shadow-soft-card">
        <div className="mb-4 flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
          <div className="flex items-start gap-3">
            <span className="grid h-10 w-10 shrink-0 place-items-center rounded-full bg-orange-500/10 text-orange-500 shadow-[0_10px_30px_rgba(249,115,22,0.16)]">
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
                size="sm"
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
                size="sm"
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
          <p className="mb-3 rounded-xl border border-warning/30 bg-warning/10 px-3 py-2 text-xs text-warning">
            {hotspotError}
          </p>
        ) : null}

        {hotspotsResource.status === 'error' && hotspots.length === 0 ? null : hotspotsResource.status === 'loading' ? (
          <div className="rounded-xl border border-dashed border-border bg-surface/70 px-4 py-6 text-sm text-secondary-text">
            {text.refreshing}
          </div>
        ) : !hotspotsExpanded ? (
          <div className="flex flex-col gap-2 rounded-xl border border-border/70 bg-surface/70 px-4 py-3 text-sm text-secondary-text sm:flex-row sm:items-center sm:justify-between">
            <span>
              {hotspots.length > 0
                ? formatUiText(text.cachedHotspots, { count: hotspots.length })
                : hotspotsResource.data.emptyMessage || text.hotspotsCollapsed}
            </span>
            <span className="text-xs">{text.liveDetailHint}</span>
          </div>
        ) : hotspots.length === 0 ? (
          <div className="rounded-xl border border-dashed border-border bg-surface/70 px-4 py-6 text-sm text-secondary-text">
            {hotspotsResource.data.emptyMessage || text.refreshDescription}
          </div>
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
                className={`group relative min-h-28 overflow-hidden rounded-xl border px-3 py-3 text-left transition-all ${
                  selected
                    ? 'border-orange-400 bg-gradient-to-br from-orange-500/10 via-card to-card shadow-[0_0_0_1px_rgba(249,115,22,0.16),0_18px_44px_rgba(249,115,22,0.14)]'
                    : 'border-border/80 bg-card hover:-translate-y-0.5 hover:border-orange-300/70 hover:shadow-soft-card'
                }`}
                type="button"
                onClick={() => handleHotspotSelect(item.topic)}
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="flex min-w-0 items-start gap-3">
                    <span
                      className={`grid h-6 w-6 shrink-0 place-items-center rounded-full text-xs font-bold ${
                        index < 3 ? 'bg-orange-500 text-white shadow-[0_8px_24px_rgba(249,115,22,0.24)]' : 'bg-surface text-secondary-text'
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
                <div className="mt-4 grid max-w-3xl gap-1 text-xs text-secondary-text">
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
          <div className="mt-4 rounded-xl border border-border/80 bg-surface/80 p-4">
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
              <p className="mb-3 rounded-xl border border-warning/30 bg-warning/10 px-3 py-2 text-xs text-warning">
                {hotspotDetailError}
              </p>
            ) : null}

            {hotspotDetail && ((hotspotDetail.missingFields || []).length > 0 || (hotspotDetail.sourceErrors || []).length > 0) ? (
              <details className="mb-3 rounded-xl border border-warning/30 bg-warning/10 px-3 py-2 text-xs text-warning">
                <summary className="cursor-pointer font-semibold">{text.degradedDetail}</summary>
                <div className="mt-2 space-y-1 leading-5">
                  {(hotspotDetail.missingFields || []).length > 0 ? (
                    <p>{formatUiText(text.missingFields, { fields: (hotspotDetail.missingFields || []).join(language === 'en' ? ', ' : '、') })}</p>
                  ) : null}
                  {(hotspotDetail.sourceErrors || []).slice(0, 4).map((message, index) => (
                    <p key={`${message}-${index}`}>{message}</p>
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
                        <div className="rounded-lg border border-border/70 bg-card/80 p-3">
                          <p className="text-xs font-semibold text-orange-500">{getRouteTimeLabel(item, language, text)}</p>
                          <p className="mt-1 text-xs font-semibold text-foreground">{item.title}</p>
                          <p className="mt-1 text-xs leading-5 text-secondary-text">{item.description}</p>
                          {item.source ? <p className="mt-2 text-xs text-secondary-text">{formatUiText(text.source, { source: item.source })}</p> : null}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
                <div>
                  <p className="mb-2 text-xs font-semibold text-secondary-text">{text.conceptStocks}</p>
                  <div className="grid gap-2 sm:grid-cols-2">
                    {(hotspotDetail.stocks || []).slice(0, 10).map((stock) => (
                      <div key={`${stock.code || stock.name}`} className="rounded-lg border border-border/70 bg-card/80 p-3">
                        <div className="flex items-start justify-between gap-2">
                          <div className="min-w-0">
                            <p className="truncate text-xs font-semibold text-foreground">{stock.name || stock.code || '-'}</p>
                            <p className="mt-1 text-xs text-secondary-text">{stock.code || '-'}</p>
                          </div>
                          <div className="flex shrink-0 items-center gap-1">
                            <span className="rounded-lg bg-cyan/10 px-2 py-1 text-xs font-semibold text-cyan">
                              {stock.role || text.conceptStock}
                            </span>
                            {stock.code ? (
                              <button
                                type="button"
                                aria-label={formatUiText(text.analyzeStock, { stock: stock.name || stock.code })}
                                className="inline-flex min-h-11 items-center gap-1 rounded-lg border border-cyan/30 bg-cyan/10 px-3 text-xs font-semibold text-cyan transition-colors hover:border-cyan hover:bg-cyan/15 hover:text-foreground"
                                onClick={() => handleAnalyzeHotspotStock(stock)}
                              >
                                <Play className="h-3 w-3" />
                                {text.analyze}
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
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            ) : null}
          </div>
        ) : null}
      </section>

      <section className="rounded-2xl border border-cyan/35 bg-card/95 p-4 shadow-soft-card">
        <div className="mb-4 flex items-center justify-between gap-3">
          <div>
            <h2 className="text-sm font-semibold text-foreground">{text.selectStrategy}</h2>
            <p className="mt-1 text-xs text-secondary-text">{text.strategyDescription}</p>
          </div>
          <span className="rounded-full border border-cyan/30 bg-cyan/10 px-3 py-1 text-xs font-semibold text-cyan">
            {selectedStrategyTag}
          </span>
        </div>

        <div className="grid gap-2 md:grid-cols-2 xl:grid-cols-4">
          {strategiesResource.status === 'error' ? (
            <div className="rounded-xl border border-warning/30 bg-warning/10 p-4 text-sm text-warning">
              {strategyLoadError || text.strategyLoadFailed}
            </div>
          ) : loadingStrategies ? (
            <div className="rounded-xl border border-dashed border-border bg-surface/70 p-4 text-sm text-secondary-text">
              {text.loadingStrategies}
            </div>
          ) : strategies.length === 0 ? (
            <div className="rounded-xl border border-dashed border-border bg-surface/70 p-4 text-sm text-secondary-text">
              {text.strategiesUnavailable}
            </div>
          ) : (
            strategies.map((item) => {
              const selected = item.id === strategy;
              const display = getStrategyDisplay(item, language);
              return (
                <button
                  key={item.id}
                  className={`min-h-28 rounded-xl border p-4 text-left transition-all ${
                    selected
                      ? 'border-cyan bg-cyan/10 shadow-[0_0_0_1px_hsl(var(--primary)/0.15),0_16px_36px_hsl(var(--primary)/0.12)]'
                      : 'border-border/80 bg-surface/70 hover:border-cyan/45 hover:bg-hover/70'
                  }`}
                  type="button"
                  disabled={loading}
                  onClick={() => handleStrategyChange(item.id)}
                >
                  <span className="text-base font-semibold text-foreground">{display.name}</span>
                  <span className="mt-2 block text-sm leading-6 text-secondary-text">{display.description}</span>
                  <span className="mt-3 inline-flex text-xs font-semibold text-cyan">
                    {display.category}
                  </span>
                </button>
              );
            })
          )}
        </div>
      </section>

      <section className="rounded-2xl border border-border bg-card/95 p-4 shadow-soft-card">
        <div className="mb-4 flex items-center gap-2 text-sm font-semibold text-foreground">
          <SlidersHorizontal className="h-4 w-4 text-cyan" />
          {text.parameters}
        </div>

        <div className="grid gap-4 lg:grid-cols-[1fr_1.2fr_180px_auto] lg:items-end">
          <Select
            label={text.market}
            value={market}
            disabled={loading}
            onChange={handleMarketChange}
            options={markets.map((item) => ({ value: item.id, label: item.label }))}
          />

          <label className="space-y-2 text-xs font-medium text-secondary-text">
            {text.strategyParameter}
            <input
              className="h-11 w-full rounded-xl border border-border bg-surface px-3 text-sm text-foreground outline-none transition-colors focus:border-cyan"
              value={strategy}
              disabled={loading}
              onChange={(event) => handleStrategyChange(event.target.value)}
            />
          </label>

          <label className="space-y-2 text-xs font-medium text-secondary-text">
            {text.resultCount}
            <input
              className="h-11 w-full rounded-xl border border-border bg-surface px-3 text-sm text-foreground outline-none transition-colors focus:border-cyan"
              type="number"
              min={1}
              max={100}
              value={maxResults}
              disabled={loading}
              onChange={(event) => handleMaxResultsChange(Number(event.target.value))}
            />
          </label>

          <Button
            className="h-11 min-w-40"
            isLoading={loading}
            loadingText={text.screening}
            disabled={!isScreeningEnabled || loading}
            onClick={() => void handleSubmit()}
          >
            <Play className="h-4 w-4" />
            {text.run}
          </Button>
        </div>
      </section>

      <section className="rounded-2xl border border-border bg-card/95 p-4 shadow-soft-card">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-3">
            <span
              className={`grid h-7 w-7 place-items-center rounded-full ${
                candidates.length > 0 ? 'text-success' : isScreeningEnabled ? 'text-cyan' : 'text-warning'
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
            <span>{text.runId}: {screenMeta?.runId || '-'}</span>
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
      </section>

      {screenMeta && alertMessages.length > 0 ? (
        <InlineAlert
          variant={llmDegraded ? 'warning' : 'info'}
          title={llmDegraded ? text.llmDegraded : text.alphaSiftNotice}
          message={<ScreenAlertMessage messages={alertMessages} />}
        />
      ) : null}

      <section className="rounded-2xl border border-border bg-card/95 p-4 shadow-soft-card">
        <div className="mb-5 flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <h2 className="text-base font-semibold text-foreground">{text.results}</h2>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-secondary-text">
              {text.resultsDescription}
            </p>
          </div>
          <div className="flex items-center gap-2 rounded-full border border-border bg-surface px-3 py-2 text-xs text-secondary-text">
            <Search className="h-4 w-4 text-cyan" />
            {formatUiText(text.candidateCount, { count: candidates.length })}
          </div>
        </div>

        {candidates.length === 0 ? (
          <div className="rounded-xl border border-dashed border-border bg-surface/70 px-5 py-10 text-center">
            <p className="text-sm font-medium text-foreground">{text.noResults}</p>
            <p className="mt-2 text-sm text-secondary-text">{text.noResultsDescription}</p>
          </div>
        ) : (
          <div className="overflow-x-auto rounded-xl border border-border" role="region" aria-label={text.results} tabIndex={0}>
            <table className="w-full min-w-[860px] border-collapse text-sm">
              <thead className="bg-surface text-left text-xs text-secondary-text">
                <tr>
                  <th className="w-14 px-4 py-3 font-semibold">#</th>
                  <th className="px-4 py-3 font-semibold">{text.code}</th>
                  <th className="px-4 py-3 font-semibold">{text.name}</th>
                  <th className="px-4 py-3 font-semibold">{text.industry}</th>
                  <th className="px-4 py-3 font-semibold">{text.price}</th>
                  <th className="px-4 py-3 font-semibold">{text.change}</th>
                  <th className="px-4 py-3 font-semibold">{text.score}</th>
                  <th className="px-4 py-3 font-semibold">LLM</th>
                  <th className="px-4 py-3 font-semibold">{text.risk}</th>
                  <th className="px-4 py-3 font-semibold">{text.details}</th>
                </tr>
              </thead>
              <tbody>
                {candidates.map((item) => {
                  const expanded = expandedCode === item.code;
                  const factors = getFactorEntries(item);
                  const llmInsightAvailable = hasLlmInsight(item);
                  const llmFallbackText =
                    llmDegraded && !llmInsightAvailable
                      ? text.llmFallbackRow
                      : text.noLlmJudgement;
                  const dsaWarnings = item.dsaContext?.warnings || [];
                  const dsaNews = item.dsaNews || [];
                  return (
                    <Fragment key={`${item.rank}-${item.code}`}>
                      <tr className="border-t border-border align-top transition-colors hover:bg-hover/50">
                        <td className="px-4 py-3 text-secondary-text">{item.rank}</td>
                        <td className="px-4 py-3 font-mono font-semibold text-foreground">{item.code}</td>
                        <td className="px-4 py-3 font-semibold text-foreground">{item.name || '-'}</td>
                        <td className="px-4 py-3 text-secondary-text">{item.industry || '-'}</td>
                        <td className="px-4 py-3 text-secondary-text">{formatNumber(item.price)}</td>
                        <td className="px-4 py-3 text-secondary-text">{formatNumber(item.changePct)}%</td>
                        <td className="px-4 py-3 font-bold text-cyan">{formatScore(item.score)}</td>
                        <td className="px-4 py-3 text-secondary-text">{llmDegraded ? text.notReranked : formatScore(item.llmScore)}</td>
                        <td className="px-4 py-3">
                          <span className="rounded-lg bg-success/10 px-2.5 py-1 text-xs font-semibold text-success">
                            {item.riskLevel || 'unknown'}
                          </span>
                        </td>
                        <td className="px-4 py-3">
                          <button
                            className="min-h-11 min-w-11 text-sm font-semibold text-cyan transition-colors hover:text-foreground"
                            type="button"
                            aria-expanded={expanded}
                            onClick={() => setExpandedCode(expanded ? null : item.code)}
                          >
                            {expanded ? text.collapse : text.expand}
                          </button>
                        </td>
                      </tr>
                      {expanded ? (
                        <tr className="border-t border-border bg-surface/45">
                          <td colSpan={10} className="px-4 py-4">
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
                                        <div key={key} className="rounded-lg border border-border bg-card px-3 py-2">
                                          <span className="block text-xs text-secondary-text">{key}</span>
                                          <span className="text-sm font-semibold text-foreground">{formatNumber(value)}</span>
                                        </div>
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
                                    {item.llmWatchItems?.length ? item.llmWatchItems.join(language === 'en' ? ', ' : '，') : llmDegraded ? text.degradedNoValue : text.none}
                                  </p>
                                </div>
                                <div>
                                  <p className="text-xs font-semibold text-secondary-text">{text.catalysts}</p>
                                  <p className="mt-1 text-sm text-foreground">
                                    {item.llmCatalysts?.length ? item.llmCatalysts.join(language === 'en' ? ', ' : '，') : llmDegraded ? text.degradedNoValue : text.none}
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
                                    <p className="mt-1 text-sm text-secondary-text">{dsaWarnings.join('，')}</p>
                                  </div>
                                ) : null}
                              </div>
                            </div>
                          </td>
                        </tr>
                      ) : null}
                    </Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </AppPage>
  );
};

export default StockScreeningPage;
