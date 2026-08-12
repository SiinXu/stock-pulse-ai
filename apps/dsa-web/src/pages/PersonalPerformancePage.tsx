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
  EmptyState,
  IconButton,
  PageHeader,
  StatePanel,
  Surface,
} from '../components/common';
import { useRouteFocusTarget } from '../components/routing';
import { useUiLanguage } from '../contexts/UiLanguageContext';
import { formatUiText } from '../i18n/uiText';
import { PERSONAL_PERFORMANCE_TEXT } from '../locales/personalPerformance';
import { APP_ROUTE_PATHS } from '../routing/routes';
import type {
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
    setAccountId(nextId);
    setRefreshing(true);
    setError(null);
    try {
      const quality = await portfolioApi.getPaperDecisionQuality(nextId, { limit: 50 });
      setReport(quality);
    } catch (cause) {
      setReport(null);
      setError(getParsedApiError(cause));
    } finally {
      setRefreshing(false);
    }
  };

  const aggregateScore = report?.aggregate?.processScore;
  const dims = report?.aggregate?.dimensions ?? {};

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
            <label className="text-sm font-medium" htmlFor="paper-account-select">
              {text.selectAccount}
            </label>
            <select
              id="paper-account-select"
              className="rounded-md border border-border bg-background px-2 py-1 text-sm"
              value={accountId ?? ''}
              onChange={(event) => {
                const next = Number(event.target.value);
                if (Number.isFinite(next)) {
                  void onAccountChange(next);
                }
              }}
            >
              {paperAccounts.map((account) => (
                <option key={account.id} value={account.id}>
                  {account.name} (#{account.id})
                </option>
              ))}
            </select>
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
                  {formatUiText(text.sampleSize, { count: report.sampleSize })}
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
            <Surface level="section" className="overflow-x-auto p-4">
              <h2 className="mb-3 text-base font-semibold">{text.tradeListTitle}</h2>
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border text-left text-secondary-text">
                    <th className="py-2 pr-3">{text.colTrade}</th>
                    <th className="py-2 pr-3">{text.colSide}</th>
                    <th className="py-2 pr-3">{text.colDate}</th>
                    <th className="py-2 pr-3">{text.colScore}</th>
                    <th className="py-2 pr-3">{text.colSignal}</th>
                    <th className="py-2">{text.colReasons}</th>
                  </tr>
                </thead>
                <tbody>
                  {report.items.map((item) => (
                    <tr
                      key={`${item.tradeId}-${item.symbol}-${item.tradeDate}`}
                      className="border-b border-border/60 align-top"
                    >
                      <td className="py-2 pr-3 font-medium">{item.symbol ?? '—'}</td>
                      <td className="py-2 pr-3">{item.side ?? '—'}</td>
                      <td className="py-2 pr-3">{item.tradeDate ?? '—'}</td>
                      <td className="py-2 pr-3 tabular-nums">{item.processScore.toFixed(1)}</td>
                      <td className="py-2 pr-3">
                        {item.linkedSignalId != null ? `#${item.linkedSignalId}` : text.noSignal}
                      </td>
                      <td className="py-2">
                        <ul className="list-disc space-y-1 pl-4">
                          {(item.reasons ?? []).slice(0, 4).map((reason) => (
                            <li key={`${reason.dimension}-${reason.code}`}>
                              {reason.message}
                            </li>
                          ))}
                        </ul>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
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
