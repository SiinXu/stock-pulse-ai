// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

import type React from 'react';
import { useEffect, useMemo, useRef, useState } from 'react';
import { portfolioInsightsApi } from '../../api/portfolioInsights';
import { formatParsedApiError, getParsedApiError } from '../../api/error';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { PORTFOLIO_INSIGHTS_TEXT } from '../../locales/portfolioInsights';
import type { PortfolioCostMethod } from '../../types/portfolio';
import type { PortfolioStressResponse, StressScenario, StressShock } from '../../types/portfolioInsights';
import { formatMoney } from '../../utils/portfolioFormat';
import { formatUiNumber } from '../../utils/uiLocale';
import { Badge, Button, Card, EmptyState, InlineAlert, Input, Loading, SegmentedControl, Select, Textarea } from '../common';

type Props = { accountId?: number; costMethod: PortfolioCostMethod };
type StressMode = 'preset' | 'custom';
type ShockFactor = StressShock['factor'];

function parseSectorMap(value: string): Record<string, string> {
  const result: Record<string, string> = {};
  for (const line of value.split(/\n+/).map((item) => item.trim()).filter(Boolean)) {
    const separator = line.indexOf('=');
    if (separator <= 0 || separator === line.length - 1) throw new Error('invalid');
    result[line.slice(0, separator).trim().toUpperCase()] = line.slice(separator + 1).trim();
  }
  return result;
}

