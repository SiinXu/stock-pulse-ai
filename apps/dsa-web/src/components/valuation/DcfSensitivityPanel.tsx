// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type React from 'react';
import { useCallback, useId, useMemo, useState } from 'react';
import {
  estimateStockValuation,
  type ValuationEstimate,
  type ValuationEstimateParams,
} from '../../api/valuation';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { VALUATION_TEXT } from '../../locales/valuation';
import {
  Button,
  Card,
  DataTable,
  type DataTableColumn,
  EmptyState,
  InlineAlert,
  Input,
} from '../common';

export type DcfSensitivityPanelProps = {
  estimate?: ValuationEstimate | null;
  stockCode?: string;
  fetchEstimate?: (params: ValuationEstimateParams) => Promise<ValuationEstimate>;
  readOnly?: boolean;
  className?: string;
};

type SensitivityRow = { growthRate?: number; discountRate?: number; equityValue?: number };
type SensitivityMatrixRow = { discountRate: number };

const asNumber = (value: unknown): number | undefined => {
  if (typeof value === 'number' && Number.isFinite(value)) return value;
  if (typeof value === 'string' && value.trim()) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : undefined;
  }
  return undefined;
};

const formatRate = (value: number | undefined): string =>
  value === undefined ? '—' : `${(value * 100).toFixed(1)}%`;

const formatMoney = (value: number | undefined | null): string => {
  if (value === undefined || value === null || !Number.isFinite(value)) return '—';
  return value.toLocaleString(undefined, { maximumFractionDigits: 2 });
};

const readAssumptions = (estimate: ValuationEstimate | null | undefined) => {
  const raw = (estimate?.dcf?.assumptions ?? {}) as Record<string, unknown>;
  return {
    growthRate: asNumber(raw.growthRate ?? raw.growth_rate),
    discountRate: asNumber(raw.discountRate ?? raw.discount_rate),
    terminalGrowthRate: asNumber(raw.terminalGrowthRate ?? raw.terminal_growth_rate),
    projectionYears: asNumber(raw.projectionYears ?? raw.projection_years),
  };
};

const heatClass = (value: number, min: number, max: number): string => {
  if (!Number.isFinite(value) || max <= min) return 'bg-surface-muted text-content';
  const t = (value - min) / (max - min);
  if (t >= 0.75) return 'bg-emerald-500/25 text-content font-medium';
  if (t >= 0.5) return 'bg-emerald-500/15 text-content';
  if (t >= 0.25) return 'bg-amber-500/15 text-content';
  return 'bg-rose-500/15 text-content';
};

