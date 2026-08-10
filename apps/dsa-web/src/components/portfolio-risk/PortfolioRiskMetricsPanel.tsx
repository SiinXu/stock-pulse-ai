// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
// V1 portfolio risk metrics panel: historical VaR, correlation, concentration + assumptions.

import type React from 'react';
import { useMemo } from 'react';
import { Badge, Button, Card, EmptyState, InlineAlert, Loading } from '../common';
import { formatParsedApiError, getParsedApiError } from '../../api/error';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import type { UiLanguage } from '../../i18n/uiText';
import { PORTFOLIO_RISK_METRICS_TEXT } from '../../locales/portfolioRiskMetrics';
import { usePortfolioRiskMetricsQuery } from '../../hooks/portfolio/usePortfolioRiskMetricsQuery';
import type {
  PortfolioConcentrationBlock,
  PortfolioCorrelationBlock,
  PortfolioHistoricalVaRBlock,
  PortfolioRiskAssumptions,
  PortfolioRiskMetricsResponse,
} from '../../types/portfolioRiskMetrics';
import { formatMoney, formatPct } from '../../utils/portfolioFormat';
import { formatUiNumber } from '../../utils/uiLocale';
import { cn } from '../../utils/cn';

export type PortfolioRiskMetricsPanelProps = {
  accountId?: number;
  costMethod?: string;
  asOf?: string;
  enabled?: boolean;
  className?: string;
  'data-testid'?: string;
};

function statusBadgeVariant(
  status: string,
): 'success' | 'warning' | 'danger' | 'default' | 'info' {
  switch (status) {
    case 'ok':
      return 'success';
    case 'partial':
      return 'warning';
    case 'insufficient_history':
      return 'warning';
    case 'empty_portfolio':
      return 'default';
    case 'unavailable':
      return 'default';
    default:
      return 'info';
  }
}

function statusLabel(status: string, text: (typeof PORTFOLIO_RISK_METRICS_TEXT)['en']): string {
  switch (status) {
    case 'ok':
      return text.statusOk;
    case 'empty_portfolio':
      return text.statusEmpty;
    case 'insufficient_history':
      return text.statusInsufficient;
    case 'partial':
      return text.statusPartial;
    case 'unavailable':
      return text.statusUnavailable;
    default:
      return text.statusUnknown;
  }
}

function formatFiniteNumber(
  value: number | null | undefined,
  language: UiLanguage,
  options?: Intl.NumberFormatOptions,
): string {
  if (value == null || !Number.isFinite(value)) return '—';
  return formatUiNumber(value, language, options);
}

function formatFinitePct(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return '—';
  return formatPct(value);
}

function correlationCellBackground(value: number | null): string | undefined {
  if (value == null || !Number.isFinite(value)) return undefined;
  // Map [-1, 1] → opacity for a cool/warm tint without inventing missing values.
  const intensity = Math.min(1, Math.abs(value));
  if (value >= 0) {
    return `rgba(37, 99, 235, ${0.08 + intensity * 0.42})`;
  }
  return `rgba(220, 38, 38, ${0.08 + intensity * 0.42})`;
}

const MetricRow: React.FC<{ label: string; value: string; testId?: string }> = ({
  label,
  value,
  testId,
}) => (
  <div className="flex items-start justify-between gap-3 text-xs">
    <span className="text-secondary">{label}</span>
    <span className="text-right font-medium text-foreground" data-testid={testId}>
      {value}
    </span>
  </div>
);

