import type React from 'react';
import { useId, useState } from 'react';
import { ChevronDown } from 'lucide-react';
import type {
  ReportDetails as ReportDetailsType,
  ReportLanguage,
  ReportStrataGapOrConflict,
  ReportStrataVerifiedFact,
} from '../../types/analysis';
import { EDUCATION_HELP_KEYS } from '../../locales/educationHelpKeys';
import { Button, Card, Collapsible } from '../common';
import { HelpKeyButton } from '../help';
import { DashboardPanelHeader } from '../dashboard';
import { getReportText, normalizeReportLanguage } from '../../utils/reportLanguage';
import { resolveReportStrataFromDetails } from './reportStrataUtils';

interface ReportStrataProps {
  details?: ReportDetailsType;
  language?: ReportLanguage;
  alwaysShowDisclaimer?: boolean;
  defaultCollapsed?: boolean;
}

const asStringList = (value: unknown): string[] => {
  if (!Array.isArray(value)) {
    return [];
  }
  return value
    .map((item) => (typeof item === 'string' ? item.trim() : String(item ?? '').trim()))
    .filter(Boolean);
};

const trimText = (value: unknown): string =>
  typeof value === 'string' ? value.trim() : '';

const collectNonEmptyStrings = (values: unknown[]): string[] =>
  values.map(trimText).filter(Boolean);

const normalizeFact = (value: unknown): ReportStrataVerifiedFact | null => {
  if (value !== null && typeof value === 'object' && !Array.isArray(value)) {
    const record = value as Record<string, unknown>;
    const statement = typeof record.statement === 'string' ? record.statement.trim() : '';
    if (!statement) {
      return null;
    }
    return {
      statement,
      sourceId:
        typeof record.sourceId === 'string'
          ? record.sourceId
          : typeof record.source_id === 'string'
            ? record.source_id
            : null,
      asOf:
        typeof record.asOf === 'string'
          ? record.asOf
          : typeof record.as_of === 'string'
            ? record.as_of
            : null,
    };
  }
  if (typeof value === 'string' && value.trim()) {
    return { statement: value.trim() };
  }
  return null;
};

const normalizeGap = (value: unknown): ReportStrataGapOrConflict | null => {
  if (value !== null && typeof value === 'object' && !Array.isArray(value)) {
    const record = value as Record<string, unknown>;
    const description =
      typeof record.description === 'string' ? record.description.trim() : '';
    if (!description) {
      return null;
    }
    const kind = record.kind === 'conflict' ? 'conflict' : 'missing';
    const sourceIds = asStringList(record.sourceIds ?? record.source_ids);
    return { kind, description, sourceIds };
  }
  if (typeof value === 'string' && value.trim()) {
    return { kind: 'missing', description: value.trim(), sourceIds: [] };
  }
  return null;
};

const AnnotationDetails: React.FC<{
  testId: string;
  summary: string;
  children: React.ReactNode;
}> = ({ testId, summary, children }) => (
  <details className="mt-1 text-xs text-muted-text" data-testid={testId}>
    <summary className="cursor-pointer text-secondary-text">{summary}</summary>
    <div className="mt-1 space-y-0.5">{children}</div>
  </details>
);

const EmptyPlaceholder: React.FC<{ label: string }> = ({ label }) => (
  <p className="text-muted-text">{label}</p>
);

