import type React from 'react';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { BellPlus, LineChart as LineChartIcon, PlusCircle, RefreshCw, Sparkles } from 'lucide-react';
import { stocksApi } from '../api/stocks';
import { systemConfigApi } from '../api/systemConfig';
import { getParsedApiError, type ParsedApiError } from '../api/error';
import {
  ApiErrorAlert,
  AppPage,
  Button,
  Card,
  DataTable,
  type DataTableColumn,
  EmptyState,
  Field,
  InlineAlert,
  Input,
  Loading,
  PageHeader,
  Select,
} from '../components/common';
import { useUiLanguage } from '../contexts/UiLanguageContext';
import {
  buildStockDetailsHistoryQueryKey,
  buildStockDetailsQuoteQueryKey,
  useStockDetailsHistoryQuery,
  useStockDetailsQuoteQuery,
} from '../hooks';
import type { UiTextKey } from '../i18n/uiText';
import type {
  StockHistoryCandle,
  StockHistoryPeriod,
  StockQuote,
} from '../types/stocks';
import { aggregateCandles, summarizeCandles } from '../utils/klineAggregate';
import {
  SIGNAL_CENTER_TAB_VALUES,
  buildAnalysisWorkbenchHref,
  buildSignalCenterHref,
} from '../routing/routes';
import { normalizeStockCode } from '../utils/stockCode';
import {
  changeColorCssVar,
  changeSemantics,
  formatMarketTime,
  formatPrice,
  formatSignedChangeAmount,
  formatSignedChangePercent,
  parseChangeColorPreference,
  resolveMarketIdFromStockCode,
  type ChangeColorPreference,
  type MarketId,
} from '../utils/marketFormat';
import { formatUiNumber } from '../utils/uiLocale';
import type { UiLanguage } from '../i18n/uiText';

const PERIOD_OPTIONS: StockHistoryPeriod[] = ['daily', 'weekly', 'monthly'];
const MIN_DAYS = 1;
const MAX_DAYS = 365;
const DEFAULT_DAYS = 90;

function parsePeriodParam(value: string | null): StockHistoryPeriod {
  return PERIOD_OPTIONS.includes(value as StockHistoryPeriod) ? (value as StockHistoryPeriod) : 'daily';
}

function parseDaysParam(value: string | null): number {
  const parsed = Number(value);
  if (Number.isInteger(parsed) && parsed >= MIN_DAYS && parsed <= MAX_DAYS) return parsed;
  return DEFAULT_DAYS;
}

/** Non-price quantities (volume/amount) — host-locale grouping only. */
function formatQuantity(value: number | null | undefined, language: UiLanguage, fractionDigits = 2): string {
  if (value === null || value === undefined || !Number.isFinite(Number(value))) return '—';
  return formatUiNumber(Number(value), language, {
    minimumFractionDigits: 0,
    maximumFractionDigits: fractionDigits,
  });
}

function formatPriceCell(
  value: number | null | undefined,
  market: MarketId | null,
  language: UiLanguage,
): string {
  if (market) return formatPrice(value, market, language);
  if (value === null || value === undefined || !Number.isFinite(Number(value))) return '—';
  return formatUiNumber(Number(value), language, {
    minimumFractionDigits: 0,
    maximumFractionDigits: 2,
  });
}

function formatSignedFallback(value: number | null | undefined, language: UiLanguage): string {
  if (value === null || value === undefined || !Number.isFinite(Number(value))) return '—';
  const numeric = Number(value);
  const body = formatUiNumber(Math.abs(numeric), language, {
    minimumFractionDigits: 0,
    maximumFractionDigits: 2,
  });
  if (numeric > 0) return `+${body}`;
  if (numeric < 0) return `-${body}`;
  return body;
}

