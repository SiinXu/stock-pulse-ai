import type React from 'react';
import { lazy, Suspense } from 'react';
import { Badge, JsonViewer, Section, Surface } from '../common';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import type { UiLanguage, UiTextKey } from '../../i18n/uiText';
import type {
  DecisionSignalFeedbackItem,
  DecisionSignalFeedbackValue,
  DecisionSignalItem,
  DecisionSignalOutcomeItem,
  DecisionSignalStatus,
} from '../../types/decisionSignals';
import {
  buildDecisionActionLabelMap,
  getDecisionActionTone,
  type DecisionActionTone,
} from '../../utils/decisionAction';
import { cn } from '../../utils/cn';
import { parseDecisionSignalDate } from '../../utils/decisionSignalTime';
import { getUiLocale } from '../../utils/uiLocale';
import { getDecisionSignalProfileLabel } from '../../utils/decisionSignalProfile';
import { getDecisionSignalPresentation } from '../../utils/decisionSignalPresentation';
import {
  getDecisionSignalHorizonLabel,
  getDecisionSignalMarketLabel,
  getDecisionSignalMarketPhaseLabel,
  getDecisionSignalPlanQualityLabel,
} from '../../utils/decisionSignalLabels';
import { getReportLanguageForUi } from '../../utils/reportLanguage';
import ReportExportDownloadButtons from '../report/ReportExportDownloadButtons';
import { ReportRiskGateBanner } from '../report/ReportRiskGateBanner';
import { buildRiskGatePresentation } from '../report/reportRiskGateUtils';
import { DecisionSignalOutcomeBadge } from './DecisionSignalDisplay';

const DecisionSignalCommitteeInsights = lazy(() => import('./DecisionSignalCommitteeInsights'));

type BadgeVariant = 'default' | 'success' | 'warning' | 'danger' | 'info' | 'history';

const STATUS_LABEL_KEYS: Record<DecisionSignalStatus, UiTextKey> = {
  active: 'decisionSignals.active',
  expired: 'decisionSignals.expired',
  invalidated: 'decisionSignals.invalidated',
  closed: 'decisionSignals.closed',
  archived: 'decisionSignals.archived',
};

const STATUS_VARIANTS: Record<DecisionSignalStatus, BadgeVariant> = {
  active: 'success',
  expired: 'warning',
  invalidated: 'danger',
  closed: 'default',
  archived: 'history',
};

const ACTION_VARIANTS: Record<DecisionActionTone, BadgeVariant> = {
  success: 'success',
  warning: 'warning',
  danger: 'danger',
  default: 'default',
};