export const ReportStrata: React.FC<ReportStrataProps> = ({
  details,
  language = 'zh',
  alwaysShowDisclaimer = true,
  defaultCollapsed = true,
}) => {
  const reportLanguage = normalizeReportLanguage(language);
  const text = getReportText(reportLanguage);
  const strata = resolveReportStrataFromDetails(details);
  const rawResult = details?.rawResult;
  const [isExpanded, setIsExpanded] = useState(!defaultCollapsed);
  const beforeId = useId();
  const afterId = useId();

  const facts = (strata?.verifiedFacts ?? [])
    .map(normalizeFact)
    .filter((item): item is ReportStrataVerifiedFact => item !== null);
  const gaps = (strata?.missingOrConflicts ?? [])
    .map(normalizeGap)
    .filter((item): item is ReportStrataGapOrConflict => item !== null);
  const inference = asStringList(strata?.modelInference);
  const structuredRisks = asStringList(strata?.risksCounterEvidence);
  const risks = structuredRisks.length > 0
    ? structuredRisks
    : collectNonEmptyStrings([
      rawResult?.riskWarning ?? rawResult?.risk_warning,
    ]);
  const framework = strata?.frameworkAlignment;
  const frameworkSummary =
    (framework?.summary && framework.summary.trim())
    || text.frameworkNotConfigured;
  const disclaimer =
    (strata?.disclaimer && strata.disclaimer.trim())
    || text.defaultDisclaimer;

  const rawFallbackBlobs = strata
    ? collectNonEmptyStrings([
      ...(facts.length > 0 ? [] : [
        rawResult?.technicalAnalysis ?? rawResult?.technical_analysis,
        rawResult?.maAnalysis ?? rawResult?.ma_analysis,
        rawResult?.volumeAnalysis ?? rawResult?.volume_analysis,
      ]),
      ...(gaps.length > 0 ? [] : [
        rawResult?.fundamentalAnalysis ?? rawResult?.fundamental_analysis,
        rawResult?.dataSources ?? rawResult?.data_sources,
      ]),
      ...(inference.length > 0 ? [] : [
        rawResult?.analysisSummary ?? rawResult?.analysis_summary,
        rawResult?.trendAnalysis ?? rawResult?.trend_analysis,
        rawResult?.buyReason ?? rawResult?.buy_reason,
      ]),
    ])
    : [];

  const hasStructuredSecondary = Boolean(strata);
  const hasRawFallback = rawFallbackBlobs.length > 0;
  const hasSecondary = hasStructuredSecondary;
  const showRisks = Boolean(strata);
  const showSecondary = hasSecondary && isExpanded;

  if (!strata && !alwaysShowDisclaimer) {
    return null;
  }

  const ariaControls = [
    hasStructuredSecondary ? beforeId : null,
    (hasStructuredSecondary || hasRawFallback) ? afterId : null,
  ].filter((value): value is string => Boolean(value)).join(' ');

  const renderRawFallback = () => {
    if (!hasRawFallback) {
      return null;
    }
    return (
      <div data-testid="report-strata-raw-fallback">
        <Collapsible title={text.rawResult} defaultOpen={false}>
          <ul className="list-disc space-y-1 pl-5 text-sm text-foreground">
            {rawFallbackBlobs.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </Collapsible>
      </div>
    );
  };

  return (
    <Card
      level="interactive"
      padding="md"
      className="text-left"
      data-testid="report-strata"
      data-collapsed={hasSecondary && !isExpanded ? 'true' : 'false'}
    >
      <DashboardPanelHeader
        eyebrow={text.transparency}
        title={text.evidenceStrata}
        className="mb-3"
        actions={hasSecondary ? (
          <Button
            type="button"
            variant="ghost"
            size="comfortable"
            aria-expanded={isExpanded}
            aria-controls={ariaControls}
            data-testid="report-strata-toggle"
            onClick={() => setIsExpanded((prev) => !prev)}
          >
            {isExpanded ? text.evidenceDetailsCollapse : text.evidenceDetails}
            <ChevronDown
              className={`h-4 w-4 transition-transform ${isExpanded ? 'rotate-180' : ''}`}
              aria-hidden="true"
            />
          </Button>
        ) : undefined}
      />

      {hasStructuredSecondary ? (
        <div
          id={beforeId}
          hidden={!showSecondary}
          data-testid="report-strata-secondary-before"
        >
          <div className="space-y-4 text-sm text-foreground">
            <section data-testid="report-strata-facts">
              <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted-text">
                1. {text.verifiedFacts}
              </h3>
              {facts.length > 0 ? (
                <ul className="list-disc space-y-1 pl-5">
                  {facts.map((fact) => {
                    const sourceId = fact.sourceId?.trim() || '';
                    const asOf = fact.asOf?.trim() || '';
                    return (
                      <li key={`${fact.statement}-${sourceId}-${asOf}`}>
                        <span>{fact.statement}</span>
                        {sourceId || asOf ? (
                          <AnnotationDetails
                            testId="report-strata-fact-annotations"
                            summary={text.details}
                          >
                            {sourceId ? (
                              <p>{text.factSource}: {sourceId}</p>
                            ) : null}
                            {asOf ? (
                              <p>{text.factAsOf}: {asOf}</p>
                            ) : null}
                          </AnnotationDetails>
                        ) : null}
                      </li>
                    );
                  })}
                </ul>
              ) : (
                <EmptyPlaceholder label={text.noValue} />
              )}
            </section>

            <section data-testid="report-strata-gaps">
              <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted-text">
                2. {text.missingOrConflicts}
              </h3>
              {gaps.length > 0 ? (
                <ul className="list-disc space-y-1 pl-5">
                  {gaps.map((gap) => {
                    const sourceIds = (gap.sourceIds ?? []).map((item) => item.trim()).filter(Boolean);
                    return (
                      <li key={`${gap.kind}-${gap.description}`}>
                        <span className="mr-1 font-medium">
                          [{gap.kind === 'conflict' ? text.gapConflict : text.gapMissing}]
                        </span>
                        {gap.description}
                        {sourceIds.length > 0 ? (
                          <AnnotationDetails
                            testId="report-strata-gap-annotations"
                            summary={text.details}
                          >
                            <p>{text.factSource}: {sourceIds.join(', ')}</p>
                          </AnnotationDetails>
                        ) : null}
                      </li>
                    );
                  })}
                </ul>
              ) : (
                <EmptyPlaceholder label={text.noValue} />
              )}
            </section>

            <section data-testid="report-strata-inference">
              <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted-text">
                3. {text.modelInference}
              </h3>
              {inference.length > 0 ? (
                <ul className="list-disc space-y-1 pl-5">
                  {inference.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              ) : (
                <EmptyPlaceholder label={text.noValue} />
              )}
            </section>
          </div>
        </div>
      ) : null}

      {showRisks ? (
        <section
          className={`${hasStructuredSecondary ? 'mt-4' : ''} text-sm text-foreground`}
          data-testid="report-strata-risks"
        >
          <h3 className="mb-1 flex flex-wrap items-center gap-1 text-xs font-semibold uppercase tracking-wide text-muted-text">
            <span>{strata ? `4. ${text.risksCounterEvidence}` : text.risksCounterEvidence}</span>
            <HelpKeyButton
              helpKey={EDUCATION_HELP_KEYS.riskSection}
              data-testid="report-strata-risks-help"
            />
          </h3>
          {risks.length > 0 ? (
            <ul className="list-disc space-y-1 pl-5">
              {risks.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          ) : (
            <EmptyPlaceholder label={text.noValue} />
          )}
        </section>
      ) : null}

      {hasSecondary ? (
        <div
          id={afterId}
          hidden={!showSecondary}
          data-testid="report-strata-secondary-after"
        >
          <div className="mt-4 space-y-4 text-sm text-foreground">
            {hasStructuredSecondary ? (
              <section data-testid="report-strata-framework">
                <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted-text">
                  5. {text.frameworkAlignment}
                </h3>
                <p>
                  {frameworkSummary}
                  {framework?.status ? (
                    <span className="ml-1 text-xs text-muted-text">({framework.status})</span>
                  ) : null}
                </p>
              </section>
            ) : null}
            {renderRawFallback()}
          </div>
        </div>
      ) : null}

      <section
        className={`${strata || showRisks ? 'mt-4 border-t border-[color:var(--home-border)] pt-3' : ''} text-xs text-muted-text`}
        data-testid="report-strata-disclaimer"
      >
        <h3 className="mb-1 font-semibold uppercase tracking-wide">
          {strata ? '6. ' : ''}{text.disclaimerHeading}
        </h3>
        <p>{disclaimer}</p>
      </section>
    </Card>
  );
};

export default ReportStrata;
