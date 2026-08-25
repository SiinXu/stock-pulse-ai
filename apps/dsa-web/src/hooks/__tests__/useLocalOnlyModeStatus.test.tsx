// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { outboundActivityApi } from '../../api/outboundActivity';
import type { LocalOnlyModeStatus } from '../../types/outboundActivity';
import { useLocalOnlyModeStatus } from '../useLocalOnlyModeStatus';

vi.mock('../../api/outboundActivity', () => ({
  outboundActivityApi: {
    getLocalOnlyStatus: vi.fn(),
  },
}));

const getLocalOnlyStatus = vi.mocked(outboundActivityApi.getLocalOnlyStatus);

const STATUS: LocalOnlyModeStatus = {
  enabled: false,
  envKey: 'LOCAL_ONLY_MODE',
  policy: 'non_loopback_denied',
  allowedDestinationClasses: ['loopback'],
  blockedErrorReason: 'local_only_mode_blocked',
};

describe('useLocalOnlyModeStatus', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('starts unknown and becomes on only when enabled is true', async () => {
    getLocalOnlyStatus.mockResolvedValue({ ...STATUS, enabled: true });
    const { result } = renderHook(() => useLocalOnlyModeStatus());

    expect(result.current).toEqual({ status: 'unknown' });
    await waitFor(() => expect(result.current).toEqual({ status: 'on' }));
  });

  it('reports off when enabled is false', async () => {
    getLocalOnlyStatus.mockResolvedValue({ ...STATUS, enabled: false });
    const { result } = renderHook(() => useLocalOnlyModeStatus());

    await waitFor(() => expect(result.current).toEqual({ status: 'off' }));
  });

  it('stays unknown when the request fails so callers cannot claim protection', async () => {
    getLocalOnlyStatus.mockRejectedValue(new Error('timeout'));
    const { result } = renderHook(() => useLocalOnlyModeStatus());

    expect(result.current).toEqual({ status: 'unknown' });
    await waitFor(() => expect(getLocalOnlyStatus).toHaveBeenCalledTimes(1));
    expect(result.current).toEqual({ status: 'unknown' });
  });
});
