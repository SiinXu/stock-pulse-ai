import type React from 'react';
import { useId, useState } from 'react';
import { ChevronDown } from 'lucide-react';
import type {
  ReportDetails as ReportDetailsType,
  ReportLanguage,
  ReportStrataGapOrConflict,
  ReportStrataVerifiedFact,
} from '../../types/analysis';
import { Card } from '../common';
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

export const ReportStrata: React.FC<ReportStrataProps> = ({
  details,
  language = 'zh',
  alwaysShowDisclaimer = true,
  defaultCollapsed = true,
}) => {
  const reportLanguage = normalizeReportLanguage(language);
  const text = getReportText(reportLanguage);
  const strata = resolveReportStrataFromDetails(details);
  const [isExpanded, setIsExpanded] = useState(!defaultCollapsed);
  const bodyId = useId();

  const facts = (strata?.verifiedFacts ?? [])
    .map(normalizeFact)
    .filter((item): item is ReportStrataVerifiedFact => item !== null);
  const gaps = (strata?.missingOrConflicts ?? [])
    .map(normalizeGap)
    .filter((item): item is ReportStrataGapOrConflict => item !== null);
  const inference = asStringList(strata?.modelInference);
  const risks = asStringList(strata?.risksCounterEvidence);
  const framework = strata?.frameworkAlignment;
  const frameworkSummary =
    (framework?.summary && framework.summary.trim())
    || text.frameworkNotConfigured;
  const disclaimer =
    (strata?.disclaimer && strata.disclaimer.trim())
    || text.defaultDisclaimer;

  if (!strata && !alwaysShowDisclaimer) {
    return null;
  }

  const hasExpandableBody = Boolean(strata);
  const showBody = !hasExpandableBody || isExpanded;

  return (
    <Card
      variant="bordered"
      padding="md"
      className="text-left"
      data-testid="report-strata"
      data-collapsed={hasExpandableBody && !isExpanded ? 'true' : 'false'}
    >
      <DashboardPanelHeader
        eyebrow={text.transparency}
        title={text.evidenceStrata}
        className="mb-3"
        actions={hasExpandableBody ? (
          <button
            type="button"
            className="inline-flex min-h-11 items-center gap-1.5 rounded-lg px-2 text-xs font-medium text-secondary-text transition-colors hover:bg-hover hover:text-foreground"
            aria-expanded={isExpanded}
            aria-controls={bodyId}
            data-testid="report-strata-toggle"
            onClick={() => setIsExpanded((prev) => !prev)}
          >
            {isExpanded ? text.evidenceDetailsCollapse : text.evidenceDetails}
            <ChevronDown
              className={`h-4 w-4 transition-transform ${isExpanded ? 'rotate-180' : ''}`}
              aria-hidden="true"
            />
          </button>
        ) : undefined}
      />

      {hasExpandableBody ? (
        <div
          id={bodyId}
          hidden={!showBody}
          data-testid="report-strata-body"
        >
          <div className="space-y-4 text-sm text-foreground">
            <section data-testid="report-strata-facts">
              <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted-text">
                1. {text.verifiedFacts}
              </h3>
              {facts.length > 0 ? (
                <ul className="list-disc space-y-1 pl-5">
                  {facts.map((fact) => (
                    <li key={`${fact.statement}-${fact.sourceId ?? ''}-${fact.asOf ?? ''}`}>
                      <span>{fact.statement}</span>
                      <span className="ml-1 text-xs text-muted-text">
                        ({text.factSource}: {fact.sourceId?.trim() || text.sourceUnknown}
                        {' · '}
                        {text.factAsOf}: {fact.asOf?.trim() || text.asOfUnknown})
                      </span>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-muted-text">—</p>
              )}
            </section>

            <section data-testid="report-strata-gaps">
              <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted-text">
                2. {text.missingOrConflicts}
              </h3>
              {gaps.length > 0 ? (
                <ul className="list-disc space-y-1 pl-5">
                  {gaps.map((gap) => (
                    <li key={`${gap.kind}-${gap.description}`}>
                      <span className="mr-1 font-medium">
                        [{gap.kind === 'conflict' ? text.gapConflict : text.gapMissing}]
                      </span>
                      {gap.description}
                      {gap.sourceIds && gap.sourceIds.length > 0 ? (
                        <span className="ml-1 text-xs text-muted-text">
                          ({gap.sourceIds.join(', ')})
                        </span>
                      ) : null}
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-muted-text">—</p>
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
                <p className="text-muted-text">—</p>
              )}
            </section>

            <section data-testid="report-strata-risks">
              <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted-text">
                4. {text.risksCounterEvidence}
              </h3>
              {risks.length > 0 ? (
                <ul className="list-disc space-y-1 pl-5">
                  {risks.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              ) : (
                <p className="text-muted-text">—</p>
              )}
            </section>

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
          </div>
        </div>
      ) : null}

      <section
        className={`${strata ? 'mt-4 border-t border-[color:var(--home-border)] pt-3' : ''} text-xs text-muted-text`}
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
