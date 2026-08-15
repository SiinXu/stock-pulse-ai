// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

import type React from 'react';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
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
  PortfolioStressResponse,
  StressScenario,
} from '../../types/portfolioInsights';
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
  Textarea,
} from '../common';
import PortfolioEvidenceSection from './PortfolioEvidenceSection';

type PortfolioStressPanelProps = {
  accountId?: number;
  costMethod: PortfolioCostMethod;
  text: PortfolioInsightsText;
};

function parseSectorMap(value: string): Record<string, string> | undefined {
  if (!value.trim()) return undefined;
  const parsed: unknown = JSON.parse(value);
  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) throw new Error('invalid_sector_map');
  if (Object.values(parsed).some((item) => typeof item !== 'string')) throw new Error('invalid_sector_map');
  return parsed as Record<string, string>;
}

const PortfolioStressPanel: React.FC<PortfolioStressPanelProps> = ({ accountId, costMethod, text }) => {
  const { language } = useUiLanguage();
  const [scenarios, setScenarios] = useState<StressScenario[]>([]);
  const [scenarioId, setScenarioId] = useState('');
  const [scenarioLoading, setScenarioLoading] = useState(true);
  const [scenarioError, setScenarioError] = useState<string | null>(null);
  const [targetSector, setTargetSector] = useState('');
  const [sectorMapInput, setSectorMapInput] = useState('');
  const [rateSensitivity, setRateSensitivity] = useState(1);
  const [formError, setFormError] = useState<string | null>(null);
  const scenarioRequestId = useRef(0);
  const selectedScenario = scenarios.find((scenario) => scenario.id === scenarioId);
  const contextKey = JSON.stringify({
    accountId: accountId ?? null,
    costMethod,
    scenarioId,
    targetSector,
    sectorMapInput,
    rateSensitivity,
  });
  const request = useContextBoundPortfolioRequest<PortfolioStressResponse>(contextKey);
  const expectedContext = useMemo(() => ({ accountId, costMethod }), [accountId, costMethod]);

  const loadScenarios = useCallback(async () => {
    const requestId = scenarioRequestId.current + 1;
    scenarioRequestId.current = requestId;
    setScenarioLoading(true);
    setScenarioError(null);
    try {
      const response = await portfolioInsightsApi.listStressScenarios();
      if (scenarioRequestId.current !== requestId) return;
      setScenarios(response.scenarios);
      setScenarioId((current) => (
        response.scenarios.some((item) => item.id === current)
          ? current
          : response.scenarios[0]?.id ?? ''
      ));
    } catch (error) {
      if (scenarioRequestId.current !== requestId) return;
      setScenarioError(getParsedApiError(error).message);
    } finally {
      if (scenarioRequestId.current === requestId) setScenarioLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadScenarios();
    return () => {
      scenarioRequestId.current += 1;
    };
  }, [loadScenarios]);

  const run = async () => {
    if (!selectedScenario) return;
    try {
      const sectorMap = parseSectorMap(sectorMapInput);
      if (selectedScenario.requiresTargetSector && (!targetSector.trim() || !sectorMap)) {
        setFormError(text.targetSectorHint);
        return;
      }
      setFormError(null);
      await request.execute(
        () => selectedScenario.requiresTargetSector
          ? portfolioInsightsApi.runStressCustom({
            accountId,
            costMethod,
            scenarioId,
            targetSector: targetSector.trim(),
            sectorMap,
            rateSensitivityPctPer100bp: rateSensitivity,
          })
          : portfolioInsightsApi.runStressPreset({
            accountId,
            costMethod,
            scenarioId,
            rateSensitivityPctPer100bp: rateSensitivity,
          }),
        (response) => assertPortfolioResponseContext(response, expectedContext),
      );
    } catch (error) {
      if (error instanceof SyntaxError || (error instanceof Error && error.message === 'invalid_sector_map')) {
        setFormError(text.invalidJson);
        return;
      }
      throw error;
    }
  };

  const result = request.result;
  const errorMessage = request.error instanceof PortfolioResponseContextError
    ? text.responseMismatch
    : request.error
      ? getParsedApiError(request.error).message
      : null;
  const impactColumns: Array<DataTableColumn<PortfolioStressResponse['positionImpacts'][number]>> = [
    {
      id: 'symbol',
      header: text.symbol,
      rowHeader: true,
      cell: (row) => <span className="font-medium text-foreground">{row.symbol}</span>,
    },
    { id: 'market-value', header: text.marketValue, align: 'end', cell: (row) => formatMoney(row.marketValue, result?.currency, language) },
    { id: 'weight', header: text.weight, align: 'end', cell: (row) => formatPct(row.weightPct) },
    { id: 'shock', header: text.shock, align: 'end', cell: (row) => formatSignedPct(row.shockPct) },
    { id: 'pnl', header: text.pnl, align: 'end', cell: (row) => formatMoney(row.pnl, result?.currency, language) },
    {
      id: 'source',
      header: text.source,
      cell: (row) => [row.priceSource, row.priceProvider, row.priceDate].filter(Boolean).join(' · ') || text.notAvailable,
    },
    {
      id: 'quality',
      header: text.dataQuality,
      cell: (row) => [row.dataQuality, row.priceStale ? text.stale : null, ...row.limitations].filter(Boolean).join(' · '),
    },
  ];

  return (
    <Section
      title={text.stressTitle}
      description={text.stressDescription}
      level="section"
      padding="md"
      data-testid="portfolio-stress-panel"
    >
      <div className="space-y-4">
        {scenarioLoading ? (
          <StatePanel state="loading" title={text.scenarioLoading} size="compact" titleAs="p" />
        ) : scenarioError ? (
          <StatePanel
            state="error"
            title={text.scenarioUnavailable}
            description={scenarioError}
            action={(
              <Button type="button" variant="secondary" onClick={() => { void loadScenarios(); }}>
                {text.retry}
              </Button>
            )}
            size="compact"
            titleAs="p"
          />
        ) : (
          <>
            <Select
              id="portfolio-stress-scenario"
              label={text.scenario}
              placeholder={text.selectScenario}
              value={scenarioId}
              onChange={setScenarioId}
              options={scenarios.map((scenario) => ({
                value: scenario.id,
                label: scenario.name,
              }))}
              className="w-full"
              triggerClassName="w-full"
              disabled={request.isRunning}
              error={Boolean(formError)}
            />
            {selectedScenario ? (
              <p className="text-sm text-secondary-text">{selectedScenario.description}</p>
            ) : null}
            {selectedScenario?.requiresTargetSector ? (
              <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                <Input
                  id="portfolio-stress-target-sector"
                  label={text.targetSector}
                  hint={text.targetSectorHint}
                  value={targetSector}
                  onChange={(event) => setTargetSector(event.target.value)}
                  error={formError || undefined}
                  disabled={request.isRunning}
                />
                <Textarea
                  id="portfolio-stress-sector-map"
                  label={text.sectorMapJson}
                  hint={text.sectorMapJsonHint}
                  value={sectorMapInput}
                  onChange={(event) => setSectorMapInput(event.target.value)}
                  error={formError || undefined}
                  disabled={request.isRunning}
                  size="default"
                />
              </div>
            ) : null}
            <Collapsible title={text.advancedParameters}>
              <Input
                id="portfolio-stress-rate-sensitivity"
                type="number"
                min={0.01}
                max={20}
                step={0.1}
                label={text.rateSensitivity}
                value={rateSensitivity}
                onChange={(event) => setRateSensitivity(Number(event.target.value))}
                disabled={request.isRunning}
                fieldClassName="max-w-sm"
              />
            </Collapsible>
            <div className="flex justify-end">
              <Button
                type="button"
                variant="primary"
                onClick={() => { void run(); }}
                isLoading={request.isRunning}
                loadingText={text.running}
                disabled={!selectedScenario}
              >
                {text.run}
              </Button>
            </div>
          </>
        )}
        {errorMessage ? (
          <StatePanel state="error" title={text.requestFailed} description={errorMessage} titleAs="p" />
        ) : null}
        {result ? (
          <div className="space-y-4">
            {result.status === 'empty_portfolio' ? (
              <StatePanel
                state="empty"
                title={text.emptyPortfolioTitle}
                description={result.statusMessage || text.emptyPortfolioDescription}
                titleAs="p"
              />
            ) : null}
            {result.status === 'unavailable' ? (
              <StatePanel
                state="blocked"
                title={text.unavailableResult}
                description={result.statusMessage}
                titleAs="p"
              />
            ) : null}
            {result.status === 'partial' ? (
              <InlineAlert variant="warning" message={result.statusMessage || text.partialResult} />
            ) : null}
            {result.status === 'ok' || result.status === 'partial' ? (
              <>
                <SummaryStrip
                  aria-label={text.stressTitle}
                  items={[
                    { id: 'value', label: text.portfolioValue, value: formatMoney(result.portfolioValue, result.currency, language) },
                    { id: 'stressed', label: text.stressedValue, value: formatMoney(result.stressedPortfolioValue, result.currency, language) },
                    {
                      id: 'pnl',
                      label: text.portfolioPnl,
                      value: result.portfolioPnl == null
                        ? text.notAvailable
                        : `${formatMoney(result.portfolioPnl, result.currency, language)} · ${formatSignedPct(result.portfolioPnlPct)}`,
                      tone: result.portfolioPnl != null && result.portfolioPnl < 0 ? 'danger' : 'default',
                    },
                    { id: 'positions', label: text.positionsUsed, value: result.positionsUsed },
                  ]}
                />
                <DataTable
                  caption={text.positionImpacts}
                  captionMode="visible"
                  columns={impactColumns}
                  rows={result.positionImpacts}
                  getRowKey={(row) => row.positionKey}
                  emptyState={{ title: text.noRows, description: text.noRowsDescription }}
                  density="compact"
                  minWidth="extra-wide"
                />
              </>
            ) : null}
            <PortfolioEvidenceSection
              title={text.assumptions}
              values={{
                scenario: result.scenario,
                assumptions: result.assumptions,
                limitations: result.snapshotLimitations,
                missingData: result.missingData,
                excludedPositions: result.excludedPositions,
                concentration: result.concentration,
                snapshotId: result.snapshotId,
                calculatedAt: result.calculatedAt,
                snapshotDataQuality: result.snapshotDataQuality,
                snapshotFxStale: result.snapshotFxStale,
                reconciliationDelta: result.reconciliationDelta,
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

export default PortfolioStressPanel;
