// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type React from 'react';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { GitCompareArrows, RefreshCw } from 'lucide-react';
import { useSearchParams } from 'react-router-dom';
import { type ReportVersionRunItem } from '../api/reportVersionCompare';
import {
  ApiErrorAlert,
  AppPage,
  Button,
  EmptyState,
  Field,
  IconButton,
  PageHeader,
  Select,
  Surface,
} from '../components/common';
import { ReportVersionCompareView } from '../components/report-version-compare';
import { useRouteFocusTarget } from '../components/routing';
import { useUiLanguage } from '../contexts/UiLanguageContext';
import { useReportVersionCompareQueries } from '../hooks/useReportVersionCompareQueries';
import { formatUiText } from '../i18n/uiText';
import { REPORT_VERSION_COMPARE_TEXT } from '../locales/reportVersionCompare';
import {
  APP_ROUTE_PATHS,
  REPORT_VERSION_COMPARE_ROUTE_QUERY_KEYS,
  parsePositiveRouteInteger,
} from '../routing/routes';

function formatRunOption(
  text: (typeof REPORT_VERSION_COMPARE_TEXT)['en'],
  run: ReportVersionRunItem,
): string {
  return formatUiText(text.runOption, {
    time: run.createdAt ?? '—',
    action: run.actionLabel ?? run.action ?? '—',
    score:
      run.sentimentScore === null || run.sentimentScore === undefined
        ? '—'
        : String(run.sentimentScore),
    model: run.modelUsed ?? '—',
    fingerprint: run.configFingerprint ?? '—',
  });
}

function normalizeStockIdentity(value: string): string {
  return value.trim().toUpperCase();
}

