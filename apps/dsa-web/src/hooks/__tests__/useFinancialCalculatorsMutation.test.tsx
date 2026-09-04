// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { calculatorsApi } from '../../api/calculators';
import type {
  CompoundGrowthResponse,
  TargetContributionResponse,
  TargetDurationResponse,
} from '../../api/calculators';
import { createAppQueryClient } from '../../query/createAppQueryClient';
import { createDeferred } from '../../test-utils';
import {
  FINANCIAL_CALCULATORS_MUTATION_SCHEDULE,
  useFinancialCalculatorsMutation,
  type FinancialCalculatorParsedInput,
} from '../useFinancialCalculatorsMutation';

vi.mock('../../api/calculators', () => ({
  calculatorsApi: {
    compoundGrowth: vi.fn(),
    targetContribution: vi.fn(),
    targetDuration: vi.fn(),
  },
}));

function createWrapper(client?: QueryClient) {
  const queryClient = client ?? createAppQueryClient();
  function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
  }
  return { client: queryClient, wrapper: Wrapper };
}

const parsed: FinancialCalculatorParsedInput = {
  principal: 1000,
  annualRate: 0.12,
  years: 1,
  contribution: 0,
  target: 5000,
  periodsPerYear: 12,
};

function growthPayload(finalValue = 1126.83): CompoundGrowthResponse {
  return {
    status: 'ok',
    principal: 1000,
    annualRate: 0.12,
    years: 1,
    contributionPerPeriod: 0,
    periodsPerYear: 12,
    periodCount: 12,
    periodRate: 0.01,
    finalValue,
    totalContributed: 1000,
    totalGain: finalValue - 1000,
    seriesTotalPoints: 13,
    seriesReturnedPoints: 2,
    seriesSampled: true,
    seriesStride: 12,
    series: [
      { period: 0, balance: 1000, totalContributed: 1000, gain: 0 },
      { period: 12, balance: finalValue, totalContributed: 1000, gain: finalValue - 1000 },
    ],
  };
}

const contributionPayload: TargetContributionResponse = {
  status: 'ok',
  target: 5000,
  principal: 1000,
  annualRate: 0.12,
  years: 1,
  periodsPerYear: 12,
  periodCount: 12,
  periodRate: 0.01,
  currencyPrecisionDigits: 2,
  contributionRounding: 'ceiling',
  reasonCode: 'contribution_required',
  contributionPerPeriod: 300,
};

const durationPayload: TargetDurationResponse = {
  status: 'ok',
  target: 5000,
  principal: 1000,
  annualRate: 0.12,
  contributionPerPeriod: 0,
  periodsPerYear: 12,
  periodRate: 0.01,
  reasonCode: 'duration_solved',
  periodCount: 24,
  years: 2,
};

