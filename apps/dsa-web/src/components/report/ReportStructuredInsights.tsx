// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type React from 'react';
import { useId, useState } from 'react';
import type {
  ReportCommitteeDeliberation,
  ReportCommitteeMember,
  ReportCommitteeOpinion,
  ReportLanguage,
  ReportPhaseDecision,
  ReportSignalAttribution,
  ReportStrategySynthesis,
  ReportStrategySynthesisSkill,
  ReportStructuredInsights as ReportStructuredInsightsType,
} from '../../types/analysis';
import { EDUCATION_HELP_KEYS } from '../../locales/educationHelpKeys';
import { Badge, Button, Card, Collapsible, Progress } from '../common';
import { HelpKeyButton } from '../help';
import { DashboardPanelHeader } from '../dashboard';
import { REPORT_STRUCTURED_INSIGHTS_TEXT } from '../../locales/reportStructuredInsights';
import { normalizeReportLanguage } from '../../utils/reportLanguage';
import { normalizeReportStructuredInsights } from './reportStructuredInsightsUtils';

const REPORT_INSIGHT_LIST_PREVIEW_LIMIT = 3;

const formatInsightCountLabel = (template: string, count: number): string => (
  template.replaceAll('{count}', String(count))
);

const useInsightListOverflow = (itemCount: number) => {
  const [expanded, setExpanded] = useState(false);
  const listId = useId();
  const needsDisclosure = itemCount > REPORT_INSIGHT_LIST_PREVIEW_LIMIT;
  return {
    expanded,
    listId,
    needsDisclosure,
    toggle: () => setExpanded((current) => !current),
    isOverflowHidden: (index: number) => (
      needsDisclosure && !expanded && index >= REPORT_INSIGHT_LIST_PREVIEW_LIMIT
    ),
  };
};

const InsightOverflowToggle: React.FC<{
  expanded: boolean;
  onToggle: () => void;
  controlsId: string;
  testId: string;
  sectionTitle: string;
  showAllLabel: string;
  showLessLabel: string;
}> = ({
  expanded,
  onToggle,
  controlsId,
  testId,
  sectionTitle,
  showAllLabel,
  showLessLabel,
}) => {
  const visibleLabel = expanded ? showLessLabel : showAllLabel;
  return (
    <Button
      type="button"
      variant="ghost"
      size="default"
      className="mt-2"
      aria-expanded={expanded}
      aria-controls={controlsId}
      aria-label={`${sectionTitle}: ${visibleLabel}`}
      data-testid={testId}
      onClick={onToggle}
    >
      {visibleLabel}
    </Button>
  );
};

interface ReportStructuredInsightsProps {
  insights?: ReportStructuredInsightsType | null;
  language?: ReportLanguage;
}

