// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type React from 'react';
import { useCallback, useEffect, useState } from 'react';
import { X } from 'lucide-react';
import { onboardingApi } from '../../api/onboarding';
import type { UiTextKey } from '../../i18n/uiText';
import type { AnalysisReport, ReportLanguage } from '../../types/analysis';
import type {
  DemoAnalysisPayload,
  FirstRunPrimaryPath,
  FirstRunReasonCode,
  FirstRunReadiness,
} from '../../types/onboarding';
import { Badge, Button, IconButton, InlineAlert, Spinner, Surface } from '../common';
import BeginnerReportSummary from '../report/BeginnerReportSummary';

export type ZeroConfigFirstRunPanelProps = {
  /** Optional fixture for playground / tests; when omitted the panel fetches readiness. */
  readiness?: FirstRunReadiness | null;
  reportLanguage?: ReportLanguage;
  autoLoad?: boolean;
  onContinue?: (readiness: FirstRunReadiness) => void | Promise<void>;
  onDismiss?: () => void;
  t: (key: UiTextKey, params?: Record<string, string | number>) => string;
};

function pathMessageKey(path: FirstRunPrimaryPath): UiTextKey {
  if (path === 'local_ollama') return 'firstRun.pathLocal';
  if (path === 'configured') return 'firstRun.pathConfigured';
  return 'firstRun.pathDemo';
}

function reasonMessageKey(reasonCode: FirstRunReasonCode): UiTextKey {
  if (reasonCode === 'primary_model_configured') return 'firstRun.reasonConfigured';
  if (reasonCode === 'local_model_ready') return 'firstRun.detectedModels';
  if (reasonCode === 'local_runtime_no_models') return 'firstRun.noModelsListed';
  if (reasonCode === 'local_detect_disabled') return 'firstRun.reasonDetectDisabled';
  return 'firstRun.reasonUnavailable';
}

function toAnalysisReport(demo: DemoAnalysisPayload): AnalysisReport {
  return {
    meta: {
      queryId: demo.report.meta.queryId,
      stockCode: demo.report.meta.stockCode,
      stockName: demo.report.meta.stockName,
      reportType: demo.report.meta.reportType,
      reportLanguage: demo.report.meta.reportLanguage,
      createdAt: demo.report.meta.createdAt,
      currentPrice: demo.report.meta.currentPrice ?? undefined,
      changePct: demo.report.meta.changePct ?? undefined,
      modelUsed: demo.report.meta.modelUsed ?? undefined,
    },
    summary: {
      analysisSummary: demo.report.summary.analysisSummary,
      operationAdvice: demo.report.summary.operationAdvice,
      action: demo.report.summary.action,
      actionLabel: demo.report.summary.actionLabel,
      trendPrediction: demo.report.summary.trendPrediction,
      sentimentScore: demo.report.summary.sentimentScore,
      sentimentLabel: demo.report.summary.sentimentLabel,
    },
  };
}

/**
 * Self-contained zero-config first-run panel (#796).
 * Readiness is observational; host-owned navigation is explicit and demo data
 * stays local to the panel.
 */
