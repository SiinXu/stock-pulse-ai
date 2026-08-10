// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type React from 'react';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { GitCompareArrows, RefreshCw } from 'lucide-react';
import {
  reportVersionCompareApi,
  type ReportVersionCompareResponse,
  type ReportVersionRunItem,
} from '../api/reportVersionCompare';
import { getParsedApiError, type ParsedApiError } from '../api/error';
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
import { formatUiText } from '../i18n/uiText';
import { REPORT_VERSION_COMPARE_TEXT } from '../locales/reportVersionCompare';
import { APP_ROUTE_PATHS } from '../routing/routes';

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

const RUN_PAGE_SIZE = 50;

type FailedOperation =
  | {
    kind: 'list';
    stockCode: string;
    page: number;
    append: boolean;
  }
  | {
    kind: 'compare';
    stockCode: string;
    baseRunId: string;
    targetRunId: string;
  };

function normalizeStockIdentity(value: string): string {
  return value.trim().toUpperCase();
}

const ReportVersionComparePage: React.FC = () => {
  const { language } = useUiLanguage();
  const text = REPORT_VERSION_COMPARE_TEXT[language];
  const pageHeadingRef = useRef<HTMLHeadingElement | null>(null);
  const requestIdRef = useRef(0);

  const [draftStockCode, setDraftStockCode] = useState('');
  const [loadedStockCode, setLoadedStockCode] = useState<string | null>(null);
  const [runs, setRuns] = useState<ReportVersionRunItem[]>([]);
  const [totalRuns, setTotalRuns] = useState(0);
  const [runPage, setRunPage] = useState(1);
  const [baseRunId, setBaseRunId] = useState('');
  const [targetRunId, setTargetRunId] = useState('');
  const [result, setResult] = useState<ReportVersionCompareResponse | null>(null);
  const [loadingRuns, setLoadingRuns] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [comparing, setComparing] = useState(false);
  const [error, setError] = useState<ParsedApiError | null>(null);
  const [failedOperation, setFailedOperation] = useState<FailedOperation | null>(null);
  const [hasLoadedRuns, setHasLoadedRuns] = useState(false);

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

  const loadRuns = useCallback(async ({
    stockCode,
    page,
    append,
  }: Extract<FailedOperation, { kind: 'list' }>) => {
    const code = stockCode.trim();
    if (!code) return;
    const requestId = requestIdRef.current + 1;
    requestIdRef.current = requestId;
    if (append) setLoadingMore(true);
    else setLoadingRuns(true);
    setError(null);
    setFailedOperation(null);
    if (!append) setResult(null);
    try {
      const response = await reportVersionCompareApi.listRuns({
        stockCode: code,
        page,
        limit: RUN_PAGE_SIZE,
      });
      if (requestIdRef.current !== requestId) return;
      if (append) {
        setRuns((current) => {
          const byId = new Map(current.map((run) => [run.runId, run]));
          for (const run of response.items ?? []) byId.set(run.runId, run);
          return [...byId.values()];
        });
      } else {
        setRuns(response.items ?? []);
        setBaseRunId('');
        setTargetRunId('');
      }
      setLoadedStockCode(normalizeStockIdentity(response.stockCode || code));
      setTotalRuns(response.total);
      setRunPage(response.page);
      setHasLoadedRuns(true);
    } catch (cause) {
      if (requestIdRef.current !== requestId) return;
      if (!append) {
        setRuns([]);
        setTotalRuns(0);
        setLoadedStockCode(null);
        setHasLoadedRuns(true);
      }
      setError(getParsedApiError(cause));
      setFailedOperation({ kind: 'list', stockCode: code, page, append });
    } finally {
      if (requestIdRef.current === requestId) {
        if (append) setLoadingMore(false);
        else setLoadingRuns(false);
      }
    }
  }, []);

  const compareRuns = useCallback(async ({
    stockCode,
    baseRunId: baseId,
    targetRunId: targetId,
  }: Extract<FailedOperation, { kind: 'compare' }>) => {
    if (!stockCode || !baseId || !targetId) return;
    if (baseId === targetId) {
      setError(null);
      setResult(null);
      return;
    }
    const requestId = requestIdRef.current + 1;
    requestIdRef.current = requestId;
    setComparing(true);
    setError(null);
    setFailedOperation(null);
    try {
      const response = await reportVersionCompareApi.compare({
        stockCode,
        baseRunId: baseId,
        targetRunId: targetId,
      });
      if (requestIdRef.current !== requestId) return;
      setResult(response);
    } catch (cause) {
      if (requestIdRef.current !== requestId) return;
      setResult(null);
      setError(getParsedApiError(cause));
      setFailedOperation({
        kind: 'compare',
        stockCode,
        baseRunId: baseId,
        targetRunId: targetId,
      });
    } finally {
      if (requestIdRef.current === requestId) {
        setComparing(false);
      }
    }
  }, []);

  const loadDraftRuns = useCallback(() => {
    const code = draftStockCode.trim();
    if (!code) return;
    void loadRuns({ kind: 'list', stockCode: code, page: 1, append: false });
  }, [draftStockCode, loadRuns]);

  const runCompare = useCallback(() => {
    if (!loadedStockCode || !loadedIdentityMatchesDraft) return;
    void compareRuns({
      kind: 'compare',
      stockCode: loadedStockCode,
      baseRunId,
      targetRunId,
    });
  }, [baseRunId, compareRuns, loadedIdentityMatchesDraft, loadedStockCode, targetRunId]);

  const retryFailedOperation = useCallback(() => {
    if (!failedOperation) return;
    if (failedOperation.kind === 'compare') {
      void compareRuns(failedOperation);
    } else {
      void loadRuns(failedOperation);
    }
  }, [compareRuns, failedOperation, loadRuns]);

  const handleDraftStockChange = useCallback((value: string) => {
    setDraftStockCode(value);
    const nextIdentity = normalizeStockIdentity(value);
    if (loadedStockCode && nextIdentity !== loadedStockCode) {
      requestIdRef.current += 1;
      setLoadedStockCode(null);
      setRuns([]);
      setTotalRuns(0);
      setRunPage(1);
      setBaseRunId('');
      setTargetRunId('');
      setResult(null);
      setError(null);
      setFailedOperation(null);
      setHasLoadedRuns(false);
      setLoadingRuns(false);
      setLoadingMore(false);
      setComparing(false);
    }
  }, [loadedStockCode]);

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
                kind: 'list',
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
