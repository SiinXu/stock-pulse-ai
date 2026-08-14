// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

import type React from 'react';
import { useRef, useState } from 'react';
import { portfolioInsightsApi } from '../../api/portfolioInsights';
import { formatParsedApiError, getParsedApiError } from '../../api/error';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { PORTFOLIO_INSIGHTS_TEXT } from '../../locales/portfolioInsights';
import type { PortfolioBasketResponse } from '../../types/portfolioInsights';
import { formatUiNumber } from '../../utils/uiLocale';
import { Badge, Button, Card, EmptyState, InlineAlert, Switch, Textarea } from '../common';

function parseBasketInput(value: string): { stockCodes: string[]; weights?: Record<string, number> } {
  const tokens = value.split(/[\s,]+/).map((item) => item.trim()).filter(Boolean);
  const stockCodes: string[] = [];
  const weights: Record<string, number> = {};
  for (const token of tokens) {
    const [rawCode, rawWeight, ...rest] = token.split(':');
    if (!rawCode || rest.length) throw new Error('invalid');
    const code = rawCode.toUpperCase();
    if (stockCodes.includes(code)) throw new Error('duplicate');
    stockCodes.push(code);
    if (rawWeight !== undefined) {
      const weight = Number(rawWeight);
      if (!Number.isFinite(weight) || weight < 0) throw new Error('weight');
      weights[code] = weight;
    }
  }
  return { stockCodes, ...(Object.keys(weights).length ? { weights } : {}) };
}

