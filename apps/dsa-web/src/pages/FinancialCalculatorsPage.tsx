// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type React from 'react';
import { useEffect, useMemo, useRef, useState } from 'react';
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import {
  calculatorsApi,
  type CompoundGrowthResponse,
  type TargetContributionResponse,
  type TargetDurationResponse,
} from '../api/calculators';
import { getParsedApiError, type ParsedApiError } from '../api/error';
import {
  ApiErrorAlert,
  AppPage,
  Button,
  EmptyState,
  Input,
  PageHeader,
  SegmentedControl,
  StatCard,
  StatePanel,
  Surface,
} from '../components/common';
import { useRouteFocusTarget } from '../components/routing';
import { useUiLanguage } from '../contexts/UiLanguageContext';
import { FINANCIAL_CALCULATORS_TEXT } from '../locales/financialCalculators';
import { APP_ROUTE_PATHS } from '../routing/routes';

type CalculatorMode = 'growth' | 'contribution' | 'duration';

type FieldKey =
  | 'principal'
  | 'annualRatePercent'
  | 'years'
  | 'contribution'
  | 'target'
  | 'periodsPerYear';

type FieldErrors = Partial<Record<FieldKey, string>>;

const DEFAULTS = {
  principal: '10000',
  annualRatePercent: '7',
  years: '10',
  contribution: '500',
  target: '100000',
  periodsPerYear: '12',
};

function parseFiniteNumber(raw: string): number | null {
  const trimmed = raw.trim();
  if (trimmed === '') return null;
  const value = Number(trimmed);
  if (!Number.isFinite(value)) return null;
  return value;
}

function formatMoney(value: number | null | undefined, language: string): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—';
  return new Intl.NumberFormat(language === 'zh' ? 'zh-CN' : 'en-US', {
    maximumFractionDigits: 2,
  }).format(value);
}

