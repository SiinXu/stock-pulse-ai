// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

import type React from 'react';
import { useRef, useState } from 'react';
import { portfolioInsightsApi } from '../../api/portfolioInsights';
import { formatParsedApiError, getParsedApiError } from '../../api/error';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { formatUiText } from '../../i18n/uiText';
import { PORTFOLIO_INSIGHTS_TEXT } from '../../locales/portfolioInsights';
import type { PortfolioCostMethod } from '../../types/portfolio';
import type { PortfolioRebalancingResponse, RiskTolerance } from '../../types/portfolioInsights';
import { formatMoney } from '../../utils/portfolioFormat';
import { formatUiNumber } from '../../utils/uiLocale';
import { Badge, Button, Card, EmptyState, InlineAlert, Input, Select, StatePanel } from '../common';

type Props = { accountId?: number; costMethod: PortfolioCostMethod };

const RebalanceView: React.FC<Props> = ({ accountId, costMethod }) => {
  const { language } = useUiLanguage();
  const text = PORTFOLIO_INSIGHTS_TEXT[language];
  const inFlightRef = useRef(false);
  const [riskTolerance, setRiskTolerance] = useState<RiskTolerance>('moderate');
  const [driftThreshold, setDriftThreshold] = useState('5');
  const [lookback, setLookback] = useState('252');
  const [result, setResult] = useState<PortfolioRebalancingResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isRunning, setIsRunning] = useState(false);

  const run = async () => {
    if (inFlightRef.current) return;
    const drift = Number(driftThreshold);
    const lookbackDays = Number(lookback);
    if (!Number.isFinite(drift) || drift < 0 || drift > 100 || !Number.isInteger(lookbackDays) || lookbackDays < 60 || lookbackDays > 1000) {
      setError(text.runFailed);
      return;
    }
    inFlightRef.current = true;
    setIsRunning(true);
    setError(null);
    try {
      setResult(await portfolioInsightsApi.getRebalancing({
        accountId,
        costMethod,
        riskTolerance,
        driftThresholdPct: drift,
        lookbackTradingDays: lookbackDays,
      }));
    } catch (requestError) {
      setError(formatParsedApiError(getParsedApiError(requestError, language)) || text.runFailed);
    } finally {
      inFlightRef.current = false;
      setIsRunning(false);
    }
  };

  return (
    <section className="space-y-3" aria-label={text.rebalanceTitle} data-testid="portfolio-insights-rebalance">
      <div><h2 className="text-sm font-semibold text-foreground">{text.rebalanceTitle}</h2><p className="mt-1 text-xs text-secondary">{text.rebalanceDescription}</p></div>
      <Card padding="md">
        <div className="grid grid-cols-1 items-end gap-3 sm:grid-cols-3">
          <Select label={text.rebalanceRiskTolerance} value={riskTolerance} onChange={(value) => setRiskTolerance(value as RiskTolerance)} options={[{ value: 'conservative', label: text.rebalanceConservative }, { value: 'moderate', label: text.rebalanceModerate }, { value: 'aggressive', label: text.rebalanceAggressive }]} />
          <Input type="number" label={text.rebalanceDrift} value={driftThreshold} onChange={(event) => setDriftThreshold(event.target.value)} min={0} max={100} step="0.5" />
          <Input type="number" label={text.rebalanceLookback} value={lookback} onChange={(event) => setLookback(event.target.value)} min={60} max={1000} step="1" />
        </div>
        <Button type="button" variant="primary" className="mt-3" onClick={() => void run()} disabled={isRunning} isLoading={isRunning} loadingText={text.rebalanceRunning}>{text.rebalanceRun}</Button>
      </Card>
      {error ? <InlineAlert variant="danger" title={text.runFailed} message={error} /> : null}
      {result ? (
        <div className="space-y-3" data-testid="portfolio-rebalance-result">
          <div className="flex flex-wrap items-center justify-between gap-2"><h3 className="text-sm font-semibold text-foreground">{text.rebalanceResult}</h3><Badge variant={result.status === 'ok' ? 'success' : result.status === 'insufficient_data' || result.status === 'refused' ? 'warning' : 'default'}>{text.status}: {result.status}</Badge></div>
          {result.status === 'refused' || result.status === 'insufficient_data' ? (
            <StatePanel state="blocked" title={text.rebalanceRefused} description={result.statusMessage || text.rebalanceRefusedHint} size="compact" titleAs="h4" data-testid="portfolio-rebalance-refused" />
          ) : result.status === 'empty_portfolio' ? (
            <EmptyState title={text.rebalanceEmpty} compact />
          ) : (
            <>
              <div className="grid grid-cols-2 gap-2 lg:grid-cols-4">
                <Card padding="sm"><p className="text-xs text-secondary">{text.rebalanceRiskTolerance}</p><p className="mt-1 text-sm font-semibold text-foreground">{result.riskTolerance}</p></Card>
                <Card padding="sm"><p className="text-xs text-secondary">{text.rebalanceMaxSingle}</p><p className="mt-1 text-sm font-semibold text-foreground">{formatUiNumber(result.targetModel.maxSingleWeightPct, language, { maximumFractionDigits: 1 })}%</p></Card>
                <Card padding="sm"><p className="text-xs text-secondary">{text.rebalanceEffectiveN}</p><p className="mt-1 text-sm font-semibold text-foreground">{result.current.effectiveN == null ? '—' : formatUiNumber(result.current.effectiveN, language, { maximumFractionDigits: 2 })}</p></Card>
                <Card padding="sm"><p className="text-xs text-secondary">{text.rebalanceVar}</p><p className="mt-1 text-sm font-semibold text-foreground">{result.current.varPct == null ? '—' : `${formatUiNumber(result.current.varPct, language, { maximumFractionDigits: 2 })}%`}</p></Card>
              </div>
              <Card padding="md">
                <h4 className="text-xs font-semibold text-foreground">{text.rebalanceSuggestions}</h4>
                {result.suggestions.length ? (
                  <ul className="mt-2 divide-y divide-subtle">
                    {result.suggestions.map((item) => (
                      <li key={`${item.symbol}-${item.action}`} className="py-3 first:pt-0 last:pb-0">
                        <div className="flex flex-wrap items-center justify-between gap-2"><span className="font-medium text-foreground">{item.symbol}</span><Badge variant={item.action === 'trim' ? 'warning' : item.action === 'add' ? 'success' : 'default'}>{item.action}</Badge></div>
                        <p className="mt-1 text-xs text-secondary">{formatUiText(text.rebalanceFromTo, { from: formatUiNumber(item.fromWeightPct, language, { maximumFractionDigits: 1 }), to: formatUiNumber(item.toWeightPct, language, { maximumFractionDigits: 1 }) })}</p>
                        <p className="mt-1 text-xs text-secondary">{formatUiText(text.rebalanceNotional, { value: formatMoney(Math.abs(item.approxNotional), result.currency, language) })}</p>
                        <p className="mt-1 text-xs text-muted-text">{item.rationale}</p>
                      </li>
                    ))}
                  </ul>
                ) : <EmptyState title={text.rebalanceNoSuggestions} compact />}
              </Card>
              <Card padding="md">
                <h4 className="text-xs font-semibold text-foreground">{text.rebalanceBands}</h4>
                <ul className="mt-2 grid grid-cols-1 gap-2 lg:grid-cols-2">
                  {result.positionBands.map((item) => (
                    <li key={item.symbol} className="rounded-lg border border-subtle p-3 text-xs">
                      <div className="flex items-center justify-between gap-2"><span className="font-medium text-foreground">{item.symbol}</span><Badge variant="info">{item.action}</Badge></div>
                      <p className="mt-1 text-secondary">{formatUiText(text.rebalanceBandRange, { current: formatUiNumber(item.currentWeightPct, language, { maximumFractionDigits: 1 }), low: formatUiNumber(item.targetWeightPctLow, language, { maximumFractionDigits: 1 }), high: formatUiNumber(item.targetWeightPctHigh, language, { maximumFractionDigits: 1 }), mid: formatUiNumber(item.targetWeightPctMid, language, { maximumFractionDigits: 1 }) })}</p>
                      <p className="mt-1 text-muted-text">{item.rationale}</p>
                    </li>
                  ))}
                </ul>
              </Card>
            </>
          )}
          <InlineAlert variant="info" message={text.rebalanceSuggestionOnly} />
          <p className="text-xs text-muted-text">{result.disclaimer}</p>
        </div>
      ) : null}
    </section>
  );
};

export default RebalanceView;
