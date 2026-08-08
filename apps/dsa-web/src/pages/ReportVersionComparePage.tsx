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

const ReportVersionComparePage: React.FC = () => {
  const { language } = useUiLanguage();
  const text = REPORT_VERSION_COMPARE_TEXT[language];
  const pageHeadingRef = useRef<HTMLHeadingElement | null>(null);
  const requestIdRef = useRef(0);

  const [stockCode, setStockCode] = useState('');
  const [runs, setRuns] = useState<ReportVersionRunItem[]>([]);
  const [baseRunId, setBaseRunId] = useState('');
  const [targetRunId, setTargetRunId] = useState('');
  const [result, setResult] = useState<ReportVersionCompareResponse | null>(null);
  const [loadingRuns, setLoadingRuns] = useState(false);
  const [comparing, setComparing] = useState(false);
  const [error, setError] = useState<ParsedApiError | null>(null);
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

  const loadRuns = useCallback(async () => {
    const code = stockCode.trim();
    if (!code) return;
    const requestId = requestIdRef.current + 1;
    requestIdRef.current = requestId;
    setLoadingRuns(true);
    setError(null);
    setResult(null);
    try {
      const response = await reportVersionCompareApi.listRuns({
        stockCode: code,
        page: 1,
        limit: 50,
      });
      if (requestIdRef.current !== requestId) return;
      setRuns(response.items ?? []);
      setHasLoadedRuns(true);
      setBaseRunId('');
      setTargetRunId('');
    } catch (cause) {
      if (requestIdRef.current !== requestId) return;
      setRuns([]);
      setHasLoadedRuns(true);
      setError(getParsedApiError(cause));
    } finally {
      if (requestIdRef.current === requestId) {
        setLoadingRuns(false);
      }
    }
  }, [stockCode]);

  const runCompare = useCallback(async () => {
    const code = stockCode.trim();
    if (!code || !baseRunId || !targetRunId) return;
    if (baseRunId === targetRunId) {
      setError(null);
      setResult(null);
      return;
    }
    const requestId = requestIdRef.current + 1;
    requestIdRef.current = requestId;
    setComparing(true);
    setError(null);
    try {
      const response = await reportVersionCompareApi.compare({
        stockCode: code,
        baseRunId,
        targetRunId,
      });
      if (requestIdRef.current !== requestId) return;
      setResult(response);
    } catch (cause) {
      if (requestIdRef.current !== requestId) return;
      setResult(null);
      setError(getParsedApiError(cause));
    } finally {
      if (requestIdRef.current === requestId) {
        setComparing(false);
      }
    }
  }, [baseRunId, stockCode, targetRunId]);

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
            onClick={() => void loadRuns()}
            disabled={loadingRuns || !stockCode.trim()}
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
              value={stockCode}
              onChange={(event) => setStockCode(event.target.value)}
              placeholder={text.stockPlaceholder}
              onKeyDown={(event) => {
                if (event.key === 'Enter') {
                  event.preventDefault();
                  void loadRuns();
                }
              }}
            />
          </Field>
          <Button
            type="button"
            variant="secondary"
            data-testid="report-version-compare-load-runs"
            onClick={() => void loadRuns()}
            disabled={loadingRuns || !stockCode.trim()}
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
            disabled={runOptions.length === 0}
          />
          <Select
            label={text.targetLabel}
            ariaLabel={text.targetLabel}
            value={targetRunId}
            onChange={setTargetRunId}
            options={runOptions}
            placeholder={text.selectPlaceholder}
            disabled={runOptions.length === 0}
          />
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <Button
            type="button"
            variant="primary"
            data-testid="report-version-compare-submit"
            onClick={() => void runCompare()}
            disabled={
              comparing
              || !baseRunId
              || !targetRunId
              || baseRunId === targetRunId
              || !stockCode.trim()
            }
            isLoading={comparing}
          >
            <GitCompareArrows className="h-4 w-4" aria-hidden="true" />
            {comparing ? text.comparing : text.compare}
          </Button>
        </div>
      </Surface>

      {error ? (
        <div className="space-y-3" data-testid="report-version-compare-error">
          <ApiErrorAlert error={error} actionLabel={text.retry} onAction={() => void loadRuns()} />
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
