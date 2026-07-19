import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Activity, Clock3, Cpu, Database, Gauge, RefreshCw } from 'lucide-react';
import { usageApi, type UsageDashboard, type UsageModelBreakdown, type UsagePeriod } from '../api/usage';
import { localizeParsedApiError, type ParsedApiError } from '../api/error';
import { ApiErrorAlert, AppPage, Button, PageHeader, Section, SegmentedControl, StatePanel, StatCard, Surface } from '../components/common';
import { useUiLanguage } from '../contexts/UiLanguageContext';
import type { UiLanguage, UiTextKey, UiTextParams } from '../i18n/uiText';
import { getUiLocale } from '../utils/uiLocale';

type Translate = (key: UiTextKey, params?: UiTextParams) => string;

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

const ModelUsageCard: React.FC<{ model: UsageModelBreakdown; language: UiLanguage; t: Translate }> = ({ model, language, t }) => {
  return (
    <Surface as="article" level="interactive" padding="sm">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="truncate text-base font-semibold text-foreground">{model.model}</h3>
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

const TokenUsagePage: React.FC = () => {
  const { language, t } = useUiLanguage();
  useEffect(() => {
    document.title = t('usage.documentTitle');
  }, [t]);
  const [period, setPeriod] = useState<UsagePeriod>('month');
  const [dashboard, setDashboard] = useState<UsageDashboard | null>(null);
  const [error, setError] = useState<ParsedApiError | null>(null);
  const [loading, setLoading] = useState(true);
  const requestSeqRef = useRef(0);

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
      setDashboard(data);
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

  const largestCallTypeTotal = useMemo(() => {
    return Math.max(...(dashboard?.byCallType.map((item) => item.totalTokens) ?? [0]), 1);
  }, [dashboard]);
  const localizedError = useMemo(
    () => error ? localizeParsedApiError(error, language) : null,
    [error, language],
  );

  return (
    <AppPage className="max-w-none">
      <div className="space-y-5">
        <PageHeader
          eyebrow={t('usage.eyebrow')}
          title={t('usage.title')}
          description={t('usage.description')}
          actions={(
            <div className="flex flex-wrap items-center gap-2">
              <SegmentedControl
                value={period}
                options={PERIOD_OPTIONS.map((option) => ({ value: option, label: t(PERIOD_LABEL_KEYS[option]) }))}
                onChange={setPeriod}
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
          )}
        />

        {error && dashboard ? (
          <ApiErrorAlert error={error} actionLabel={t('common.retry')} onAction={() => void loadDashboard()} />
        ) : null}

        {loading && !dashboard ? (
          <StatePanel
            state="loading"
            title={t('common.loading')}
            surfaceLevel="section"
          />
        ) : null}

        {error && !dashboard && !loading && localizedError ? (
          <StatePanel
            state="error"
            title={localizedError.title}
            description={localizedError.message}
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
            surfaceLevel="section"
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
                contentClassName="grid gap-4"
              >
                {dashboard.byModel.map((model) => (
                  <ModelUsageCard key={model.model} model={model} language={language} t={t} />
                ))}
              </Section>

              <Section
                title={t('usage.callTypeTitle')}
                eyebrow={t('usage.breakdown')}
                level="section"
                padding="sm"
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

            <section className="space-y-3">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <h2 className="text-lg font-semibold text-foreground">{t('usage.recentCalls')}</h2>
                  <p className="mt-1 text-sm text-secondary-text">{t('usage.recentCallsDescription')}</p>
                </div>
                <Clock3 className="h-5 w-5 text-secondary-text" />
              </div>
              <div className="overflow-hidden rounded-2xl border border-border/70 bg-card/75 shadow-soft-card">
                <div className="overflow-x-auto">
                  <table className="min-w-full divide-y divide-border/70 text-sm">
                    <thead className="bg-surface-2/70 text-left text-xs uppercase tracking-[0.16em] text-secondary-text">
                      <tr>
                        <th className="px-4 py-3 font-medium">{t('usage.table.time')}</th>
                        <th className="px-4 py-3 font-medium">{t('usage.table.type')}</th>
                        <th className="px-4 py-3 font-medium">{t('usage.table.model')}</th>
                        <th className="px-4 py-3 text-right font-medium">{t('usage.promptLabel')}</th>
                        <th className="px-4 py-3 text-right font-medium">{t('usage.completionLabel')}</th>
                        <th className="px-4 py-3 text-right font-medium">{t('usage.totalLabel')}</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-border/60">
                      {dashboard.recentCalls.length ? dashboard.recentCalls.map((item) => (
                        <tr key={item.id} className="hover:bg-hover/60">
                          <td className="whitespace-nowrap px-4 py-3 text-secondary-text">{formatDateTime(item.calledAt, language)}</td>
                          <td className="whitespace-nowrap px-4 py-3 text-foreground">{getCallTypeLabel(item.callType, t)}</td>
                          <td className="min-w-56 px-4 py-3">
                            <div className="max-w-[18rem] truncate font-medium text-foreground">{item.model}</div>
                            {item.stockCode ? <div className="text-xs text-secondary-text">{item.stockCode}</div> : null}
                          </td>
                          <td className="whitespace-nowrap px-4 py-3 text-right text-secondary-text">{formatNumber(item.promptTokens, language)}</td>
                          <td className="whitespace-nowrap px-4 py-3 text-right text-secondary-text">{formatNumber(item.completionTokens, language)}</td>
                          <td className="whitespace-nowrap px-4 py-3 text-right font-medium text-foreground">{formatNumber(item.totalTokens, language)}</td>
                        </tr>
                      )) : (
                        <tr>
                          <td colSpan={6} className="px-4 py-8 text-center text-secondary-text">{t('usage.noRecentCalls')}</td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>
              </div>
            </section>
          </>
        ) : null}
      </div>
    </AppPage>
  );
};

export default TokenUsagePage;
