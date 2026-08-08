// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type React from 'react';
import {
  type ReportFieldDiff,
  type ReportVersionCompareResponse,
  type ReportVersionSeverity,
} from '../../api/reportVersionCompare';
import { Badge, EmptyState, InlineAlert, Surface } from '../common';
import { REPORT_VERSION_COMPARE_TEXT } from '../../locales/reportVersionCompare';
import type { UiLanguage } from '../../i18n/uiLanguages';
import { severityBadgeVariant, severityRowClass } from './severityStyles';

export type ReportVersionCompareViewProps = {
  language: UiLanguage;
  result: ReportVersionCompareResponse | null;
  idle?: boolean;
};

function fieldLabel(
  text: (typeof REPORT_VERSION_COMPARE_TEXT)['en'],
  field: string,
): string {
  switch (field) {
    case 'action':
      return text.fieldAction;
    case 'sentiment_score':
      return text.fieldSentimentScore;
    case 'trend_prediction':
      return text.fieldTrendPrediction;
    case 'operation_advice':
      return text.fieldOperationAdvice;
    case 'analysis_summary':
      return text.fieldAnalysisSummary;
    case 'model_used':
      return text.fieldModelUsed;
    default:
      return field;
  }
}

function severityLabel(
  text: (typeof REPORT_VERSION_COMPARE_TEXT)['en'],
  severity: ReportVersionSeverity,
): string {
  switch (severity) {
    case 'major':
      return text.severityMajor;
    case 'moderate':
      return text.severityModerate;
    case 'minor':
      return text.severityMinor;
    case 'none':
      return text.severityNone;
    default:
      return text.severityUnknown;
  }
}

function formatCell(value: string | null | undefined): string {
  if (value === null || value === undefined || value === '') return '—';
  return value;
}

function renderDeltaBucket(items: unknown[] | undefined, emptyLabel: string): React.ReactNode {
  if (!items || items.length === 0) {
    return <p className="text-sm text-secondary-text">{emptyLabel}</p>;
  }
  return (
    <ul className="space-y-2">
      {items.map((item, index) => (
        <li
          key={`delta-${index}`}
          className="rounded-lg border border-border/50 bg-elevated/50 px-3 py-2 text-sm text-foreground"
        >
          <pre className="whitespace-pre-wrap break-words font-sans text-sm">
            {typeof item === 'string' ? item : JSON.stringify(item, null, 2)}
          </pre>
        </li>
      ))}
    </ul>
  );
}

