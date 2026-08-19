// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

import type React from 'react';
import { useMemo, useState } from 'react';
import { getParsedApiError } from '../../api/error';
import { portfolioInsightsApi } from '../../api/portfolioInsights';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import {
  assertPortfolioResponseContext,
  PortfolioResponseContextError,
  useContextBoundPortfolioRequest,
} from '../../hooks/portfolio/useContextBoundPortfolioRequest';
import type { PortfolioInsightsText } from '../../locales/portfolioInsights';
import type { PortfolioCostMethod } from '../../types/portfolio';
import type {
  PortfolioRebalancingResponse,
  RiskTolerance,
} from '../../types/portfolioInsights';
import {
  formatAuthoritativeStatusMessage,
  formatPortfolioInsightDisclaimer,
  formatPortfolioInsightStatus,
  formatPortfolioRebalanceAction,
  formatPortfolioRebalanceRationale,
} from '../../utils/dataQualityFormat/portfolioInsights';
import { formatMoney, formatPct, formatSignedPct } from '../../utils/portfolioFormat';
import {
  Button,
  Collapsible,
  DataTable,
  type DataTableColumn,
  InlineAlert,
  Input,
  Section,
  Select,
  StatePanel,
  SummaryStrip,
} from '../common';
import PortfolioEvidenceSection from './PortfolioEvidenceSection';

type PortfolioRebalancePanelProps = {
  accountId?: number;
  costMethod: PortfolioCostMethod;
  text: PortfolioInsightsText;
};