describe('useFinancialCalculatorsMutation', () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it('pins retry: false on the mutation schedule and does not retry a rejected POST', async () => {
    expect(FINANCIAL_CALCULATORS_MUTATION_SCHEDULE.retry).toBe(false);
    vi.mocked(calculatorsApi.compoundGrowth).mockRejectedValue(new Error('growth failed'));
    const { client, wrapper } = createWrapper();
    const { result } = renderHook(() => useFinancialCalculatorsMutation(), { wrapper });

    await act(async () => {
      await result.current.run('growth', parsed);
    });

    expect(calculatorsApi.compoundGrowth).toHaveBeenCalledTimes(1);
    expect(result.current.growth).toBeNull();
    expect(result.current.error).not.toBeNull();
    expect(result.current.loading).toBe(false);
    const retries = client.getMutationCache().getAll().map((entry) => entry.options.retry);
    expect(retries.length).toBeGreaterThan(0);
    expect(retries.every((retry) => retry === false)).toBe(true);
  });

  it('passes an AbortSignal to compoundGrowth', async () => {
    vi.mocked(calculatorsApi.compoundGrowth).mockResolvedValue(growthPayload());
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useFinancialCalculatorsMutation(), { wrapper });

    await act(async () => {
      await result.current.run('growth', parsed);
    });

    expect(calculatorsApi.compoundGrowth).toHaveBeenCalledTimes(1);
    const options = vi.mocked(calculatorsApi.compoundGrowth).mock.calls[0]?.[1];
    expect(options?.signal).toBeInstanceOf(AbortSignal);
  });

  it('cancel aborts the in-flight POST and discards a later completion', async () => {
    const deferred = createDeferred<CompoundGrowthResponse>();
    vi.mocked(calculatorsApi.compoundGrowth).mockImplementation((_body, options) => {
      expect(options?.signal).toBeInstanceOf(AbortSignal);
      return deferred.promise;
    });
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useFinancialCalculatorsMutation(), { wrapper });

    await act(async () => {
      void result.current.run('growth', parsed);
    });
    await waitFor(() => expect(result.current.loading).toBe(true));

    const signal = vi.mocked(calculatorsApi.compoundGrowth).mock.calls[0]?.[1]?.signal;
    await act(async () => {
      result.current.cancel();
    });
    expect(result.current.loading).toBe(false);
    expect(signal?.aborted).toBe(true);

    await act(async () => {
      deferred.resolve(growthPayload(999999));
      await deferred.promise;
    });

    expect(result.current.growth).toBeNull();
    expect(result.current.error).toBeNull();
  });

  it('replaces an in-flight growth POST so a stale completion cannot write', async () => {
    const first = createDeferred<CompoundGrowthResponse>();
    const second = createDeferred<CompoundGrowthResponse>();
    vi.mocked(calculatorsApi.compoundGrowth)
      .mockImplementationOnce((_body, options) => {
        expect(options?.signal).toBeInstanceOf(AbortSignal);
        return first.promise;
      })
      .mockImplementationOnce((_body, options) => {
        expect(options?.signal).toBeInstanceOf(AbortSignal);
        return second.promise;
      });
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useFinancialCalculatorsMutation(), { wrapper });

    await act(async () => {
      void result.current.run('growth', parsed);
    });
    const firstSignal = vi.mocked(calculatorsApi.compoundGrowth).mock.calls[0]?.[1]?.signal;
    await act(async () => {
      void result.current.run('growth', parsed);
    });
    expect(firstSignal?.aborted).toBe(true);
    expect(calculatorsApi.compoundGrowth).toHaveBeenCalledTimes(2);

    await act(async () => {
      first.resolve(growthPayload(999999));
      await first.promise;
    });
    expect(result.current.growth).toBeNull();
    expect(result.current.error).toBeNull();
    expect(result.current.loading).toBe(true);

    await act(async () => {
      second.resolve(growthPayload(1126.83));
      await second.promise;
    });
    await waitFor(() => expect(result.current.growth?.finalValue).toBe(1126.83));
    expect(result.current.contribution).toBeNull();
    expect(result.current.duration).toBeNull();
    expect(result.current.loading).toBe(false);
  });

  it('routes the three calculator POSTs and nulls the other result slots', async () => {
    vi.mocked(calculatorsApi.compoundGrowth).mockResolvedValue(growthPayload());
    vi.mocked(calculatorsApi.targetContribution).mockResolvedValue(contributionPayload);
    vi.mocked(calculatorsApi.targetDuration).mockResolvedValue(durationPayload);
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useFinancialCalculatorsMutation(), { wrapper });

    await act(async () => {
      await result.current.run('growth', parsed);
    });
    expect(calculatorsApi.compoundGrowth).toHaveBeenCalledTimes(1);
    expect(calculatorsApi.targetContribution).not.toHaveBeenCalled();
    expect(calculatorsApi.targetDuration).not.toHaveBeenCalled();
    expect(result.current.growth?.finalValue).toBe(1126.83);
    expect(result.current.contribution).toBeNull();
    expect(result.current.duration).toBeNull();

    await act(async () => {
      await result.current.run('contribution', parsed);
    });
    expect(calculatorsApi.targetContribution).toHaveBeenCalledTimes(1);
    expect(result.current.contribution?.contributionPerPeriod).toBe(300);
    expect(result.current.growth).toBeNull();
    expect(result.current.duration).toBeNull();

    await act(async () => {
      await result.current.run('duration', parsed);
    });
    expect(calculatorsApi.targetDuration).toHaveBeenCalledTimes(1);
    expect(result.current.duration?.periodCount).toBe(24);
    expect(result.current.growth).toBeNull();
    expect(result.current.contribution).toBeNull();
    expect(vi.mocked(calculatorsApi.targetContribution).mock.calls[0]?.[1]?.signal)
      .toBeInstanceOf(AbortSignal);
    expect(vi.mocked(calculatorsApi.targetDuration).mock.calls[0]?.[1]?.signal)
      .toBeInstanceOf(AbortSignal);
  });

  it('does not paint an error after unmount when the in-flight POST later rejects', async () => {
    const deferred = createDeferred<CompoundGrowthResponse>();
    vi.mocked(calculatorsApi.compoundGrowth).mockReturnValue(deferred.promise);
    const { wrapper } = createWrapper();
    const { result, unmount } = renderHook(() => useFinancialCalculatorsMutation(), { wrapper });

    await act(async () => {
      void result.current.run('growth', parsed);
    });
    unmount();
    await act(async () => {
      deferred.reject(new Error('late failure'));
    });
    expect(calculatorsApi.compoundGrowth).toHaveBeenCalledTimes(1);
  });
});
