// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type React from 'react';
import type {
  ReportLanguage,
  ReportPhaseDecision,
  ReportSignalAttribution,
  ReportStrategySynthesis,
  ReportStrategySynthesisSkill,
  ReportStructuredInsights as ReportStructuredInsightsType,
} from '../../types/analysis';
import { Badge, Card, Progress } from '../common';
import { DashboardPanelHeader } from '../dashboard';
import { REPORT_STRUCTURED_INSIGHTS_TEXT } from '../../locales/reportStructuredInsights';
import { normalizeReportLanguage } from '../../utils/reportLanguage';
import { normalizeReportStructuredInsights } from './reportStructuredInsightsUtils';

interface ReportStructuredInsightsProps {
  insights?: ReportStructuredInsightsType | null;
  language?: ReportLanguage;
}

const readableFallback = (value: string): string => value.replaceAll('_', ' ');

const localizedValue = (
  value: string | undefined,
  labels: Record<string, string>,
): string | undefined => {
  if (!value) {
    return undefined;
  }
  return labels[value] ?? readableFallback(value);
};

const confidencePercent = (value: number | undefined): number | undefined => {
  if (value === undefined || !Number.isFinite(value)) {
    return undefined;
  }
  const percentage = Math.abs(value) <= 1 ? value * 100 : value;
  return Math.round(Math.min(100, Math.max(0, percentage)));
};

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

