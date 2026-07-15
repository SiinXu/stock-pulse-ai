import type React from 'react';
import { useState, useEffect, useCallback, useRef } from 'react';
import { Check, Minus, X } from 'lucide-react';
import { useSearchParams } from 'react-router-dom';
import { backtestApi } from '../api/backtest';
import type { ParsedApiError } from '../api/error';
import { getParsedApiError } from '../api/error';
import { ApiErrorAlert, Card, Badge, EmptyState, Pagination, Select, StatusDot, Tooltip } from '../components/common';
import { useUiLanguage } from '../contexts/UiLanguageContext';
import { createRequestKey, useAsyncResource } from '../hooks/useAsyncResource';
import { formatUiText, type UiLanguage } from '../i18n/uiText';
import {
  BACKTEST_DIRECTION_EXPECTED_LABELS,
  BACKTEST_MOVEMENT_LABELS,
  BACKTEST_OUTCOME_LABELS,
  BACKTEST_PHASE_FILTER_OPTIONS,
  BACKTEST_PHASE_LABELS,
  BACKTEST_STATUS_LABELS,
  BACKTEST_TEXT,
} from '../locales/backtest';
import type {
  BacktestResultItem,
  BacktestRunResponse,
  PerformanceMetrics,
  BacktestPhaseFilter,
} from '../types/backtest';
import { buildDecisionActionLabelMap, getDecisionActionLabel } from '../utils/decisionAction';
import { getMarketPhaseSummaryLabel } from '../utils/marketPhase';

const BACKTEST_INPUT_CLASS =
  'h-8 w-full rounded-[10px] border border-border bg-transparent px-3 text-xs text-foreground placeholder:text-muted-text transition-colors duration-200 focus:outline-none focus:border-muted-text disabled:cursor-not-allowed disabled:opacity-60';
const BACKTEST_COMPACT_INPUT_CLASS =
  'h-8 rounded-[10px] border border-border bg-transparent px-3 text-xs text-foreground placeholder:text-muted-text transition-colors duration-200 focus:outline-none focus:border-muted-text disabled:cursor-not-allowed disabled:opacity-60';
type BacktestText = (typeof BACKTEST_TEXT)[UiLanguage];

interface BacktestResultsResourceData {
  items: BacktestResultItem[];
  total: number;
  page: number;
}

interface BacktestPerformanceResourceData {
  overall: PerformanceMetrics | null;
  stock: PerformanceMetrics | null;
}

const EMPTY_BACKTEST_RESULTS: BacktestResultsResourceData = { items: [], total: 0, page: 1 };
const EMPTY_BACKTEST_PERFORMANCE: BacktestPerformanceResourceData = { overall: null, stock: null };
const BACKTEST_PHASE_FILTERS = new Set<BacktestPhaseFilter>(['all', 'premarket', 'intraday', 'postmarket', 'unknown']);
const BACKTEST_DATE_PATTERN = /^\d{4}-\d{2}-\d{2}$/;
const BACKTEST_MAX_WINDOW_DAYS = 120;

interface BacktestRouteState {
  code?: string;
  evalWindowDays?: number;
  analysisDateFrom?: string;
  analysisDateTo?: string;
  phase: BacktestPhaseFilter;
  page: number;
}

// ============ Helpers ============

function pct(value?: number | null): string {
  if (value == null) return '--';
  return `${value.toFixed(1)}%`;
}

function phaseLabel(row: BacktestResultItem, language: UiLanguage): string {
  const label = getMarketPhaseSummaryLabel(row.marketPhaseSummary, language);
  if (label) {
    return label
      .replace('市场阶段: ', '')
      .replace('市场阶段：', '')
      .replace('Market phase: ', '');
  }
  return (row.marketPhase ? BACKTEST_PHASE_LABELS[language][row.marketPhase] : undefined) || row.marketPhase || '--';
}

function normalizeBacktestCode(value: string): string | undefined {
  const trimmed = value.trim();
  if (!trimmed) return undefined;
  return trimmed.toUpperCase();
}

function parseEvalWindowDays(value: string): number | undefined {
  const trimmed = value.trim();
  if (!trimmed) {
    return undefined;
  }

  const parsed = Number(trimmed);
  if (!Number.isInteger(parsed) || parsed < 1 || parsed > BACKTEST_MAX_WINDOW_DAYS) {
    return undefined;
  }

  return parsed;
}

