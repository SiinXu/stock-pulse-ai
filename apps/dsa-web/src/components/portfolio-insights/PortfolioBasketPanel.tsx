// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

import type React from 'react';
import { useMemo, useState } from 'react';
import { getParsedApiError } from '../../api/error';
import { portfolioInsightsApi } from '../../api/portfolioInsights';
import { useContextBoundPortfolioRequest } from '../../hooks/portfolio/useContextBoundPortfolioRequest';
import type { PortfolioInsightsText } from '../../locales/portfolioInsights';
import type { PortfolioBasketResponse } from '../../types/portfolioInsights';
import { formatPct } from '../../utils/portfolioFormat';
import {
  Button,
  Checkbox,
  Collapsible,
  DataTable,
  type DataTableColumn,
  InlineAlert,
  Input,
  Section,
  StatePanel,
  SummaryStrip,
  Textarea,
} from '../common';
import PortfolioEvidenceSection from './PortfolioEvidenceSection';

function parseOptionalObject(value: string): Record<string, number> | undefined;
function parseOptionalObject(value: string, stringValues: true): Record<string, string> | undefined;
function parseOptionalObject(
  value: string,
  stringValues = false,
): Record<string, number> | Record<string, string> | undefined {
  if (!value.trim()) return undefined;
  const parsed: unknown = JSON.parse(value);
  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) throw new Error('not_object');
  for (const item of Object.values(parsed)) {
    if (stringValues ? typeof item !== 'string' : typeof item !== 'number' || !Number.isFinite(item)) {
      throw new Error('invalid_value');
    }
  }
  return parsed as Record<string, number> | Record<string, string>;
}

type PortfolioBasketPanelProps = {
  text: PortfolioInsightsText;
};