const StockDetailsPage: React.FC = () => {
  const { stockCode: rawParam = '' } = useParams<{ stockCode: string }>();
  const navigate = useNavigate();
  const { language, t } = useUiLanguage();

  const decodedParam = useMemo(() => {
    try {
      return decodeURIComponent(rawParam).trim();
    } catch {
      return rawParam.trim();
    }
  }, [rawParam]);
  const canonicalCode = useMemo(() => normalizeStockCode(decodedParam), [decodedParam]);

  const [searchParams, setSearchParams] = useSearchParams();
  // The URL is the source of truth for period/days so browser back/forward
  // restore them (react-router observes searchParams, unlike replaceState).
  const period = useMemo(() => parsePeriodParam(searchParams.get('period')), [searchParams]);
  const days = useMemo(() => parseDaysParam(searchParams.get('days')), [searchParams]);
  const [daysDraft, setDaysDraft] = useState<string>(() => String(days));

  const [quote, setQuote] = useState<StockQuote | null>(null);
  const [quoteLoading, setQuoteLoading] = useState(true);
  const [quoteError, setQuoteError] = useState<ParsedApiError | null>(null);

  const [dailyCandles, setDailyCandles] = useState<StockHistoryCandle[] | null>(null);
  const [historyLoading, setHistoryLoading] = useState(true);
  const [historyError, setHistoryError] = useState<ParsedApiError | null>(null);

  const [watchState, setWatchState] = useState<'idle' | 'adding' | 'added' | 'error'>('idle');
  const [watchError, setWatchError] = useState<ParsedApiError | null>(null);
  /** Settings MARKET_REVIEW_COLOR_SCHEME when loadable; null → market convention. */
  const [changeColorPref, setChangeColorPref] = useState<ChangeColorPreference | null>(null);

  const quoteReqRef = useRef(0);
  const historyReqRef = useRef(0);
  const mountedRef = useRef(true);
  const marketId = useMemo(
    () => resolveMarketIdFromStockCode(canonicalCode),
    [canonicalCode],
  );

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  // Keep the editable days field in sync when days changes via back/forward.
  useEffect(() => {
    setDaysDraft(String(days));
  }, [days]);

  // Canonicalize the URL so equivalent spellings share one route and cache key.
  useEffect(() => {
    if (decodedParam && canonicalCode && decodedParam !== canonicalCode) {
      const search = searchParams.toString();
      navigate(`/stocks/${encodeURIComponent(canonicalCode)}${search ? `?${search}` : ''}`, { replace: true });
    }
  }, [decodedParam, canonicalCode, navigate, searchParams]);

  useEffect(() => {
    document.title = t('stocks.workspace.pageTitle', { code: canonicalCode || decodedParam });
  }, [t, canonicalCode, decodedParam]);

  // Prefer Settings MARKET_REVIEW_COLOR_SCHEME when the config API is available;
  // fail open to market convention (never block the quote surface).
  useEffect(() => {
    let cancelled = false;
    void systemConfigApi
      .getConfig(false)
      .then((config) => {
        if (cancelled) return;
        const item = config.items.find((entry) => entry.key === 'MARKET_REVIEW_COLOR_SCHEME');
        setChangeColorPref(parseChangeColorPreference(item?.value));
      })
      .catch(() => {
        if (!cancelled) setChangeColorPref(null);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const loadQuote = useCallback(async (code: string) => {
    if (!code) return;
    const requestId = quoteReqRef.current + 1;
    quoteReqRef.current = requestId;
    setQuoteLoading(true);
    try {
      const response = await stocksApi.getQuote(code);
      if (!mountedRef.current || quoteReqRef.current !== requestId) return;
      setQuote(response);
      setQuoteError(null);
    } catch (err) {
      if (!mountedRef.current || quoteReqRef.current !== requestId) return;
      setQuote(null);
      setQuoteError(getParsedApiError(err));
    } finally {
      if (mountedRef.current && quoteReqRef.current === requestId) setQuoteLoading(false);
    }
  }, []);

  const loadHistory = useCallback(async (code: string, dayCount: number) => {
    if (!code) return;
    const requestId = historyReqRef.current + 1;
    historyReqRef.current = requestId;
    setHistoryLoading(true);
    try {
      const response = await stocksApi.getDailyHistory(code, dayCount);
      if (!mountedRef.current || historyReqRef.current !== requestId) return;
      setDailyCandles(response.data);
      setHistoryError(null);
    } catch (err) {
      if (!mountedRef.current || historyReqRef.current !== requestId) return;
      setDailyCandles(null);
      setHistoryError(getParsedApiError(err));
    } finally {
      if (mountedRef.current && historyReqRef.current === requestId) setHistoryLoading(false);
    }
  }, []);

  const quoteQueryKey = useMemo(
    () => buildStockDetailsQuoteQueryKey(canonicalCode || ''),
    [canonicalCode],
  );
  const historyQueryKey = useMemo(
    () => buildStockDetailsHistoryQueryKey(canonicalCode || '', days),
    [canonicalCode, days],
  );

  useStockDetailsQuoteQuery({
    queryKey: quoteQueryKey,
    enabled: Boolean(canonicalCode),
    load: () => loadQuote(canonicalCode),
    onCancelInFlight: () => {
      quoteReqRef.current += 1;
    },
  });

  useStockDetailsHistoryQuery({
    queryKey: historyQueryKey,
    enabled: Boolean(canonicalCode),
    load: () => loadHistory(canonicalCode, days),
    onCancelInFlight: () => {
      historyReqRef.current += 1;
    },
  });

  const displayCandles = useMemo(
    () => (dailyCandles ? aggregateCandles(dailyCandles, period) : []),
    [dailyCandles, period],
  );
  const summary = useMemo(() => summarizeCandles(displayCandles), [displayCandles]);

  const handlePeriodChange = useCallback((value: string) => {
    const next = value as StockHistoryPeriod;
    setSearchParams((prev) => {
      const nextParams = new URLSearchParams(prev);
      if (next === 'daily') nextParams.delete('period');
      else nextParams.set('period', next);
      return nextParams;
    }, { replace: true });
  }, [setSearchParams]);

  const handleDaysSubmit = useCallback((event: React.FormEvent) => {
    event.preventDefault();
    const parsed = Number(daysDraft);
    if (!Number.isInteger(parsed) || parsed < MIN_DAYS || parsed > MAX_DAYS) return;
    setSearchParams((prev) => {
      const nextParams = new URLSearchParams(prev);
      if (parsed === DEFAULT_DAYS) nextParams.delete('days');
      else nextParams.set('days', String(parsed));
      return nextParams;
    }, { replace: true });
  }, [daysDraft, setSearchParams]);

  const handleAddWatchlist = useCallback(async () => {
    if (!canonicalCode || watchState === 'adding') return;
    setWatchState('adding');
    setWatchError(null);
    try {
      await systemConfigApi.addToWatchlist(canonicalCode);
      if (!mountedRef.current) return;
      setWatchState('added');
    } catch (err) {
      if (!mountedRef.current) return;
      setWatchState('error');
      setWatchError(getParsedApiError(err));
    }
  }, [canonicalCode, watchState]);

  const daysDraftInvalid = useMemo(() => {
    const parsed = Number(daysDraft);
    return !Number.isInteger(parsed) || parsed < MIN_DAYS || parsed > MAX_DAYS;
  }, [daysDraft]);

  const periodOptions = useMemo(
    () => PERIOD_OPTIONS.map((value) => ({
      value,
      label: t(`stocks.workspace.period.${value}` as UiTextKey),
    })),
    [t],
  );

  if (!canonicalCode) {
    return (
      <AppPage>
        <PageHeader title={t('stocks.workspace.title')} description={t('stocks.workspace.description')} />
        <EmptyState
          title={t('stocks.workspace.invalidTitle')}
          description={t('stocks.workspace.invalidDescription')}
          icon={<LineChartIcon className="h-6 w-6" />}
        />
      </AppPage>
    );
  }

  const quoteName = quote?.stockName?.trim();

  const quoteChangeSemantics = marketId
    ? changeSemantics(quote?.change, marketId, changeColorPref)
    : null;
  const quoteChangeColor = quoteChangeSemantics
    ? changeColorCssVar(quoteChangeSemantics.color)
    : undefined;
  const quoteChangeLabel = marketId
    ? `${formatSignedChangeAmount(quote?.change, marketId, language)} (${formatSignedChangePercent(quote?.changePercent)})`
    : `${formatSignedFallback(quote?.change, language)} (${formatSignedChangePercent(quote?.changePercent)})`;
  const quoteFreshness = quote?.updateTime
    ? (marketId
      ? (formatMarketTime(quote.updateTime, marketId, language)?.text
        ?? new Date(quote.updateTime).toLocaleString())
      : new Date(quote.updateTime).toLocaleString())
    : null;

  const candleColumns: DataTableColumn<StockHistoryCandle>[] = [
    { id: 'date', header: t('stocks.workspace.date'), cell: (candle) => <span className="font-mono">{candle.date}</span> },
    { id: 'open', header: t('stocks.workspace.open'), cell: (candle) => formatPriceCell(candle.open, marketId, language) },
    { id: 'high', header: t('stocks.workspace.high'), cell: (candle) => formatPriceCell(candle.high, marketId, language) },
    { id: 'low', header: t('stocks.workspace.low'), cell: (candle) => formatPriceCell(candle.low, marketId, language) },
    { id: 'close', header: t('stocks.workspace.close'), cell: (candle) => formatPriceCell(candle.close, marketId, language) },
    { id: 'volume', header: t('stocks.workspace.volume'), cell: (candle) => formatQuantity(candle.volume, language) },
  ];

  return (
    <AppPage className="max-w-none">
      <div className="space-y-5">
        <PageHeader
          eyebrow={quoteName ? canonicalCode : undefined}
          title={quoteName || canonicalCode}
          description={t('stocks.workspace.description')}
          actions={(
            <Button
              type="button"
              variant="secondary"
              size="comfortable"
              onClick={() => {
                void loadQuote(canonicalCode);
                void loadHistory(canonicalCode, days);
              }}
              disabled={quoteLoading || historyLoading}
            >
              <RefreshCw className="h-4 w-4" aria-hidden="true" />
              {t('stocks.workspace.refresh')}
            </Button>
          )}
        />

        <div className="flex flex-wrap items-center gap-2">
          <Button type="button" variant="secondary" size="comfortable" onClick={() => void handleAddWatchlist()} disabled={watchState === 'adding' || watchState === 'added'}>
            <PlusCircle className="h-4 w-4" aria-hidden="true" />
            {watchState === 'added' ? t('stocks.workspace.watchlistAdded') : t('stocks.workspace.watchlistAdd')}
          </Button>
          <Button type="button" variant="secondary" size="comfortable" onClick={() => navigate(buildAnalysisWorkbenchHref({ stock: canonicalCode }))}>
            <Sparkles className="h-4 w-4" aria-hidden="true" />
            {t('stocks.workspace.analyze')}
          </Button>
          <Button
            type="button"
            variant="secondary"
            size="comfortable"
            onClick={() => navigate(buildSignalCenterHref({
              tab: SIGNAL_CENTER_TAB_VALUES.rules,
              createRule: true,
              stock: canonicalCode,
            }))}
          >
            <BellPlus className="h-4 w-4" aria-hidden="true" />
            {t('decisionSignals.createRuleFromSignal')}
          </Button>
        </div>
        {watchState === 'error' && watchError ? <ApiErrorAlert error={watchError} /> : null}

        <Card title={t('stocks.workspace.quoteTitle')} padding="md">
          {quoteError ? (
            <ApiErrorAlert
              error={quoteError}
              actionLabel={t('common.retry')}
              onAction={() => void loadQuote(canonicalCode)}
            />
          ) : quoteLoading && !quote ? (
            <Loading />
          ) : quote ? (
            <div className="space-y-3">
              <div className="flex flex-wrap items-baseline gap-3">
                <span className="text-3xl font-semibold text-foreground">
                  {formatPriceCell(quote.currentPrice, marketId, language)}
                </span>
                <span
                  className="text-sm font-medium text-foreground"
                  style={quoteChangeColor ? { color: quoteChangeColor } : undefined}
                  data-change-direction={quoteChangeSemantics?.direction}
                  data-change-color={quoteChangeSemantics?.color}
                  data-change-pref={quoteChangeSemantics?.colorPreference}
                >
                  {quoteChangeLabel}
                </span>
              </div>
              <dl className="grid gap-x-4 gap-y-2 text-sm sm:grid-cols-3 lg:grid-cols-6">
                {([
                  ['stocks.workspace.open', quote.open, 'price'],
                  ['stocks.workspace.high', quote.high, 'price'],
                  ['stocks.workspace.low', quote.low, 'price'],
                  ['stocks.workspace.prevClose', quote.prevClose, 'price'],
                  ['stocks.workspace.volume', quote.volume, 'qty'],
                  ['stocks.workspace.amount', quote.amount, 'qty'],
                ] as Array<[UiTextKey, number | null | undefined, 'price' | 'qty']>).map(([key, value, kind]) => (
                  <div key={key} className="flex flex-col">
                    <dt className="text-xs text-secondary-text">{t(key)}</dt>
                    <dd className="font-medium text-foreground">
                      {kind === 'price'
                        ? formatPriceCell(value, marketId, language)
                        : formatQuantity(value, language)}
                    </dd>
                  </div>
                ))}
              </dl>
              <p className="text-xs text-secondary-text">
                {quoteFreshness
                  ? t('stocks.workspace.freshness', { time: quoteFreshness })
                  : t('stocks.workspace.freshnessUnknown')}
              </p>
            </div>
          ) : (
            <EmptyState
              compact
              title={t('stocks.workspace.quoteEmptyTitle')}
              description={t('stocks.workspace.quoteEmptyDescription')}
              icon={<LineChartIcon className="h-6 w-6" />}
            />
          )}
        </Card>

        <Card title={t('stocks.workspace.historyTitle')} padding="md">
          <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
            <Field controlId="stock-history-period" label={t('stocks.workspace.periodLabel')} className="sm:w-48">
              <Select
                id="stock-history-period"
                className="w-full"
                value={period}
                onChange={handlePeriodChange}
                options={periodOptions}
                ariaLabel={t('stocks.workspace.periodLabel')}
              />
            </Field>
            <form className="flex items-end gap-2" onSubmit={handleDaysSubmit}>
              <Input
                label={t('stocks.workspace.daysLabel')}
                type="number"
                min={MIN_DAYS}
                max={MAX_DAYS}
                value={daysDraft}
                onChange={(event) => setDaysDraft(event.target.value)}
                error={daysDraftInvalid ? t('stocks.workspace.daysError') : undefined}
                fieldClassName="w-32"
              />
              <Button type="submit" variant="secondary" size="comfortable" disabled={daysDraftInvalid}>
                {t('stocks.workspace.apply')}
              </Button>
            </form>
          </div>

          {historyError ? (
            <ApiErrorAlert
              error={historyError}
              actionLabel={t('common.retry')}
              onAction={() => void loadHistory(canonicalCode, days)}
            />
          ) : historyLoading && !dailyCandles ? (
            <Loading />
          ) : displayCandles.length > 0 ? (
            <div className="space-y-4">
              <p className="text-sm text-secondary-text">
                {t('stocks.workspace.summary', {
                  count: summary.count,
                  start: summary.periodStart ?? '—',
                  end: summary.periodEnd ?? '—',
                  change: formatSignedChangePercent(summary.changePercent).replace(/%$/, ''),
                })}
              </p>
              <div className="h-64 w-full" role="img" aria-label={t('stocks.workspace.chartLabel', { code: canonicalCode })}>
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={displayCandles} margin={{ top: 8, right: 8, bottom: 8, left: 8 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                    <XAxis dataKey="date" tick={{ fontSize: 11 }} minTickGap={24} />
                    <YAxis domain={['auto', 'auto']} tick={{ fontSize: 11 }} width={56} />
                    <Tooltip />
                    <Line type="monotone" dataKey="close" stroke="hsl(var(--primary))" dot={false} strokeWidth={2} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
              <div className="max-h-72 overflow-y-auto">
                <DataTable<StockHistoryCandle>
                  caption={t('stocks.workspace.tableCaption', { code: canonicalCode })}
                  columns={candleColumns}
                  rows={[...displayCandles].reverse()}
                  getRowKey={(candle) => candle.date}
                  emptyState={{
                    title: t('stocks.workspace.historyEmptyTitle'),
                    description: t('stocks.workspace.historyEmptyDescription'),
                  }}
                  density="compact"
                  minWidth="content"
                />
              </div>
              <InlineAlert variant="info" message={t('stocks.workspace.aggregationNote')} />
            </div>
          ) : (
            <EmptyState
              compact
              title={t('stocks.workspace.historyEmptyTitle')}
              description={t('stocks.workspace.historyEmptyDescription')}
              icon={<LineChartIcon className="h-6 w-6" />}
            />
          )}
        </Card>
      </div>
    </AppPage>
  );
};

export default StockDetailsPage;