const VaRCard: React.FC<{
  block: PortfolioHistoricalVaRBlock;
  currency: string;
  language: UiLanguage;
  text: (typeof PORTFOLIO_RISK_METRICS_TEXT)['en'];
}> = ({ block, currency, language, text }) => {
  const isOk = block.status === 'ok';
  return (
    <Card padding="md" data-testid="portfolio-risk-var-card">
      <div className="mb-2 flex items-center justify-between gap-2">
        <h3 className="text-sm font-semibold text-foreground">{text.varTitle}</h3>
        <Badge variant={statusBadgeVariant(block.status)} size="sm">
          {statusLabel(block.status, text)}
        </Badge>
      </div>
      {isOk ? (
        <div className="space-y-1.5">
          <MetricRow
            label={text.varPct}
            value={formatFinitePct(block.varPct)}
            testId="portfolio-risk-var-pct"
          />
          <MetricRow
            label={text.varValue}
            value={
              block.varValue != null && Number.isFinite(block.varValue)
                ? formatMoney(block.varValue, currency, language)
                : '—'
            }
            testId="portfolio-risk-var-value"
          />
          <MetricRow
            label={text.varConfidence}
            value={
              block.confidence != null && Number.isFinite(block.confidence)
                ? formatFiniteNumber(block.confidence * 100, language, {
                    maximumFractionDigits: 1,
                  }) + '%'
                : '—'
            }
          />
          <MetricRow
            label={text.varHorizon}
            value={
              block.horizonDays != null && Number.isFinite(block.horizonDays)
                ? String(block.horizonDays)
                : '—'
            }
          />
          <MetricRow
            label={text.varOneDay}
            value={formatFinitePct(block.oneDayVarPct)}
          />
          <MetricRow label={text.varObservations} value={String(block.observationCount)} />
        </div>
      ) : (
        <div className="space-y-1 text-xs text-secondary">
          <p data-testid="portfolio-risk-var-unavailable">{text.varUnavailable}</p>
          {block.statusMessage ? <p>{block.statusMessage}</p> : null}
          <p>{text.varNullHint}</p>
          <MetricRow
            label={text.varPct}
            value="—"
            testId="portfolio-risk-var-pct"
          />
          <MetricRow
            label={text.varValue}
            value="—"
            testId="portfolio-risk-var-value"
          />
          <MetricRow label={text.varObservations} value={String(block.observationCount)} />
        </div>
      )}
    </Card>
  );
};