const PortfolioBasketPanel: React.FC<PortfolioBasketPanelProps> = ({ text }) => {
  const [symbolsInput, setSymbolsInput] = useState('AAPL, MSFT');
  const [weightsInput, setWeightsInput] = useState('');
  const [sectorMapInput, setSectorMapInput] = useState('');
  const [currency, setCurrency] = useState('CNY');
  const [lookbackTradingDays, setLookbackTradingDays] = useState(252);
  const [confidence, setConfidence] = useState(0.95);
  const [horizonDays, setHorizonDays] = useState(1);
  const [highCorrelationThreshold, setHighCorrelationThreshold] = useState(0.7);
  const [includeStress, setIncludeStress] = useState(true);
  const [scenarioId, setScenarioId] = useState('market_down_10');
  const [formError, setFormError] = useState<string | null>(null);
  const contextKey = JSON.stringify({
    symbolsInput,
    weightsInput,
    sectorMapInput,
    currency,
    lookbackTradingDays,
    confidence,
    horizonDays,
    highCorrelationThreshold,
    includeStress,
    scenarioId,
  });
  const request = useContextBoundPortfolioRequest<PortfolioBasketResponse>(contextKey);

  const run = async () => {
    const symbols = symbolsInput
      .split(/[\s,;]+/)
      .map((symbol) => symbol.trim().toUpperCase())
      .filter(Boolean);
    if (symbols.length === 0) {
      setFormError(text.symbolsRequired);
      return;
    }
    try {
      const weights = parseOptionalObject(weightsInput);
      const sectorMap = parseOptionalObject(sectorMapInput, true);
      setFormError(null);
      await request.execute(() => portfolioInsightsApi.analyzeBasket({
        stockCodes: symbols,
        weights,
        sectorMap,
        currency,
        lookbackTradingDays,
        confidence,
        horizonDays,
        highCorrelationThreshold,
        includeStress,
        scenarioId: includeStress ? scenarioId : undefined,
      }));
    } catch (error) {
      if (error instanceof SyntaxError || (error instanceof Error && (
        error.message === 'not_object' || error.message === 'invalid_value'
      ))) {
        setFormError(text.invalidJson);
        return;
      }
      throw error;
    }
  };

  const result = request.result;
  const errorMessage = request.error ? getParsedApiError(request.error).message : null;
  const weightColumns: Array<DataTableColumn<PortfolioBasketResponse['weights'][number]>> = [
    {
      id: 'symbol',
      header: text.symbol,
      rowHeader: true,
      cell: (row) => <span className="font-medium text-foreground">{row.symbol}</span>,
    },
    { id: 'weight', header: text.weight, align: 'end', cell: (row) => formatPct(row.weightPct) },
  ];
  const degradedColumns: Array<DataTableColumn<PortfolioBasketResponse['degradedSymbols'][number]>> = [
    { id: 'symbol', header: text.symbol, rowHeader: true, cell: (row) => row.stockCode },
    { id: 'reason', header: text.reason, cell: (row) => row.reason },
    { id: 'detail', header: text.detail, cell: (row) => row.detail || text.notAvailable },
  ];
  const correlationHighlightColumns: Array<DataTableColumn<PortfolioBasketResponse['correlationHighlights'][number]>> = [
    { id: 'pair', header: text.pair, rowHeader: true, cell: (row) => `${row.left} / ${row.right}` },
    { id: 'correlation', header: text.correlation, align: 'end', cell: (row) => row.correlation.toFixed(3) },
    { id: 'direction', header: text.direction, cell: (row) => row.direction },
  ];
  const sharedRiskColumns: Array<DataTableColumn<PortfolioBasketResponse['sharedRiskExposures'][number]>> = [
    { id: 'kind', header: text.kind, rowHeader: true, cell: (row) => row.kind },
    { id: 'symbols', header: text.symbols, cell: (row) => row.symbols.join(', ') },
    { id: 'summary', header: text.summary, cell: (row) => row.summary },
  ];
  const matrixRows = useMemo(() => result?.correlation.symbols.map((symbol, index) => ({
    symbol,
    values: result.correlation.matrix[index] ?? [],
  })) ?? [], [result]);
  const matrixColumns = useMemo<Array<DataTableColumn<(typeof matrixRows)[number]>>>(() => [
    {
      id: 'symbol',
      header: text.symbol,
      rowHeader: true,
      cell: (row) => <span className="font-medium text-foreground">{row.symbol}</span>,
    },
    ...(result?.correlation.symbols ?? []).map((symbol, index) => ({
      id: `correlation-${symbol}`,
      header: symbol,
      align: 'end' as const,
      cell: (row: (typeof matrixRows)[number]) => row.values[index]?.toFixed(2) ?? text.notAvailable,
    })),
  ], [result, text.notAvailable, text.symbol]);

  return (
    <Section
      title={text.basketTitle}
      description={text.basketDescription}
      level="section"
      padding="md"
      data-testid="portfolio-basket-panel"
    >
      <div className="space-y-4">
        <Textarea
          id="portfolio-basket-symbols"
          label={text.symbols}
          hint={text.symbolsHint}
          value={symbolsInput}
          onChange={(event) => setSymbolsInput(event.target.value)}
          error={formError || undefined}
          disabled={request.isRunning}
        />
        <Checkbox
          checked={includeStress}
          onChange={(event) => setIncludeStress(event.target.checked)}
          label={text.includeStress}
          disabled={request.isRunning}
        />
        <Collapsible title={text.advancedParameters}>
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
            <Textarea
              id="portfolio-basket-weights"
              label={text.weightsJson}
              hint={text.weightsJsonHint}
              value={weightsInput}
              onChange={(event) => setWeightsInput(event.target.value)}
              disabled={request.isRunning}
              size="default"
            />
            <Textarea
              id="portfolio-basket-sector-map"
              label={text.sectorMapJson}
              hint={text.sectorMapJsonHint}
              value={sectorMapInput}
              onChange={(event) => setSectorMapInput(event.target.value)}
              disabled={request.isRunning}
              size="default"
            />
            <Input
              id="portfolio-basket-currency"
              label={text.currency}
              value={currency}
              maxLength={8}
              onChange={(event) => setCurrency(event.target.value.toUpperCase())}
              disabled={request.isRunning}
            />
            <Input
              id="portfolio-basket-lookback"
              type="number"
              min={60}
              max={1000}
              label={text.lookbackDays}
              value={lookbackTradingDays}
              onChange={(event) => setLookbackTradingDays(Number(event.target.value))}
              disabled={request.isRunning}
            />
            <Input
              id="portfolio-basket-confidence"
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
              id="portfolio-basket-horizon"
              type="number"
              min={1}
              label={text.horizonDays}
              value={horizonDays}
              onChange={(event) => setHorizonDays(Number(event.target.value))}
              disabled={request.isRunning}
            />
            <Input
              id="portfolio-basket-correlation-threshold"
              type="number"
              min={0}
              max={1}
              step={0.05}
              label={text.correlationThreshold}
              value={highCorrelationThreshold}
              onChange={(event) => setHighCorrelationThreshold(Number(event.target.value))}
              disabled={request.isRunning}
            />
            {includeStress ? (
              <Input
                id="portfolio-basket-scenario"
                label={text.scenarioId}
                value={scenarioId}
                onChange={(event) => setScenarioId(event.target.value)}
                disabled={request.isRunning}
              />
            ) : null}
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
            {result.status !== 'ok' && result.statusMessage ? (
              <InlineAlert variant="warning" title={text.riskStatus} message={result.statusMessage} />
            ) : null}
            <InlineAlert variant="info" message={result.disclaimer} />
            <SummaryStrip
              aria-label={text.basketTitle}
              items={[
                { id: 'requested', label: text.requestedSymbols, value: result.symbolsRequestedCount },
                { id: 'used', label: text.symbolsUsed, value: result.symbolsUsedCount },
                {
                  id: 'diversification',
                  label: text.diversificationScore,
                  value: result.concentration.diversificationScore?.toFixed(1) ?? text.notAvailable,
                },
                { id: 'status', label: text.riskStatus, value: result.riskMetricsStatus || result.status },
              ]}
            />
            <DataTable
              caption={text.weights}
              captionMode="visible"
              columns={weightColumns}
              rows={result.weights}
              getRowKey={(row) => row.symbol}
              emptyState={{ title: text.noRows, description: text.noRowsDescription }}
              density="compact"
              minWidth="narrow"
            />
            <DataTable
              caption={text.degradedSymbols}
              captionMode="visible"
              columns={degradedColumns}
              rows={result.degradedSymbols}
              getRowKey={(row) => row.stockCode}
              emptyState={{ title: text.noRows, description: text.noRowsDescription }}
              density="compact"
              minWidth="content"
            />
            <DataTable
              caption={text.correlationHighlights}
              captionMode="visible"
              columns={correlationHighlightColumns}
              rows={result.correlationHighlights}
              getRowKey={(row) => `${row.left}-${row.right}`}
              emptyState={{ title: text.noRows, description: text.noRowsDescription }}
              density="compact"
              minWidth="content"
            />
            <DataTable
              caption={text.correlation}
              captionMode="visible"
              columns={matrixColumns}
              rows={matrixRows}
              getRowKey={(row) => row.symbol}
              emptyState={{ title: text.noRows, description: text.noRowsDescription }}
              density="compact"
              minWidth="extra-wide"
            />
            <DataTable
              caption={text.sharedRisks}
              captionMode="visible"
              columns={sharedRiskColumns}
              rows={result.sharedRiskExposures}
              getRowKey={(row, index) => `${row.kind}-${index}`}
              emptyState={{ title: text.noRows, description: text.noRowsDescription }}
              density="compact"
              minWidth="wide"
            />
            <PortfolioEvidenceSection
              title={text.evidence}
              values={{
                assumptions: result.assumptions,
                annotations: result.annotations,
                riskHistory: result.riskHistory,
                health: result.health,
                stress: result.stress,
                stanceDistribution: result.stanceDistribution,
                correlationStatus: result.correlation.status,
                concentrationStatus: result.concentration.status,
                var: result.var,
                calculatedAt: result.calculatedAt,
              }}
              emptyLabel={text.notAvailable}
              yesLabel={text.yes}
              noLabel={text.no}
            />
          </div>
        ) : null}
      </div>
    </Section>
  );
};

export default PortfolioBasketPanel;
