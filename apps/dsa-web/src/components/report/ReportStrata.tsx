import type React from 'react';
import type {
  ReportDetails as ReportDetailsType,
  ReportLanguage,
  ReportStrata as ReportStrataType,
  ReportStrataGapOrConflict,
  ReportStrataVerifiedFact,
} from '../../types/analysis';
import { Card } from '../common';
import { DashboardPanelHeader } from '../dashboard';
import { getReportText, normalizeReportLanguage } from '../../utils/reportLanguage';

interface ReportStrataProps {
  details?: ReportDetailsType;
  language?: ReportLanguage;
  /** When true, always render the disclaimer even if strata payload is absent. */
  alwaysShowDisclaimer?: boolean;
}

const asRecord = (value: unknown): Record<string, unknown> | null =>
  value !== null && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;

const asStringList = (value: unknown): string[] => {
  if (!Array.isArray(value)) {
    return [];
  }
  return value
    .map((item) => (typeof item === 'string' ? item.trim() : String(item ?? '').trim()))
    .filter(Boolean);
};

const normalizeFact = (value: unknown): ReportStrataVerifiedFact | null => {
  const record = asRecord(value);
  if (!record) {
    if (typeof value === 'string' && value.trim()) {
      return { statement: value.trim() };
    }
    return null;
  }
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
};

const normalizeGap = (value: unknown): ReportStrataGapOrConflict | null => {
  const record = asRecord(value);
  if (!record) {
    if (typeof value === 'string' && value.trim()) {
      return { kind: 'missing', description: value.trim(), sourceIds: [] };
    }
    return null;
  }
  const description =
    typeof record.description === 'string' ? record.description.trim() : '';
  if (!description) {
    return null;
  }
  const kind = record.kind === 'conflict' ? 'conflict' : 'missing';
  const sourceIds = asStringList(record.sourceIds ?? record.source_ids);
  return { kind, description, sourceIds };
};

const pickList = (record: Record<string, unknown>, camel: string, snake: string): unknown =>
  record[camel] ?? record[snake];

/** Normalize camelCase or snake_case strata payloads into the Web presentation shape. */
export const normalizeReportStrataPayload = (value: unknown): ReportStrataType | null => {
  const record = asRecord(value);
  if (!record) {
    return null;
  }
  const frameworkRaw = asRecord(
    pickList(record, 'frameworkAlignment', 'framework_alignment'),
  );
  return {
    schemaVersion:
      typeof record.schemaVersion === 'string'
        ? record.schemaVersion
        : typeof record.schema_version === 'string'
          ? record.schema_version
          : undefined,
    verifiedFacts: Array.isArray(pickList(record, 'verifiedFacts', 'verified_facts'))
      ? (pickList(record, 'verifiedFacts', 'verified_facts') as unknown[])
      : [],
    missingOrConflicts: Array.isArray(
      pickList(record, 'missingOrConflicts', 'missing_or_conflicts'),
    )
      ? (pickList(record, 'missingOrConflicts', 'missing_or_conflicts') as unknown[])
      : [],
    modelInference: asStringList(pickList(record, 'modelInference', 'model_inference')),
    risksCounterEvidence: asStringList(
      pickList(record, 'risksCounterEvidence', 'risks_counter_evidence'),
    ),
    frameworkAlignment: frameworkRaw
      ? {
          status: (
            frameworkRaw.status === 'aligned'
            || frameworkRaw.status === 'partial'
            || frameworkRaw.status === 'conflict'
            || frameworkRaw.status === 'not_configured'
              ? frameworkRaw.status
              : 'not_configured'
          ),
          summary:
            typeof frameworkRaw.summary === 'string' ? frameworkRaw.summary : undefined,
          frameworkTitle:
            typeof frameworkRaw.frameworkTitle === 'string'
              ? frameworkRaw.frameworkTitle
              : typeof frameworkRaw.framework_title === 'string'
                ? frameworkRaw.framework_title
                : null,
          frameworkVersion:
            typeof frameworkRaw.frameworkVersion === 'number'
              ? frameworkRaw.frameworkVersion
              : typeof frameworkRaw.framework_version === 'number'
                ? frameworkRaw.framework_version
                : null,
          frameworkId:
            typeof frameworkRaw.frameworkId === 'string'
              ? frameworkRaw.frameworkId
              : typeof frameworkRaw.framework_id === 'string'
                ? frameworkRaw.framework_id
                : null,
        }
      : undefined,
    disclaimer:
      typeof record.disclaimer === 'string' ? record.disclaimer : undefined,
  };
};

/** Prefer projected details.reportStrata; fall back to rawResult.dashboard.report_strata. */
export const resolveReportStrataFromDetails = (
  details?: ReportDetailsType | null,
): ReportStrataType | null => {
  if (!details) {
    return null;
  }
  if (details.reportStrata && typeof details.reportStrata === 'object') {
    return normalizeReportStrataPayload(details.reportStrata);
  }
  const raw = details.rawResult;
  if (!raw || typeof raw !== 'object') {
    return null;
  }
  const dashboard = asRecord((raw as Record<string, unknown>).dashboard);
  const nested = dashboard?.reportStrata ?? dashboard?.report_strata;
  if (nested && typeof nested === 'object') {
    return normalizeReportStrataPayload(nested);
  }
  const top = (raw as Record<string, unknown>).reportStrata
    ?? (raw as Record<string, unknown>).report_strata;
  if (top && typeof top === 'object') {
    return normalizeReportStrataPayload(top);
  }
  return null;
};

/**
 * Full-report evidence strata panel (Issue #616).
 * Section order matches Markdown / brief / WeChat templates.
 */
export const ReportStrata: React.FC<ReportStrataProps> = ({
  details,
  language = 'zh',
  alwaysShowDisclaimer = true,
}) => {
  const reportLanguage = normalizeReportLanguage(language);
  const text = getReportText(reportLanguage);
  const strata = resolveReportStrataFromDetails(details);

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

  return (
    <Card
      variant="bordered"
      padding="md"
      className="text-left"
      data-testid="report-strata"
    >
      <DashboardPanelHeader
        eyebrow={text.transparency}
        title={text.evidenceStrata}
        className="mb-3"
      />

      {strata ? (
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