function parsePositiveInteger(value: string | null, fallback: number): number {
  const raw = String(value ?? '');
  if (!/^\d+$/.test(raw)) return fallback;
  const parsed = Number(raw);
  return Number.isSafeInteger(parsed) && parsed >= 1 ? parsed : fallback;
}

function parseBacktestDate(value: string | null): string | undefined {
  if (!value || !BACKTEST_DATE_PATTERN.test(value)) return undefined;
  const parsed = new Date(`${value}T00:00:00Z`);
  return !Number.isNaN(parsed.getTime()) && parsed.toISOString().slice(0, 10) === value
    ? value
    : undefined;
}

function parseBacktestRoute(searchParams: URLSearchParams): BacktestRouteState {
  const rawPhase = searchParams.get('phase') as BacktestPhaseFilter | null;
  return {
    code: normalizeBacktestCode(searchParams.get('code') ?? ''),
    evalWindowDays: parseEvalWindowDays(searchParams.get('window') ?? ''),
    analysisDateFrom: parseBacktestDate(searchParams.get('from')),
    analysisDateTo: parseBacktestDate(searchParams.get('to')),
    phase: rawPhase && BACKTEST_PHASE_FILTERS.has(rawPhase) ? rawPhase : 'all',
    page: parsePositiveInteger(searchParams.get('page'), 1),
  };
}

function writeBacktestRoute(current: URLSearchParams, state: BacktestRouteState): URLSearchParams {
  const next = new URLSearchParams(current);
  const write = (key: string, value: string | number | undefined, omit?: boolean) => {
    if (value === undefined || value === '' || omit) {
      next.delete(key);
    } else {
      next.set(key, String(value));
    }
  };
  write('code', state.code);
  write('window', state.evalWindowDays);
  write('from', state.analysisDateFrom);
  write('to', state.analysisDateTo);
  write('phase', state.phase, state.phase === 'all');
  write('page', state.page, state.page === 1);
  return next;
}

const backtestRouteKey = (state: BacktestRouteState): string => JSON.stringify([
  state.code ?? '',
  state.evalWindowDays ?? null,
  state.analysisDateFrom ?? '',
  state.analysisDateTo ?? '',
  state.phase,
  state.page,
]);

function labelFromMap(value: string | null | undefined, labels: Record<string, string>): string {
  if (!value) return '--';
  return labels[value] ?? value;
}

function outcomeBadge(outcome: string | undefined, language: UiLanguage) {
  const labels = BACKTEST_OUTCOME_LABELS[language];
  if (!outcome) return <Badge variant="default">--</Badge>;
  switch (outcome) {
    case 'win':
      return <Badge variant="success" glow>{labels.win}</Badge>;
    case 'loss':
      return <Badge variant="danger" glow>{labels.loss}</Badge>;
    case 'neutral':
      return <Badge variant="warning">{labels.neutral}</Badge>;
    default:
      return <Badge variant="default">{outcome}</Badge>;
  }
}

function statusBadge(status: string, language: UiLanguage) {
  const labels = BACKTEST_STATUS_LABELS[language];
  switch (status) {
    case 'completed':
      return <Badge variant="success">{labels.completed}</Badge>;
    case 'insufficient':
    case 'insufficient_data':
      return <Badge variant="warning">{labels.insufficient}</Badge>;
    case 'error':
      return <Badge variant="danger">{labels.error}</Badge>;
    default:
      return <Badge variant="default">{status}</Badge>;
  }
}

function actualMovementBadge(movement: string | null | undefined, language: UiLanguage) {
  const labels = BACKTEST_MOVEMENT_LABELS[language];
  switch (movement) {
    case 'up':
      return <Badge variant="success">{labels.up}</Badge>;
    case 'down':
      return <Badge variant="danger">{labels.down}</Badge>;
    case 'flat':
      return <Badge variant="warning">{labels.flat}</Badge>;
    default:
      return <Badge variant="default">--</Badge>;
  }
}

function boolIcon(value: boolean | null | undefined, text: BacktestText) {
  if (value === true) {
    return (
      <span
        className="backtest-status-chip backtest-status-chip-success"
        aria-label={text.yes}
      >
        <StatusDot tone="success" className="backtest-status-chip-dot" />
        <Check className="h-3.5 w-3.5" />
      </span>
    );
  }

  if (value === false) {
    return (
      <span
        className="backtest-status-chip backtest-status-chip-danger"
        aria-label={text.no}
      >
        <StatusDot tone="danger" className="backtest-status-chip-dot" />
        <X className="h-3.5 w-3.5" />
      </span>
    );
  }

  return (
    <span
      className="backtest-status-chip backtest-status-chip-neutral"
      aria-label={text.unknown}
    >
      <StatusDot tone="neutral" className="backtest-status-chip-dot" />
      <Minus className="h-3.5 w-3.5" />
    </span>
  );
}

