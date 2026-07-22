import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Activity, Clock3, Cpu, Database, Gauge, RefreshCw } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import {
  usageApi,
  type UsageCallRecord,
  type UsageDashboard,
  type UsageModelBreakdown,
  type UsagePeriod,
} from '../../api/usage';
import { localizeParsedApiError, type ParsedApiError } from '../../api/error';
import {
  ApiErrorAlert,
  AppPage,
  Button,
  DataTable,
  type DataTableColumn,
  PageHeader,
  Section,
  SegmentedControl,
  StatePanel,
  StatCard,
  Surface,
} from '../common';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import type { UiLanguage, UiTextKey, UiTextParams } from '../../i18n/uiText';
import { APP_ROUTE_PATHS } from '../../routing/routes';
import { getUiLocale } from '../../utils/uiLocale';

type Translate = (key: UiTextKey, params?: UiTextParams) => string;
type UsageDashboardSnapshot = { period: UsagePeriod; dashboard: UsageDashboard };

const PERIOD_OPTIONS: UsagePeriod[] = ['today', 'month', 'all'];

const PERIOD_LABEL_KEYS: Record<UsagePeriod, UiTextKey> = {
  today: 'usage.period.today',
  month: 'usage.period.month',
  all: 'usage.period.all',
};

const CALL_TYPE_LABEL_KEYS: Record<string, UiTextKey> = {
  analysis: 'usage.callType.analysis',
  agent: 'usage.callType.agent',
  market_review: 'usage.callType.marketReview',
};

function formatNumber(value: number | null | undefined, language: UiLanguage): string {
  return new Intl.NumberFormat(getUiLocale(language)).format(value ?? 0);
}

