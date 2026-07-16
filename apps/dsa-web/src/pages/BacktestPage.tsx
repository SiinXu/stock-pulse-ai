import type React from 'react';
import { useState, useEffect, useCallback, useRef } from 'react';
import { Check, Minus, X } from 'lucide-react';
import { backtestApi } from '../api/backtest';
import type { ParsedApiError } from '../api/error';
import { getParsedApiError } from '../api/error';
import { ApiErrorAlert, Card, Badge, EmptyState, Pagination, Select, StatusDot, Tooltip } from '../components/common';
import { useUiLanguage } from '../contexts/UiLanguageContext';
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
import { getMarketPhaseSummaryLabel, stripMarketPhaseSummaryPrefix } from '../utils/marketPhase';

const BACKTEST_INPUT_CLASS =
  'h-11 w-full rounded-[10px] border border-border bg-transparent px-3 text-xs text-foreground placeholder:text-muted-text transition-colors duration-200 focus:outline-none focus:border-muted-text disabled:cursor-not-allowed disabled:opacity-60';
const BACKTEST_COMPACT_INPUT_CLASS =
  'h-11 rounded-[10px] border border-border bg-transparent px-3 text-xs text-foreground placeholder:text-muted-text transition-colors duration-200 focus:outline-none focus:border-muted-text disabled:cursor-not-allowed disabled:opacity-60';
type BacktestText = (typeof BACKTEST_TEXT)[UiLanguage];

type BacktestFilterSnapshot = {
  code: string;
  windowDays?: number;
  startDate: string;
  endDate: string;
  phase: BacktestPhaseFilter;
  page: number;
};

const BACKTEST_PHASES = new Set<BacktestPhaseFilter>(['all', 'premarket', 'intraday', 'postmarket', 'unknown']);

function getInitialBacktestFilters(search = typeof window === 'undefined' ? '' : window.location.search): BacktestFilterSnapshot {
  const params = new URLSearchParams(search);
  const rawWindow = params.get('window') ?? '';
  const parsedWindow = parseEvalWindowDays(rawWindow);
  const rawPage = Number(params.get('page'));
  const rawPhase = params.get('phase') as BacktestPhaseFilter | null;
  return {
    code: normalizeBacktestCode(params.get('code') ?? '') ?? '',
    windowDays: parsedWindow && parsedWindow <= 120 ? parsedWindow : undefined,
    startDate: params.get('from') ?? '',
    endDate: params.get('to') ?? '',
    phase: rawPhase && BACKTEST_PHASES.has(rawPhase) ? rawPhase : 'all',
    page: Number.isInteger(rawPage) && rawPage > 0 ? rawPage : 1,
  };
}

function syncBacktestFiltersToUrl(filters: BacktestFilterSnapshot): void {
  if (typeof window === 'undefined') return;
  const url = new URL(window.location.href);
  const values: Record<string, string | undefined> = {
    code: normalizeBacktestCode(filters.code),
    window: filters.windowDays ? String(filters.windowDays) : undefined,
    from: filters.startDate || undefined,
    to: filters.endDate || undefined,
    phase: filters.phase === 'all' ? undefined : filters.phase,
    page: filters.page > 1 ? String(filters.page) : undefined,
  };
  Object.entries(values).forEach(([key, value]) => {
    if (value) url.searchParams.set(key, value);
    else url.searchParams.delete(key);
  });
  window.history.replaceState(window.history.state, '', `${url.pathname}${url.search}${url.hash}`);
}

// ============ Helpers ============

function pct(value?: number | null): string {
  if (value == null) return '--';
  return `${value.toFixed(1)}%`;
}