const StressTestView: React.FC<Props> = ({ accountId, costMethod }) => {
  const { language } = useUiLanguage();
  const text = PORTFOLIO_INSIGHTS_TEXT[language];
  const inFlightRef = useRef(false);
  const [scenarios, setScenarios] = useState<StressScenario[]>([]);
  const [catalogLoading, setCatalogLoading] = useState(true);
  const [catalogError, setCatalogError] = useState<string | null>(null);
  const [mode, setMode] = useState<StressMode>('preset');
  const [scenarioId, setScenarioId] = useState('');
  const [factor, setFactor] = useState<ShockFactor>('market');
  const [shockValue, setShockValue] = useState('-10');
  const [targetSector, setTargetSector] = useState('');
  const [sectorMapInput, setSectorMapInput] = useState('');
  const [result, setResult] = useState<PortfolioStressResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isRunning, setIsRunning] = useState(false);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      setCatalogLoading(true);
      setCatalogError(null);
      try {
        const response = await portfolioInsightsApi.listStressScenarios();
        if (cancelled) return;
        setScenarios(response.scenarios);
        setScenarioId((current) => current || response.scenarios.find((item) => item.availability === 'ready')?.id || response.scenarios[0]?.id || '');
      } catch (requestError) {
        if (!cancelled) setCatalogError(formatParsedApiError(getParsedApiError(requestError, language)) || text.stressCatalogFailed);
      } finally {
        if (!cancelled) setCatalogLoading(false);
      }
    };
    void load();
    return () => { cancelled = true; };
  }, [language, text.stressCatalogFailed]);

  const selectedScenario = useMemo(() => scenarios.find((item) => item.id === scenarioId), [scenarioId, scenarios]);

  const run = async () => {
    if (inFlightRef.current) return;
    inFlightRef.current = true;
    setIsRunning(true);
    setError(null);
    try {
      let response: PortfolioStressResponse;
      if (mode === 'preset' && selectedScenario?.availability === 'ready') {
        response = await portfolioInsightsApi.runStressPreset({ scenarioId, accountId, costMethod });
      } else if (mode === 'preset') {
        const sectorMap = parseSectorMap(sectorMapInput);
        if (!targetSector.trim() || !Object.keys(sectorMap).length) throw new Error(text.stressSectorRequired);
        response = await portfolioInsightsApi.runStressCustom({
          scenarioId,
          accountId,
          costMethod,
          targetSector: targetSector.trim(),
          sectorMap,
        });
      } else {
        const numericValue = Number(shockValue);
        if (!Number.isFinite(numericValue)) throw new Error(text.runFailed);
        const customShocks: StressShock[] = factor === 'rate'
          ? [{ factor, valueBp: numericValue }]
          : [{ factor, valuePct: numericValue }];
        const sectorMap = factor === 'sector' ? parseSectorMap(sectorMapInput) : undefined;
        if (factor === 'sector' && (!targetSector.trim() || !sectorMap || !Object.keys(sectorMap).length)) {
          throw new Error(text.stressSectorRequired);
        }
        response = await portfolioInsightsApi.runStressCustom({
          accountId,
          costMethod,
          customShocks,
          targetSector: factor === 'sector' ? targetSector.trim() : undefined,
          sectorMap,
        });
      }
      setResult(response);
    } catch (requestError) {
      setError(requestError instanceof Error && !('response' in requestError)
        ? requestError.message
        : formatParsedApiError(getParsedApiError(requestError, language)) || text.runFailed);
    } finally {
      inFlightRef.current = false;
      setIsRunning(false);
    }
  };

  const impactList = (items: PortfolioStressResponse['topLosers']) => items.length ? (
    <ul className="mt-2 space-y-2 text-xs">
      {items.map((item) => (
        <li key={item.positionKey} className="flex items-start justify-between gap-3">
          <span className="font-medium text-foreground">{item.symbol}</span>
          <span className={item.pnl < 0 ? 'text-danger' : 'text-success'}>{formatMoney(item.pnl, result?.currency || 'CNY', language)} ({formatUiNumber(item.shockPct, language, { maximumFractionDigits: 2 })}%)</span>
        </li>
      ))}
    </ul>
  ) : <EmptyState title={text.stressNoImpacts} compact />;

  return (
    <section className="space-y-3" aria-label={text.stressTitle} data-testid="portfolio-insights-stress">
      <div><h2 className="text-sm font-semibold text-foreground">{text.stressTitle}</h2><p className="mt-1 text-xs text-secondary">{text.stressDescription}</p></div>
      <Card padding="md" className="space-y-3">
        <SegmentedControl id="portfolio-stress-mode" value={mode} onChange={setMode} ariaLabel={text.stressMode} semantics="single-select" options={[{ value: 'preset', label: text.stressPreset }, { value: 'custom', label: text.stressCustom }]} />
        {catalogLoading && mode === 'preset' ? <Loading label={text.stressCatalogLoading} /> : null}
        {catalogError && mode === 'preset' ? <InlineAlert variant="danger" title={text.stressCatalogFailed} message={catalogError} /> : null}
        {mode === 'preset' && !catalogLoading ? (
          <Select label={text.stressScenario} value={scenarioId} onChange={setScenarioId} options={scenarios.map((item) => ({ value: item.id, label: `${item.name}${item.availability === 'requires_parameters' ? ' *' : ''}` }))} />
        ) : null}
        {mode === 'custom' ? (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <Select label={text.stressFactor} value={factor} onChange={(value) => setFactor(value as ShockFactor)} options={[{ value: 'market', label: text.stressFactorMarket }, { value: 'sector', label: text.stressFactorSector }, { value: 'fx', label: text.stressFactorFx }, { value: 'rate', label: text.stressFactorRate }]} />
            <Input type="number" label={factor === 'rate' ? text.stressShockBp : text.stressShockPct} value={shockValue} onChange={(event) => setShockValue(event.target.value)} min={factor === 'rate' ? -1000 : -100} max={factor === 'rate' ? 1000 : 100} />
          </div>
        ) : null}
        {(mode === 'custom' ? factor === 'sector' : selectedScenario?.requiresTargetSector) ? (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <Input label={text.stressTargetSector} value={targetSector} onChange={(event) => setTargetSector(event.target.value)} />
            <Textarea label={text.stressSectorMap} hint={text.stressSectorMapHint} value={sectorMapInput} onChange={(event) => setSectorMapInput(event.target.value)} />
          </div>
        ) : null}
        <p className="text-xs text-secondary">{text.stressHistoricalUnavailable}</p>
        <Button type="button" variant="primary" onClick={() => void run()} disabled={isRunning || (mode === 'preset' && (!scenarioId || catalogLoading))} isLoading={isRunning} loadingText={text.stressRunning}>{text.stressRun}</Button>
      </Card>
      {error ? <InlineAlert variant="danger" title={text.runFailed} message={error} /> : null}
      {result ? (
        <div className="space-y-3" data-testid="portfolio-stress-result">
          <div className="flex flex-wrap items-center justify-between gap-2"><h3 className="text-sm font-semibold text-foreground">{text.stressResult}</h3><Badge variant={result.status === 'ok' ? 'success' : result.status === 'partial' ? 'warning' : 'default'}>{text.status}: {result.status}</Badge></div>
          {result.statusMessage ? <InlineAlert variant={result.status === 'partial' ? 'warning' : 'info'} message={result.statusMessage} /> : null}
          <div className="grid grid-cols-2 gap-2 lg:grid-cols-5">
            {[[text.stressPortfolioValue, formatMoney(result.portfolioValue, result.currency, language)], [text.stressStressedValue, result.stressedPortfolioValue == null ? '—' : formatMoney(result.stressedPortfolioValue, result.currency, language)], [text.stressPnl, result.portfolioPnl == null ? '—' : formatMoney(result.portfolioPnl, result.currency, language)], [text.stressPnlPct, result.portfolioPnlPct == null ? '—' : `${formatUiNumber(result.portfolioPnlPct, language, { maximumFractionDigits: 2 })}%`], [text.stressPositions, String(result.positionsUsed)]].map(([label, value]) => <Card key={label} padding="sm"><p className="text-xs text-secondary">{label}</p><p className="mt-1 text-sm font-semibold text-foreground">{value}</p></Card>)}
          </div>
          <div className="grid grid-cols-1 gap-3 lg:grid-cols-2"><Card padding="md"><h4 className="text-xs font-semibold text-foreground">{text.stressTopLosers}</h4>{impactList(result.topLosers)}</Card><Card padding="md"><h4 className="text-xs font-semibold text-foreground">{text.stressTopWinners}</h4>{impactList(result.topWinners)}</Card></div>
        </div>
      ) : null}
    </section>
  );
};

export default StressTestView;