export const ZeroConfigFirstRunPanel: React.FC<ZeroConfigFirstRunPanelProps> = ({
  readiness: readinessProp,
  reportLanguage = 'zh',
  autoLoad = true,
  onContinue,
  onDismiss,
  t,
}) => {
  const [readiness, setReadiness] = useState<FirstRunReadiness | null>(readinessProp ?? null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [demo, setDemo] = useState<DemoAnalysisPayload | null>(null);
  const [demoLoading, setDemoLoading] = useState(false);
  const [showProfessional, setShowProfessional] = useState(false);

  useEffect(() => {
    if (readinessProp !== undefined) {
      setReadiness(readinessProp);
    }
  }, [readinessProp]);

  useEffect(() => {
    if (!autoLoad || readinessProp !== undefined) {
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    onboardingApi.getFirstRunReadiness()
      .then((payload) => {
        if (!cancelled) setReadiness(payload);
      })
      .catch(() => {
        if (!cancelled) setError(t('firstRun.loadError'));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [autoLoad, readinessProp, t]);

  const loadDemo = useCallback(async () => {
    setDemoLoading(true);
    setError(null);
    try {
      const payload = await onboardingApi.getDemoAnalysis(reportLanguage);
      setDemo(payload);
      setShowProfessional(false);
    } catch {
      setError(t('firstRun.loadError'));
    } finally {
      setDemoLoading(false);
    }
  }, [reportLanguage, t]);

  const handlePrimary = useCallback(async () => {
    if (!readiness) return;
    if (readiness.primaryCta === 'view_demo' || readiness.primaryPath === 'demo') {
      await loadDemo();
      return;
    }
    if (!onContinue) return;
    setError(null);
    try {
      await onContinue(readiness);
    } catch {
      setError(t('firstRun.actionError'));
    }
  }, [loadDemo, onContinue, readiness, t]);

  const demoReport = demo ? toAnalysisReport(demo) : null;

  return (
    <Surface
      as="section"
      level="section"
      padding="md"
      className="space-y-4"
      data-testid="zero-config-first-run-panel"
    >
      <header className="flex items-start justify-between gap-3">
        <div className="min-w-0 space-y-1">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="text-base font-semibold text-foreground">
              {t('firstRun.zeroConfigTitle')}
            </h2>
            {readiness?.beginnerModeRecommended ? (
              <Badge variant="default">{t('firstRun.beginnerRecommended')}</Badge>
            ) : null}
          </div>
          <p className="text-sm text-secondary-text">{t('firstRun.zeroConfigSubtitle')}</p>
        </div>
        {onDismiss ? (
          <IconButton
            type="button"
            variant="ghost"
            size="default"
            aria-label={t('common.close')}
            onClick={onDismiss}
          >
            <X aria-hidden="true" />
          </IconButton>
        ) : null}
      </header>

      {loading ? (
        <div className="flex items-center gap-2 text-sm text-muted-text">
          <Spinner size="sm" />
          <span>{t('firstRun.loading')}</span>
        </div>
      ) : null}

      {error ? (
        <InlineAlert variant="danger" size="compact" title={t('onboarding.errorTitle')} message={error} />
      ) : null}

      {readiness && !loading ? (
        <div className="space-y-3">
          <InlineAlert
            variant={readiness.primaryPath === 'configured' ? 'info' : 'warning'}
            size="compact"
            title={t(pathMessageKey(readiness.primaryPath))}
            message={t(reasonMessageKey(readiness.reasonCode), readiness.reasonParams)}
          />

          {readiness.primaryPath !== 'demo' && !onContinue ? (
            <InlineAlert
              variant="warning"
              size="compact"
              title={t('onboarding.errorTitle')}
              message={t('firstRun.integrationUnavailable')}
            />
          ) : null}

          <div className="flex flex-wrap items-center gap-2">
            <Button
              variant="primary"
              size="default"
              disabled={demoLoading || (readiness.primaryPath !== 'demo' && !onContinue)}
              onClick={() => {
                void handlePrimary();
              }}
            >
              {readiness.primaryCta === 'open_local_setup'
                ? t('firstRun.ctaLocal')
                : readiness.primaryCta === 'continue'
                  ? t('firstRun.ctaContinue')
                  : t('firstRun.ctaDemo')}
            </Button>

            {readiness.primaryPath !== 'demo' && readiness.demoAvailable ? (
              <Button
                variant="secondary"
                size="default"
                disabled={demoLoading}
                onClick={() => {
                  void loadDemo();
                }}
              >
                {t('firstRun.ctaDemo')}
              </Button>
            ) : null}

            {demo ? (
              <Button
                variant="ghost"
                size="default"
                onClick={() => setDemo(null)}
              >
                {t('firstRun.hideDemo')}
              </Button>
            ) : null}
          </div>
        </div>
      ) : null}

      {demoLoading ? (
        <div className="flex items-center gap-2 text-sm text-muted-text">
          <Spinner size="sm" />
          <span>{t('firstRun.demoLoading')}</span>
        </div>
      ) : null}

      {demo && demoReport ? (
        <div className="space-y-3" data-testid="zero-config-demo-analysis">
          <InlineAlert
            variant="warning"
            size="compact"
            title={demo.sampleBanner}
            message={demo.sampleDisclaimer}
          />
          {!showProfessional ? (
            <BeginnerReportSummary
              data={demoReport}
              onShowProfessional={() => setShowProfessional(true)}
            />
          ) : (
            <Surface level="interactive" padding="md" className="space-y-2 text-sm text-secondary-text">
              <p className="font-medium text-foreground">{demo.stockName} ({demo.stockCode})</p>
              <p className="whitespace-pre-wrap">{demoReport.summary.analysisSummary}</p>
              <p className="whitespace-pre-wrap">{demoReport.summary.operationAdvice}</p>
              <Button variant="secondary" size="default" onClick={() => setShowProfessional(false)}>
                {t('firstRun.hideDemo')}
              </Button>
            </Surface>
          )}
        </div>
      ) : null}
    </Surface>
  );
};

export default ZeroConfigFirstRunPanel;
