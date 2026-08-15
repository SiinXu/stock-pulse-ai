// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type React from 'react';
import type {
  ReportDetails as ReportDetailsType,
  ReportLanguage,
  ReportMeta,
  ReportStrategy,
  ReportSummary as ReportSummaryType,
} from '../../types/analysis';
import { Badge, Card } from '../common';
import { DashboardPanelHeader } from '../dashboard';
import { buildDecisionActionLabelMap, getDecisionActionLabel } from '../../utils/decisionAction';
import { getReportText, normalizeReportLanguage } from '../../utils/reportLanguage';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import {
  buildReportDecisionCardModel,
  hasReportDecisionCardContent,
  type ReportDecisionCardModel,
} from './reportDecisionCardUtils';
import { ReportRiskGateBanner } from './ReportRiskGateBanner';
import { buildRiskGatePresentation } from './reportRiskGateUtils';

export interface ReportDecisionCardProps {
  meta: ReportMeta;
  summary: ReportSummaryType;
  strategy?: ReportStrategy | null;
  details?: ReportDetailsType;
  language?: ReportLanguage;
  compact?: boolean;
  /** When true, show the risk-gate loading state instead of missing-as-pass. */
  riskGateLoading?: boolean;
  /** When true, show the risk-gate load-error state. */
  riskGateError?: boolean;
}

const DetailLine: React.FC<{ label: string; value?: React.ReactNode }> = ({
  label,
  value,
}) => {
  if (value === undefined || value === null || value === '') {
    return null;
  }
  return (
    <div className="grid gap-1 sm:grid-cols-[9rem_minmax(0,1fr)]">
      <dt className="text-xs font-medium uppercase tracking-wide text-muted-text">{label}</dt>
      <dd className="min-w-0 text-sm text-foreground">{value}</dd>
    </div>
  );
};

const BulletList: React.FC<{ label: string; items: string[]; testId: string }> = ({
  label,
  items,
  testId,
}) => {
  if (items.length === 0) {
    return null;
  }
  return (
    <section data-testid={testId}>
      <h4 className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-muted-text">
        {label}
      </h4>
      <ul className="list-disc space-y-1 pl-5 text-sm text-foreground">
        {items.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </section>
  );
};

const resolveSignalLabel = (
  summary: ReportSummaryType,
  text: ReturnType<typeof getReportText>,
  actionLabels: ReturnType<typeof buildDecisionActionLabelMap>,
): string | undefined => {
  if (summary.action) {
    const label = getDecisionActionLabel(summary.action, null, null, text.noAdvice, actionLabels);
    return label ?? undefined;
  }
  const fallback =
    summary.operationAdvice?.trim()
    || summary.actionLabel?.trim()
    || '';
  return fallback || undefined;
};

export const ReportDecisionCard: React.FC<ReportDecisionCardProps> = ({
  meta,
  summary,
  strategy,
  details,
  language,
  compact = false,
  riskGateLoading = false,
  riskGateError = false,
}) => {
  const { t } = useUiLanguage();
  const reportLanguage = normalizeReportLanguage(language ?? meta.reportLanguage);
  const text = getReportText(reportLanguage);
  const actionLabels = buildDecisionActionLabelMap(t);
  const signalLabel = resolveSignalLabel(summary, text, actionLabels);
  const model: ReportDecisionCardModel = buildReportDecisionCardModel({
    meta,
    summary,
    strategy,
    details,
    signalLabel,
  });
  const riskGate = buildRiskGatePresentation({
    summary,
    details,
    loading: riskGateLoading,
    error: riskGateError,
  });
  // Always show the decision surface so the Risk Manager conclusion (including
  // not-evaluated) cannot be omitted when other decision fields are empty.
  const hasDecisionContent = hasReportDecisionCardContent(model);

  const positionParts: string[] = [];
  if (model.positionNoPosition) {
    positionParts.push(`${text.noPosition}: ${model.positionNoPosition}`);
  }
  if (model.positionHasPosition) {
    positionParts.push(`${text.hasPosition}: ${model.positionHasPosition}`);
  }

  const levelParts: string[] = [];
  if (model.stopLoss) {
    levelParts.push(`${text.stopLoss} ${model.stopLoss}`);
  }
  if (model.takeProfit) {
    levelParts.push(`${text.takeProfit} ${model.takeProfit}`);
  }

  return (
    <Card
      level="interactive"
      padding={compact ? 'sm' : 'md'}
      className="text-left"
      data-testid="report-decision-card"
    >
      <DashboardPanelHeader
        eyebrow={text.decisionCardEyebrow}
        title={text.decisionCardTitle}
        className="mb-3"
        actions={(
          <div className="flex flex-wrap items-center gap-2">
            {model.signalLabel ? (
              <Badge variant="info" data-testid="report-decision-card-signal">
                {model.signalLabel}
              </Badge>
            ) : null}
            {typeof model.score === 'number' ? (
              <Badge variant="default" data-testid="report-decision-card-score">
                {text.scoreLabel} {model.score}
              </Badge>
            ) : null}
          </div>
        )}
      />

      <ReportRiskGateBanner
        presentation={riskGate}
        language={reportLanguage}
        compact={compact}
        className="mb-4"
      />

      {hasDecisionContent ? (
        <>
          <dl className="space-y-2.5">
            <DetailLine label={text.oneSentence} value={model.oneSentence} />
            <DetailLine label={text.trendPrediction} value={model.trendPrediction} />
            <DetailLine label={text.confidence} value={model.confidenceLevel} />
            <DetailLine label={text.confidenceReason} value={model.confidenceReason} />
            <DetailLine label={text.immediateAction} value={model.immediateAction} />
            <DetailLine label={text.timeSensitivity} value={model.timeSensitivity} />
            <DetailLine
              label={text.positionAdvice}
              value={positionParts.length > 0 ? positionParts.join(' · ') : undefined}
            />
            <DetailLine
              label={text.actionLevels}
              value={levelParts.length > 0 ? levelParts.join(' · ') : undefined}
            />
          </dl>

          <div className="mt-4 space-y-3">
            <BulletList
              label={text.keyRisks}
              items={model.keyRisks}
              testId="report-decision-card-risks"
            />
            {!model.keyRisks.length && model.riskWarning ? (
              <DetailLine label={text.riskWarning} value={model.riskWarning} />
            ) : null}
            <BulletList
              label={text.watchConditions}
              items={model.watchConditions}
              testId="report-decision-card-watch"
            />
          </div>
        </>
      ) : null}
    </Card>
  );
};

export default ReportDecisionCard;
