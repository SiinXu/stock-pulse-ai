// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

import type React from 'react';
import { useCallback, useEffect, useMemo, useRef } from 'react';
import { RefreshCw } from 'lucide-react';
import { getParsedApiError } from '../../api/error';
import { portfolioHealthApi } from '../../api/portfolioHealth';
import {
  assertPortfolioResponseContext,
  PortfolioResponseContextError,
  useContextBoundPortfolioRequest,
} from '../../hooks/portfolio/useContextBoundPortfolioRequest';
import type { PortfolioInsightsText } from '../../locales/portfolioInsights';
import type { PortfolioCostMethod } from '../../types/portfolio';
import type {
  PortfolioHealthDimensionKey,
  PortfolioHealthResponse,
} from '../../types/portfolioHealth';
import { formatPct } from '../../utils/portfolioFormat';
import {
  Button,
  DataTable,
  type DataTableColumn,
  InlineAlert,
  Section,
  StatePanel,
  SummaryStrip,
} from '../common';
import PortfolioEvidenceSection from './PortfolioEvidenceSection';

type PortfolioHealthPanelProps = {
  accountId?: number;
  costMethod: PortfolioCostMethod;
  text: PortfolioInsightsText;
};

const DIMENSION_KEYS: PortfolioHealthDimensionKey[] = [
  'concentration',
  'riskExposure',
  'diversification',
  'pnl',
  'cashRatio',
];