const PortfolioRebalancePanel: React.FC<PortfolioRebalancePanelProps> = ({
  accountId,
  costMethod,
  text,
}) => {
  const { language } = useUiLanguage();
  const [riskTolerance, setRiskTolerance] = useState<RiskTolerance>('moderate');
  const [driftThresholdPct, setDriftThresholdPct] = useState(5);
  const [confidence, setConfidence] = useState(0.95);
  const [horizonDays, setHorizonDays] = useState(1);
  const [lookbackTradingDays, setLookbackTradingDays] = useState(252);
  const contextKey = JSON.stringify({
    accountId: accountId ?? null,
    costMethod,
    riskTolerance,
    driftThresholdPct,
    confidence,
    horizonDays,
    lookbackTradingDays,
  });
  const request = useContextBoundPortfolioRequest<PortfolioRebalancingResponse>(contextKey);
  const expectedContext = useMemo(() => ({ accountId, costMethod }), [accountId, costMethod]);

  const run = () => request.execute(
    () => portfolioInsightsApi.getRebalancing({
      accountId,
      costMethod,
      riskTolerance,
      driftThresholdPct,
      confidence,
      horizonDays,
      lookbackTradingDays,
    }),
    (response) => assertPortfolioResponseContext(response, expectedContext),
  );

  const result = request.result;
  const errorMessage = request.error instanceof PortfolioResponseContextError
    ? text.responseMismatch
    : request.error
      ? getParsedApiError(request.error).message
      : null;
  const suggestionColumns: Array<DataTableColumn<PortfolioRebalancingResponse['suggestions'][number]>> = [
    {
      id: 'symbol',
      header: text.symbol,
      rowHeader: true,
      cell: (row) => <span className="font-medium text-foreground">{row.symbol}</span>,
    },
    { id: 'action', header: text.action, cell: (row) => formatPortfolioRebalanceAction(row.action, language) },
    { id: 'from', header: text.fromWeight, align: 'end', cell: (row) => formatPct(row.fromWeightPct) },
    { id: 'to', header: text.toWeight, align: 'end', cell: (row) => formatPct(row.toWeightPct) },
    { id: 'delta', header: text.deltaWeight, align: 'end', cell: (row) => formatSignedPct(row.deltaWeightPct) },
    {
      id: 'notional',
      header: text.approxNotional,
      align: 'end',
      cell: (row) => formatMoney(row.approxNotional, result?.currency, language),
    },
    { id: 'rationale', header: text.rationale, cell: (row) => formatPortfolioRebalanceRationale(row, language) },
  ];
  const positionBandColumns: Array<DataTableColumn<PortfolioRebalancingResponse['positionBands'][number]>> = [
    { id: 'symbol', header: text.symbol, rowHeader: true, cell: (row) => row.symbol },
    { id: 'action', header: text.action, cell: (row) => formatPortfolioRebalanceAction(row.action, language) },
    { id: 'current', header: text.fromWeight, align: 'end', cell: (row) => formatPct(row.currentWeightPct) },
    {
      id: 'range',
      header: text.targetRange,
      align: 'end',
      cell: (row) => `${formatPct(row.targetWeightPctLow)} – ${formatPct(row.targetWeightPctHigh)}`,
    },
    { id: 'rationale', header: text.rationale, cell: (row) => formatPortfolioRebalanceRationale(row, language) },
  ];

  return (
    <Section
      title={text.rebalanceTitle}
      description={text.rebalanceDescription}
      level="section"
      padding="md"
      data-testid="portfolio-rebalance-panel"
    >
      <div className="space-y-4">
        <Select
          id="portfolio-rebalance-risk-tolerance"
          label={text.riskTolerance}
          value={riskTolerance}
          onChange={(value) => setRiskTolerance(value as RiskTolerance)}
          options={[
            { value: 'conservative', label: text.conservative },
            { value: 'moderate', label: text.moderate },
            { value: 'aggressive', label: text.aggressive },
          ]}
          className="w-full sm:w-72"
          triggerClassName="w-full"
          disabled={request.isRunning}
        />
        <Collapsible title={text.advancedParameters}>
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
            <Input
              id="portfolio-rebalance-drift"
              type="number"
              min={0}
              max={100}
              step={0.5}
              label={text.driftThreshold}
              value={driftThresholdPct}
              onChange={(event) => setDriftThresholdPct(Number(event.target.value))}
              disabled={request.isRunning}
            />
            <Input
              id="portfolio-rebalance-confidence"
              type="number"
              min={0.51}
              max={0.99}
              step={0.01}
              label={text.confidence}
              value={confidence}
              onChange={(event) => setConfidence(Number(event.target.value))}
              disabled={request.isRunning}
            />
            <Input
              id="portfolio-rebalance-horizon"
              type="number"
              min={1}
              label={text.horizonDays}
              value={horizonDays}
              onChange={(event) => setHorizonDays(Number(event.target.value))}
              disabled={request.isRunning}
            />
            <Input
              id="portfolio-rebalance-lookback"
              type="number"
              min={60}
              max={1000}
              label={text.lookbackDays}
              value={lookbackTradingDays}
              onChange={(event) => setLookbackTradingDays(Number(event.target.value))}
              disabled={request.isRunning}
            />
          </div>
        </Collapsible>
        <div className="flex justify-end">
          <Button
            type="button"
            variant="primary"
            onClick={() => { void run(); }}
            isLoading={request.isRunning}
            loadingText={text.running}
          >
            {text.run}
          </Button>
        </div>
        {errorMessage ? (
          <StatePanel state="error" title={text.requestFailed} description={errorMessage} titleAs="p" />
        ) : null}
        {result ? (
          <div className="space-y-4">
            {result.status === 'empty_portfolio' ? (
              <StatePanel
                state="empty"
                title={text.emptyPortfolioTitle}
                description={text.emptyPortfolioDescription}
                titleAs="p"
              />
            ) : null}
            {result.status === 'insufficient_data' ? (
              <StatePanel
                state="blocked"
                title={formatPortfolioInsightStatus(result.status, language)}
                description={
                  result.statusMessage
                    ? formatAuthoritativeStatusMessage(result.statusMessage, language)
                    : text.insufficientTitle
                }
                titleAs="p"
              />
            ) : null}
            {result.status === 'refused' ? (
              <StatePanel
                state="blocked"
                title={formatPortfolioInsightStatus(result.status, language)}
                description={
                  result.statusMessage
                    ? formatAuthoritativeStatusMessage(result.statusMessage, language)
                    : text.refusedTitle
                }
                titleAs="p"
              />
            ) : null}
            <InlineAlert variant="info" title={text.suggestionOnly} message={formatPortfolioInsightDisclaimer('rebalance', language)} />
            <SummaryStrip
              aria-label={text.rebalanceTitle}
              items={[
                {
                  id: 'value',
                  label: text.currentValue,
                  value: formatMoney(result.current.portfolioValue, result.currency, language),
                },
                { id: 'drift', label: text.maxDrift, value: formatPct(result.drift.maxAbsWeightDriftPct) },
                {
                  id: 'diversification',
                  label: text.diversificationScore,
                  value: result.current.diversificationScore == null
                    ? text.notAvailable
                    : result.current.diversificationScore.toFixed(2),
                },
                { id: 'status', label: text.status, value: formatPortfolioInsightStatus(result.status, language) },
              ]}
            />
            <DataTable
              caption={text.suggestions}
              captionMode="visible"
              columns={suggestionColumns}
              rows={result.suggestions}
              getRowKey={(row) => `${row.symbol}-${row.action}`}
              emptyState={{ title: text.noRows, description: text.noRowsDescription }}
              density="compact"
              minWidth="extra-wide"
              virtualization={false}
            />
            <DataTable
              caption={text.positionBands}
              captionMode="visible"
              columns={positionBandColumns}
              rows={result.positionBands}
              getRowKey={(row) => row.symbol}
              emptyState={{ title: text.noRows, description: text.noRowsDescription }}
              density="compact"
              minWidth="wide"
              virtualization={false}
            />
            <PortfolioEvidenceSection
              title={text.evidence}
              values={{
                targetModel: result.targetModel,
                riskMetricsSummary: result.riskMetricsSummary,
                assumptions: result.assumptions,
                current: result.current,
                drift: result.drift,
                suggestionAssumptions: result.suggestions.map((item) => ({
                  symbol: item.symbol,
                  assumptions: item.assumptions,
                })),
                positionBandAssumptions: result.positionBands.map((item) => ({
                  symbol: item.symbol,
                  assumptions: item.assumptions,
                })),
              }}
              emptyLabel={text.notAvailable}
              yesLabel={text.yes}
              noLabel={text.no}
              defaultOpen={result.status !== 'ok'}
            />
          </div>
        ) : null}
      </div>
    </Section>
  );
};

export default PortfolioRebalancePanel;