const FinancialCalculatorsPage: React.FC = () => {
  const { language } = useUiLanguage();
  const text = FINANCIAL_CALCULATORS_TEXT[language];
  const pageHeadingRef = useRef<HTMLHeadingElement | null>(null);

  const [mode, setMode] = useState<CalculatorMode>('growth');
  const [principal, setPrincipal] = useState(DEFAULTS.principal);
  const [annualRatePercent, setAnnualRatePercent] = useState(DEFAULTS.annualRatePercent);
  const [years, setYears] = useState(DEFAULTS.years);
  const [contribution, setContribution] = useState(DEFAULTS.contribution);
  const [target, setTarget] = useState(DEFAULTS.target);
  const [periodsPerYear, setPeriodsPerYear] = useState(DEFAULTS.periodsPerYear);
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<ParsedApiError | null>(null);
  const [growthResult, setGrowthResult] = useState<CompoundGrowthResponse | null>(null);
  const [contributionResult, setContributionResult] = useState<TargetContributionResponse | null>(null);
  const [durationResult, setDurationResult] = useState<TargetDurationResponse | null>(null);

  useRouteFocusTarget({
    routeId: APP_ROUTE_PATHS.calculators,
    headingRef: pageHeadingRef,
    ready: true,
  });

  useEffect(() => {
    document.title = text.documentTitle;
  }, [text.documentTitle]);

  const modeOptions = useMemo(
    () => [
      { value: 'growth' as const, label: text.modeGrowth },
      { value: 'contribution' as const, label: text.modeContribution },
      { value: 'duration' as const, label: text.modeDuration },
    ],
    [text.modeContribution, text.modeDuration, text.modeGrowth],
  );

  const validate = (): {
    principal: number;
    annualRate: number;
    years: number;
    contribution: number;
    target: number;
    periodsPerYear: number;
  } | null => {
    const nextErrors: FieldErrors = {};

    const principalValue = parseFiniteNumber(principal);
    if (principalValue === null) {
      nextErrors.principal = text.validationFinite;
    } else if (principalValue < 0) {
      nextErrors.principal = text.validationNonNegativeMoney;
    }

    const ratePercentValue = parseFiniteNumber(annualRatePercent);
    if (ratePercentValue === null) {
      nextErrors.annualRatePercent = text.validationFinite;
    }

    const yearsValue = parseFiniteNumber(years);
    if (mode !== 'duration') {
      if (yearsValue === null) {
        nextErrors.years = text.validationFinite;
      } else if (yearsValue <= 0) {
        nextErrors.years = text.validationPositiveYears;
      }
    }

    const contributionValue = parseFiniteNumber(contribution);
    if (mode === 'growth' || mode === 'duration') {
      if (contributionValue === null) {
        nextErrors.contribution = text.validationFinite;
      }
    }

    const targetValue = parseFiniteNumber(target);
    if (mode === 'contribution' || mode === 'duration') {
      if (targetValue === null) {
        nextErrors.target = text.validationFinite;
      } else if (targetValue < 0) {
        nextErrors.target = text.validationNonNegativeMoney;
      }
    }

    const periodsValue = parseFiniteNumber(periodsPerYear);
    if (
      periodsValue === null
      || !Number.isInteger(periodsValue)
      || periodsValue < 1
      || periodsValue > 365
    ) {
      nextErrors.periodsPerYear = text.validationPeriods;
    }

    setFieldErrors(nextErrors);
    if (Object.keys(nextErrors).length > 0) {
      return null;
    }

    return {
      principal: principalValue as number,
      annualRate: (ratePercentValue as number) / 100,
      years: (yearsValue as number) ?? 1,
      contribution: (contributionValue as number) ?? 0,
      target: (targetValue as number) ?? 0,
      periodsPerYear: periodsValue as number,
    };
  };

  const clearResults = () => {
    setGrowthResult(null);
    setContributionResult(null);
    setDurationResult(null);
    setError(null);
  };

  const handleReset = () => {
    setPrincipal(DEFAULTS.principal);
    setAnnualRatePercent(DEFAULTS.annualRatePercent);
    setYears(DEFAULTS.years);
    setContribution(DEFAULTS.contribution);
    setTarget(DEFAULTS.target);
    setPeriodsPerYear(DEFAULTS.periodsPerYear);
    setFieldErrors({});
    clearResults();
  };

  const handleCalculate = async () => {
    const parsed = validate();
    if (!parsed) return;
    setLoading(true);
    setError(null);
    try {
      if (mode === 'growth') {
        const result = await calculatorsApi.compoundGrowth({
          principal: parsed.principal,
          annualRate: parsed.annualRate,
          years: parsed.years,
          contributionPerPeriod: parsed.contribution,
          periodsPerYear: parsed.periodsPerYear,
        });
        setGrowthResult(result);
        setContributionResult(null);
        setDurationResult(null);
      } else if (mode === 'contribution') {
        const result = await calculatorsApi.targetContribution({
          target: parsed.target,
          principal: parsed.principal,
          annualRate: parsed.annualRate,
          years: parsed.years,
          periodsPerYear: parsed.periodsPerYear,
        });
        setContributionResult(result);
        setGrowthResult(null);
        setDurationResult(null);
      } else {
        const result = await calculatorsApi.targetDuration({
          target: parsed.target,
          principal: parsed.principal,
          annualRate: parsed.annualRate,
          contributionPerPeriod: parsed.contribution,
          periodsPerYear: parsed.periodsPerYear,
        });
        setDurationResult(result);
        setGrowthResult(null);
        setContributionResult(null);
      }
    } catch (cause) {
      clearResults();
      setError(getParsedApiError(cause));
    } finally {
      setLoading(false);
    }
  };

  const chartData = useMemo(() => {
    if (!growthResult?.series) return [];
    // Downsample long series for chart readability (keep endpoints).
    const series = growthResult.series;
    if (series.length <= 120) {
      return series.map((row) => ({
        period: row.period,
        balance: row.balance,
        contributed: row.totalContributed,
      }));
    }
    const step = Math.ceil(series.length / 100);
    const sampled = series.filter((_, index) => index % step === 0 || index === series.length - 1);
    return sampled.map((row) => ({
      period: row.period,
      balance: row.balance,
      contributed: row.totalContributed,
    }));
  }, [growthResult]);

  const hasAnyResult = Boolean(growthResult || contributionResult || durationResult);
  const statusTone = (status: string | undefined) => {
    if (status === 'unreachable') return 'danger' as const;
    if (status === 'already_met') return 'warning' as const;
    return 'success' as const;
  };

  const statusLabel = (status: string | undefined) => {
    if (status === 'unreachable') return text.statusUnreachable;
    if (status === 'already_met') return text.statusAlreadyMet;
    if (status === 'ok') return text.statusOk;
    return status ?? '';
  };

  return (
    <AppPage>
      <PageHeader
        ref={pageHeadingRef}
        className="shrink-0"
        title={text.title}
        description={text.description}
      />

      <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-auto pb-6">
        <Surface level="section" padding="md" className="space-y-4">
          <SegmentedControl
            value={mode}
            options={modeOptions}
            onChange={(value) => {
              setMode(value);
              clearResults();
              setFieldErrors({});
            }}
            ariaLabel={text.title}
            semantics="single-select"
          />

          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            <Input
              label={text.principal}
              inputMode="decimal"
              value={principal}
              error={fieldErrors.principal}
              onChange={(event) => setPrincipal(event.target.value)}
            />
            <Input
              label={text.annualRatePercent}
              inputMode="decimal"
              value={annualRatePercent}
              error={fieldErrors.annualRatePercent}
              onChange={(event) => setAnnualRatePercent(event.target.value)}
            />
            {mode !== 'duration' ? (
              <Input
                label={text.years}
                inputMode="decimal"
                value={years}
                error={fieldErrors.years}
                onChange={(event) => setYears(event.target.value)}
              />
            ) : null}
            {mode === 'growth' || mode === 'duration' ? (
              <Input
                label={text.contribution}
                inputMode="decimal"
                value={contribution}
                error={fieldErrors.contribution}
                onChange={(event) => setContribution(event.target.value)}
              />
            ) : null}
            {mode === 'contribution' || mode === 'duration' ? (
              <Input
                label={text.target}
                inputMode="decimal"
                value={target}
                error={fieldErrors.target}
                onChange={(event) => setTarget(event.target.value)}
              />
            ) : null}
            <Input
              label={text.periodsPerYear}
              hint={text.periodsPerYearHint}
              inputMode="numeric"
              value={periodsPerYear}
              error={fieldErrors.periodsPerYear}
              onChange={(event) => setPeriodsPerYear(event.target.value)}
            />
          </div>

          <div className="flex flex-wrap gap-2">
            <Button variant="primary" onClick={() => void handleCalculate()} disabled={loading} isLoading={loading}>
              {loading ? text.calculating : text.calculate}
            </Button>
            <Button variant="secondary" onClick={handleReset} disabled={loading}>
              {text.reset}
            </Button>
          </div>
          <p className="text-xs text-secondary-text">{text.disclaimer}</p>
        </Surface>

        {error ? <ApiErrorAlert error={error} /> : null}

        {!hasAnyResult && !error ? (
          <EmptyState title={text.emptyResults} />
        ) : null}

        {growthResult ? (
          <Surface level="section" padding="md" className="space-y-4">
            <h2 className="text-base font-medium text-foreground">{text.resultsTitle}</h2>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              <StatCard label={text.finalValue} value={formatMoney(growthResult.finalValue, language)} tone="primary" />
              <StatCard
                label={text.totalContributed}
                value={formatMoney(growthResult.totalContributed, language)}
              />
              <StatCard
                label={text.totalGain}
                value={formatMoney(growthResult.totalGain, language)}
                tone={growthResult.totalGain >= 0 ? 'success' : 'danger'}
              />
              <StatCard label={text.periodCount} value={String(growthResult.periodCount)} />
            </div>

            {chartData.length > 1 ? (
              <div className="space-y-2">
                <h3 className="text-sm font-medium text-foreground">{text.chartTitle}</h3>
                <div className="h-64 w-full" data-testid="growth-chart">
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={chartData} margin={{ top: 8, right: 12, bottom: 8, left: 8 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                      <XAxis dataKey="period" tick={{ fontSize: 11 }} minTickGap={24} />
                      <YAxis tick={{ fontSize: 11 }} width={64} />
                      <Tooltip />
                      <Legend />
                      <Line
                        type="monotone"
                        dataKey="balance"
                        name={text.chartBalance}
                        stroke="hsl(var(--primary))"
                        dot={false}
                        strokeWidth={2}
                      />
                      <Line
                        type="monotone"
                        dataKey="contributed"
                        name={text.chartContributed}
                        stroke="hsl(var(--secondary-text))"
                        dot={false}
                        strokeWidth={1.5}
                      />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              </div>
            ) : null}

            <div className="space-y-2">
              <h3 className="text-sm font-medium text-foreground">{text.seriesTitle}</h3>
              <div className="max-h-64 overflow-auto rounded-md border border-subtle">
                <table className="w-full text-left text-sm">
                  <thead className="sticky top-0 bg-surface text-secondary-text">
                    <tr>
                      <th className="px-3 py-2 font-medium">{text.seriesPeriod}</th>
                      <th className="px-3 py-2 font-medium">{text.seriesBalance}</th>
                      <th className="px-3 py-2 font-medium">{text.seriesContributed}</th>
                      <th className="px-3 py-2 font-medium">{text.seriesGain}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {growthResult.series.map((row) => (
                      <tr key={row.period} className="border-t border-subtle">
                        <td className="px-3 py-1.5">{row.period}</td>
                        <td className="px-3 py-1.5">{formatMoney(row.balance, language)}</td>
                        <td className="px-3 py-1.5">{formatMoney(row.totalContributed, language)}</td>
                        <td className="px-3 py-1.5">{formatMoney(row.gain, language)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </Surface>
        ) : null}

        {contributionResult ? (
          <Surface level="section" padding="md" className="space-y-4">
            <h2 className="text-base font-medium text-foreground">{text.resultsTitle}</h2>
            {contributionResult.status === 'unreachable' ? (
              <StatePanel
                state="error"
                title={text.unreachableTitle}
                description={contributionResult.message || text.unreachableDescription}
              />
            ) : null}
            {contributionResult.status === 'already_met' ? (
              <StatePanel
                state="partial"
                title={text.alreadyMetTitle}
                description={contributionResult.message || text.alreadyMetDescription}
              />
            ) : null}
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              <StatCard
                label={text.statusOk}
                value={statusLabel(contributionResult.status)}
                tone={statusTone(contributionResult.status)}
              />
              <StatCard
                label={text.requiredContribution}
                value={formatMoney(contributionResult.contributionPerPeriod ?? null, language)}
                tone="primary"
              />
              <StatCard label={text.periodCount} value={String(contributionResult.periodCount)} />
            </div>
          </Surface>
        ) : null}

        {durationResult ? (
          <Surface level="section" padding="md" className="space-y-4">
            <h2 className="text-base font-medium text-foreground">{text.resultsTitle}</h2>
            {durationResult.status === 'unreachable' ? (
              <StatePanel
                state="error"
                title={text.unreachableTitle}
                description={durationResult.message || text.unreachableDescription}
                data-testid="unreachable-panel"
              />
            ) : null}
            {durationResult.status === 'already_met' ? (
              <StatePanel
                state="partial"
                title={text.alreadyMetTitle}
                description={durationResult.message || text.alreadyMetDescription}
              />
            ) : null}
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              <StatCard
                label={text.statusOk}
                value={statusLabel(durationResult.status)}
                tone={statusTone(durationResult.status)}
              />
              <StatCard
                label={text.periodCount}
                value={
                  durationResult.periodCount === null || durationResult.periodCount === undefined
                    ? '—'
                    : String(durationResult.periodCount)
                }
                tone="primary"
              />
              <StatCard
                label={text.yearsResult}
                value={
                  durationResult.years === null || durationResult.years === undefined
                    ? '—'
                    : formatMoney(durationResult.years, language)
                }
              />
            </div>
          </Surface>
        ) : null}
      </div>
    </AppPage>
  );
};

export default FinancialCalculatorsPage;
