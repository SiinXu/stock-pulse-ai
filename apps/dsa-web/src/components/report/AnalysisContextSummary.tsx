import type React from 'react';
import { ChevronDown, Database } from 'lucide-react';
import type {
  AnalysisContextPackBlockStatus,
  AnalysisContextPackOverview,
  ReportLanguage,
} from '../../types/analysis';
import type { UiLanguage } from '../../i18n/uiLanguages';
import { FIELD_TRUST_TEXT, fieldTrustGapMessage } from '../../locales/fieldTrust';
import { ANALYSIS_CONTEXT_CONTENT_TEXT } from '../../locales/reportContent';
import {
  formatDataQualityLevel,
  formatDataQualityLimitation,
} from '../../utils/dataQualityFormat/analysis';
import { normalizeReportLanguage } from '../../utils/reportLanguage';
import { Badge, InlineAlert, StatusDot, Surface } from '../common';
import { DashboardPanelHeader } from '../dashboard';

interface AnalysisContextSummaryProps {
  overview?: AnalysisContextPackOverview | null;
  language?: ReportLanguage;
}

type BadgeVariant = NonNullable<React.ComponentProps<typeof Badge>['variant']>;
type StatusTone = NonNullable<React.ComponentProps<typeof StatusDot>['tone']>;

const STATUS_STYLE: Record<AnalysisContextPackBlockStatus, { variant: BadgeVariant; tone: StatusTone }> = {
  available: { variant: 'success', tone: 'success' },
  missing: { variant: 'danger', tone: 'danger' },
  not_supported: { variant: 'default', tone: 'neutral' },
  fallback: { variant: 'warning', tone: 'warning' },
  stale: { variant: 'warning', tone: 'warning' },
  estimated: { variant: 'info', tone: 'info' },
  partial: { variant: 'warning', tone: 'warning' },
  fetch_failed: { variant: 'danger', tone: 'danger' },
};

const QUALITY_STYLE = {
  good: { variant: 'success', tone: 'success' },
  usable: { variant: 'info', tone: 'info' },
  limited: { variant: 'warning', tone: 'warning' },
  poor: { variant: 'danger', tone: 'danger' },
} as const satisfies Record<string, { variant: BadgeVariant; tone: StatusTone }>;

const STATUS_ORDER: AnalysisContextPackBlockStatus[] = [
  'available',
  'missing',
  'fetch_failed',
  'not_supported',
  'fallback',
  'stale',
  'estimated',
  'partial',
];

const DIAGNOSTIC_CODE_PATTERN = /^[a-z][a-z0-9_]{0,127}$/;
const QUOTE_TRUST_WARNING_PREFIX = 'quote_trust_';

const toUiLanguage = (language: ReportLanguage): UiLanguage => {
  if (language === 'zh') return 'zh';
  if (language === 'ko') return 'ko';
  return 'en';
};

const quoteTrustGapCodes = (warnings: string[] | undefined): string[] => {
  const codes: string[] = [];
  for (const warning of warnings || []) {
    const token = warning.trim().toLowerCase();
    if (!token.startsWith(QUOTE_TRUST_WARNING_PREFIX)) continue;
    const code = token.slice(QUOTE_TRUST_WARNING_PREFIX.length).replace(/^_+|_+$/g, '');
    if (code && !codes.includes(code)) codes.push(code);
  }
  return codes;
};

const formatBlockWarning = (warning: string, language: ReportLanguage): string => {
  const token = warning.trim().toLowerCase();
  if (!token.startsWith(QUOTE_TRUST_WARNING_PREFIX)) return warning;
  const code = token.slice(QUOTE_TRUST_WARNING_PREFIX.length).replace(/^_+|_+$/g, '');
  const trustText = FIELD_TRUST_TEXT[toUiLanguage(language)] ?? FIELD_TRUST_TEXT.en;
  return fieldTrustGapMessage(trustText, { code });
};

const getCount = (
  overview: AnalysisContextPackOverview,
  status: AnalysisContextPackBlockStatus,
): number => {
  if (status === 'not_supported') {
    return overview.counts.notSupported || 0;
  }
  if (status === 'fetch_failed') {
    return overview.counts.fetchFailed || 0;
  }
  return overview.counts[status] || 0;
};

const formatMissingReason = (
  reason: string,
  language: ReportLanguage,
  status: AnalysisContextPackBlockStatus,
): string => {
  const text = ANALYSIS_CONTEXT_CONTENT_TEXT[language];
  const safeCode = DIAGNOSTIC_CODE_PATTERN.test(reason);
  const detail = (safeCode ? text.missingReasonLabels[reason] : undefined)
    || text.statusGuidance[status]
    || text.unknownReasonDetails;
  const diagnosticCode = safeCode ? reason : text.diagnosticCodeUnavailable;
  return `${detail} (${text.diagnosticCode}: ${diagnosticCode})`;
};