export const ReportVersionCompareView: React.FC<ReportVersionCompareViewProps> = ({
  language,
  result,
  idle = false,
}) => {
  const text = REPORT_VERSION_COMPARE_TEXT[language];

  if (idle || !result) {
    return (
      <EmptyState
        data-testid="report-version-compare-idle"
        title={text.emptyStateTitle}
        description={text.emptyStateDescription}
      />
    );
  }

  const statusAlert = (() => {
    switch (result.status) {
      case 'engine_pending':
        return {
          variant: 'warning' as const,
          title: text.statusEnginePendingTitle,
          message: text.statusEnginePendingDescription,
        };
      case 'no_baseline':
        return {
          variant: 'info' as const,
          title: text.statusNoBaselineTitle,
          message: text.statusNoBaselineDescription,
        };
      case 'incomparable':
        return {
          variant: 'danger' as const,
          title: text.statusIncomparableTitle,
          message: text.statusIncomparableDescription,
        };
      default:
        return {
          variant: 'success' as const,
          title: text.statusOk,
          message: text.statusOk,
        };
    }
  })();

  const sortedFields: ReportFieldDiff[] = [...(result.fieldDiffs ?? [])].sort((left, right) => {
    const rank = (severity: ReportVersionSeverity, changed: boolean): number => {
      if (!changed || severity === 'none') return 4;
      if (severity === 'major') return 0;
      if (severity === 'moderate') return 1;
      if (severity === 'minor') return 2;
      return 3;
    };
    return rank(left.severity, left.changed) - rank(right.severity, right.changed);
  });

  return (
    <div className="space-y-6" data-testid="report-version-compare-result">
      <InlineAlert
        variant={statusAlert.variant}
        title={statusAlert.title}
        message={statusAlert.message}
        data-testid={`report-version-compare-status-${result.status}`}
      />

      <div className="grid gap-4 md:grid-cols-2">
        {[
          { key: 'base', run: result.baseRun, label: text.baseLabel },
          { key: 'target', run: result.targetRun, label: text.targetLabel },
        ].map(({ key, run, label }) => (
          <Surface key={key} className="space-y-2 p-4" data-testid={`report-version-run-card-${key}`}>
            <h3 className="text-sm font-semibold text-foreground">{label}</h3>
            <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-sm">
              <dt className="text-secondary-text">{text.metaTime}</dt>
              <dd className="text-foreground">{formatCell(run.createdAt)}</dd>
              <dt className="text-secondary-text">{text.metaAction}</dt>
              <dd className="text-foreground">{formatCell(run.actionLabel ?? run.action)}</dd>
              <dt className="text-secondary-text">{text.metaScore}</dt>
              <dd className="text-foreground">
                {run.sentimentScore === null || run.sentimentScore === undefined
                  ? '—'
                  : String(run.sentimentScore)}
              </dd>
              <dt className="text-secondary-text">{text.metaModel}</dt>
              <dd className="text-foreground">{formatCell(run.modelUsed)}</dd>
              <dt className="text-secondary-text">{text.metaFingerprint}</dt>
              <dd className="font-mono text-xs text-foreground">{formatCell(run.configFingerprint)}</dd>
            </dl>
          </Surface>
        ))}
      </div>

      <Surface className="space-y-3 p-4" data-testid="report-version-config-diff">
        <div className="flex flex-wrap items-center gap-2">
          <h3 className="text-sm font-semibold text-foreground">{text.configTitle}</h3>
          <Badge variant={result.configDiff.hasDifferences ? 'warning' : 'history'}>
            {result.configDiff.hasDifferences ? text.configDifferent : text.configIdentical}
          </Badge>
        </div>
        <p className="text-sm text-secondary-text">
          {text.configBase}:{' '}
          <span className="font-mono text-foreground">
            {formatCell(result.configDiff.baseFingerprint)}
          </span>
          {' · '}
          {text.configTarget}:{' '}
          <span className="font-mono text-foreground">
            {formatCell(result.configDiff.targetFingerprint)}
          </span>
        </p>
        <div className="overflow-x-auto">
          <table className="min-w-full text-left text-sm">
            <thead className="text-secondary-text">
              <tr>
                <th className="px-2 py-1 font-medium">{text.configKey}</th>
                <th className="px-2 py-1 font-medium">{text.configBaseValue}</th>
                <th className="px-2 py-1 font-medium">{text.configTargetValue}</th>
              </tr>
            </thead>
            <tbody>
              {(result.configDiff.components ?? []).map((component) => (
                <tr
                  key={component.key}
                  className={
                    component.changed
                      ? 'border-t border-warning/30 bg-warning/5'
                      : 'border-t border-border/30'
                  }
                >
                  <td className="px-2 py-1.5 font-medium text-foreground">{component.key}</td>
                  <td className="px-2 py-1.5 text-secondary-text">
                    {formatCell(component.baseValue)}
                  </td>
                  <td className="px-2 py-1.5 text-secondary-text">
                    {formatCell(component.targetValue)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Surface>

      <Surface className="space-y-3 p-4" data-testid="report-version-field-diffs">
        <h3 className="text-sm font-semibold text-foreground">{text.fieldsTitle}</h3>
        <ul className="space-y-2">
          {sortedFields.map((diff) => (
            <li
              key={diff.field}
              data-testid={`report-version-field-${diff.field}`}
              data-severity={diff.severity}
              data-changed={diff.changed ? 'true' : 'false'}
              className={`rounded-lg border px-3 py-2 ${severityRowClass(diff.severity, diff.changed)}`}
            >
              <div className="mb-1 flex flex-wrap items-center gap-2">
                <span className="text-sm font-medium text-foreground">
                  {fieldLabel(text, diff.field)}
                </span>
                <Badge variant={severityBadgeVariant(diff.severity)} size="sm">
                  {severityLabel(text, diff.severity)}
                </Badge>
              </div>
              <div className="grid gap-2 text-sm sm:grid-cols-2">
                <div>
                  <div className="text-xs text-secondary-text">{text.baseValue}</div>
                  <div className="text-foreground">{formatCell(diff.baseValue)}</div>
                </div>
                <div>
                  <div className="text-xs text-secondary-text">{text.targetValue}</div>
                  <div className="text-foreground">{formatCell(diff.targetValue)}</div>
                </div>
              </div>
            </li>
          ))}
        </ul>
      </Surface>

      {result.delta ? (
        <Surface className="space-y-4 p-4" data-testid="report-version-engine-delta">
          <h3 className="text-sm font-semibold text-foreground">{text.deltaTitle}</h3>
          <div className="space-y-3">
            <div>
              <h4 className="mb-1 text-xs font-medium uppercase tracking-wide text-secondary-text">
                {text.deltaConclusion}
              </h4>
              {renderDeltaBucket(result.delta.conclusionChanges, text.deltaEmpty)}
            </div>
            <div>
              <h4 className="mb-1 text-xs font-medium uppercase tracking-wide text-secondary-text">
                {text.deltaScore}
              </h4>
              {renderDeltaBucket(result.delta.scoreChanges, text.deltaEmpty)}
            </div>
            <div>
              <h4 className="mb-1 text-xs font-medium uppercase tracking-wide text-secondary-text">
                {text.deltaEvidence}
              </h4>
              {renderDeltaBucket(result.delta.evidenceChanges, text.deltaEmpty)}
            </div>
            <div>
              <h4 className="mb-1 text-xs font-medium uppercase tracking-wide text-secondary-text">
                {text.deltaRisk}
              </h4>
              {renderDeltaBucket(result.delta.riskChanges, text.deltaEmpty)}
            </div>
          </div>
        </Surface>
      ) : null}
    </div>
  );
};

export default ReportVersionCompareView;