const BasketAnalysisView: React.FC = () => {
  const { language } = useUiLanguage();
  const text = PORTFOLIO_INSIGHTS_TEXT[language];
  const inFlightRef = useRef(false);
  const [input, setInput] = useState('');
  const [includeStress, setIncludeStress] = useState(true);
  const [result, setResult] = useState<PortfolioBasketResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isRunning, setIsRunning] = useState(false);

  const run = async () => {
    if (inFlightRef.current) return;
    let parsed;
    try {
      parsed = parseBasketInput(input);
    } catch {
      setError(text.basketInputRequired);
      return;
    }
    if (!parsed.stockCodes.length) {
      setError(text.basketInputRequired);
      return;
    }
    if (parsed.stockCodes.length > 20) {
      setError(text.basketTooMany);
      return;
    }
    inFlightRef.current = true;
    setIsRunning(true);
    setError(null);
    try {
      setResult(await portfolioInsightsApi.analyzeBasket({
        ...parsed,
        includeStress,
      }));
    } catch (requestError) {
      setError(formatParsedApiError(getParsedApiError(requestError, language)) || text.runFailed);
    } finally {
      inFlightRef.current = false;
      setIsRunning(false);
    }
  };

  return (
    <section className="space-y-3" aria-label={text.basketTitle} data-testid="portfolio-insights-basket">
      <div>
        <h2 className="text-sm font-semibold text-foreground">{text.basketTitle}</h2>
        <p className="mt-1 text-xs text-secondary">{text.basketDescription}</p>
      </div>
      <Card padding="md">
        <div className="space-y-3">
          <Textarea
            label={text.basketSymbols}
            hint={text.basketSymbolsHint}
            placeholder={text.basketPlaceholder}
            value={input}
            onChange={(event) => setInput(event.target.value)}
            error={error && !result ? error : undefined}
          />
          <div className="flex min-h-11 items-center justify-between gap-3">
            <label htmlFor="portfolio-basket-stress" className="text-xs font-medium text-foreground">
              {text.basketIncludeStress}
            </label>
            <Switch
              id="portfolio-basket-stress"
              checked={includeStress}
              onCheckedChange={setIncludeStress}
              aria-label={text.basketIncludeStress}
            />
          </div>
          <Button
            type="button"
            variant="primary"
            onClick={() => void run()}
            isLoading={isRunning}
            disabled={isRunning}
            loadingText={text.basketRunning}
          >
            {text.basketRun}
          </Button>
        </div>
      </Card>

      {error ? <InlineAlert variant="danger" title={text.runFailed} message={error} /> : null}
      {result ? (
        <div className="space-y-3" data-testid="portfolio-basket-result">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h3 className="text-sm font-semibold text-foreground">{text.basketResult}</h3>
            <Badge variant={result.status === 'ok' ? 'success' : result.status === 'partial' ? 'warning' : 'default'}>
              {text.status}: {result.status}
            </Badge>
          </div>
          {result.statusMessage ? <InlineAlert variant="warning" message={result.statusMessage} /> : null}
          <div className="grid grid-cols-1 gap-3 lg:grid-cols-3">
            <Card padding="md">
              <h4 className="text-xs font-semibold text-foreground">{text.basketSymbolsUsed}</h4>
              <div className="mt-2 flex flex-wrap gap-1.5">
                {result.weights.map((item) => (
                  <Badge key={item.symbol} variant="info">{item.symbol} {formatUiNumber(item.weightPct, language, { maximumFractionDigits: 1 })}%</Badge>
                ))}
              </div>
            </Card>
            <Card padding="md">
              <h4 className="text-xs font-semibold text-foreground">{text.basketStance}</h4>
              <dl className="mt-2 space-y-1 text-xs">
                <div className="flex justify-between"><dt className="text-secondary">{text.basketScored}</dt><dd>{result.stanceDistribution.scoredCount}</dd></div>
                <div className="flex justify-between"><dt className="text-secondary">{text.basketUnanalyzed}</dt><dd>{result.stanceDistribution.unanalyzedCount}</dd></div>
                <div className="flex justify-between"><dt className="text-secondary">{text.basketAverage}</dt><dd>{result.stanceDistribution.averageScore == null ? '—' : formatUiNumber(result.stanceDistribution.averageScore, language, { maximumFractionDigits: 1 })}</dd></div>
              </dl>
            </Card>
            <Card padding="md">
              <h4 className="text-xs font-semibold text-foreground">{text.basketHealth}</h4>
              <p className="mt-2 text-2xl font-semibold text-foreground">{result.health.score ?? result.health.partialScore ?? '—'}</p>
              <p className="mt-1 text-xs text-secondary">{result.health.status ?? text.statusUnavailable}</p>
            </Card>
          </div>
          <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
            <Card padding="md">
              <h4 className="text-xs font-semibold text-foreground">{text.basketCorrelations}</h4>
              {result.correlationHighlights.length ? (
                <ul className="mt-2 space-y-1.5 text-xs text-secondary">
                  {result.correlationHighlights.map((item) => <li key={`${item.left}-${item.right}`}>{item.left} / {item.right}: {item.correlation.toFixed(2)}</li>)}
                </ul>
              ) : <EmptyState title={text.basketNoCorrelations} compact />}
            </Card>
            <Card padding="md">
              <h4 className="text-xs font-semibold text-foreground">{text.basketSharedRisks}</h4>
              {result.sharedRiskExposures.length ? (
                <ul className="mt-2 space-y-2 text-xs text-secondary">
                  {result.sharedRiskExposures.map((item, index) => <li key={`${item.kind}-${index}`}><span className="font-medium text-foreground">{item.symbols.join(', ')}</span><br />{item.summary}</li>)}
                </ul>
              ) : <EmptyState title={text.basketNoSharedRisks} compact />}
            </Card>
          </div>
          <Card padding="md">
            <h4 className="text-xs font-semibold text-foreground">{text.basketDegraded}</h4>
            {result.degradedSymbols.length ? (
              <ul className="mt-2 space-y-1 text-xs text-warning">
                {result.degradedSymbols.map((item) => <li key={item.stockCode}>{item.stockCode}: {item.detail || item.reason}</li>)}
              </ul>
            ) : <p className="mt-2 text-xs text-secondary">{text.basketNoDegraded}</p>}
            <p className="mt-3 border-t border-subtle pt-3 text-xs text-muted-text">{result.disclaimer}</p>
          </Card>
        </div>
      ) : null}
    </section>
  );
};

export default BasketAnalysisView;