const TextList: React.FC<{ label: string; items?: string[]; tone?: 'default' | 'warning' }> = ({
  label,
  items,
  tone = 'default',
}) => {
  if (!items?.length) {
    return null;
  }
  return (
    <section>
      <h4 className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-muted-text">
        {label}
      </h4>
      <ul
        className={`list-disc space-y-1 pl-5 text-sm ${
          tone === 'warning' ? 'text-warning' : 'text-foreground'
        }`}
      >
        {items.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </section>
  );
};

const PhaseDecisionCard: React.FC<{
  decision: ReportPhaseDecision;
  language: ReportLanguage;
}> = ({ decision, language }) => {
  const text = REPORT_STRUCTURED_INSIGHTS_TEXT[language];
  const context = decision.phaseContext;
  const phase = localizedValue(context?.phase, text.phaseLabels);
  const phaseMetadata = [
    context?.market,
    context?.marketLocalTime,
  ].filter((item): item is string => Boolean(item));

  return (
    <Card
      variant="bordered"
      padding="md"
      className="text-left"
      data-testid="report-phase-decision"
    >
      <DashboardPanelHeader
        eyebrow={text.phaseEyebrow}
        title={text.phaseTitle}
        actions={phase ? <Badge variant="info">{phase}</Badge> : undefined}
      />
      <dl className="space-y-2.5">
        <DetailLine
          label={text.marketPhase}
          value={phaseMetadata.length > 0 ? phaseMetadata.join(' · ') : phase}
        />
        <DetailLine label={text.immediateAction} value={decision.immediateAction} />
        <DetailLine label={text.actionWindow} value={decision.actionWindow} />
        <DetailLine label={text.nextCheckTime} value={decision.nextCheckTime} />
        <DetailLine label={text.confidenceReason} value={decision.confidenceReason} />
        <DetailLine label={text.triggerSource} value={context?.triggerSource} />
        <DetailLine label={text.analysisIntent} value={context?.analysisIntent} />
      </dl>
      <div className="mt-4 space-y-3">
        <TextList label={text.watchConditions} items={decision.watchConditions} />
        <TextList
          label={text.dataLimitations}
          items={decision.dataLimitations}
          tone="warning"
        />
        <TextList
          label={text.contextWarnings}
          items={context?.warnings}
          tone="warning"
        />
      </div>
    </Card>
  );
};

const AttributionCard: React.FC<{
  attribution: ReportSignalAttribution;
  language: ReportLanguage;
}> = ({ attribution, language }) => {
  const text = REPORT_STRUCTURED_INSIGHTS_TEXT[language];
  const weights: Array<[keyof ReportSignalAttribution, number | undefined]> = [
    ['technicalIndicators', attribution.technicalIndicators],
    ['newsSentiment', attribution.newsSentiment],
    ['fundamentals', attribution.fundamentals],
    ['marketConditions', attribution.marketConditions],
  ];
  const visibleWeights = weights.filter((item): item is [keyof ReportSignalAttribution, number] => (
    typeof item[1] === 'number'
  ));

  return (
    <Card
      variant="bordered"
      padding="md"
      className="text-left"
      data-testid="report-signal-attribution"
    >
      <DashboardPanelHeader
        eyebrow={text.attributionEyebrow}
        title={text.attributionTitle}
      />
      {visibleWeights.length > 0 ? (
        <div className="space-y-3">
          {visibleWeights.map(([key, value]) => {
            const label = text.attributionLabels[key] ?? readableFallback(key);
            return (
              <div key={key}>
                <div className="mb-1 flex items-center justify-between gap-3 text-xs">
                  <span className="font-medium text-foreground">{label}</span>
                  <span className="tabular-nums text-muted-text">{Math.round(value)}%</span>
                </div>
                <Progress
                  value={value}
                  label={label}
                  valueText={`${Math.round(value)}%`}
                  tone="primary"
                />
              </div>
            );
          })}
        </div>
      ) : null}
      <dl className={`${visibleWeights.length > 0 ? 'mt-4' : ''} space-y-2.5`}>
        <DetailLine
          label={text.strongestBullish}
          value={attribution.strongestBullishSignal}
        />
        <DetailLine
          label={text.strongestBearish}
          value={attribution.strongestBearishSignal}
        />
      </dl>
    </Card>
  );
};

const StrategySkillList: React.FC<{
  title: string;
  skills?: ReportStrategySynthesisSkill[];
  signalLabels: Record<string, string>;
  testId: string;
}> = ({ title, skills, signalLabels, testId }) => {
  if (!skills?.length) {
    return null;
  }
  return (
    <section data-testid={testId}>
      <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-text">
        {title}
      </h4>
      <div className="space-y-2">
        {skills.map((skill, index) => {
          const name = skill.skillId || skill.agentName || `#${index + 1}`;
          const confidence = confidencePercent(skill.confidence);
          return (
            <div
              key={`${name}-${index}`}
              className="rounded-lg border border-border/55 bg-elevated/40 px-3 py-2"
            >
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-sm font-medium text-foreground">{name}</span>
                {skill.signal ? (
                  <Badge variant="default">
                    {localizedValue(skill.signal, signalLabels)}
                  </Badge>
                ) : null}
                {confidence !== undefined ? (
                  <span className="text-xs tabular-nums text-muted-text">{confidence}%</span>
                ) : null}
              </div>
              {skill.reasoning ? (
                <p className="mt-1 text-xs leading-5 text-secondary-text">{skill.reasoning}</p>
              ) : null}
            </div>
          );
        })}
      </div>
    </section>
  );
};

const StrategySynthesisCard: React.FC<{
  synthesis: ReportStrategySynthesis;
  language: ReportLanguage;
}> = ({ synthesis, language }) => {
  const text = REPORT_STRUCTURED_INSIGHTS_TEXT[language];
  const confidence = confidencePercent(synthesis.confidence);
  const conflicts = synthesis.conflicts ?? [];
  const conflictCount = synthesis.conflictCount ?? conflicts.length;
  const invalidCount = synthesis.summaryParams?.invalidOpinionCount;
  const finalSignal = localizedValue(synthesis.finalSignal, text.signalLabels);
  const consensus = localizedValue(synthesis.consensusLevel, text.consensusLabels);
  const conflictSeverity = localizedValue(
    synthesis.conflictSeverity,
    text.severityLabels,
  );

  return (
    <Card
      variant="bordered"
      padding="md"
      className="text-left md:col-span-2"
      data-testid="report-strategy-synthesis"
    >
      <DashboardPanelHeader
        eyebrow={text.synthesisEyebrow}
        title={text.synthesisTitle}
        actions={finalSignal ? <Badge variant="info" size="md">{finalSignal}</Badge> : undefined}
      />
      <dl className="grid gap-2.5 sm:grid-cols-2 lg:grid-cols-4">
        <DetailLine label={text.finalSignal} value={finalSignal} />
        <DetailLine
          label={text.weightedScore}
          value={synthesis.weightedScore?.toFixed(2)}
        />
        <DetailLine
          label={text.confidence}
          value={confidence === undefined ? undefined : `${confidence}%`}
        />
        <DetailLine label={text.consensus} value={consensus} />
        <DetailLine label={text.conflictSeverity} value={conflictSeverity} />
        <DetailLine
          label={text.conflicts}
          value={conflictCount === undefined ? undefined : String(conflictCount)}
        />
        <DetailLine
          label={text.invalidOpinions}
          value={invalidCount === undefined ? undefined : String(invalidCount)}
        />
      </dl>

      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <StrategySkillList
          title={text.supportingSkills}
          skills={synthesis.supportingSkills}
          signalLabels={text.signalLabels}
          testId="report-supporting-skills"
        />
        <StrategySkillList
          title={text.opposingSkills}
          skills={synthesis.opposingSkills}
          signalLabels={text.signalLabels}
          testId="report-opposing-skills"
        />
      </div>

      {conflicts.length > 0 ? (
        <section className="mt-4" data-testid="report-strategy-conflicts">
          <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-text">
            {text.conflicts}
          </h4>
          <ul className="space-y-2">
            {conflicts.map((conflict, index) => {
              const label = localizedValue(conflict.conflictType, text.conflictLabels)
                ?? conflict.descriptionKey
                ?? `#${index + 1}`;
              const severity = localizedValue(conflict.severity, text.severityLabels);
              return (
                <li
                  key={`${conflict.conflictType ?? 'conflict'}-${index}`}
                  className="rounded-lg border border-warning/25 bg-warning/5 px-3 py-2 text-sm"
                >
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-medium text-foreground">{label}</span>
                    {severity ? <Badge variant="warning">{severity}</Badge> : null}
                  </div>
                  <p className="mt-1 text-xs text-secondary-text">
                    {text.participants}:{' '}
                    {conflict.participants?.join(', ') || text.noParticipants}
                  </p>
                </li>
              );
            })}
          </ul>
        </section>
      ) : null}
    </Card>
  );
};

export const ReportStructuredInsights: React.FC<ReportStructuredInsightsProps> = ({
  insights,
  language = 'zh',
}) => {
  const normalized = normalizeReportStructuredInsights(insights);
  if (!normalized) {
    return null;
  }
  const reportLanguage = normalizeReportLanguage(language);

  return (
    <div
      className="grid gap-4 md:grid-cols-2"
      data-testid="report-structured-insights"
    >
      {normalized.phaseDecision ? (
        <PhaseDecisionCard
          decision={normalized.phaseDecision}
          language={reportLanguage}
        />
      ) : null}
      {normalized.signalAttribution ? (
        <AttributionCard
          attribution={normalized.signalAttribution}
          language={reportLanguage}
        />
      ) : null}
      {normalized.strategySynthesis ? (
        <StrategySynthesisCard
          synthesis={normalized.strategySynthesis}
          language={reportLanguage}
        />
      ) : null}
    </div>
  );
};

export default ReportStructuredInsights;