// ============ Metric Row ============

const MetricRow: React.FC<{ label: string; value: string; accent?: boolean }> = ({ label, value, accent }) => (
  <div className="backtest-metric-row">
    <span className="label">{label}</span>
    <span className={`value ${accent ? 'accent' : ''}`}>{value}</span>
  </div>
);

function phaseBreakdownText(metrics: PerformanceMetrics, language: UiLanguage): string | null {
  const breakdown = metrics.diagnostics?.phaseBreakdown;
  if (!breakdown || typeof breakdown !== 'object') return null;
  const item = breakdown as Record<string, unknown>;
  const phaseLabels = BACKTEST_PHASE_LABELS[language];
  const parts = [
    [phaseLabels.premarket, item.premarket],
    [phaseLabels.intraday, item.intraday],
    [phaseLabels.postmarket, item.postmarket],
    [phaseLabels.unknown, item.unknown],
  ]
    .map(([label, value]) => `${label} ${Number(value || 0)}`)
    .join(' / ');
  return parts;
}

// ============ Performance Card ============

const PerformanceCard: React.FC<{ metrics: PerformanceMetrics; title: string; language: UiLanguage }> = ({ metrics, title, language }) => {
  const text = BACKTEST_TEXT[language];
  const phaseText = phaseBreakdownText(metrics, language);
  return (
    <Card variant="gradient" padding="md" className="animate-fade-in">
      <div className="mb-3">
        <span className="label-uppercase">{title}</span>
      </div>
      <MetricRow label={text.directionAccuracy} value={pct(metrics.directionAccuracyPct)} accent />
      <MetricRow label={text.winRate} value={pct(metrics.winRatePct)} accent />
      <MetricRow label={text.avgSimulatedReturn} value={pct(metrics.avgSimulatedReturnPct)} />
      <MetricRow label={text.avgStockReturn} value={pct(metrics.avgStockReturnPct)} />
      <MetricRow label={text.stopLossTriggerRate} value={pct(metrics.stopLossTriggerRate)} />
      <MetricRow label={text.takeProfitTriggerRate} value={pct(metrics.takeProfitTriggerRate)} />
      <MetricRow label={text.avgDaysToFirstHit} value={metrics.avgDaysToFirstHit != null ? metrics.avgDaysToFirstHit.toFixed(1) : '--'} />
      <div className="backtest-metric-footer">
        <span className="text-xs text-muted-text">{text.evaluationCount}</span>
        <span className="text-xs text-secondary-text font-mono">
          {Number(metrics.completedCount)} / {Number(metrics.totalEvaluations)}
        </span>
      </div>
      <div className="flex items-center justify-between">
        <span className="text-xs text-muted-text">{text.outcomeSummary}</span>
        <span className="text-xs font-mono">
          <span className="text-success">{metrics.winCount}</span>
          {' / '}
          <span className="text-danger">{metrics.lossCount}</span>
          {' / '}
          <span className="text-warning">{metrics.neutralCount}</span>
        </span>
      </div>
      {phaseText ? (
        <div className="mt-3 border-t border-white/10 pt-2 text-xs text-muted-text">
          {formatUiText(text.phaseDistribution, { text: phaseText })}
        </div>
      ) : null}
    </Card>
  );
};

// ============ Run Summary ============

const RunSummary: React.FC<{ data: BacktestRunResponse; language: UiLanguage }> = ({ data, language }) => {
  const text = BACKTEST_TEXT[language];
  return (
  <div className="backtest-summary animate-fade-in">
    <span className="label">{text.processed} <span className="value">{data.processed}</span></span>
    <span className="label">{text.saved} <span className="value primary">{data.saved}</span></span>
    <span className="label">{text.completed} <span className="value success">{data.completed}</span></span>
    <span className="label">{text.insufficient} <span className="value warning">{data.insufficient}</span></span>
    {data.errors > 0 && (
      <span className="label">{text.errors} <span className="value danger">{data.errors}</span></span>
    )}
    {data.message && (
      <span className="label message">{data.message}</span>
    )}
  </div>
  );
};

// ============ Main Page ============