export const DcfSensitivityPanel: React.FC<DcfSensitivityPanelProps> = ({
  estimate: initialEstimate = null,
  stockCode: initialStockCode = '',
  fetchEstimate,
  readOnly = false,
  className,
}) => {
  const { language } = useUiLanguage();
  const text = VALUATION_TEXT[language] ?? VALUATION_TEXT.en;
  const formId = useId();
  const stockCodeId = `${formId}-stock-code`;
  const growthRateId = `${formId}-growth-rate`;
  const discountRateId = `${formId}-discount-rate`;
  const terminalGrowthId = `${formId}-terminal-growth`;
  const projectionYearsId = `${formId}-projection-years`;
  const [estimate, setEstimate] = useState<ValuationEstimate | null>(initialEstimate ?? null);
  const [stockCode, setStockCode] = useState(initialStockCode || initialEstimate?.stockCode || '');
  const initialAssumptions = readAssumptions(initialEstimate);
  const [growthRate, setGrowthRate] = useState(
    initialAssumptions.growthRate !== undefined ? String(initialAssumptions.growthRate) : '0.05',
  );
  const [discountRate, setDiscountRate] = useState(
    initialAssumptions.discountRate !== undefined ? String(initialAssumptions.discountRate) : '0.10',
  );
  const [terminalGrowth, setTerminalGrowth] = useState(
    initialAssumptions.terminalGrowthRate !== undefined
      ? String(initialAssumptions.terminalGrowthRate)
      : '0.03',
  );
  const [projectionYears, setProjectionYears] = useState(
    initialAssumptions.projectionYears !== undefined
      ? String(Math.round(initialAssumptions.projectionYears))
      : '5',
  );
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const rows: SensitivityRow[] = useMemo(() => {
    const rawRows = estimate?.dcf?.sensitivity?.rows;
    if (!Array.isArray(rawRows)) return [];
    return rawRows.map((row) => ({
      growthRate: asNumber(row.growthRate),
      discountRate: asNumber(row.discountRate),
      equityValue: asNumber(row.equityValue),
    }));
  }, [estimate]);

  const matrix = useMemo(() => {
    const growthRates = Array.from(
      new Set(rows.map((row) => row.growthRate).filter((v): v is number => v !== undefined)),
    ).sort((a, b) => a - b);
    const discountRates = Array.from(
      new Set(rows.map((row) => row.discountRate).filter((v): v is number => v !== undefined)),
    ).sort((a, b) => a - b);
    const lookup = new Map<string, number>();
    const values: number[] = [];
    for (const row of rows) {
      if (row.growthRate === undefined || row.discountRate === undefined || row.equityValue === undefined) {
        continue;
      }
      lookup.set(`${row.growthRate}|${row.discountRate}`, row.equityValue);
      values.push(row.equityValue);
    }
    return {
      growthRates,
      discountRates,
      lookup,
      min: values.length ? Math.min(...values) : 0,
      max: values.length ? Math.max(...values) : 0,
    };
  }, [rows]);
  const sensitivityRows = useMemo<SensitivityMatrixRow[]>(
    () => matrix.discountRates.map((discountRate) => ({ discountRate })),
    [matrix.discountRates],
  );
  const sensitivityColumns = useMemo<DataTableColumn<SensitivityMatrixRow>[]>(() => [
    {
      id: 'discount-rate',
      header: `${text.discountAxis} / ${text.growthAxis}`,
      cell: (row) => formatRate(row.discountRate),
      rowHeader: true,
    },
    ...matrix.growthRates.map((growth) => ({
      id: `growth-${growth}`,
      header: formatRate(growth),
      align: 'end' as const,
      cell: (row: SensitivityMatrixRow) => {
        const value = matrix.lookup.get(`${growth}|${row.discountRate}`);
        return (
          <div
            className={`rounded-md px-2 py-1 text-right tabular-nums ${
              value === undefined
                ? 'bg-surface-muted text-content-muted'
                : heatClass(value, matrix.min, matrix.max)
            }`}
          >
            {formatMoney(value)}
          </div>
        );
      },
    })),
  ], [matrix.growthRates, matrix.lookup, matrix.max, matrix.min, text.discountAxis, text.growthAxis]);

  const dcfStatus = estimate?.dcf?.status ?? estimate?.status;
  const insufficient =
    dcfStatus === 'insufficient_fundamentals' || dcfStatus === 'invalid_assumptions';

  const handleRecompute = useCallback(async () => {
    const code = stockCode.trim();
    if (!code) {
      setError(text.stockCode);
      return;
    }
    const g = Number(growthRate);
    const d = Number(discountRate);
    const tg = Number(terminalGrowth);
    const years = Number(projectionYears);
    if (![g, d, tg, years].every((n) => Number.isFinite(n))) {
      setError(text.percentHint);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const fetcher = fetchEstimate ?? estimateStockValuation;
      const next = await fetcher({
        stockCode: code,
        growthRate: g,
        discountRate: d,
        terminalGrowthRate: tg,
        projectionYears: Math.round(years),
      });
      setEstimate(next);
      const nextAssumptions = readAssumptions(next);
      if (nextAssumptions.growthRate !== undefined) setGrowthRate(String(nextAssumptions.growthRate));
      if (nextAssumptions.discountRate !== undefined) setDiscountRate(String(nextAssumptions.discountRate));
      if (nextAssumptions.terminalGrowthRate !== undefined) {
        setTerminalGrowth(String(nextAssumptions.terminalGrowthRate));
      }
      if (nextAssumptions.projectionYears !== undefined) {
        setProjectionYears(String(Math.round(nextAssumptions.projectionYears)));
      }
    } catch (err) {
      const message =
        err && typeof err === 'object' && 'message' in err
          ? String((err as { message?: string }).message || text.loadFailed)
          : text.loadFailed;
      setError(message);
    } finally {
      setLoading(false);
    }
  }, [discountRate, fetchEstimate, growthRate, projectionYears, stockCode, terminalGrowth, text]);

  return (
    <div className={className}>
      <Card data-testid="dcf-sensitivity-panel">
        <div className="flex flex-col gap-4 p-4">
        <header className="space-y-1">
          <h2 className="text-base font-semibold text-content">{text.title}</h2>
          <p className="text-sm text-content-muted">{text.description}</p>
        </header>

        {!readOnly && (
          <section
            className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3"
            data-testid="dcf-assumptions-form"
            aria-label={text.assumptions}
          >
            <Input
              id={stockCodeId}
              label={text.stockCode}
              value={stockCode}
              onChange={(event) => setStockCode(event.target.value)}
              placeholder={text.stockCodePlaceholder}
              data-testid="dcf-stock-code"
            />
            <Input
              id={growthRateId}
              label={text.growthRate}
              hint={text.percentHint}
              value={growthRate}
              onChange={(event) => setGrowthRate(event.target.value)}
              inputMode="decimal"
              data-testid="dcf-growth-rate"
            />
            <Input
              id={discountRateId}
              label={text.discountRate}
              hint={text.percentHint}
              value={discountRate}
              onChange={(event) => setDiscountRate(event.target.value)}
              inputMode="decimal"
              data-testid="dcf-discount-rate"
            />
            <Input
              id={terminalGrowthId}
              label={text.terminalGrowth}
              hint={text.percentHint}
              value={terminalGrowth}
              onChange={(event) => setTerminalGrowth(event.target.value)}
              inputMode="decimal"
              data-testid="dcf-terminal-growth"
            />
            <Input
              id={projectionYearsId}
              label={text.projectionYears}
              value={projectionYears}
              onChange={(event) => setProjectionYears(event.target.value)}
              inputMode="numeric"
              data-testid="dcf-projection-years"
            />
            <div className="flex items-end">
              <Button variant="primary" type="button" onClick={() => void handleRecompute()} disabled={loading} data-testid="dcf-recompute">
                {loading ? text.recomputing : text.recompute}
              </Button>
            </div>
          </section>
        )}

        {error && <InlineAlert variant="danger" title={text.loadFailed} message={error} data-testid="dcf-error" />}

        {!estimate && !loading && (
          <EmptyState title={text.noEstimate} description={text.emptyDescription} data-testid="dcf-empty-estimate" />
        )}

        {estimate && (
          <section className="space-y-3" data-testid="dcf-base-case">
            <div className="grid gap-2 sm:grid-cols-3">
              <div className="rounded-md border border-border bg-surface-muted/40 px-3 py-2">
                <div className="text-xs text-content-muted">{text.status}</div>
                <div className="text-sm font-medium">{estimate.status}</div>
              </div>
              <div className="rounded-md border border-border bg-surface-muted/40 px-3 py-2">
                <div className="text-xs text-content-muted">{text.equityValue}</div>
                <div className="text-sm font-medium">{formatMoney(estimate.dcf?.equityValue ?? null)}</div>
              </div>
              <div className="rounded-md border border-border bg-surface-muted/40 px-3 py-2">
                <div className="text-xs text-content-muted">{text.intrinsicPerShare}</div>
                <div className="text-sm font-medium">{formatMoney(estimate.dcf?.intrinsicValuePerShare ?? null)}</div>
              </div>
            </div>

            <div className="rounded-md border border-border px-3 py-2 text-sm" data-testid="dcf-visible-assumptions">
              <div className="mb-1 font-medium">{text.assumptions}</div>
              <ul className="grid gap-1 sm:grid-cols-2">
                <li>{text.growthRate}: {formatRate(readAssumptions(estimate).growthRate)}</li>
                <li>{text.discountRate}: {formatRate(readAssumptions(estimate).discountRate)}</li>
                <li>{text.terminalGrowth}: {formatRate(readAssumptions(estimate).terminalGrowthRate)}</li>
                <li>{text.projectionYears}: {readAssumptions(estimate).projectionYears ?? '—'}</li>
              </ul>
              <div className="mt-2 text-xs text-content-muted">
                {text.rangeLow}: {formatMoney(estimate.dcf?.sensitivity?.equityValueLow ?? null)} ·{' '}
                {text.rangeMid}: {formatMoney(estimate.dcf?.sensitivity?.equityValueMid ?? null)} ·{' '}
                {text.rangeHigh}: {formatMoney(estimate.dcf?.sensitivity?.equityValueHigh ?? null)}
              </div>
            </div>

            {insufficient && (
              <InlineAlert
                variant="warning"
                title={text.insufficientTitle}
                message={estimate.dcf?.message || estimate.message || text.insufficientDescription}
                data-testid="dcf-insufficient"
              />
            )}

            {rows.length === 0 ? (
              <EmptyState title={text.emptyTitle} description={text.emptyDescription} data-testid="dcf-empty-sensitivity" />
            ) : (
              <div className="overflow-x-auto" data-testid="dcf-sensitivity-table">
                <div className="mb-2 text-sm font-medium">{text.sensitivityTable}</div>
                <DataTable
                  caption={text.sensitivityTable}
                  columns={sensitivityColumns}
                  rows={sensitivityRows}
                  getRowKey={(row) => row.discountRate}
                  emptyState={{ title: text.emptyTitle, description: text.emptyDescription }}
                  density="compact"
                  frame="embedded"
                  minWidth="container"
                />
              </div>
            )}
          </section>
        )}

        <p className="text-xs text-content-muted" data-testid="dcf-disclaimer" role="note">
          {estimate?.disclaimer || text.disclaimer}
        </p>
        </div>
      </Card>
    </div>
  );
};

export default DcfSensitivityPanel;
