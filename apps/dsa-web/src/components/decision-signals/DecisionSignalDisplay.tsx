import type React from 'react';
import { PanelRightOpen } from 'lucide-react';
import { Badge, Surface } from '../common';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import type { UiLanguage, UiTextKey } from '../../i18n/uiText';
import type {
  DecisionSignalItem,
  DecisionSignalOutcomeItem,
  DecisionSignalOutcomeValue,
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
import { ReportRiskGateBanner } from '../report/ReportRiskGateBanner';
import { buildRiskGatePresentation } from '../report/reportRiskGateUtils';

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

const OUTCOME_VARIANTS: Record<DecisionSignalOutcomeValue, BadgeVariant> = {
  hit: 'success',
  miss: 'danger',
  neutral: 'warning',
};

export const DecisionSignalOutcomeBadge: React.FC<{
  item: Pick<DecisionSignalOutcomeItem, 'evalStatus' | 'outcome'>;
}> = ({ item }) => {
  const { t } = useUiLanguage();
  return item.evalStatus === 'completed' && item.outcome ? (
    <Badge variant={OUTCOME_VARIANTS[item.outcome]}>
      {getOutcomeLabel(item.outcome, t)}
    </Badge>
  ) : (
    <Badge variant="warning">{t('decisionSignals.outcome.unable')}</Badge>
  );
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

function getOutcomeLabel(value: DecisionSignalOutcomeValue | null | undefined, t: (key: UiTextKey) => string): string {
  if (!value) return '-';
  const key = `decisionSignals.outcome.${value}` as UiTextKey;
  return t(key);
}

function hasDisplayValue(value: string): boolean {
  return value !== '-';
}

type SignalMetricTone = 'default' | 'success' | 'warning' | 'danger';

const metricToneClass: Record<SignalMetricTone, string> = {
  default: 'text-foreground',
  success: 'text-success',
  warning: 'text-warning',
  danger: 'text-danger',
};

type SignalMetricProps = {
  label: string;
  value: string;
  tone?: SignalMetricTone;
};

const SignalMetric: React.FC<SignalMetricProps> = ({ label, value, tone = 'default' }) => (
  <div className="min-w-0 rounded-xl border border-border/60 bg-elevated/45 px-3 py-2">
    <p className="truncate text-xs text-muted-text">{label}</p>
    <p className={cn('mt-1 truncate text-sm font-semibold tabular-nums', metricToneClass[tone])}>{value}</p>
  </div>
);

type SignalTextTone = 'default' | 'warning' | 'danger' | 'info';

const textToneClass: Record<SignalTextTone, string> = {
  default: 'border-border/55 bg-elevated/35 text-secondary-text',
  warning: 'border-warning/25 bg-warning/10 text-warning',
  danger: 'border-danger/25 bg-danger/10 text-danger',
  info: 'border-primary/25 bg-primary/10 text-primary',
};

type SignalTextBlockProps = {
  label: string;
  value?: string | null;
  tone?: SignalTextTone;
  clamp?: boolean;
};

const SignalTextBlock: React.FC<SignalTextBlockProps> = ({ label, value, tone = 'default', clamp = true }) => {
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

type DecisionSignalCardProps = {
  item: DecisionSignalItem;
  onSelect?: (item: DecisionSignalItem) => void;
  selected?: boolean;
};

export const DecisionSignalCard: React.FC<DecisionSignalCardProps> = ({ item, onSelect, selected = false }) => {
  const { language, t } = useUiLanguage();
  const presentation = getDecisionSignalPresentation(item, buildDecisionActionLabelMap(t));
  const profileLabel = getDecisionSignalProfileLabel(item, t);
  const interactive = Boolean(onSelect);
  const entryRange = formatEntryRange(item);
  const pricePlanItems = [
    { label: t('decisionSignals.entryRange'), value: entryRange, tone: 'default' as const },
    { label: t('decisionSignals.stopLoss'), value: formatNumber(item.stopLoss), tone: 'danger' as const },
    { label: t('decisionSignals.targetPrice'), value: formatNumber(item.targetPrice), tone: 'success' as const },
  ].filter((entry) => hasDisplayValue(entry.value));
  const content = (
    <>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant={getActionVariant(presentation.action)}>{presentation.label}</Badge>
            <Badge variant={STATUS_VARIANTS[item.status]}>{t(STATUS_LABEL_KEYS[item.status])}</Badge>
            <Badge variant="info">{t('decisionSignals.profile')}: {profileLabel}</Badge>
            <span className="font-mono text-sm text-secondary-text">{item.stockCode}</span>
          </div>
          <h3 className="mt-2 text-base font-semibold text-foreground">
            {item.stockName || item.stockCode}
          </h3>
        </div>
        <div className="text-right text-xs text-secondary-text">
          <div>{getDecisionSignalMarketLabel(item.market, t)}</div>
          <div className="mt-1">{formatDateTime(presentation.timestamp, language)}</div>
        </div>
      </div>

      <ReportRiskGateBanner
        presentation={buildRiskGatePresentation({
          metadata:
            item.metadata && typeof item.metadata === 'object' && !Array.isArray(item.metadata)
              ? (item.metadata as Record<string, unknown>)
              : null,
        })}
        language={getReportLanguageForUi(language)}
        compact
        className="mt-3"
      />

      <div className="mt-4 grid grid-cols-3 gap-2">
        <SignalMetric label={t('decisionSignals.score')} value={formatNumber(item.score)} />
        <SignalMetric label={t('decisionSignals.confidence')} value={formatConfidence(presentation.confidence)} />
        <SignalMetric label={t('decisionSignals.horizon')} value={getDecisionSignalHorizonLabel(item.horizon, t)} />
      </div>

      {pricePlanItems.length > 0 ? (
        <div className="mt-3 rounded-xl border border-border/60 bg-elevated/35 px-3 py-2.5">
          <div className="grid gap-2 sm:grid-cols-3">
            {pricePlanItems.map((entry) => (
              <div key={entry.label} className="min-w-0">
                <p className="truncate text-xs text-muted-text">{entry.label}</p>
                <p className={cn('mt-1 truncate text-sm font-semibold tabular-nums', metricToneClass[entry.tone])}>
                  {entry.value}
                </p>
              </div>
            ))}
          </div>
        </div>
      ) : null}

      <div className="mt-3 grid gap-2">
        <SignalTextBlock label={t('decisionSignals.reason')} value={presentation.summary} />
        <SignalTextBlock label={t('decisionSignals.catalystSummary')} value={item.catalystSummary} tone="info" />
        <SignalTextBlock label={t('decisionSignals.watchConditions')} value={item.watchConditions} />
        <SignalTextBlock label={t('decisionSignals.riskSummary')} value={presentation.risk} tone="warning" />
        <SignalTextBlock label={t('decisionSignals.invalidation')} value={item.invalidation} tone="danger" />
      </div>

      <div className="mt-3 flex flex-wrap gap-2 text-xs text-muted-text">
        <span>{t('decisionSignals.planQuality')}: {getDecisionSignalPlanQualityLabel(item.planQuality, t)}</span>
        <span>{t('decisionSignals.marketPhase')}: {getDecisionSignalMarketPhaseLabel(item.marketPhase, t)}</span>
        <span>{t('decisionSignals.expiresAt')}: {formatDateTime(item.expiresAt, language)}</span>
        {item.sourceReportId ? <span>{t('decisionSignals.sourceReport')}: #{item.sourceReportId}</span> : null}
      </div>
    </>
  );

  return (
    <Surface
      as="article"
      level={interactive ? 'interactive' : 'section'}
      hoverable={interactive}
      className="block w-full p-4 text-left"
      data-selected={selected ? 'true' : undefined}
    >
      {selected ? (
        <span className="absolute inset-y-3 left-0 w-1 rounded-r-full bg-primary" aria-hidden="true" />
      ) : null}
      {content}
      {interactive ? (
        <div className="mt-4 flex justify-end">
          <button
            type="button"
            onClick={() => onSelect?.(item)}
            className="btn-secondary inline-flex min-h-11 min-w-11 items-center gap-1.5 !px-3 !py-1.5 !text-xs"
            aria-label={t('decisionSignals.viewDetailsFor', { stock: item.stockName || item.stockCode })}
          >
            <PanelRightOpen className="h-3.5 w-3.5" />
            {t('common.details')}
          </button>
        </div>
      ) : null}
    </Surface>
  );
};