export const AnalysisContextSummary: React.FC<AnalysisContextSummaryProps> = ({
  overview,
  language = 'zh',
}) => {
  const reportLanguage = normalizeReportLanguage(language);
  const text = ANALYSIS_CONTEXT_CONTENT_TEXT[reportLanguage];

  if (!overview || !overview.blocks?.length) {
    return null;
  }

  const visibleCounts = STATUS_ORDER
    .map((status) => ({ status, value: getCount(overview, status) }))
    .filter((item) => item.value > 0);
  const summaryCounts = STATUS_ORDER
    .map((status) => ({ status, value: getCount(overview, status) }))
    .filter((item) => item.status === 'available' || item.status === 'missing' || item.value > 0);
  const metadataItems = [
    typeof overview.metadata?.newsResultCount === 'number'
      ? `${text.newsResultCount}: ${overview.metadata.newsResultCount}`
      : null,
  ].filter((item): item is string => Boolean(item));
  const triggerSource = overview.metadata?.triggerSource?.trim();
  const quality = overview.dataQuality;
  const qualityLevel = quality?.level || undefined;
  const qualityStyle = qualityLevel ? QUALITY_STYLE[qualityLevel as keyof typeof QUALITY_STYLE] : undefined;
  const qualityLabel = formatDataQualityLevel(qualityLevel, reportLanguage) || undefined;
  const limitations = quality?.limitations?.map((item) => formatDataQualityLimitation(item, reportLanguage)) || [];

  return (
    <Surface level="interactive" padding="none" className="overflow-hidden">
      <details data-testid="analysis-context-summary" className="group">
        <summary className="flex cursor-pointer list-none flex-col items-stretch gap-3 px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex min-w-0 items-center gap-3">
            <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
              <Database className="h-4 w-4" aria-hidden="true" />
            </span>
            <span className="min-w-0">
              <span className="label-uppercase">{text.eyebrow}</span>
              <span className="mt-0.5 block truncate text-base font-semibold text-foreground">
                {text.title}
              </span>
              <span className="mt-1 block text-xs leading-5 text-muted-text">
                {text.evidenceScope}
              </span>
            </span>
          </div>
          <span className="flex min-w-0 flex-wrap items-center justify-start gap-2 sm:justify-end">
            {typeof quality?.overallScore === 'number' ? (
              <Badge variant={qualityStyle?.variant || 'default'} className="gap-1.5 shadow-none">
                {qualityStyle ? <StatusDot tone={qualityStyle.tone} className="h-1.5 w-1.5" /> : null}
                {text.qualityScore} {quality.overallScore}/100{qualityLabel ? ` ${qualityLabel}` : ''}
              </Badge>
            ) : null}
            {summaryCounts.map(({ status, value }) => {
              const style = STATUS_STYLE[status];
              return (
                <Badge key={status} variant={style.variant} className="gap-1.5 shadow-none">
                  <StatusDot tone={style.tone} className="h-1.5 w-1.5" />
                  {text.status[status]} {value}
                </Badge>
              );
            })}
            {triggerSource ? (
              <Badge variant="default" size="sm">
                {text.triggerSource}: {triggerSource}
              </Badge>
            ) : null}
            <Badge variant="default" size="sm">
              {text.inputScope}
            </Badge>
            <ChevronDown className="h-4 w-4 shrink-0 text-muted-text transition-transform group-open:rotate-180" aria-hidden="true" />
          </span>
        </summary>

        <div className="border-t border-border px-4 pb-4 pt-3">
          <DashboardPanelHeader
            eyebrow={text.eyebrow}
            title={text.title}
            leading={(
              <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary/10 text-primary">
                <Database className="h-4 w-4" aria-hidden="true" />
              </span>
            )}
            actions={metadataItems.length > 0 || typeof quality?.overallScore === 'number' ? (
              <div className="hidden flex-wrap justify-end gap-2 text-xs text-muted-text md:flex">
                {typeof quality?.overallScore === 'number' ? (
                  <Badge variant="default" size="sm">
                    {text.qualityScore}: {quality.overallScore}/100{qualityLabel ? ` ${qualityLabel}` : ''}
                  </Badge>
                ) : null}
                {metadataItems.map((item) => (
                  <Badge key={item} variant="default" size="sm">
                    {item}
                  </Badge>
                ))}
                <Badge variant="default" size="sm">
                  {text.inputScope}
                </Badge>
              </div>
            ) : undefined}
          />

          {visibleCounts.length > 0 ? (
            <div className="mb-3 flex flex-wrap items-center gap-2">
              <span className="label-uppercase">{text.counts}</span>
              {visibleCounts.map(({ status, value }) => {
                const style = STATUS_STYLE[status];
                return (
                  <Badge key={status} variant={style.variant} className="gap-1.5 shadow-none">
                    <StatusDot tone={style.tone} className="h-1.5 w-1.5" />
                    {text.status[status]} {value}
                  </Badge>
                );
              })}
            </div>
          ) : null}

          {limitations.length ? (
            <InlineAlert
              variant="warning"
              size="compact"
              title={text.limitations}
              message={limitations.join(', ')}
              className="mb-3"
            />
          ) : null}

          {overview.warnings?.length ? (
            <InlineAlert
              variant="warning"
              size="compact"
              title={text.warnings}
              message={overview.warnings.join(', ')}
              className="mb-3"
            />
          ) : null}

          <div className="grid grid-cols-1 md:grid-cols-2">
            {overview.blocks.map((block) => {
              const style = STATUS_STYLE[block.status] || STATUS_STYLE.missing;
              const detail = block.missingReasons?.length
                ? block.missingReasons
                  .map((reason) => formatMissingReason(reason, reportLanguage, block.status))
                  .join('; ')
                : text.statusGuidance[block.status];
              const trustText = FIELD_TRUST_TEXT[toUiLanguage(reportLanguage)] ?? FIELD_TRUST_TEXT.en;
              const quoteGaps = block.key === 'quote' ? quoteTrustGapCodes(block.warnings) : [];
              const quoteConfidence = block.key === 'quote' && quoteGaps.length === 0 && block.status === 'available'
                ? 'high'
                : block.key === 'quote'
                  ? 'low'
                  : null;
              const localizedWarnings = (block.warnings || []).map((warning) => (
                formatBlockWarning(warning, reportLanguage)
              ));
              return (
                <div
                  key={block.key}
                  data-testid={`analysis-context-block-${block.key}`}
                  className="min-w-0 border-t border-border py-3 md:odd:pr-4 md:even:border-l md:even:pl-4"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="truncate text-sm font-medium text-foreground">{block.label}</p>
                      <p className="mt-1 break-words text-xs text-secondary-text [overflow-wrap:anywhere]">
                        {text.source}: {block.source || text.sourceUnavailable}
                      </p>
                    </div>
                    <Badge variant={style.variant} className="shrink-0 gap-1.5 shadow-none">
                      <StatusDot tone={style.tone} className="h-1.5 w-1.5" />
                      {text.status[block.status] || block.status}
                    </Badge>
                  </div>

                  {quoteConfidence ? (
                    <p
                      data-testid="analysis-context-quote-trust"
                      className="mt-2 break-words text-xs leading-5 text-secondary-text [overflow-wrap:anywhere]"
                    >
                      {trustText.title}: {trustText.confidence}
                      {' '}
                      {quoteConfidence === 'high' ? trustText.confidenceHigh : trustText.confidenceLow}
                      {quoteGaps.length ? ` · ${trustText.gaps}: ${quoteGaps.map((code) => fieldTrustGapMessage(trustText, { code })).join('; ')}` : ''}
                    </p>
                  ) : null}

                  {localizedWarnings.length ? (
                    <InlineAlert
                      variant="warning"
                      size="compact"
                      title={text.warnings}
                      message={localizedWarnings.join(', ')}
                      className="mt-3"
                    />
                  ) : null}
                  {detail ? (
                    <p className="mt-3 break-words text-xs leading-5 text-muted-text [overflow-wrap:anywhere]">
                      {text.details}: {detail}
                    </p>
                  ) : null}
                </div>
              );
            })}
          </div>

          {metadataItems.length > 0 || typeof quality?.overallScore === 'number' ? (
            <div className="mt-3 flex flex-wrap gap-2 text-xs text-muted-text md:hidden">
              {typeof quality?.overallScore === 'number' ? (
                <Badge variant="default" size="sm">
                  {text.qualityScore}: {quality.overallScore}/100{qualityLabel ? ` ${qualityLabel}` : ''}
                </Badge>
              ) : null}
              {metadataItems.map((item) => (
                <Badge key={item} variant="default" size="sm">
                  {item}
                </Badge>
              ))}
              <Badge variant="default" size="sm">
                {text.inputScope}
              </Badge>
            </div>
          ) : null}
        </div>
      </details>
    </Surface>
  );
};
