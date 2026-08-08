// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type React from 'react';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { onboardingApi } from '../../api/onboarding';
import type { UiTextKey } from '../../i18n/uiText';
import type { AnalysisReport } from '../../types/analysis';
import type {
  DemoAnalysisPayload,
  FirstRunReadiness,
  UserOnboardingProfile,
} from '../../types/onboarding';
import { DEFAULT_ONBOARDING_PROFILE } from '../../types/onboarding';
import { Badge, Button, InlineAlert, Spinner, Surface } from '../common';
import BeginnerReportSummary from '../report/BeginnerReportSummary';

export type ZeroConfigFirstRunPanelProps = {
  /** Optional fixture for playground / tests; when omitted the panel fetches readiness. */
  readiness?: FirstRunReadiness | null;
  reportLanguage?: string;
  configVersion?: string;
  autoLoad?: boolean;
  onApplyLocalPreset?: (profile: UserOnboardingProfile) => void | Promise<void>;
  onContinue?: () => void;
  t: (key: UiTextKey, params?: Record<string, string | number>) => string;
};

function pathMessageKey(path: string): UiTextKey {
  if (path === 'local_ollama') return 'firstRun.pathLocal';
  if (path === 'configured') return 'firstRun.pathConfigured';
  return 'firstRun.pathDemo';
}

function toAnalysisReport(demo: DemoAnalysisPayload): AnalysisReport {
  return {
    meta: {
      queryId: demo.report.meta.queryId || demo.queryId,
      stockCode: demo.report.meta.stockCode || demo.stockCode,
      stockName: demo.report.meta.stockName || demo.stockName,
      reportType: (demo.report.meta.reportType as AnalysisReport['meta']['reportType']) || 'brief',
      reportLanguage: (demo.report.meta.reportLanguage as AnalysisReport['meta']['reportLanguage']) || 'zh',
      createdAt: demo.report.meta.createdAt || demo.createdAt,
      currentPrice: demo.report.meta.currentPrice ?? undefined,
      changePct: demo.report.meta.changePct ?? undefined,
      modelUsed: demo.report.meta.modelUsed ?? undefined,
    },
    summary: {
      analysisSummary: demo.report.summary.analysisSummary,
      operationAdvice: demo.report.summary.operationAdvice,
      action: (demo.report.summary.action as AnalysisReport['summary']['action']) || 'watch',
      actionLabel: demo.report.summary.actionLabel,
      trendPrediction: demo.report.summary.trendPrediction,
      sentimentScore: demo.report.summary.sentimentScore,
      sentimentLabel: demo.report.summary.sentimentLabel as AnalysisReport['summary']['sentimentLabel'],
    },
  };
}

/**
 * Self-contained zero-config first-run panel (#796).
 *
 * Does not mutate host pages. Integration Point: mount under Home onboarding
 * when setup is incomplete, or open from FirstRun success step.
 */
export const ZeroConfigFirstRunPanel: React.FC<ZeroConfigFirstRunPanelProps> = ({
  readiness: readinessProp,
  reportLanguage = 'zh',
  configVersion,
  autoLoad = true,
  onApplyLocalPreset,
  onContinue,
  t,
}) => {
  const [readiness, setReadiness] = useState<FirstRunReadiness | null>(readinessProp ?? null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [demo, setDemo] = useState<DemoAnalysisPayload | null>(null);
  const [demoLoading, setDemoLoading] = useState(false);
  const [applying, setApplying] = useState(false);
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

  const modelsLabel = useMemo(() => {
    const models = readiness?.localRuntime?.models || [];
    if (!models.length) return null;
    return t('firstRun.detectedModels', { models: models.slice(0, 3).join(', ') });
  }, [readiness, t]);

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
    if (readiness.primaryCta === 'start_with_local' || readiness.primaryPath === 'local_ollama') {
      if (onApplyLocalPreset) {
        setApplying(true);
        try {
          await onApplyLocalPreset({
            ...DEFAULT_ONBOARDING_PROFILE,
            experienceStage: 'beginner',
            infrastructure: 'local_models',
            reportLanguage,
          });
        } finally {
          setApplying(false);
        }
        return;
      }
      await loadDemo();
      return;
    }
    onContinue?.();
  }, [loadDemo, onApplyLocalPreset, onContinue, readiness, reportLanguage]);

  const handleApplyLocal = useCallback(async () => {
    if (!onApplyLocalPreset) {
      await loadDemo();
      return;
    }
    setApplying(true);
    try {
      await onApplyLocalPreset({
        ...DEFAULT_ONBOARDING_PROFILE,
        experienceStage: 'beginner',
        infrastructure: 'local_models',
        reportLanguage,
      });
    } finally {
      setApplying(false);
    }
  }, [loadDemo, onApplyLocalPreset, reportLanguage]);

  const demoReport = demo ? toAnalysisReport(demo) : null;

  return (
    <Surface
      as="section"
      level="section"
      padding="md"
      className="space-y-4"
      data-testid="zero-config-first-run-panel"
    >
      <header className="space-y-1">
        <div className="flex flex-wrap items-center gap-2">
          <h2 className="text-base font-semibold text-foreground">
            {t('firstRun.zeroConfigTitle')}
          </h2>
          {readiness?.beginnerModeRecommended ? (
            <Badge variant="default">{t('firstRun.beginnerRecommended')}</Badge>
          ) : null}
        </div>
        <p className="text-sm text-secondary-text">{t('firstRun.zeroConfigSubtitle')}</p>
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
            title={t(pathMessageKey(String(readiness.primaryPath)))}
            message={readiness.headline}
          />

          {readiness.recommendedPresetName ? (
            <p className="text-sm text-secondary-text">
              {t('firstRun.presetLabel', { name: readiness.recommendedPresetName })}
            </p>
          ) : null}

          {readiness.primaryPath === 'local_ollama' ? (
            <p className="text-sm text-secondary-text">
              {modelsLabel || t('firstRun.noModelsListed')}
            </p>
          ) : null}

          <div className="flex flex-wrap items-center gap-2">
            <Button
              variant="primary"
              size="default"
              disabled={applying || demoLoading}
              onClick={() => {
                void handlePrimary();
              }}
            >
              {readiness.primaryCta === 'start_with_local'
                ? t('firstRun.ctaLocal')
                : readiness.primaryCta === 'continue'
                  ? t('firstRun.ctaContinue')
                  : t('firstRun.ctaDemo')}
            </Button>

            {readiness.primaryPath === 'local_ollama' ? (
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

            {readiness.primaryPath === 'local_ollama' && onApplyLocalPreset && configVersion ? (
              <Button
                variant="secondary"
                size="default"
                disabled={applying}
                onClick={() => {
                  void handleApplyLocal();
                }}
              >
                {t('firstRun.ctaApplyLocal')}
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
            title={demo.isSample ? (demo.sampleBanner || t('firstRun.sampleBanner')) : t('firstRun.sampleBanner')}
            message={demo.sampleDisclaimer || t('firstRun.sampleDisclaimer')}
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