const BacktestPage: React.FC = () => {
  const [searchParams, setSearchParams] = useSearchParams();
  const { language, t } = useUiLanguage();
  const text = BACKTEST_TEXT[language];
  const phaseFilterOptions = BACKTEST_PHASE_FILTER_OPTIONS[language];
  const actionLabels = buildDecisionActionLabelMap(t);
  const initialRouteStateRef = useRef<BacktestRouteState | null>(null);
  if (initialRouteStateRef.current === null) {
    initialRouteStateRef.current = parseBacktestRoute(searchParams);
  }
  const initialRouteState = initialRouteStateRef.current;
  const appliedRouteState = parseBacktestRoute(searchParams);
  const routeSearch = searchParams.toString();
  const preserveDraftRouteSyncRef = useRef<string | null>(null);

  // Set page title
  useEffect(() => {
    document.title = text.documentTitle;
  }, [text.documentTitle]);

  // Input state
  const [codeFilter, setCodeFilter] = useState(initialRouteState.code ?? '');
  const [analysisDateFrom, setAnalysisDateFrom] = useState(initialRouteState.analysisDateFrom ?? '');
  const [analysisDateTo, setAnalysisDateTo] = useState(initialRouteState.analysisDateTo ?? '');
  const [phaseFilter, setPhaseFilter] = useState<BacktestPhaseFilter>(initialRouteState.phase);
  const [evalDays, setEvalDays] = useState(
    initialRouteState.evalWindowDays === undefined ? '' : String(initialRouteState.evalWindowDays),
  );
  const [forceRerun, setForceRerun] = useState(false);
  const [isRunning, setIsRunning] = useState(false);
  const [runResult, setRunResult] = useState<BacktestRunResponse | null>(null);
  const [runError, setRunError] = useState<ParsedApiError | null>(null);

  // Results state
  const [resultsResource, resultsRequests] = useAsyncResource<BacktestResultsResourceData, ParsedApiError>({
    initialData: EMPTY_BACKTEST_RESULTS,
    isEmpty: (data) => data.items.length === 0,
  });
  const results = resultsResource.data.items;
  const totalResults = resultsResource.data.total;
  const currentPage = resultsResource.data.page;
  const isLoadingResults = resultsResource.status === 'idle' || resultsResource.status === 'loading';
  const pageSize = 20;

  // Performance state
  const [performanceResource, performanceRequests] = useAsyncResource<BacktestPerformanceResourceData, ParsedApiError>({
    initialData: EMPTY_BACKTEST_PERFORMANCE,
    isEmpty: (data) => data.overall == null && data.stock == null,
  });
  const overallPerf = performanceResource.data.overall;
  const stockPerf = performanceResource.data.stock;
  const isLoadingPerf = performanceResource.status === 'idle' || performanceResource.status === 'loading';
  const effectiveWindowDays = appliedRouteState.evalWindowDays ?? overallPerf?.evalWindowDays;
  const isNextDayValidation = effectiveWindowDays === 1;
  const showNextDayActualColumns = isNextDayValidation;

  // Fetch results
  const fetchResults = useCallback(async (
    page = 1,
    code?: string,
    windowDays?: number,
    startDate?: string,
    endDate?: string,
    phase?: BacktestPhaseFilter,
  ) => {
    const query = {
      code: code || undefined,
      evalWindowDays: windowDays,
      analysisDateFrom: startDate || undefined,
      analysisDateTo: endDate || undefined,
      analysisPhase: phase && phase !== 'all' ? phase : undefined,
      page,
      limit: pageSize,
    };
    const request = resultsRequests.begin(
      createRequestKey('backtest-results', [
        query.code ?? null,
        query.evalWindowDays ?? null,
        query.analysisDateFrom ?? null,
        query.analysisDateTo ?? null,
        query.analysisPhase ?? null,
        query.page,
        query.limit,
      ]),
      { retainData: false },
    );
    try {
      const response = await backtestApi.getResults(query);
      resultsRequests.resolve(request, {
        items: response.items,
        total: response.total,
        page: response.page,
      });
      return resultsRequests.isCurrent(request) ? response : null;
    } catch (err) {
      console.error('Failed to fetch backtest results:', err);
      resultsRequests.reject(request, getParsedApiError(err));
      return null;
    }
  }, [resultsRequests]);

  // Fetch performance
  const fetchPerformance = useCallback(async (
    code?: string,
    windowDays?: number,
    startDate?: string,
    endDate?: string,
    phase?: BacktestPhaseFilter,
  ) => {
    const query = {
      evalWindowDays: windowDays,
      analysisDateFrom: startDate || undefined,
      analysisDateTo: endDate || undefined,
      analysisPhase: phase && phase !== 'all' ? phase : undefined,
    };
    const request = performanceRequests.begin(
      createRequestKey('backtest-performance', [
        code ?? null,
        query.evalWindowDays ?? null,
        query.analysisDateFrom ?? null,
        query.analysisDateTo ?? null,
        query.analysisPhase ?? null,
      ]),
      { retainData: false },
    );
    try {
      const overall = await backtestApi.getOverallPerformance(query);
      if (!performanceRequests.isCurrent(request)) {
        return null;
      }

      let stock: PerformanceMetrics | null = null;
      if (code) {
        stock = await backtestApi.getStockPerformance(code, query);
      }
      const data = { overall, stock };
      return performanceRequests.resolve(request, data) ? data : null;
    } catch (err) {
      console.error('Failed to fetch performance:', err);
      return performanceRequests.reject(request, getParsedApiError(err))
        ? EMPTY_BACKTEST_PERFORMANCE
        : null;
    }
  }, [performanceRequests]);

  const loadAppliedRoute = useCallback((state: BacktestRouteState) => {
    void fetchResults(
      state.page,
      state.code,
      state.evalWindowDays,
      state.analysisDateFrom,
      state.analysisDateTo,
      state.phase,
    );
    void fetchPerformance(
      state.code,
      state.evalWindowDays,
      state.analysisDateFrom,
      state.analysisDateTo,
      state.phase,
    ).then((performance) => {
      const backendWindowDays = performance?.overall?.evalWindowDays;
      if (state.evalWindowDays !== undefined || backendWindowDays === undefined) return;

      setEvalDays((current) => current || String(backendWindowDays));
      setSearchParams((current) => {
        if (backtestRouteKey(parseBacktestRoute(current)) !== backtestRouteKey(state)) {
          return current;
        }
        const next = writeBacktestRoute(current, { ...state, evalWindowDays: backendWindowDays });
        if (next.toString() === current.toString()) return current;
        preserveDraftRouteSyncRef.current = next.toString();
        return next;
      }, { replace: true });
    });
  }, [fetchPerformance, fetchResults, setSearchParams]);

  const applyRoute = useCallback((state: BacktestRouteState, options?: { replace?: boolean }) => {
    const normalizedState: BacktestRouteState = {
      ...state,
      code: normalizeBacktestCode(state.code ?? ''),
      phase: BACKTEST_PHASE_FILTERS.has(state.phase) ? state.phase : 'all',
      page: Math.max(1, Math.trunc(state.page)),
    };
    setCodeFilter(normalizedState.code ?? '');
    setEvalDays(normalizedState.evalWindowDays === undefined ? '' : String(normalizedState.evalWindowDays));
    setAnalysisDateFrom(normalizedState.analysisDateFrom ?? '');
    setAnalysisDateTo(normalizedState.analysisDateTo ?? '');
    setPhaseFilter(normalizedState.phase);
    const next = writeBacktestRoute(searchParams, normalizedState);
    if (next.toString() === routeSearch) {
      loadAppliedRoute(normalizedState);
      return;
    }
    setSearchParams(next, { replace: options?.replace ?? false });
  }, [loadAppliedRoute, routeSearch, searchParams, setSearchParams]);

  // URL search is the applied filter state. Browser navigation restores both
  // form controls and independently guarded results/performance resources.
  useEffect(() => {
    const current = new URLSearchParams(routeSearch);
    const state = parseBacktestRoute(current);
    const canonical = writeBacktestRoute(current, state);
    if (canonical.toString() !== routeSearch) {
      preserveDraftRouteSyncRef.current = null;
      setSearchParams(canonical, { replace: true });
      return;
    }
    const preserveDraft = preserveDraftRouteSyncRef.current === routeSearch;
    preserveDraftRouteSyncRef.current = null;
    if (!preserveDraft) {
      setCodeFilter(state.code ?? '');
      setEvalDays(state.evalWindowDays === undefined ? '' : String(state.evalWindowDays));
      setAnalysisDateFrom(state.analysisDateFrom ?? '');
      setAnalysisDateTo(state.analysisDateTo ?? '');
      setPhaseFilter(state.phase);
    }
    loadAppliedRoute(state);
  }, [loadAppliedRoute, routeSearch, setSearchParams]);

  // Run backtest
  const handleRun = async () => {
    setIsRunning(true);
    setRunResult(null);
    setRunError(null);
    try {
      const code = normalizeBacktestCode(codeFilter);
      const requestedEvalWindowDays = parseEvalWindowDays(evalDays);
      const dateFrom = analysisDateFrom || undefined;
      const dateTo = analysisDateTo || undefined;
      const response = await backtestApi.run({
        code,
        force: forceRerun || undefined,
        minAgeDays: forceRerun ? 0 : undefined,
        evalWindowDays: requestedEvalWindowDays,
        analysisDateFrom: dateFrom,
        analysisDateTo: dateTo,
      });
      setRunResult(response);
      const effectiveEvalWindowDays =
        response.appliedEvalWindowDays
        ?? requestedEvalWindowDays;
      applyRoute({
        code,
        evalWindowDays: effectiveEvalWindowDays,
        analysisDateFrom: dateFrom,
        analysisDateTo: dateTo,
        phase: phaseFilter,
        page: 1,
      });
    } catch (err) {
      setRunError(getParsedApiError(err));
    } finally {
      setIsRunning(false);
    }
  };

  // Phase is a result-only filter (backtestApi.run never receives it), so apply
  // it immediately to the fetched results/performance rather than on Run.
  const handlePhaseChange = (value: BacktestPhaseFilter) => {
    applyRoute({
      code: normalizeBacktestCode(codeFilter),
      evalWindowDays: parseEvalWindowDays(evalDays),
      analysisDateFrom: analysisDateFrom || undefined,
      analysisDateTo: analysisDateTo || undefined,
      phase: value,
      page: 1,
    });
  };

  // Filter by code
  const handleFilter = () => {
    applyRoute({
      code: normalizeBacktestCode(codeFilter),
      evalWindowDays: parseEvalWindowDays(evalDays),
      analysisDateFrom: analysisDateFrom || undefined,
      analysisDateTo: analysisDateTo || undefined,
      phase: phaseFilter,
      page: 1,
    });
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      handleFilter();
    }
  };

  const handleShowNextDay = () => {
    applyRoute({
      code: normalizeBacktestCode(codeFilter),
      evalWindowDays: 1,
      analysisDateFrom: analysisDateFrom || undefined,
      analysisDateTo: analysisDateTo || undefined,
      phase: phaseFilter,
      page: 1,
    });
  };

  // Pagination
  const totalPages = Math.ceil(totalResults / pageSize);
  const handlePageChange = (page: number) => {
    applyRoute({ ...appliedRouteState, page });
  };

  return (
    <div className="min-h-full flex flex-col rounded-[1.5rem] bg-transparent">
      {/* Header */}
      <header className="flex-shrink-0 border-b border-white/5 px-3 py-3 sm:px-4">
        <div className="flex flex-wrap items-center gap-2">
          <div className="relative min-w-0 flex-[1_1_220px]">
            <input
              type="text"
              value={codeFilter}
              onChange={(e) => setCodeFilter(e.target.value.toUpperCase())}
              onKeyDown={handleKeyDown}
              placeholder={text.codePlaceholder}
              disabled={isRunning}
              className={BACKTEST_INPUT_CLASS}
            />
          </div>
          <button
            type="button"
            onClick={handleFilter}
            disabled={isLoadingResults}
            className="btn-secondary flex items-center gap-1.5 whitespace-nowrap"
          >
            {text.filter}
          </button>
          <div className="flex flex-col gap-1 whitespace-nowrap">
            <span className="text-xs text-muted-text">{text.evalWindow}</span>
            <input
              type="number"
              min={1}
              max={BACKTEST_MAX_WINDOW_DAYS}
              value={evalDays}
              onChange={(e) => setEvalDays(e.target.value)}
              placeholder="10"
              disabled={isRunning}
              className={`${BACKTEST_COMPACT_INPUT_CLASS} w-24 text-center tabular-nums`}
            />
          </div>
          <div className="flex flex-col gap-1 whitespace-nowrap">
            <span className="text-xs text-muted-text">{text.startDate}</span>
            <input
              type="date"
              aria-label={text.startDateAria}
              value={analysisDateFrom}
              onChange={(e) => setAnalysisDateFrom(e.target.value)}
              onKeyDown={handleKeyDown}
              disabled={isRunning}
              className={`${BACKTEST_COMPACT_INPUT_CLASS} w-40 text-center tabular-nums`}
            />
          </div>
          <div className="flex flex-col gap-1 whitespace-nowrap">
            <span className="text-xs text-muted-text">{text.endDate}</span>
            <input
              type="date"
              aria-label={text.endDateAria}
              value={analysisDateTo}
              onChange={(e) => setAnalysisDateTo(e.target.value)}
              onKeyDown={handleKeyDown}
              disabled={isRunning}
              className={`${BACKTEST_COMPACT_INPUT_CLASS} w-40 text-center tabular-nums`}
            />
          </div>
          <button
            type="button"
            onClick={handleShowNextDay}
            disabled={isLoadingResults || isLoadingPerf}
            className={`backtest-force-btn ${isNextDayValidation ? 'active' : ''}`}
          >
            <span className="dot" />
            {text.oneDayValidation}
          </button>
          <button
            type="button"
            onClick={() => setForceRerun(!forceRerun)}
            disabled={isRunning}
            className={`backtest-force-btn ${forceRerun ? 'active' : ''}`}
          >
            <span className="dot" />
            {text.forceRerun}
          </button>
          <button
            type="button"
            onClick={handleRun}
            disabled={isRunning}
            className="btn-primary flex items-center gap-1.5 whitespace-nowrap"
          >
            {isRunning ? (
              <>
                <svg className="w-3.5 h-3.5 animate-spin" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                </svg>
                {text.running}
              </>
            ) : (
              text.runBacktest
            )}
          </button>
        </div>
        {runResult && (
          <div className="mt-2 max-w-4xl">
            <RunSummary data={runResult} language={language} />
          </div>
        )}
        {runError && (
          <ApiErrorAlert error={runError} className="mt-2 max-w-4xl" />
        )}
        <p className="mt-2 text-xs text-muted-text">
          {isNextDayValidation
            ? text.oneDayModeDescription
            : text.windowModeDescription}
        </p>
      </header>

      {/* Main content */}
      <main className="flex min-h-0 flex-1 flex-col gap-3 overflow-hidden p-3 lg:flex-row">
        {/* Left sidebar - Performance */}
        <div className="flex max-h-[38vh] flex-col gap-3 overflow-y-auto lg:max-h-none lg:w-60 lg:flex-shrink-0">
          {performanceResource.status === 'error' && performanceResource.error ? (
            <ApiErrorAlert error={performanceResource.error} />
          ) : isLoadingPerf ? (
            <div className="flex items-center justify-center py-8">
              <div className="backtest-spinner sm" />
            </div>
          ) : overallPerf ? (
            <>
              <PerformanceCard metrics={overallPerf} title={text.overallPerformance} language={language} />
              {stockPerf ? (
                <PerformanceCard metrics={stockPerf} title={`${stockPerf.code || appliedRouteState.code || ''}`} language={language} />
              ) : null}
            </>
          ) : (
            <EmptyState
              title={text.noMetricsTitle}
              description={text.noMetricsDescription}
              className="h-full min-h-[12rem] border-dashed bg-card/45 shadow-none"
            />
          )}
        </div>

        {/* Right content - Results table */}
        <section className="min-h-0 flex-1 overflow-y-auto">
          <div className="mb-3 flex flex-wrap items-end gap-2">
            <Select
              label={`${text.resultFilters} · ${text.phase}`}
              value={phaseFilter}
              onChange={(value) => handlePhaseChange(value as BacktestPhaseFilter)}
              disabled={isRunning}
              className="w-40"
              options={phaseFilterOptions.map((option) => ({ value: option.value, label: option.label }))}
            />
            <span className="pb-1.5 text-xs text-muted-text">{text.resultPhaseHint}</span>
          </div>
          {resultsResource.status === 'error' && resultsResource.error ? (
            <ApiErrorAlert error={resultsResource.error} className="mb-3" />
          ) : isLoadingResults ? (
            <div className="flex flex-col items-center justify-center h-64">
              <div className="backtest-spinner md" />
              <p className="mt-3 text-secondary-text text-sm">{text.loadingResults}</p>
            </div>
          ) : results.length === 0 ? (
            <EmptyState
              title={text.noResultsTitle}
              description={text.noResultsDescription}
              className="backtest-empty-state border-dashed"
              icon={(
                <svg className="h-6 w-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
                </svg>
              )}
            />
          ) : (
            <div className="animate-fade-in">
              <div className="backtest-table-toolbar">
                <div className="backtest-table-toolbar-meta">
                  <span className="label-uppercase">{isNextDayValidation ? text.nextDayValidation : text.resultSet}</span>
                  <span className="text-xs text-secondary-text">
                    {appliedRouteState.code ? formatUiText(text.filteredStock, { code: appliedRouteState.code }) : text.allStocks}
                    {appliedRouteState.evalWindowDays ? ` · ${formatUiText(text.dayWindow, { days: appliedRouteState.evalWindowDays })}` : ''}
                    {appliedRouteState.phase !== 'all' ? ` · ${phaseFilterOptions.find((item) => item.value === appliedRouteState.phase)?.label ?? appliedRouteState.phase}` : ''}
                    {appliedRouteState.analysisDateFrom ? ` · ${formatUiText(text.fromDate, { date: appliedRouteState.analysisDateFrom })}` : ''}
                    {appliedRouteState.analysisDateTo ? ` · ${formatUiText(text.toDate, { date: appliedRouteState.analysisDateTo })}` : ''}
                  </span>
                </div>
                <span className="backtest-table-scroll-hint">{text.scrollHint}</span>
              </div>
              <div className="backtest-table-wrapper">
                <table className="backtest-table min-w-[900px] w-full text-sm">
                  <thead className="backtest-table-head">
                    <tr className="text-left">
                      <th className="backtest-table-head-cell">{text.stock}</th>
                      <th className="backtest-table-head-cell">{text.analysisDate}</th>
                      <th className="backtest-table-head-cell">{text.phase}</th>
                      <th className="backtest-table-head-cell">{text.aiPrediction}</th>
                      <th className="backtest-table-head-cell">
                        {showNextDayActualColumns ? text.actualPerformance : text.windowReturn}
                      </th>
                      <th className="backtest-table-head-cell">
                        {showNextDayActualColumns ? text.accuracy : text.directionMatch}
                      </th>
                      <th className="backtest-table-head-cell">{text.result}</th>
                      <th className="backtest-table-head-cell">{text.status}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {results.map((row) => {
                      const actionLabel = getDecisionActionLabel(row.action, row.actionLabel, null, null, actionLabels);
                      const predictionParts = [actionLabel, row.trendPrediction, row.operationAdvice]
                        .filter((part): part is string => Boolean(part));

                      return (
                        <tr
                          key={row.analysisHistoryId}
                          className="backtest-table-row"
                        >
                          <td className="backtest-table-cell backtest-table-code">
                            <div className="flex flex-col">
                              <span>{row.code}</span>
                              <span className="text-xs text-muted-text">{row.stockName || '--'}</span>
                            </div>
                          </td>
                          <td className="backtest-table-cell text-secondary-text">{row.analysisDate || '--'}</td>
                          <td className="backtest-table-cell text-secondary-text">{phaseLabel(row, language)}</td>
                          <td className="backtest-table-cell max-w-[220px] text-foreground">
                            {predictionParts.length ? (
                              <Tooltip
                                content={predictionParts.join(' / ')}
                                focusable
                              >
                                <div className="flex flex-col gap-1">
                                  <span className="block truncate">{actionLabel || row.trendPrediction || '--'}</span>
                                  {actionLabel && row.trendPrediction && (
                                    <span className="block truncate text-xs text-secondary-text">{row.trendPrediction}</span>
                                  )}
                                  {row.operationAdvice && (
                                    <span className="block truncate text-xs text-secondary-text">{row.operationAdvice}</span>
                                  )}
                                </div>
                              </Tooltip>
                            ) : (
                              '--'
                            )}
                          </td>
                          <td className="backtest-table-cell">
                            <div className="flex items-center gap-2">
                              {actualMovementBadge(row.actualMovement, language)}
                              <span className={
                                row.actualReturnPct != null
                                  ? row.actualReturnPct > 0 ? 'text-success' : row.actualReturnPct < 0 ? 'text-danger' : 'text-secondary-text'
                                  : 'text-muted-text'
                              }>
                                {pct(row.actualReturnPct)}
                              </span>
                            </div>
                          </td>
                          <td className="backtest-table-cell">
                            <span className="flex items-center gap-2">
                              {boolIcon(row.directionCorrect, text)}
                              <span className="text-muted-text">
                                {row.directionExpected ? labelFromMap(row.directionExpected, BACKTEST_DIRECTION_EXPECTED_LABELS[language]) : ''}
                              </span>
                            </span>
                          </td>
                          <td className="backtest-table-cell">{outcomeBadge(row.outcome, language)}</td>
                          <td className="backtest-table-cell">{statusBadge(row.evalStatus, language)}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>

              {/* Pagination */}
              <div className="mt-4">
                <Pagination
                  currentPage={currentPage}
                  totalPages={totalPages}
                  onPageChange={handlePageChange}
                />
              </div>

              <p className="text-xs text-muted-text text-center mt-2">
                {formatUiText(text.totalPage, { total: totalResults, page: currentPage, pages: Math.max(totalPages, 1) })}
              </p>
            </div>
          )}
        </section>
      </main>
    </div>
  );
};

export default BacktestPage;