function phaseLabel(row: BacktestResultItem, language: UiLanguage): string {
  const label = getMarketPhaseSummaryLabel(row.marketPhaseSummary, language);
  if (label) {
    return stripMarketPhaseSummaryPrefix(label) ?? label;
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

  const parsed = parseInt(trimmed, 10);
  if (Number.isNaN(parsed) || parsed < 1) {
    return undefined;
  }

  return parsed;
}

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
  const { language, t } = useUiLanguage();
  const text = BACKTEST_TEXT[language];
  const phaseFilterOptions = BACKTEST_PHASE_FILTER_OPTIONS[language];
  const actionLabels = buildDecisionActionLabelMap(t);
  const [initialFilters] = useState(() => getInitialBacktestFilters());

  // Set page title
  useEffect(() => {
    document.title = text.documentTitle;
  }, [text.documentTitle]);

  // Input state
  const [codeFilter, setCodeFilter] = useState(initialFilters.code);
  const [analysisDateFrom, setAnalysisDateFrom] = useState(initialFilters.startDate);
  const [analysisDateTo, setAnalysisDateTo] = useState(initialFilters.endDate);
  const [phaseFilter, setPhaseFilter] = useState<BacktestPhaseFilter>(initialFilters.phase);
  const [evalDays, setEvalDays] = useState(initialFilters.windowDays ? String(initialFilters.windowDays) : '');
  const [forceRerun, setForceRerun] = useState(false);
  const [isRunning, setIsRunning] = useState(false);
  const [runResult, setRunResult] = useState<BacktestRunResponse | null>(null);
  const [runError, setRunError] = useState<ParsedApiError | null>(null);
  const runRequestGenerationRef = useRef(0);

  // Results state
  const [results, setResults] = useState<BacktestResultItem[]>([]);
  const [totalResults, setTotalResults] = useState(0);
  const [currentPage, setCurrentPage] = useState(1);
  const [isLoadingResults, setIsLoadingResults] = useState(false);
  const [resultsError, setResultsError] = useState<ParsedApiError | null>(null);
  const resultsRequestGenerationRef = useRef(0);
  const pageSize = 20;

  // Performance state
  const [overallPerf, setOverallPerf] = useState<PerformanceMetrics | null>(null);
  const [stockPerf, setStockPerf] = useState<PerformanceMetrics | null>(null);
  const [isLoadingPerf, setIsLoadingPerf] = useState(false);
  const [performanceError, setPerformanceError] = useState<ParsedApiError | null>(null);
  const performanceRequestGenerationRef = useRef(0);
  const effectiveWindowDays = parseEvalWindowDays(evalDays) ?? overallPerf?.evalWindowDays;
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
    const requestGeneration = resultsRequestGenerationRef.current + 1;
    resultsRequestGenerationRef.current = requestGeneration;
    const isLatestRequest = () => resultsRequestGenerationRef.current === requestGeneration;
    setIsLoadingResults(true);
    setResultsError(null);
    try {
      const response = await backtestApi.getResults({
        code: code || undefined,
        evalWindowDays: windowDays,
        analysisDateFrom: startDate || undefined,
        analysisDateTo: endDate || undefined,
        analysisPhase: phase && phase !== 'all' ? phase : undefined,
        page,
        limit: pageSize,
      });
      if (!isLatestRequest()) return;
      setResults(response.items);
      setTotalResults(response.total);
      setCurrentPage(response.page);
    } catch (err) {
      if (!isLatestRequest()) return;
      console.error('Failed to fetch backtest results:', err);
      setResultsError(getParsedApiError(err));
    } finally {
      if (isLatestRequest()) setIsLoadingResults(false);
    }
  }, []);

  // Fetch performance
  const fetchPerformance = useCallback(async (
    code?: string,
    windowDays?: number,
    startDate?: string,
    endDate?: string,
    phase?: BacktestPhaseFilter,
  ): Promise<PerformanceMetrics | null> => {
    const requestGeneration = performanceRequestGenerationRef.current + 1;
    performanceRequestGenerationRef.current = requestGeneration;
    const isLatestRequest = () => performanceRequestGenerationRef.current === requestGeneration;
    setIsLoadingPerf(true);
    setPerformanceError(null);
    try {
      const query = {
        evalWindowDays: windowDays,
        analysisDateFrom: startDate || undefined,
        analysisDateTo: endDate || undefined,
        analysisPhase: phase && phase !== 'all' ? phase : undefined,
      };
      const [overall, stock] = await Promise.all([
        backtestApi.getOverallPerformance(query),
        code ? backtestApi.getStockPerformance(code, query) : Promise.resolve(null),
      ]);
      if (!isLatestRequest()) return null;
      setOverallPerf(overall);
      setStockPerf(stock);
      return overall;
    } catch (err) {
      if (!isLatestRequest()) return null;
      console.error('Failed to fetch performance:', err);
      setPerformanceError(getParsedApiError(err));
      return null;
    } finally {
      if (isLatestRequest()) setIsLoadingPerf(false);
    }
  }, []);

  // Initial load — fetch performance first, then filter results by its window
  useEffect(() => {
    const init = async () => {
      const { code, windowDays: restoredWindow, startDate, endDate, phase, page } = initialFilters;
      if (restoredWindow) {
        void fetchPerformance(code || undefined, restoredWindow, startDate, endDate, phase);
        void fetchResults(page, code || undefined, restoredWindow, startDate, endDate, phase);
        return;
      }
      const overall = await fetchPerformance(code || undefined, undefined, startDate, endDate, phase);
      if (!overall) return;
      const inferredWindow = overall.evalWindowDays;
      setEvalDays(String(inferredWindow));
      void fetchResults(page, code || undefined, inferredWindow, startDate, endDate, phase);
    };
    void init();
    return () => {
      resultsRequestGenerationRef.current += 1;
      performanceRequestGenerationRef.current += 1;
      runRequestGenerationRef.current += 1;
    };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Run backtest
  const handleRun = async () => {
    const requestGeneration = runRequestGenerationRef.current + 1;
    runRequestGenerationRef.current = requestGeneration;
    const isLatestRequest = () => runRequestGenerationRef.current === requestGeneration;
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
      if (!isLatestRequest()) return;
      setRunResult(response);
      const effectiveEvalWindowDays =
        response.appliedEvalWindowDays
        ?? requestedEvalWindowDays
        ?? parseEvalWindowDays(evalDays)
        ?? overallPerf?.evalWindowDays;
      if (effectiveEvalWindowDays != null) {
        setEvalDays(String(effectiveEvalWindowDays));
      }
      syncBacktestFiltersToUrl({
        code: code ?? '',
        windowDays: effectiveEvalWindowDays,
        startDate: analysisDateFrom,
        endDate: analysisDateTo,
        phase: phaseFilter,
        page: 1,
      });
      // Refresh data with same eval_window_days
      void fetchResults(1, code, effectiveEvalWindowDays, dateFrom, dateTo, phaseFilter);
      void fetchPerformance(code, effectiveEvalWindowDays, dateFrom, dateTo, phaseFilter);
    } catch (err) {
      if (isLatestRequest()) setRunError(getParsedApiError(err));
    } finally {
      if (isLatestRequest()) setIsRunning(false);
    }
  };

  // Phase is a result-only filter (backtestApi.run never receives it), so apply
  // it immediately to the fetched results/performance rather than on Run.
  const handlePhaseChange = (value: BacktestPhaseFilter) => {
    setPhaseFilter(value);
    const code = normalizeBacktestCode(codeFilter);
    const windowDays = parseEvalWindowDays(evalDays);
    setCurrentPage(1);
    syncBacktestFiltersToUrl({ code: code ?? '', windowDays, startDate: analysisDateFrom, endDate: analysisDateTo, phase: value, page: 1 });
    void fetchResults(1, code, windowDays, analysisDateFrom, analysisDateTo, value);
    void fetchPerformance(code, windowDays, analysisDateFrom, analysisDateTo, value);
  };

  // Filter by code
  const handleFilter = () => {
    const code = normalizeBacktestCode(codeFilter);
    const windowDays = parseEvalWindowDays(evalDays);
    setCurrentPage(1);
    syncBacktestFiltersToUrl({ code: code ?? '', windowDays, startDate: analysisDateFrom, endDate: analysisDateTo, phase: phaseFilter, page: 1 });
    void fetchResults(1, code, windowDays, analysisDateFrom, analysisDateTo, phaseFilter);
    void fetchPerformance(code, windowDays, analysisDateFrom, analysisDateTo, phaseFilter);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      handleFilter();
    }
  };

  const handleShowNextDay = () => {
    const code = normalizeBacktestCode(codeFilter);
    setEvalDays('1');
    setCurrentPage(1);
    syncBacktestFiltersToUrl({ code: code ?? '', windowDays: 1, startDate: analysisDateFrom, endDate: analysisDateTo, phase: phaseFilter, page: 1 });
    void fetchResults(1, code, 1, analysisDateFrom, analysisDateTo, phaseFilter);
    void fetchPerformance(code, 1, analysisDateFrom, analysisDateTo, phaseFilter);
  };

  // Pagination
  const totalPages = Math.ceil(totalResults / pageSize);
  const handlePageChange = (page: number) => {
    const windowDays = parseEvalWindowDays(evalDays);
    const code = normalizeBacktestCode(codeFilter);
    syncBacktestFiltersToUrl({ code: code ?? '', windowDays, startDate: analysisDateFrom, endDate: analysisDateTo, phase: phaseFilter, page });
    void fetchResults(page, code, windowDays, analysisDateFrom, analysisDateTo, phaseFilter);
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
              max={120}
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
            className={`backtest-force-btn min-h-11 min-w-11 ${isNextDayValidation ? 'active' : ''}`}
          >
            <span className="dot" />
            {text.oneDayValidation}
          </button>
          <button
            type="button"
            onClick={() => setForceRerun(!forceRerun)}
            disabled={isRunning}
            className={`backtest-force-btn min-h-11 min-w-11 ${forceRerun ? 'active' : ''}`}
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
          {performanceError ? <ApiErrorAlert error={performanceError} /> : null}
          {isLoadingPerf ? (
            <div className="flex items-center justify-center py-8">
              <div className="backtest-spinner sm" />
            </div>
          ) : overallPerf ? (
            <PerformanceCard metrics={overallPerf} title={text.overallPerformance} language={language} />
          ) : performanceError ? null : (
            <EmptyState
              title={text.noMetricsTitle}
              description={text.noMetricsDescription}
              className="h-full min-h-[12rem] border-dashed bg-card/45 shadow-none"
            />
          )}

          {stockPerf && (
            <PerformanceCard metrics={stockPerf} title={`${stockPerf.code || codeFilter}`} language={language} />
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
          {resultsError ? (
            <ApiErrorAlert error={resultsError} className="mb-3" />
          ) : null}
          {isLoadingResults ? (
            <div className="flex flex-col items-center justify-center h-64">
              <div className="backtest-spinner md" />
              <p className="mt-3 text-secondary-text text-sm">{text.loadingResults}</p>
            </div>
          ) : results.length === 0 && !resultsError ? (
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
          ) : results.length > 0 ? (
            <div className="animate-fade-in">
              <div className="backtest-table-toolbar">
                <div className="backtest-table-toolbar-meta">
                  <span className="label-uppercase">{isNextDayValidation ? text.nextDayValidation : text.resultSet}</span>
                  <span className="text-xs text-secondary-text">
                    {codeFilter.trim() ? formatUiText(text.filteredStock, { code: codeFilter.trim() }) : text.allStocks}
                    {evalDays ? ` · ${formatUiText(text.dayWindow, { days: evalDays })}` : ''}
                    {phaseFilter !== 'all' ? ` · ${phaseFilterOptions.find((item) => item.value === phaseFilter)?.label ?? phaseFilter}` : ''}
                    {analysisDateFrom ? ` · ${formatUiText(text.fromDate, { date: analysisDateFrom })}` : ''}
                    {analysisDateTo ? ` · ${formatUiText(text.toDate, { date: analysisDateTo })}` : ''}
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
          ) : null}
        </section>
      </main>
    </div>
  );
};

export default BacktestPage;