const CorrelationCard: React.FC<{
  block: PortfolioCorrelationBlock;
  text: (typeof PORTFOLIO_RISK_METRICS_TEXT)['en'];
}> = ({ block, text }) => {
  const symbols = block.symbols ?? [];
  const matrix = block.matrix ?? [];
  const hasMatrix = block.status === 'ok' && symbols.length > 0 && matrix.length > 0;

  return (
    <Card padding="md" data-testid="portfolio-risk-correlation-card">
      <div className="mb-2 flex items-center justify-between gap-2">
        <h3 className="text-sm font-semibold text-foreground">{text.correlationTitle}</h3>
        <Badge variant={statusBadgeVariant(block.status)} size="sm">
          {statusLabel(block.status, text)}
        </Badge>
      </div>
      <p className="mb-2 text-xs text-secondary">
        {text.correlationObservations}: {block.observationCount}
      </p>
      {block.statusMessage ? (
        <p className="mb-2 text-xs text-secondary">{block.statusMessage}</p>
      ) : null}
      {hasMatrix ? (
        <div className="overflow-x-auto" data-testid="portfolio-risk-correlation-matrix">
          <table className="min-w-full border-collapse text-[11px]">
            <caption className="sr-only">{text.correlationTitle}</caption>
            <thead>
              <tr>
                <th scope="col" className="sticky left-0 bg-surface p-1 text-left text-secondary">
                  {' '}
                </th>
                {symbols.map((symbol) => (
                  <th
                    key={`col-${symbol}`}
                    scope="col"
                    className="p-1 text-center font-medium text-secondary"
                  >
                    {symbol}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {symbols.map((rowSymbol, rowIndex) => (
                <tr key={`row-${rowSymbol}`}>
                  <th
                    scope="row"
                    className="sticky left-0 bg-surface p-1 text-left font-medium text-secondary"
                  >
                    {rowSymbol}
                  </th>
                  {symbols.map((colSymbol, colIndex) => {
                    const raw = matrix[rowIndex]?.[colIndex] ?? null;
                    const display =
                      raw == null || !Number.isFinite(raw)
                        ? text.correlationMissingCell
                        : raw.toFixed(2);
                    return (
                      <td
                        key={`cell-${rowSymbol}-${colSymbol}`}
                        className="p-1 text-center tabular-nums text-foreground"
                        style={{ backgroundColor: correlationCellBackground(raw) }}
                        data-testid={
                          rowIndex === colIndex
                            ? `portfolio-risk-corr-diag-${rowSymbol}`
                            : undefined
                        }
                      >
                        {display}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <EmptyState title={text.correlationEmpty} compact />
      )}
    </Card>
  );
};

const ConcentrationCard: React.FC<{
  block: PortfolioConcentrationBlock;
  language: UiLanguage;
  text: (typeof PORTFOLIO_RISK_METRICS_TEXT)['en'];
}> = ({ block, language, text }) => {
  const isOk = block.status === 'ok';
  const weights = block.weights ?? [];

  return (
    <Card padding="md" data-testid="portfolio-risk-concentration-card">
      <div className="mb-2 flex items-center justify-between gap-2">
        <h3 className="text-sm font-semibold text-foreground">{text.concentrationTitle}</h3>
        <Badge variant={statusBadgeVariant(block.status)} size="sm">
          {statusLabel(block.status, text)}
        </Badge>
      </div>
      <div className="space-y-1.5">
        <MetricRow
          label={text.hhi}
          value={formatFiniteNumber(block.hhi, language, { maximumFractionDigits: 4 })}
          testId="portfolio-risk-hhi"
        />
        <MetricRow
          label={text.effectiveN}
          value={formatFiniteNumber(block.effectiveN, language, { maximumFractionDigits: 2 })}
          testId="portfolio-risk-effective-n"
        />
        <MetricRow
          label={text.diversificationScore}
          value={formatFiniteNumber(block.diversificationScore, language, {
            maximumFractionDigits: 3,
          })}
          testId="portfolio-risk-diversification-score"
        />
        <MetricRow
          label={text.topWeight}
          value={formatFinitePct(block.topWeightPct)}
          testId="portfolio-risk-top-weight"
        />
        <MetricRow label={text.positionCount} value={String(block.positionCount)} />
      </div>
      {isOk && weights.length > 0 ? (
        <ul className="mt-3 space-y-1 border-t border-border pt-2" data-testid="portfolio-risk-weights">
          {weights.slice(0, 12).map((item) => (
            <li
              key={item.symbol}
              className="flex justify-between gap-2 text-xs text-secondary"
            >
              <span className="font-medium text-foreground">{item.symbol}</span>
              <span>{formatFinitePct(item.weightPct)}</span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-2 text-xs text-secondary">{text.noWeights}</p>
      )}
    </Card>
  );
};

const AssumptionsCard: React.FC<{
  assumptions: PortfolioRiskAssumptions;
  text: (typeof PORTFOLIO_RISK_METRICS_TEXT)['en'];
}> = ({ assumptions, text }) => (
  <Card padding="md" data-testid="portfolio-risk-assumptions-card">
    <h3 className="mb-2 text-sm font-semibold text-foreground">{text.assumptionsTitle}</h3>
    <dl className="grid grid-cols-1 gap-1.5 sm:grid-cols-2">
      {(
        [
          [text.assumptionMethod, assumptions.varMethod],
          [text.assumptionReturns, assumptions.returnDefinition],
          [text.assumptionAggregation, assumptions.portfolioAggregation],
          [text.assumptionCash, assumptions.cashExcluded ? text.yes : text.no],
          [text.assumptionWeights, assumptions.weightBasis],
          [text.assumptionHorizonScale, assumptions.horizonScaling],
          [text.assumptionDistribution, assumptions.distributionAssumption],
          [text.assumptionCorrelation, assumptions.correlationMethod],
          [text.assumptionConcentration, assumptions.concentrationMetrics],
          [text.assumptionDataSource, assumptions.dataSource],
          [text.assumptionLookback, String(assumptions.lookbackTradingDays)],
          [text.assumptionMinVarObs, String(assumptions.minReturnObservations)],
          [text.assumptionMinCorrObs, String(assumptions.minCorrelationObservations)],
          [
            text.assumptionProviderCalls,
            assumptions.providerCallsOnHotPath ? text.yes : text.no,
          ],
        ] as const
      ).map(([label, value]) => (
        <div key={label} className="text-xs">
          <dt className="text-secondary">{label}</dt>
          <dd className="break-words font-medium text-foreground">{value}</dd>
        </div>
      ))}
    </dl>
  </Card>
);

function topLevelBanner(
  data: PortfolioRiskMetricsResponse,
  text: (typeof PORTFOLIO_RISK_METRICS_TEXT)['en'],
): React.ReactNode {
  if (data.status === 'empty_portfolio') {
    return (
      <EmptyState
        title={text.emptyPortfolioTitle}
        description={text.emptyPortfolioDescription}
        compact
        data-testid="portfolio-risk-empty-state"
      />
    );
  }
  if (data.status === 'insufficient_history') {
    return (
      <InlineAlert
        variant="warning"
        size="compact"
        title={text.insufficientTitle}
        message={data.statusMessage || text.insufficientDescription}
        data-testid="portfolio-risk-insufficient-banner"
      />
    );
  }
  if (data.status === 'partial') {
    return (
      <InlineAlert
        variant="warning"
        size="compact"
        title={text.partialTitle}
        message={data.statusMessage || text.partialDescription}
        data-testid="portfolio-risk-partial-banner"
      />
    );
  }
  return null;
}

export const PortfolioRiskMetricsPanel: React.FC<PortfolioRiskMetricsPanelProps> = ({
  accountId,
  costMethod = 'fifo',
  asOf,
  enabled = true,
  className,
  'data-testid': testId = 'portfolio-risk-metrics-panel',
}) => {
  const { language } = useUiLanguage();
  const text = PORTFOLIO_RISK_METRICS_TEXT[language];
  const query = usePortfolioRiskMetricsQuery({
    accountId,
    costMethod,
    asOf,
    enabled,
  });

  const summaryLine = useMemo(() => {
    if (!query.data) return null;
    const data = query.data;
    return [
      `${text.asOf}: ${data.asOf}`,
      `${text.currency}: ${data.currency}`,
      `${text.costMethod}: ${data.costMethod.toUpperCase()}`,
      `${text.positionsUsed}: ${data.positionsUsed}`,
      `${text.portfolioValue}: ${
        Number.isFinite(data.portfolioValue)
          ? formatMoney(data.portfolioValue, data.currency, language)
          : '—'
      }`,
    ].join(' · ');
  }, [language, query.data, text]);

  return (
    <section
      className={cn('space-y-3', className)}
      data-testid={testId}
      aria-label={text.title}
    >
      <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h2 className="text-sm font-semibold text-foreground">{text.title}</h2>
          <p className="mt-0.5 text-xs text-secondary">{text.description}</p>
          {summaryLine ? (
            <p className="mt-1 text-xs text-secondary" data-testid="portfolio-risk-summary">
              {summaryLine}
            </p>
          ) : null}
        </div>
        {query.data ? (
          <Badge
            variant={statusBadgeVariant(query.data.status)}
            size="sm"
            data-testid="portfolio-risk-status-badge"
          >
            {text.statusLabel}: {statusLabel(query.data.status, text)}
          </Badge>
        ) : null}
      </div>

      {query.isLoading || (query.isFetching && !query.data) ? (
        <div data-testid="portfolio-risk-loading">
          <Loading label={text.loading} />
        </div>
      ) : null}

      {query.isError ? (
        <div className="space-y-2" data-testid="portfolio-risk-error">
          <InlineAlert
            variant="danger"
            size="compact"
            title={text.loadFailed}
            message={
              formatParsedApiError(getParsedApiError(query.error, language)) || text.loadFailedHint
            }
          />
          <p className="text-xs text-secondary">{text.loadFailedHint}</p>
          <Button type="button" size="compact" variant="secondary" onClick={() => void query.refetch()}>
            {text.retry}
          </Button>
        </div>
      ) : null}

      {query.data ? (
        <>
          {topLevelBanner(query.data, text)}
          <div className="grid grid-cols-1 gap-3 lg:grid-cols-3">
            <VaRCard
              block={query.data.var}
              currency={query.data.currency}
              language={language}
              text={text}
            />
            <CorrelationCard block={query.data.correlation} text={text} />
            <ConcentrationCard
              block={query.data.concentration}
              language={language}
              text={text}
            />
          </div>
          <AssumptionsCard assumptions={query.data.assumptions} text={text} />
          {query.data.history ? (
            <Card padding="md" data-testid="portfolio-risk-history-card">
              <h3 className="mb-2 text-sm font-semibold text-foreground">{text.historyTitle}</h3>
              <div className="space-y-1.5">
                <MetricRow
                  label={text.historyAlignedDays}
                  value={String(query.data.history.alignedTradingDays)}
                />
                <MetricRow
                  label={text.historyRequested}
                  value={String(query.data.history.lookbackTradingDaysRequested)}
                />
                <MetricRow
                  label={text.historyRange}
                  value={
                    query.data.history.alignedStart && query.data.history.alignedEnd
                      ? `${query.data.history.alignedStart} → ${query.data.history.alignedEnd}`
                      : '—'
                  }
                />
              </div>
            </Card>
          ) : null}
        </>
      ) : null}
    </section>
  );
};

export default PortfolioRiskMetricsPanel;