const ReportVersionComparePage: React.FC = () => {
  const { language } = useUiLanguage();
  const text = REPORT_VERSION_COMPARE_TEXT[language];
  const [searchParams] = useSearchParams();
  const pageHeadingRef = useRef<HTMLHeadingElement | null>(null);
  const appliedRoutePrefillRef = useRef<string | null>(null);
  const autoComparedRouteRef = useRef<string | null>(null);

  const routePrefill = useMemo(() => ({
    stockCode: normalizeStockIdentity(
      searchParams.get(REPORT_VERSION_COMPARE_ROUTE_QUERY_KEYS.stock) ?? '',
    ),
    baseRunId: parsePositiveRouteInteger(
      searchParams.get(REPORT_VERSION_COMPARE_ROUTE_QUERY_KEYS.baseRunId),
    ),
    targetRunId: parsePositiveRouteInteger(
      searchParams.get(REPORT_VERSION_COMPARE_ROUTE_QUERY_KEYS.targetRunId),
    ),
  }), [searchParams]);

  const [draftStockCode, setDraftStockCode] = useState('');
  const [baseRunId, setBaseRunId] = useState('');
  const [targetRunId, setTargetRunId] = useState('');
  const {
    runs,
    totalRuns,
    runPage,
    loadedStockCode,
    hasLoadedRuns,
    result,
    loadingRuns,
    loadingMore,
    comparing,
    error,
    failedOperation,
    loadRuns,
    compare,
    cancelInFlight,
  } = useReportVersionCompareQueries();

  useRouteFocusTarget({
    routeId: APP_ROUTE_PATHS.researchReportCompare,
    headingRef: pageHeadingRef,
    ready: !loadingRuns && !comparing,
  });

  useEffect(() => {
    document.title = text.documentTitle;
  }, [text.documentTitle]);

  const runOptions = useMemo(
    () =>
      runs.map((run) => ({
        value: run.runId,
        label: formatRunOption(text, run),
      })),
    [runs, text],
  );

  const draftIdentity = normalizeStockIdentity(draftStockCode);
  const loadedIdentityMatchesDraft = Boolean(
    loadedStockCode && draftIdentity === loadedStockCode,
  );

  const loadDraftRuns = useCallback(() => {
    const code = draftStockCode.trim();
    if (!code) return;
    setBaseRunId('');
    setTargetRunId('');
    void loadRuns({ stockCode: code, page: 1, append: false });
  }, [draftStockCode, loadRuns]);

  const runCompare = useCallback(() => {
    if (!loadedStockCode || !loadedIdentityMatchesDraft) return;
    void compare({
      stockCode: loadedStockCode,
      baseRunId,
      targetRunId,
    });
  }, [baseRunId, compare, loadedIdentityMatchesDraft, loadedStockCode, targetRunId]);

  const retryFailedOperation = useCallback(() => {
    if (!failedOperation) return;
    if (failedOperation.kind === 'compare') {
      void compare({
        stockCode: failedOperation.stockCode,
        baseRunId: failedOperation.baseRunId,
        targetRunId: failedOperation.targetRunId,
      });
    } else {
      void loadRuns({
        stockCode: failedOperation.stockCode,
        page: failedOperation.page,
        append: failedOperation.append,
      });
    }
  }, [compare, failedOperation, loadRuns]);

  /* eslint-disable react-hooks/set-state-in-effect -- URL search is the external prefill source */
  useEffect(() => {
    if (!routePrefill.stockCode) return;
    const routeKey = [
      routePrefill.stockCode,
      routePrefill.baseRunId ?? '',
      routePrefill.targetRunId ?? '',
    ].join(':');
    if (appliedRoutePrefillRef.current === routeKey) return;
    appliedRoutePrefillRef.current = routeKey;
    autoComparedRouteRef.current = null;
    setDraftStockCode(routePrefill.stockCode);
    setBaseRunId(routePrefill.baseRunId ? String(routePrefill.baseRunId) : '');
    setTargetRunId(routePrefill.targetRunId ? String(routePrefill.targetRunId) : '');
    void loadRuns({
      stockCode: routePrefill.stockCode,
      page: 1,
      append: false,
    });
  }, [loadRuns, routePrefill]);
  /* eslint-enable react-hooks/set-state-in-effect */

  useEffect(() => {
    if (
      !hasLoadedRuns
      || loadingRuns
      || !loadedStockCode
      || loadedStockCode !== routePrefill.stockCode
      || !routePrefill.baseRunId
      || !routePrefill.targetRunId
      || routePrefill.baseRunId === routePrefill.targetRunId
    ) return;
    const routeKey = [
      loadedStockCode,
      routePrefill.baseRunId,
      routePrefill.targetRunId,
    ].join(':');
    if (autoComparedRouteRef.current === routeKey) return;
    autoComparedRouteRef.current = routeKey;
    void compare({
      stockCode: loadedStockCode,
      baseRunId: String(routePrefill.baseRunId),
      targetRunId: String(routePrefill.targetRunId),
    });
  }, [
    compare,
    hasLoadedRuns,
    loadedStockCode,
    loadingRuns,
    routePrefill,
  ]);

  const handleDraftStockChange = useCallback((value: string) => {
    setDraftStockCode(value);
    const nextIdentity = normalizeStockIdentity(value);
    if (loadedStockCode && nextIdentity !== loadedStockCode) {
      cancelInFlight();
      setBaseRunId('');
      setTargetRunId('');
    }
  }, [cancelInFlight, loadedStockCode]);

  const selectionHint = (() => {
    if (!hasLoadedRuns) return null;
    if (runs.length === 0) {
      return (
        <EmptyState
          data-testid="report-version-compare-empty-runs"
          title={text.emptyRunsTitle}
          description={text.emptyRunsDescription}
          compact
        />
      );
    }
    if (runs.length === 1) {
      return (
        <EmptyState
          data-testid="report-version-compare-need-two"
          title={text.needTwoRunsTitle}
          description={text.needTwoRunsDescription}
          compact
        />
      );
    }
    if (baseRunId && targetRunId && baseRunId === targetRunId) {
      return (
        <EmptyState
          data-testid="report-version-compare-same-run"
          title={text.sameRunTitle}
          description={text.sameRunDescription}
          compact
        />
      );
    }
    if (!baseRunId || !targetRunId) {
      return (
        <EmptyState
          data-testid="report-version-compare-pick-both"
          title={text.pickBothTitle}
          description={text.pickBothDescription}
          compact
        />
      );
    }
    return null;
  })();

  return (
    <AppPage data-testid="report-version-compare-page" className="space-y-6">
      <PageHeader
        ref={pageHeadingRef}
        title={text.title}
        description={text.description}
        actions={(
          <IconButton
            aria-label={text.loadRuns}
            onClick={loadDraftRuns}
            disabled={loadingRuns || !draftStockCode.trim()}
          >
            <RefreshCw className={loadingRuns ? 'animate-spin' : undefined} />
          </IconButton>
        )}
      />

      <Surface className="space-y-4 p-4">
        <div className="grid gap-4 md:grid-cols-[1fr_auto] md:items-end">
          <Field
            label={text.stockLabel}
            controlId="report-version-compare-stock"
          >
            <input
              id="report-version-compare-stock"
              data-testid="report-version-compare-stock-input"
              className="w-full min-h-11 rounded-lg border border-border bg-card px-3 text-sm text-foreground outline-none focus-visible:ring-2 focus-visible:ring-foreground/10 sm:min-h-9"
              value={draftStockCode}
              onChange={(event) => handleDraftStockChange(event.target.value)}
              placeholder={text.stockPlaceholder}
              onKeyDown={(event) => {
                if (event.key === 'Enter') {
                  event.preventDefault();
                  loadDraftRuns();
                }
              }}
            />
          </Field>
          <Button
            type="button"
            variant="secondary"
            data-testid="report-version-compare-load-runs"
            onClick={loadDraftRuns}
            disabled={loadingRuns || !draftStockCode.trim()}
            isLoading={loadingRuns}
          >
            {loadingRuns ? text.loadingRuns : text.loadRuns}
          </Button>
        </div>

        <div className="grid gap-4 md:grid-cols-2">
          <Select
            label={text.baseLabel}
            ariaLabel={text.baseLabel}
            value={baseRunId}
            onChange={setBaseRunId}
            options={runOptions}
            placeholder={text.selectPlaceholder}
            disabled={runOptions.length === 0 || !loadedIdentityMatchesDraft}
          />
          <Select
            label={text.targetLabel}
            ariaLabel={text.targetLabel}
            value={targetRunId}
            onChange={setTargetRunId}
            options={runOptions}
            placeholder={text.selectPlaceholder}
            disabled={runOptions.length === 0 || !loadedIdentityMatchesDraft}
          />
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <Button
            type="button"
            variant="primary"
            data-testid="report-version-compare-submit"
            onClick={runCompare}
            disabled={
              comparing
              || !baseRunId
              || !targetRunId
              || baseRunId === targetRunId
              || !loadedIdentityMatchesDraft
            }
            isLoading={comparing}
          >
            <GitCompareArrows className="h-4 w-4" aria-hidden="true" />
            {comparing ? text.comparing : text.compare}
          </Button>
          {loadedIdentityMatchesDraft && runs.length < totalRuns ? (
            <Button
              type="button"
              variant="secondary"
              data-testid="report-version-compare-load-more"
              onClick={() => void loadRuns({
                stockCode: loadedStockCode!,
                page: runPage + 1,
                append: true,
              })}
              disabled={loadingMore}
              isLoading={loadingMore}
            >
              {loadingMore ? text.loadingRuns : text.loadMore}
            </Button>
          ) : null}
        </div>
      </Surface>

      {error ? (
        <div className="space-y-3" data-testid="report-version-compare-error">
          <ApiErrorAlert
            error={error}
            actionLabel={text.retry}
            onAction={retryFailedOperation}
          />
        </div>
      ) : null}

      {selectionHint}

      {!error && !selectionHint ? (
        <ReportVersionCompareView
          language={language}
          result={result}
          idle={!result}
        />
      ) : null}
    </AppPage>
  );
};

export default ReportVersionComparePage;