const PortfolioHealthPanel: React.FC<PortfolioHealthPanelProps> = ({ accountId, costMethod, text }) => {
  const query = useMemo(() => ({ accountId, costMethod }), [accountId, costMethod]);
  const contextKey = `${accountId ?? 'all'}:${costMethod}`;
  const lastOperationRef = useRef<'load' | 'refresh'>('load');
  const {
    result,
    error,
    isRunning,
    hasCompleted,
    execute,
  } = useContextBoundPortfolioRequest<PortfolioHealthResponse | null>(contextKey);

  const validateResponse = useCallback((response: PortfolioHealthResponse | null) => {
    if (response) assertPortfolioResponseContext(response, query);
  }, [query]);

  const loadStored = useCallback(() => {
    lastOperationRef.current = 'load';
    return execute(
      () => portfolioHealthApi.getSummary(query),
      validateResponse,
    );
  }, [execute, query, validateResponse]);

  const refresh = useCallback(() => {
    lastOperationRef.current = 'refresh';
    return execute(
      () => portfolioHealthApi.refresh({ ...query, persist: true }),
      validateResponse,
    );
  }, [execute, query, validateResponse]);

  const retry = useCallback(() => (
    lastOperationRef.current === 'refresh' ? refresh() : loadStored()
  ), [loadStored, refresh]);

  useEffect(() => {
    void loadStored();
  }, [loadStored]);

  const errorMessage = error instanceof PortfolioResponseContextError
    ? text.responseMismatch
    : error
      ? getParsedApiError(error).message
      : null;

  const dimensionLabels: Record<PortfolioHealthDimensionKey, string> = {
    concentration: text.concentration,
    riskExposure: text.riskExposure,
    diversification: text.diversification,
    pnl: text.pnlDimension,
    cashRatio: text.cashRatio,
  };
  const dimensionRows = result
    ? DIMENSION_KEYS.map((key) => ({ key, ...result.dimensions[key] }))
    : [];
  const dimensionColumns: Array<DataTableColumn<(typeof dimensionRows)[number]>> = [
    {
      id: 'dimension',
      header: text.dimension,
      rowHeader: true,
      cell: (row) => <span className="font-medium text-foreground">{dimensionLabels[row.key]}</span>,
    },
    {
      id: 'score',
      header: text.dimensionScore,
      align: 'end',
      cell: (row) => row.score == null ? text.notAvailable : Math.round(row.score),
    },
    {
      id: 'detail',
      header: text.dimensionReason,
      cell: (row) => row.statusMessage || row.reason || row.status,
    },
  ];

  const insightColumns: Array<DataTableColumn<PortfolioHealthResponse['insights'][number]>> = [
    { id: 'severity', header: text.insightSeverity, cell: (row) => row.severity },
    {
      id: 'message',
      header: text.insightMessage,
      rowHeader: true,
      cell: (row) => <span className="text-foreground">{row.message}</span>,
    },
  ];

  const refreshAction = (
    <Button
      type="button"
      variant="secondary"
      size="comfortable"
      onClick={() => { void refresh(); }}
      isLoading={isRunning}
      loadingText={text.refreshing}
    >
      <RefreshCw aria-hidden="true" />
      {text.refresh}
    </Button>
  );

  return (
    <Section
      title={text.healthTitle}
      description={text.healthDescription}
      actions={refreshAction}
      level="section"
      padding="md"
      data-testid="portfolio-health-panel"
    >
      {isRunning && !hasCompleted && !result ? (
        <StatePanel state="loading" title={text.healthLoading} titleAs="p" />
      ) : errorMessage ? (
        <StatePanel
          state="error"
          title={text.requestFailed}
          description={errorMessage}
          action={(
            <Button type="button" variant="secondary" onClick={() => { void retry(); }}>
              {text.retry}
            </Button>
          )}
          titleAs="p"
        />
      ) : hasCompleted && !result ? (
        <StatePanel
          state="empty"
          title={text.healthEmptyTitle}
          description={text.healthEmptyDescription}
          action={refreshAction}
          titleAs="p"
        />
      ) : result?.status === 'empty_portfolio' ? (
        <StatePanel
          state="empty"
          title={text.emptyPortfolioTitle}
          description={result.statusMessage || text.emptyPortfolioDescription}
          titleAs="p"
        />
      ) : result ? (
        <div className="space-y-4">
          {result.status === 'unavailable' ? (
            <StatePanel
              state="blocked"
              title={text.healthUnavailableTitle}
              description={result.statusMessage || result.disclaimer}
              titleAs="p"
            />
          ) : null}
          {result.status === 'partial' ? (
            <InlineAlert
              variant="warning"
              title={text.healthPartialTitle}
              message={result.statusMessage || text.partialResult}
            />
          ) : null}
          <SummaryStrip
            aria-label={text.healthTitle}
            items={[
              {
                id: 'score',
                label: text.score,
                value: result.score == null
                  ? result.partialScore == null
                    ? text.notAvailable
                    : Math.round(result.partialScore)
                  : Math.round(result.score),
                tone: result.status === 'partial' ? 'warning' : 'default',
              },
              { id: 'band', label: text.band, value: result.band || text.notAvailable },
              { id: 'coverage', label: text.coverage, value: formatPct(result.coverageRatio * 100) },
              { id: 'as-of', label: text.asOf, value: result.asOf },
            ]}
          />
          <DataTable
            caption={text.dimensions}
            captionMode="visible"
            columns={dimensionColumns}
            rows={dimensionRows}
            getRowKey={(row) => row.key}
            emptyState={{ title: text.noRows, description: text.noRowsDescription }}
            density="compact"
            minWidth="content"
            virtualization={false}
          />
          <DataTable
            caption={text.insights}
            captionMode="visible"
            columns={insightColumns}
            rows={result.insights}
            getRowKey={(row, index) => `${row.code}-${index}`}
            emptyState={{ title: text.noRows, description: text.noRowsDescription }}
            density="compact"
            minWidth="content"
            virtualization={false}
          />
          <PortfolioEvidenceSection
            title={text.dataQuality}
            values={result.dataQuality}
            emptyLabel={text.notAvailable}
            yesLabel={text.yes}
            noLabel={text.no}
            defaultOpen={result.status !== 'ok'}
          />
          <PortfolioEvidenceSection
            title={text.evidence}
            values={{
              [text.inputs]: result.inputs,
              [text.configuration]: result.config,
              [text.provenance]: result.provenance,
              [text.assumptions]: result.disclaimer,
            }}
            emptyLabel={text.notAvailable}
            yesLabel={text.yes}
            noLabel={text.no}
          />
        </div>
      ) : null}
    </Section>
  );
};

export default PortfolioHealthPanel;
