// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type React from 'react';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { RefreshCw } from 'lucide-react';
import { portfolioApi } from '../api/portfolio';
import { getParsedApiError, type ParsedApiError } from '../api/error';
import {
  ApiErrorAlert,
  AppPage,
  Badge,
  Button,
  DataTable,
  type DataTableColumn,
  EmptyState,
  IconButton,
  PageHeader,
  Select,
  StatePanel,
  Surface,
} from '../components/common';
import { useRouteFocusTarget } from '../components/routing';
import { useUiLanguage } from '../contexts/UiLanguageContext';
import { formatUiText } from '../i18n/uiText';
import { PERSONAL_PERFORMANCE_TEXT } from '../locales/personalPerformance';
import { APP_ROUTE_PATHS } from '../routing/routes';
import type {
  PaperDecisionQualityItem,
  PaperDecisionQualityResponse,
  PortfolioAccountItem,
} from '../types/portfolio';

const PersonalPerformancePage: React.FC = () => {
  const { language } = useUiLanguage();
  const text = PERSONAL_PERFORMANCE_TEXT[language];
  const pageHeadingRef = useRef<HTMLHeadingElement | null>(null);
  const requestIdRef = useRef(0);

  const [accounts, setAccounts] = useState<PortfolioAccountItem[]>([]);
  const [accountId, setAccountId] = useState<number | null>(null);
  const [report, setReport] = useState<PaperDecisionQualityResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<ParsedApiError | null>(null);

  useRouteFocusTarget({
    routeId: APP_ROUTE_PATHS.portfolioPerformance,
    headingRef: pageHeadingRef,
    ready: !loading,
  });

  useEffect(() => {
    document.title = text.documentTitle;
  }, [text.documentTitle]);

  const paperAccounts = useMemo(
    () => accounts.filter((item) => (item.accountType || 'real') === 'paper'),
    [accounts],
  );

  const load = useCallback(async (mode: 'initial' | 'refresh' = 'initial') => {
    const requestId = requestIdRef.current + 1;
    requestIdRef.current = requestId;
    if (mode === 'initial') {
      setLoading(true);
    } else {
      setRefreshing(true);
    }
    setError(null);
    try {
      const accountList = await portfolioApi.getAccounts(false);
      if (requestIdRef.current !== requestId) return;
      const nextAccounts = accountList.accounts ?? [];
      setAccounts(nextAccounts);
      const papers = nextAccounts.filter((item) => (item.accountType || 'real') === 'paper');
      const selected =
        accountId != null && papers.some((item) => item.id === accountId)
          ? accountId
          : papers[0]?.id ?? null;
      setAccountId(selected);
      if (selected == null) {
        setReport(null);
        return;
      }
      const quality = await portfolioApi.getPaperDecisionQuality(selected, { limit: 50 });
      if (requestIdRef.current !== requestId) return;
      setReport(quality);
    } catch (cause) {
      if (requestIdRef.current !== requestId) return;
      setReport(null);
      setError(getParsedApiError(cause));
    } finally {
      if (requestIdRef.current === requestId) {
        setLoading(false);
        setRefreshing(false);
      }
    }
  }, [accountId]);

  useEffect(() => {
    void load('initial');
    // eslint-disable-next-line react-hooks/exhaustive-deps -- mount-only initial load
  }, []);

  const onAccountChange = async (nextId: number) => {
    const requestId = requestIdRef.current + 1;
    requestIdRef.current = requestId;
    setAccountId(nextId);
    setRefreshing(true);
    setError(null);
    try {
      const quality = await portfolioApi.getPaperDecisionQuality(nextId, { limit: 50 });
      if (requestIdRef.current !== requestId) return;
      setReport(quality);
    } catch (cause) {
      if (requestIdRef.current !== requestId) return;
      setReport(null);
      setError(getParsedApiError(cause));
    } finally {
      if (requestIdRef.current === requestId) {
        setRefreshing(false);
      }
    }
  };

  const aggregateScore = report?.aggregate?.processScore;
  const dims = report?.aggregate?.dimensions ?? {};
  const tradeColumns = useMemo<DataTableColumn<PaperDecisionQualityItem>[]>(() => [
    {
      id: 'trade',
      header: text.colTrade,
      cell: (item) => <span className="font-medium text-foreground">{item.symbol ?? '—'}</span>,
      rowHeader: true,
    },
    {
      id: 'side',
      header: text.colSide,
      cell: (item) => item.side ?? '—',
      nowrap: true,
    },
    {
      id: 'date',
      header: text.colDate,
      cell: (item) => item.tradeDate ?? '—',
      nowrap: true,
    },
    {
      id: 'score',
      header: text.colScore,
      cell: (item) => <span className="tabular-nums">{item.processScore.toFixed(1)}</span>,
      align: 'end',
      nowrap: true,
    },
    {
      id: 'signal',
      header: text.colSignal,
      cell: (item) => (item.linkedSignalId != null ? `#${item.linkedSignalId}` : text.noSignal),
      nowrap: true,
    },
    {
      id: 'reasons',
      header: text.colReasons,
      cell: (item) => (
        <ul className="list-disc space-y-1 pl-4">
          {(item.reasons ?? []).slice(0, 4).map((reason) => (
            <li key={`${reason.dimension}-${reason.code}`}>
              {reason.message}
            </li>
          ))}
        </ul>
      ),
      width: 'wide',
    },
  ], [text]);

  return (
    <AppPage data-testid="personal-performance-page" className="space-y-6">
      <PageHeader
        ref={pageHeadingRef}
        title={text.title}
        description={text.description}
        actions={(
          <div className="flex items-center gap-2">
            <Badge variant="info">{text.processOnlyBadge}</Badge>
            <IconButton
              type="button"
              variant="ghost"
              size="compact"
              aria-label={text.refreshAria}
              disabled={loading || refreshing}
              onClick={() => { void load('refresh'); }}
            >
              <RefreshCw
                className={`h-4 w-4 ${refreshing ? 'animate-spin' : ''}`}
                aria-hidden="true"
              />
            </IconButton>
          </div>
        )}
      />

      {loading ? (
        <StatePanel state="loading" title={text.refresh} data-testid="personal-performance-loading" />
      ) : null}

      {!loading && error ? (
        <StatePanel
          state="error"
          title={text.loadErrorTitle}
          description={<ApiErrorAlert error={error} />}
          action={(
            <Button type="button" variant="secondary" size="comfortable" onClick={() => { void load('refresh'); }}>
              {text.refresh}
            </Button>
          )}
        />
      ) : null}

      {!loading && !error && paperAccounts.length === 0 ? (
        <EmptyState
          title={text.noPaperAccountsTitle}
          description={text.noPaperAccountsDescription}
          action={(
            <Link
              to={APP_ROUTE_PATHS.portfolio}
              className="inline-flex h-7 items-center rounded-md border border-border bg-hover px-3 text-sm text-foreground"
            >
              {text.openPortfolio}
            </Link>
          )}
        />
      ) : null}

      {!loading && !error && paperAccounts.length > 0 ? (
        <div className="flex flex-col gap-4">
          <Surface level="interactive" className="flex flex-wrap items-center gap-3 px-4 py-3">
            <Select
              id="paper-account-select"
              label={text.selectAccount}
              value={String(accountId ?? '')}
              className="w-full max-w-sm [&>div]:w-full sm:w-auto"
              onChange={(value) => {
                const next = Number(value);
                if (Number.isFinite(next)) {
                  void onAccountChange(next);
                }
              }}
              options={paperAccounts.map((account) => ({
                value: String(account.id),
                label: `${account.name} (#${account.id})`,
              }))}
            />
            {report ? (
              <span className="text-xs text-secondary-text">
                {formatUiText(text.formulaVersion, { version: report.formulaVersion })}
              </span>
            ) : null}
          </Surface>

          <Surface level="section" className="p-4">
            <h2 className="mb-2 text-base font-semibold">{text.aggregateTitle}</h2>
            {report && report.sampleSize > 0 ? (
              <div className="flex flex-col gap-3">
                <div className="text-3xl font-semibold tabular-nums">
                  {aggregateScore == null ? '—' : aggregateScore.toFixed(1)}
                </div>
                <div className="text-sm text-secondary-text">
                  {formatUiText(text.sampleSize, {
                    count: report.sampleSize,
                    total: report.totalTradeCount,
                  })}
                </div>
                <div className="grid gap-2 sm:grid-cols-3">
                  {([
                    ['analysis_support', text.dimAnalysis],
                    ['risk_gate_compliance', text.dimRiskGate],
                    ['position_discipline', text.dimPosition],
                  ] as const).map(([key, label]) => {
                    const score = dims[key]?.score;
                    return (
                      <div key={key} className="rounded-md border border-border p-3">
                        <div className="text-xs text-secondary-text">{label}</div>
                        <div className="text-lg font-medium tabular-nums">
                          {score == null ? '—' : Number(score).toFixed(1)}
                        </div>
                      </div>
                    );
                  })}
                </div>
                <p className="text-xs text-secondary-text">{report.disclaimer}</p>
              </div>
            ) : (
              <EmptyState
                title={text.emptyTradesTitle}
                description={text.emptyTradesDescription}
                compact
              />
            )}
          </Surface>

          {report && report.items.length > 0 ? (
            <Surface level="section" className="overflow-hidden p-4">
              <h2 className="mb-3 text-base font-semibold">{text.tradeListTitle}</h2>
              <DataTable<PaperDecisionQualityItem>
                caption={text.tradeListTitle}
                columns={tradeColumns}
                rows={report.items}
                getRowKey={(item, index) => item.tradeId ?? `${item.symbol}-${item.tradeDate}-${index}`}
                emptyState={{
                  title: text.emptyTradesTitle,
                  description: text.emptyTradesDescription,
                }}
                density="compact"
                frame="embedded"
                minWidth="extra-wide"
              />
            </Surface>
          ) : null}

          <Surface level="section" className="p-4">
            <h2 className="mb-1 text-base font-semibold">{text.outcomePlaceholderTitle}</h2>
            <p className="text-sm text-secondary-text">{text.outcomePlaceholderDescription}</p>
            <p className="mt-2 text-xs text-secondary-text">{text.disclaimer}</p>
          </Surface>
        </div>
      ) : null}
    </AppPage>
  );
};

export default PersonalPerformancePage;