function formatDateTime(value: string, language: UiLanguage): string {
  if (!value) {
    return '-';
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return new Intl.DateTimeFormat(getUiLocale(language), {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date);
}

function getCallTypeLabel(callType: string, t: Translate): string {
  const key = CALL_TYPE_LABEL_KEYS[callType];
  return key ? t(key) : t('usage.callType.unknown', { type: callType || '-' });
}

function buildParsedError(error: unknown, t: Translate): ParsedApiError {
  if (error && typeof error === 'object' && 'parsedError' in error) {
    const parsedError = (error as { parsedError?: ParsedApiError }).parsedError;
    if (parsedError) {
      return parsedError;
    }
  }

  const message = error instanceof Error ? error.message : t('usage.error.message');
  return {
    title: t('usage.error.title'),
    message,
    rawMessage: message,
    category: 'http_error',
  };
}

const ModelUsageCard: React.FC<{
  model: UsageModelBreakdown;
  language: UiLanguage;
  t: Translate;
  headingAs?: 'h3' | 'h4';
}> = ({ model, language, t, headingAs = 'h3' }) => {
  const Heading = headingAs;
  return (
    <Surface as="article" level="section" padding="sm">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <Heading className="truncate text-base font-semibold text-foreground">{model.model}</Heading>
          <p className="mt-1 text-xs text-secondary-text">{t('usage.calls', { count: formatNumber(model.calls, language) })}</p>
        </div>
        <span className="rounded-full border border-primary/20 bg-primary/10 px-2 py-1 text-xs text-primary">
          {formatNumber(model.totalTokens, language)} {t('usage.tokenUnit')}
        </span>
      </div>
      <div className="mt-4 grid grid-cols-3 gap-3 text-sm">
        <div>
          <p className="text-xs text-secondary-text">{t('usage.promptLabel')}</p>
          <p className="mt-1 font-medium text-foreground">{formatNumber(model.promptTokens, language)}</p>
        </div>
        <div>
          <p className="text-xs text-secondary-text">{t('usage.completionLabel')}</p>
          <p className="mt-1 font-medium text-foreground">{formatNumber(model.completionTokens, language)}</p>
        </div>
        <div>
          <p className="text-xs text-secondary-text">{t('usage.maxSingleCall')}</p>
          <p className="mt-1 font-medium text-foreground">{formatNumber(model.maxTotalTokens, language)}</p>
        </div>
      </div>
    </Surface>
  );
};

type TokenUsagePageProps = {
  embedded?: boolean;
};

const TokenUsagePage: React.FC<TokenUsagePageProps> = ({ embedded = false }) => {
  const { language, t } = useUiLanguage();
  const navigate = useNavigate();
  useEffect(() => {
    if (embedded) return;
    document.title = t('usage.documentTitle');
  }, [embedded, t]);
  const [period, setPeriod] = useState<UsagePeriod>('month');
  const [snapshot, setSnapshot] = useState<UsageDashboardSnapshot | null>(null);
  const [error, setError] = useState<ParsedApiError | null>(null);
  const [loading, setLoading] = useState(true);
  const requestSeqRef = useRef(0);
  const dashboard = snapshot?.period === period ? snapshot.dashboard : null;

  const loadDashboard = useCallback(async () => {
    const requestSeq = requestSeqRef.current + 1;
    requestSeqRef.current = requestSeq;
    setLoading(true);
    setError(null);
    try {
      const data = await usageApi.getDashboard({ period, limit: 50 });
      if (requestSeq !== requestSeqRef.current) {
        return;
      }
      setSnapshot({ period, dashboard: data });
    } catch (err) {
      if (requestSeq !== requestSeqRef.current) {
        return;
      }
      setError(buildParsedError(err, t));
    } finally {
      if (requestSeq === requestSeqRef.current) {
        setLoading(false);
      }
    }
  }, [period, t]);

  useEffect(() => {
    void loadDashboard();
    return () => {
      requestSeqRef.current += 1;
    };
  }, [loadDashboard]);

  const handlePeriodChange = useCallback((nextPeriod: UsagePeriod) => {
    if (nextPeriod === period) return;
    setError(null);
    setLoading(true);
    setPeriod(nextPeriod);
  }, [period]);

  const largestCallTypeTotal = useMemo(() => {
    return Math.max(...(dashboard?.byCallType.map((item) => item.totalTokens) ?? [0]), 1);
  }, [dashboard]);
  const localizedError = useMemo(
    () => error ? localizeParsedApiError(error, language) : null,
    [error, language],
  );
  const recentCallColumns = useMemo<readonly DataTableColumn<UsageCallRecord>[]>(() => [
    {
      id: 'time',
      header: t('usage.table.time'),
      rowHeader: true,
      nowrap: true,
      cell: (item) => formatDateTime(item.calledAt, language),
    },
    {
      id: 'type',
      header: t('usage.table.type'),
      nowrap: true,
      cell: (item) => <span className="text-foreground">{getCallTypeLabel(item.callType, t)}</span>,
    },
    {
      id: 'model',
      header: t('usage.table.model'),
      width: 'wide',
      cell: (item) => (
        <>
          <div className="max-w-[18rem] truncate font-medium text-foreground">{item.model}</div>
          {item.stockCode ? <div className="text-xs text-secondary-text">{item.stockCode}</div> : null}
        </>
      ),
    },
    {
      id: 'prompt',
      header: t('usage.promptLabel'),
      align: 'end',
      nowrap: true,
      cell: (item) => formatNumber(item.promptTokens, language),
    },
    {
      id: 'completion',
      header: t('usage.completionLabel'),
      align: 'end',
      nowrap: true,
      cell: (item) => formatNumber(item.completionTokens, language),
    },
    {
      id: 'total',
      header: t('usage.totalLabel'),
      align: 'end',
      nowrap: true,
      cell: (item) => <span className="font-medium text-foreground">{formatNumber(item.totalTokens, language)}</span>,
    },
  ], [language, t]);

  const actions = (
    <div className="flex flex-wrap items-center gap-2">
      <SegmentedControl
        value={period}
        options={PERIOD_OPTIONS.map((option) => ({ value: option, label: t(PERIOD_LABEL_KEYS[option]) }))}
        onChange={handlePeriodChange}
        ariaLabel={t('usage.title')}
      />
      <Button
        type="button"
        variant="secondary"
        size="default"
        onClick={() => void loadDashboard()}
        disabled={loading}
        isLoading={loading}
        loadingText={t('usage.refresh')}
      >
        <RefreshCw className="h-4 w-4" aria-hidden="true" />
        {t('usage.refresh')}
      </Button>
    </div>
  );

  const dashboardContent = (
    <>
        {error && dashboard ? (
          <ApiErrorAlert error={error} actionLabel={t('common.retry')} onAction={() => void loadDashboard()} />
        ) : null}

        {loading && !dashboard ? (
          <StatePanel
            state="loading"
            title={t('common.loading')}
            titleAs={embedded ? 'h3' : 'h2'}
            surfaceLevel="section"
          />
        ) : null}

        {error && !dashboard && !loading && localizedError ? (
          <StatePanel
            state="error"
            title={localizedError.title}
            description={localizedError.message}
            titleAs={embedded ? 'h3' : 'h2'}
            surfaceLevel="section"
            action={(
              <Button type="button" variant="secondary" size="default" onClick={() => void loadDashboard()}>
                {t('common.retry')}
              </Button>
            )}
          />
        ) : null}

        {dashboard && dashboard.totalCalls === 0 ? (
          <StatePanel
            state="empty"
            title={t('usage.emptyTitle')}
            description={t('usage.emptyDescription')}
            titleAs={embedded ? 'h3' : 'h2'}
            surfaceLevel="section"
            action={(
              <Button
                type="button"
                variant="primary"
                size="default"
                onClick={() => navigate(APP_ROUTE_PATHS.home)}
              >
                {t('home.startAnalysisTitle')}
              </Button>
            )}
          />
        ) : null}

        {dashboard && dashboard.totalCalls > 0 ? (
          <>
            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
              <StatCard label={t('usage.totalTokens')} value={formatNumber(dashboard.totalTokens, language)} hint={t('usage.dateRange', { from: dashboard.fromDate, to: dashboard.toDate })} icon={<Database className="h-5 w-5" />} tone="primary" />
              <StatCard label={t('usage.totalCalls')} value={formatNumber(dashboard.totalCalls, language)} hint={t('usage.totalCallsHint')} icon={<Activity className="h-5 w-5" />} />
              <StatCard label={t('usage.promptTokens')} value={formatNumber(dashboard.totalPromptTokens, language)} hint={t('usage.promptTokensHint')} icon={<Cpu className="h-5 w-5" />} />
              <StatCard label={t('usage.completionTokens')} value={formatNumber(dashboard.totalCompletionTokens, language)} hint={t('usage.completionTokensHint')} icon={<Gauge className="h-5 w-5" />} />
            </div>

            <div className="grid gap-5 xl:grid-cols-[minmax(0,1.25fr)_minmax(360px,0.75fr)]">
              <Section
                title={t('usage.modelUsage')}
                description={t('usage.modelUsageDescription')}
                headingAs={embedded ? 'h3' : 'h2'}
                contentClassName="grid gap-4"
              >
                {dashboard.byModel.map((model) => (
                  <ModelUsageCard
                    key={model.model}
                    model={model}
                    language={language}
                    t={t}
                    headingAs={embedded ? 'h4' : 'h3'}
                  />
                ))}
              </Section>

              <Section
                title={t('usage.callTypeTitle')}
                eyebrow={t('usage.breakdown')}
                level="section"
                padding="sm"
                headingAs={embedded ? 'h3' : 'h2'}
              >
                    <div className="space-y-4">
                      {dashboard.byCallType.map((item) => (
                        <div key={item.callType}>
                          <div className="flex items-center justify-between gap-3 text-sm">
                            <span className="font-medium text-foreground">{getCallTypeLabel(item.callType, t)}</span>
                            <span className="text-secondary-text">{formatNumber(item.totalTokens, language)} {t('usage.tokenUnit')}</span>
                          </div>
                          <div className="mt-2 h-2 overflow-hidden rounded-full bg-border/70">
                            <div
                              className="h-full rounded-full bg-primary"
                              style={{ width: `${Math.max(4, (item.totalTokens / largestCallTypeTotal) * 100)}%` }}
                            />
                          </div>
                          <p className="mt-1 text-xs text-secondary-text">
                            {t('usage.callTypeDetail', {
                              calls: formatNumber(item.calls, language),
                              prompt: formatNumber(item.promptTokens, language),
                              completion: formatNumber(item.completionTokens, language),
                            })}
                          </p>
                        </div>
                      ))}
                    </div>
              </Section>
            </div>

            <Section
              title={t('usage.recentCalls')}
              description={t('usage.recentCallsDescription')}
              actions={<Clock3 className="h-5 w-5 text-secondary-text" aria-hidden="true" />}
              headingAs={embedded ? 'h3' : 'h2'}
            >
              <DataTable
                caption={t('usage.recentCalls')}
                scrollAreaLabel={t('usage.recentCallsDescription')}
                columns={recentCallColumns}
                rows={dashboard.recentCalls}
                getRowKey={(item) => item.id}
                emptyState={{ title: t('usage.noRecentCalls') }}
                frame="embedded"
                minWidth="container"
              />
            </Section>
          </>
        ) : null}
    </>
  );

  const content = embedded ? (
    <Section
      title={t('usage.title')}
      description={t('usage.description')}
      eyebrow={t('usage.eyebrow')}
      actions={actions}
      headingAs="h2"
      contentClassName="space-y-5"
    >
      {dashboardContent}
    </Section>
  ) : (
    <div className="space-y-5">
      <PageHeader
        eyebrow={t('usage.eyebrow')}
        title={t('usage.title')}
        description={t('usage.description')}
        actions={actions}
      />
      {dashboardContent}
    </div>
  );

  return embedded ? content : <AppPage className="max-w-none">{content}</AppPage>;
};

export default TokenUsagePage;