function formatDateTime(value: string | null | undefined, language: UiLanguage): string {
  const date = parseDecisionSignalDate(value);
  if (!date) return '-';
  return new Intl.DateTimeFormat(getUiLocale(language), {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date);
}

function formatNumber(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '-';
  return Number(value).toFixed(2).replace(/\.?0+$/, '');
}

function formatConfidence(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '-';
  const normalized = Math.abs(value) <= 1 ? value * 100 : value;
  return `${formatNumber(normalized)}%`;
}

function formatEntryRange(item: DecisionSignalItem): string {
  const hasLow = item.entryLow !== null && item.entryLow !== undefined;
  const hasHigh = item.entryHigh !== null && item.entryHigh !== undefined;
  if (hasLow && hasHigh) {
    return item.entryLow === item.entryHigh
      ? formatNumber(item.entryLow)
      : `${formatNumber(item.entryLow)} - ${formatNumber(item.entryHigh)}`;
  }
  if (hasLow) return formatNumber(item.entryLow);
  if (hasHigh) return formatNumber(item.entryHigh);
  return '-';
}

function getActionVariant(action: DecisionSignalItem['action']): BadgeVariant {
  return ACTION_VARIANTS[getDecisionActionTone(action, null, null)];
}

type SignalTextTone = 'default' | 'warning' | 'danger' | 'info';

const textToneClass: Record<SignalTextTone, string> = {
  default: 'border-border/55 bg-elevated/35 text-secondary-text',
  warning: 'border-warning/25 bg-warning/10 text-warning',
  danger: 'border-danger/25 bg-danger/10 text-danger',
  info: 'border-primary/25 bg-primary/10 text-primary',
};

const SignalTextBlock: React.FC<{
  label: string;
  value?: string | null;
  tone?: SignalTextTone;
  clamp?: boolean;
}> = ({ label, value, tone = 'default', clamp = true }) => {
  const normalized = value?.trim();
  if (!normalized) return null;
  return (
    <div className={cn('rounded-xl border px-3 py-2.5', textToneClass[tone])}>
      <p className="text-xs font-medium text-current/80">{label}</p>
      <p className={cn('mt-1 text-sm leading-5 text-current', clamp ? 'line-clamp-2' : 'whitespace-pre-wrap')}>
        {normalized}
      </p>
    </div>
  );
};

function formatPercent(value: number | null | undefined): string {
  const number = formatNumber(value);
  return number === '-' ? number : `${number}%`;
}

function formatJsonish(value: unknown): string | null {
  if (value === null || value === undefined) return null;
  if (typeof value === 'string') return value.trim() || null;
  if (typeof value === 'number' || typeof value === 'boolean') return String(value);
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

function asJsonViewerData(value: unknown): Record<string, unknown> | unknown[] | null {
  if (Array.isArray(value)) return value;
  if (value && typeof value === 'object') return value as Record<string, unknown>;
  return null;
}

function getFeedbackLabel(value: DecisionSignalFeedbackValue | null | undefined, t: (key: UiTextKey) => string): string {
  if (!value) return t('decisionSignals.feedbackNone');
  const key = `decisionSignals.feedback.${value}` as UiTextKey;
  return t(key);
}

type DetailRowProps = {
  label: string;
  value?: React.ReactNode;
};

const DetailRow: React.FC<DetailRowProps> = ({ label, value }) => (
  <div className="rounded-xl border border-border/60 bg-elevated/40 px-3 py-2">
    <p className="text-xs text-secondary-text">{label}</p>
    <div className="mt-1 text-sm text-foreground">{value || '-'}</div>
  </div>
);

type DecisionSignalDetailsProps = {
  item: DecisionSignalItem;
  actions?: React.ReactNode;
  outcomes?: DecisionSignalOutcomeItem[];
  outcomesLoading?: boolean;
  outcomesError?: string | null;
  feedback?: DecisionSignalFeedbackItem | null;
  feedbackLoading?: boolean;
  feedbackSaving?: boolean;
  feedbackError?: string | null;
  onFeedbackSubmit?: (value: DecisionSignalFeedbackValue) => void;
};

export const DecisionSignalDetails: React.FC<DecisionSignalDetailsProps> = ({
  item,
  actions,
  outcomes = [],
  outcomesLoading = false,
  outcomesError = null,
  feedback = null,
  feedbackLoading = false,
  feedbackSaving = false,
  feedbackError = null,
  onFeedbackSubmit,
}) => {
  const { language, t } = useUiLanguage();
  const presentation = getDecisionSignalPresentation(item, buildDecisionActionLabelMap(t));
  const profileLabel = getDecisionSignalProfileLabel(item, t);
  const entryRange = formatEntryRange(item);
  const evidenceData = asJsonViewerData(item.evidence);
  const qualityData = asJsonViewerData(item.dataQualitySummary);
  const metadataData = asJsonViewerData(item.metadata);
  const reportLanguage = getReportLanguageForUi(language);
  const exportRecordId = typeof item.sourceReportId === 'number'
    && Number.isInteger(item.sourceReportId)
    && item.sourceReportId > 0
    ? item.sourceReportId
    : null;

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant={getActionVariant(presentation.action)} size="md">{presentation.label}</Badge>
            <Badge variant={STATUS_VARIANTS[item.status]} size="md">{t(STATUS_LABEL_KEYS[item.status])}</Badge>
            <Badge variant="info" size="md">{t('decisionSignals.profile')}: {profileLabel}</Badge>
          </div>
          <h3 className="mt-3 text-xl font-semibold text-foreground">{item.stockName || item.stockCode}</h3>
          <p className="mt-1 font-mono text-sm text-secondary-text">{item.stockCode} · {getDecisionSignalMarketLabel(item.market, t)}</p>
        </div>
        {exportRecordId !== null || actions ? (
          <div className="flex flex-wrap items-start justify-end gap-2">
            {exportRecordId !== null ? (
              <ReportExportDownloadButtons recordId={exportRecordId} />
            ) : null}
            {actions ? <div className="flex flex-wrap gap-2">{actions}</div> : null}
          </div>
        ) : null}
      </div>

      <ReportRiskGateBanner
        presentation={buildRiskGatePresentation({
          metadata:
            item.metadata && typeof item.metadata === 'object' && !Array.isArray(item.metadata)
              ? (item.metadata as Record<string, unknown>)
              : null,
        })}
        language={reportLanguage}
      />

      {item.evidence && typeof item.evidence === 'object' && !Array.isArray(item.evidence)
      && ('committeeDeliberation' in item.evidence || 'committee_deliberation' in item.evidence) ? (
        <Suspense fallback={null}>
          <DecisionSignalCommitteeInsights
            evidence={item.evidence}
            language={reportLanguage}
          />
        </Suspense>
      ) : null}

      <div className="grid gap-3 sm:grid-cols-2">
        <DetailRow label={t('decisionSignals.score')} value={formatNumber(item.score)} />
        <DetailRow label={t('decisionSignals.confidence')} value={formatConfidence(presentation.confidence)} />
        <DetailRow label={t('decisionSignals.horizon')} value={getDecisionSignalHorizonLabel(item.horizon, t)} />
        <DetailRow label={t('decisionSignals.profile')} value={profileLabel} />
        <DetailRow label={t('decisionSignals.planQuality')} value={getDecisionSignalPlanQualityLabel(item.planQuality, t)} />
        <DetailRow label={t('decisionSignals.marketPhase')} value={getDecisionSignalMarketPhaseLabel(item.marketPhase, t)} />
        <DetailRow label={t('decisionSignals.sourceReport')} value={item.sourceReportId ? `#${item.sourceReportId}` : '-'} />
        <DetailRow label={t('decisionSignals.createdAt')} value={formatDateTime(presentation.timestamp, language)} />
        <DetailRow label={t('decisionSignals.expiresAt')} value={formatDateTime(item.expiresAt, language)} />
      </div>

      <Section title={t('decisionSignals.pricePlan')} headingAs="h3" level="section" padding="sm">
        <div className="grid gap-3 sm:grid-cols-3">
          <DetailRow label={t('decisionSignals.entryRange')} value={entryRange} />
          <DetailRow label={t('decisionSignals.stopLoss')} value={formatNumber(item.stopLoss)} />
          <DetailRow label={t('decisionSignals.targetPrice')} value={formatNumber(item.targetPrice)} />
        </div>
      </Section>

      <Surface level="section" padding="sm">
        <div className="grid gap-3">
          <SignalTextBlock label={t('decisionSignals.reason')} value={formatJsonish(presentation.summary)} clamp={false} />
          <SignalTextBlock label={t('decisionSignals.catalystSummary')} value={formatJsonish(item.catalystSummary)} tone="info" clamp={false} />
          <SignalTextBlock label={t('decisionSignals.watchConditions')} value={formatJsonish(item.watchConditions)} clamp={false} />
          <SignalTextBlock label={t('decisionSignals.riskSummary')} value={formatJsonish(presentation.risk)} tone="warning" clamp={false} />
          <SignalTextBlock label={t('decisionSignals.invalidation')} value={formatJsonish(item.invalidation)} tone="danger" clamp={false} />
        </div>
      </Surface>

      <Section title={t('decisionSignals.outcomes')} headingAs="h3" level="section" padding="sm">
        {outcomesLoading ? (
          <p className="text-sm text-secondary-text">{t('common.loading')}...</p>
        ) : outcomesError ? (
          <p className="text-sm text-danger">{outcomesError}</p>
        ) : outcomes.length === 0 ? (
          <p className="text-sm text-secondary-text">{t('decisionSignals.noOutcomes')}</p>
        ) : (
          <div className="grid gap-3">
            {outcomes.map((outcome) => (
              <div key={outcome.id} className="rounded-xl border border-border/60 bg-elevated/40 px-3 py-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-sm font-medium text-foreground">{getDecisionSignalHorizonLabel(outcome.horizon, t)}</span>
                    <DecisionSignalOutcomeBadge item={outcome} />
                  </div>
                  <span className="text-xs text-secondary-text">{outcome.engineVersion}</span>
                </div>
                <div className="mt-3 grid gap-2 sm:grid-cols-3">
                  <DetailRow label={t('decisionSignals.returnPct')} value={formatPercent(outcome.stockReturnPct)} />
                  <DetailRow label={t('decisionSignals.directionExpected')} value={outcome.directionExpected || '-'} />
                  <DetailRow label={t('decisionSignals.unableReason')} value={outcome.unableReason || '-'} />
                </div>
              </div>
            ))}
          </div>
        )}
      </Section>

      <Section title={t('decisionSignals.feedbackTitle')} headingAs="h3" level="section" padding="sm">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <p className="text-sm text-foreground">
              {feedbackLoading ? `${t('common.loading')}...` : getFeedbackLabel(feedback?.feedbackValue, t)}
            </p>
            {feedback?.reasonCode ? (
              <p className="mt-1 text-xs text-secondary-text">{feedback.reasonCode}</p>
            ) : null}
            {feedbackError ? <p className="mt-2 text-sm text-danger">{feedbackError}</p> : null}
          </div>
          {onFeedbackSubmit ? (
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                className="btn-secondary min-h-11 min-w-11 !px-3 !py-1.5 !text-xs"
                disabled={feedbackSaving}
                onClick={() => onFeedbackSubmit('useful')}
              >
                {t('decisionSignals.feedback.useful')}
              </button>
              <button
                type="button"
                className="btn-secondary min-h-11 min-w-11 !px-3 !py-1.5 !text-xs"
                disabled={feedbackSaving}
                onClick={() => onFeedbackSubmit('not_useful')}
              >
                {t('decisionSignals.feedback.not_useful')}
              </button>
            </div>
          ) : null}
        </div>
      </Section>

      {evidenceData ? (
        <Section title={t('decisionSignals.evidence')} headingAs="h3" level="section" padding="sm">
          <JsonViewer data={evidenceData} maxHeight="240px" />
        </Section>
      ) : null}
      {qualityData ? (
        <Section title={t('decisionSignals.dataQuality')} headingAs="h3" level="section" padding="sm">
          <JsonViewer data={qualityData} maxHeight="240px" />
        </Section>
      ) : null}
      {metadataData ? (
        <Section title={t('decisionSignals.metadata')} headingAs="h3" level="section" padding="sm">
          <JsonViewer data={metadataData} maxHeight="240px" />
        </Section>
      ) : null}
    </div>
  );
};
