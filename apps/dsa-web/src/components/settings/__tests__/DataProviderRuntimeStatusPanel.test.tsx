// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { DataProviderRuntimeStatusResponse } from '../../../types/systemConfig';
import { DataProviderRuntimeStatusPanel } from '../DataProviderRuntimeStatusPanel';

const getDataProviderRuntimeStatus = vi.fn();

vi.mock('../../../api/systemConfig', () => ({
  systemConfigApi: {
    getDataProviderRuntimeStatus: (...args: unknown[]) => getDataProviderRuntimeStatus(...args),
  },
}));

function okStatus(): DataProviderRuntimeStatusResponse {
  return {
    schemaVersion: 'data_provider_runtime_status_v1',
    asOf: '2026-08-12T00:00:00+00:00',
    partial: false,
    sourceState: 'ok',
    errorCode: null,
    errorMessage: null,
    markets: [
      {
        market: 'cn',
        dataType: 'daily_data',
        orderedProviderIds: ['akshare', 'tushare'],
        primaryProviderId: 'akshare',
        fallbackProviderIds: ['tushare'],
        primarySelection: 'first_eligible_with_health',
        quality: 'ok',
        asOf: null,
      },
    ],
    providers: [
      {
        providerId: 'akshare',
        displayName: 'AkshareFetcher',
        role: 'baseline',
        markets: ['cn'],
        capabilities: ['daily_data'],
        configured: null,
        available: true,
        healthStatus: 'healthy',
        healthScore: 95,
        circuitState: 'closed',
        sampleCount: 3,
        staticPriority: 5,
        lastSuccessAt: '2026-08-12T00:00:00+00:00',
        lastFailureAt: null,
        failureReason: null,
        isPrimaryFor: ['daily_data:cn'],
        isFallbackFor: [],
        configDirectory: false,
      },
      {
        providerId: 'tushare',
        displayName: 'TushareFetcher',
        role: 'enhancer',
        markets: ['cn'],
        capabilities: ['daily_data'],
        configured: false,
        available: false,
        healthStatus: 'not_configured',
        healthScore: null,
        circuitState: null,
        sampleCount: 0,
        staticPriority: -1,
        lastSuccessAt: null,
        lastFailureAt: null,
        failureReason: 'provider_availability_probe_false',
        isPrimaryFor: [],
        isFallbackFor: ['daily_data:cn'],
        configDirectory: true,
      },
    ],
    cache: {
      enabled: true,
      fetchMode: 'remote_first',
      hits: 2,
      misses: 1,
      staleHits: 0,
      writes: 1,
      quality: 'active',
      note: null,
    },
  };
}

describe('DataProviderRuntimeStatusPanel', () => {
  beforeEach(() => {
    getDataProviderRuntimeStatus.mockReset();
  });

  it('loads and shows primary, fallback, cache, enhancer health, and as-of', async () => {
    getDataProviderRuntimeStatus.mockResolvedValue(okStatus());
    render(<DataProviderRuntimeStatusPanel />);

    expect(screen.getByTestId('data-runtime-loading')).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByTestId('data-runtime-status')).toBeInTheDocument();
    });

    expect(screen.getByTestId('data-runtime-as-of')).toHaveTextContent('2026-08-12');
    expect(screen.getByTestId('data-runtime-market-cn')).toHaveTextContent(/akshare/i);
    expect(screen.getByTestId('data-runtime-cache')).toHaveTextContent(/2/);
    expect(screen.getByTestId('data-runtime-provider-akshare')).toBeInTheDocument();
    expect(screen.getByTestId('data-runtime-provider-tushare')).toHaveTextContent(/未配置|Not configured/i);
    expect(screen.getByTestId('data-runtime-failure-tushare')).toBeInTheDocument();
    expect(getDataProviderRuntimeStatus).toHaveBeenCalledTimes(1);
  });

  it('shows partial/error state without inventing healthy markets', async () => {
    getDataProviderRuntimeStatus.mockResolvedValue({
      schemaVersion: 'data_provider_runtime_status_v1',
      asOf: '2026-08-12T00:00:00+00:00',
      partial: true,
      sourceState: 'not_initialized',
      errorCode: 'data_runtime_not_initialized',
      errorMessage: 'Data provider runtime is not initialized in this process.',
      markets: [],
      providers: [],
      cache: null,
    });
    render(<DataProviderRuntimeStatusPanel />);

    await waitFor(() => {
      expect(screen.getByTestId('data-runtime-partial')).toBeInTheDocument();
    });
    expect(screen.getByTestId('data-runtime-markets-empty')).toBeInTheDocument();
    expect(screen.getByTestId('data-runtime-cache-empty')).toBeInTheDocument();
    expect(screen.queryByTestId('data-runtime-provider-akshare')).not.toBeInTheDocument();
  });

  it('surfaces API errors and keeps empty status (not healthy)', async () => {
    getDataProviderRuntimeStatus.mockRejectedValue(new Error('network down'));
    render(<DataProviderRuntimeStatusPanel />);

    await waitFor(() => {
      expect(screen.queryByTestId('data-runtime-loading')).not.toBeInTheDocument();
    });
    // Fail closed: no healthy projection, no invented market/provider rows.
    expect(screen.queryByTestId('data-runtime-status')).not.toBeInTheDocument();
    expect(screen.queryByTestId('data-runtime-provider-akshare')).not.toBeInTheDocument();
    expect(screen.queryByText(/^健康$|^Healthy$/)).not.toBeInTheDocument();
  });

  it('refreshes on demand', async () => {
    getDataProviderRuntimeStatus.mockResolvedValue(okStatus());
    render(<DataProviderRuntimeStatusPanel />);

    await waitFor(() => {
      expect(getDataProviderRuntimeStatus).toHaveBeenCalledTimes(1);
    });
    fireEvent.click(screen.getByTestId('data-runtime-refresh'));
    await waitFor(() => {
      expect(getDataProviderRuntimeStatus).toHaveBeenCalledTimes(2);
    });
  });
});
