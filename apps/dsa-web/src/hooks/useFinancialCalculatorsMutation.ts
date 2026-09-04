// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { useMutation } from '@tanstack/react-query';
import { useCallback, useEffect, useRef, useState } from 'react';
import {
  calculatorsApi,
  type CompoundGrowthResponse,
  type TargetContributionResponse,
  type TargetDurationResponse,
} from '../api/calculators';
import { getParsedApiError, type ParsedApiError } from '../api/error';

export type CalculatorMode = 'growth' | 'contribution' | 'duration';

export type FinancialCalculatorParsedInput = {
  principal: number;
  annualRate: number;
  years: number;
  contribution: number;
  target: number;
  periodsPerYear: number;
};

export const FINANCIAL_CALCULATORS_MUTATION_SCHEDULE = {
  retry: false,
} as const;

type CalculatorMutationVars = {
  mode: CalculatorMode;
  parsed: FinancialCalculatorParsedInput;
  signal: AbortSignal;
};

type CalculatorMutationResult =
  | { mode: 'growth'; result: CompoundGrowthResponse }
  | { mode: 'contribution'; result: TargetContributionResponse }
  | { mode: 'duration'; result: TargetDurationResponse };

async function postCalculatorRun(
  { mode, parsed, signal }: CalculatorMutationVars,
): Promise<CalculatorMutationResult> {
  if (mode === 'growth') {
    return {
      mode,
      result: await calculatorsApi.compoundGrowth({
        principal: parsed.principal,
        annualRate: parsed.annualRate,
        years: parsed.years,
        contributionPerPeriod: parsed.contribution,
        periodsPerYear: parsed.periodsPerYear,
      }, { signal }),
    };
  }
  if (mode === 'contribution') {
    return {
      mode,
      result: await calculatorsApi.targetContribution({
        target: parsed.target,
        principal: parsed.principal,
        annualRate: parsed.annualRate,
        years: parsed.years,
        periodsPerYear: parsed.periodsPerYear,
      }, { signal }),
    };
  }
  return {
    mode,
    result: await calculatorsApi.targetDuration({
      target: parsed.target,
      principal: parsed.principal,
      annualRate: parsed.annualRate,
      contributionPerPeriod: parsed.contribution,
      periodsPerYear: parsed.periodsPerYear,
    }, { signal }),
  };
}

/**
 * TanStack Query schedule adapter for Financial Calculators POSTs.
 *
 * Parity with the previous page-owned calculate path:
 * - Transport stays in `calculatorsApi` (`compoundGrowth` / `targetContribution` /
 *   `targetDuration`) with `{ signal }`.
 * - A new Calculate aborts and replaces the in-flight request; mode switch,
 *   reset, and unmount abort and clear. Do not ignore a second click.
 * - `retry: false`; no poll; no focus refetch; no query cache of POST bodies.
 * - Request generation fences stale completions so they cannot write results
 *   or paint `ApiErrorAlert`.
 */
export function useFinancialCalculatorsMutation() {
  const requestVersionRef = useRef(0);
  const activeRequestRef = useRef<AbortController | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<ParsedApiError | null>(null);
  const [growth, setGrowth] = useState<CompoundGrowthResponse | null>(null);
  const [contribution, setContribution] = useState<TargetContributionResponse | null>(null);
  const [duration, setDuration] = useState<TargetDurationResponse | null>(null);

  const mutation = useMutation({
    mutationFn: postCalculatorRun,
    retry: FINANCIAL_CALCULATORS_MUTATION_SCHEDULE.retry,
  });
  const { mutateAsync } = mutation;

  const clearResults = useCallback(() => {
    setGrowth(null);
    setContribution(null);
    setDuration(null);
    setError(null);
  }, []);

  const cancel = useCallback(() => {
    requestVersionRef.current += 1;
    activeRequestRef.current?.abort();
    activeRequestRef.current = null;
    setLoading(false);
  }, []);

  const run = useCallback(async (
    mode: CalculatorMode,
    parsed: FinancialCalculatorParsedInput,
  ) => {
    activeRequestRef.current?.abort();
    const controller = new AbortController();
    activeRequestRef.current = controller;
    const requestVersion = requestVersionRef.current + 1;
    requestVersionRef.current = requestVersion;
    setLoading(true);
    setError(null);
    try {
      const outcome = await mutateAsync({
        mode,
        parsed,
        signal: controller.signal,
      });
      if (requestVersionRef.current !== requestVersion) return;
      if (outcome.mode === 'growth') {
        setGrowth(outcome.result);
        setContribution(null);
        setDuration(null);
      } else if (outcome.mode === 'contribution') {
        setContribution(outcome.result);
        setGrowth(null);
        setDuration(null);
      } else {
        setDuration(outcome.result);
        setGrowth(null);
        setContribution(null);
      }
    } catch (cause) {
      if (controller.signal.aborted || requestVersionRef.current !== requestVersion) return;
      clearResults();
      setError(getParsedApiError(cause));
    } finally {
      if (requestVersionRef.current === requestVersion) {
        activeRequestRef.current = null;
        setLoading(false);
      }
    }
  }, [clearResults, mutateAsync]);

  useEffect(() => () => {
    requestVersionRef.current += 1;
    activeRequestRef.current?.abort();
  }, []);

  return {
    run,
    cancel,
    clearResults,
    loading,
    error,
    growth,
    contribution,
    duration,
  };
}

export default useFinancialCalculatorsMutation;