const InsightCollapsibleSection: React.FC<{
  title: string;
  testId: string;
  className?: string;
  children: React.ReactNode;
}> = ({ title, testId, className, children }) => (
  <section data-testid={testId} className={className}>
    <Collapsible title={title} defaultOpen={false}>
      {children}
    </Collapsible>
  </section>
);

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
    <div className="grid gap-1 sm:grid-cols-[6rem_minmax(0,1fr)]">
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
      level="interactive"
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
      level="interactive"
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
            const isTechnical = key === 'technicalIndicators';
            return (
              <div key={key}>
                <div className="mb-1 flex items-center justify-between gap-3 text-xs">
                  <span className="inline-flex flex-wrap items-center gap-1 font-medium text-foreground">
                    <span>{label}</span>
                    {isTechnical ? (
                      <HelpKeyButton
                        helpKey={EDUCATION_HELP_KEYS.indicatorCommon}
                        data-testid="report-attribution-indicator-help"
                      />
                    ) : null}
                  </span>
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
  showAllLabel: string;
  showLessLabel: string;
}> = ({ title, skills, signalLabels, testId, showAllLabel, showLessLabel }) => {
  const overflow = useInsightListOverflow(skills?.length ?? 0);
  if (!skills?.length) {
    return null;
  }
  return (
    <InsightCollapsibleSection title={title} testId={testId}>
      <div className="space-y-2" id={overflow.listId}>
        {skills.map((skill, index) => {
          const name = skill.skillId || skill.agentName || `#${index + 1}`;
          const confidence = confidencePercent(skill.confidence);
          return (
            <div
              key={`${name}-${index}`}
              data-insight-item={name}
              hidden={overflow.isOverflowHidden(index) || undefined}
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
      {overflow.needsDisclosure ? (
        <InsightOverflowToggle
          expanded={overflow.expanded}
          onToggle={overflow.toggle}
          controlsId={overflow.listId}
          testId={`${testId}-disclosure`}
          sectionTitle={title}
          showAllLabel={formatInsightCountLabel(showAllLabel, skills.length)}
          showLessLabel={showLessLabel}
        />
      ) : null}
    </InsightCollapsibleSection>
  );
};

const StrategyConflictList: React.FC<{
  title: string;
  conflicts?: Array<{
    conflictType?: string;
    descriptionKey?: string;
    severity?: string;
    participants?: string[];
  }>;
  language: ReportLanguage;
  testId: string;
}> = ({ title, conflicts, language, testId }) => {
  const text = REPORT_STRUCTURED_INSIGHTS_TEXT[language];
  const overflow = useInsightListOverflow(conflicts?.length ?? 0);
  if (!conflicts?.length) {
    return null;
  }
  return (
    <InsightCollapsibleSection title={title} testId={testId} className="mt-4">
      <ul className="space-y-2" id={overflow.listId}>
        {conflicts.map((conflict, index) => {
          const label = localizedValue(conflict.conflictType, text.conflictLabels)
            ?? conflict.descriptionKey
            ?? `#${index + 1}`;
          const severity = localizedValue(conflict.severity, text.severityLabels);
          const itemKey = `${conflict.conflictType ?? 'conflict'}-${index}`;
          return (
            <li
              key={itemKey}
              data-insight-item={itemKey}
              hidden={overflow.isOverflowHidden(index) || undefined}
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
      {overflow.needsDisclosure ? (
        <InsightOverflowToggle
          expanded={overflow.expanded}
          onToggle={overflow.toggle}
          controlsId={overflow.listId}
          testId={`${testId}-disclosure`}
          sectionTitle={title}
          showAllLabel={formatInsightCountLabel(text.showAll, conflicts.length)}
          showLessLabel={text.showLess}
        />
      ) : null}
    </InsightCollapsibleSection>
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
      level="interactive"
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
          showAllLabel={text.showAll}
          showLessLabel={text.showLess}
        />
        <StrategySkillList
          title={text.opposingSkills}
          skills={synthesis.opposingSkills}
          signalLabels={text.signalLabels}
          testId="report-opposing-skills"
          showAllLabel={text.showAll}
          showLessLabel={text.showLess}
        />
      </div>

      <StrategyConflictList
        title={text.conflicts}
        conflicts={conflicts}
        language={language}
        testId="report-strategy-conflicts"
      />
    </Card>
  );
};


const CommitteeOpinionList: React.FC<{
  title: string;
  items?: ReportCommitteeOpinion[] | ReportCommitteeMember[];
  signalLabels: Record<string, string>;
  invalidLabel: string;
  testId: string;
  showAllLabel: string;
  showLessLabel: string;
}> = ({ title, items, signalLabels, invalidLabel, testId, showAllLabel, showLessLabel }) => {
  const overflow = useInsightListOverflow(items?.length ?? 0);
  if (!items?.length) {
    return null;
  }
  return (
    <InsightCollapsibleSection title={title} testId={testId}>
      <div className="space-y-2" id={overflow.listId}>
        {items.map((item, index) => {
          const name = item.displayName || item.personaId || item.agentName || `#${index + 1}`;
          const confidence = confidencePercent(item.confidence);
          const invalid = 'invalid' in item ? Boolean(item.invalid) : false;
          const reasoning =
            'reasoningExcerpt' in item ? item.reasoningExcerpt : undefined;
          return (
            <div
              key={`${name}-${index}`}
              data-insight-item={name}
              hidden={overflow.isOverflowHidden(index) || undefined}
              className="rounded-lg border border-border/55 bg-elevated/40 px-3 py-2"
            >
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-sm font-medium text-foreground">{name}</span>
                {item.signal ? (
                  <Badge variant={invalid ? 'warning' : 'default'}>
                    {localizedValue(item.signal, signalLabels)}
                  </Badge>
                ) : null}
                {confidence !== undefined ? (
                  <span className="text-xs tabular-nums text-muted-text">{confidence}%</span>
                ) : null}
                {invalid ? <Badge variant="warning">{invalidLabel}</Badge> : null}
              </div>
              {reasoning ? (
                <p className="mt-1 text-xs leading-5 text-secondary-text">{reasoning}</p>
              ) : null}
            </div>
          );
        })}
      </div>
      {overflow.needsDisclosure ? (
        <InsightOverflowToggle
          expanded={overflow.expanded}
          onToggle={overflow.toggle}
          controlsId={overflow.listId}
          testId={`${testId}-disclosure`}
          sectionTitle={title}
          showAllLabel={formatInsightCountLabel(showAllLabel, items.length)}
          showLessLabel={showLessLabel}
        />
      ) : null}
    </InsightCollapsibleSection>
  );
};

const CommitteeDeliberationCard: React.FC<{
  deliberation: ReportCommitteeDeliberation;
  language: ReportLanguage;
}> = ({ deliberation, language }) => {
  const text = REPORT_STRUCTURED_INSIGHTS_TEXT[language];
  const conclusion = deliberation.conclusion;
  const finalSignal = localizedValue(conclusion?.finalSignal, text.signalLabels);
  const consensus = localizedValue(conclusion?.consensusLevel, text.consensusLabels);
  const conflictSeverity = localizedValue(
    conclusion?.conflictSeverity,
    text.severityLabels,
  );
  const confidence = confidencePercent(conclusion?.confidence);
  const status = deliberation.status
    ? readableFallback(deliberation.status)
    : undefined;
  const divergences = deliberation.divergencePoints ?? [];

  return (
    <Card
      level="interactive"
      padding="md"
      className="text-left md:col-span-2"
      data-testid="report-committee-deliberation"
    >
      <DashboardPanelHeader
        eyebrow={text.committeeEyebrow}
        title={text.committeeTitle}
        actions={
          finalSignal ? <Badge variant="info" size="md">{finalSignal}</Badge> : undefined
        }
      />
      {conclusion ? (
        <section className="mb-4" data-testid="report-committee-conclusion">
          <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-text">
            {text.committeeConclusion}
          </h4>
          <dl className="grid gap-2.5 sm:grid-cols-2 lg:grid-cols-4">
            <DetailLine label={text.finalSignal} value={finalSignal} />
            <DetailLine label={text.consensus} value={consensus} />
            <DetailLine
              label={text.confidence}
              value={confidence === undefined ? undefined : `${confidence}%`}
            />
            <DetailLine label={text.conflictSeverity} value={conflictSeverity} />
            <DetailLine label={text.committeeStatus} value={status} />
            <DetailLine
              label={text.conflicts}
              value={
                conclusion.conflictCount === undefined
                  ? undefined
                  : String(conclusion.conflictCount)
              }
            />
          </dl>
        </section>
      ) : null}

      <div className="grid gap-4 lg:grid-cols-2">
        <CommitteeOpinionList
          title={text.committeeMembers}
          items={deliberation.members}
          signalLabels={text.signalLabels}
          invalidLabel={text.committeeInvalid}
          testId="report-committee-members"
          showAllLabel={text.showAll}
          showLessLabel={text.showLess}
        />
        <CommitteeOpinionList
          title={text.committeeDissent}
          items={deliberation.dissentingOpinions}
          signalLabels={text.signalLabels}
          invalidLabel={text.committeeInvalid}
          testId="report-committee-dissent"
          showAllLabel={text.showAll}
          showLessLabel={text.showLess}
        />
      </div>

      <StrategyConflictList
        title={text.committeeDivergence}
        conflicts={divergences}
        language={language}
        testId="report-committee-divergence"
      />
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
      {normalized.committeeDeliberation ? (
        <CommitteeDeliberationCard
          deliberation={normalized.committeeDeliberation}
          language={reportLanguage}
        />
      ) : null}
    </div>
  );
};

export default ReportStructuredInsights;
