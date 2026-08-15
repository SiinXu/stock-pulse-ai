// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { beforeEach, describe, expect, it, vi } from 'vitest';
import apiClient from '../index';
import { capabilitiesApi } from '../capabilities';
import { getParsedApiError } from '../error';

vi.mock('../index', () => ({ default: { get: vi.fn() } }));

const mockGet = vi.mocked(apiClient.get);

function response() {
  return {
    schema_version: 'capability-inventory/v1' as const,
    partial: false,
    sources: [{
      source: 'tool' as const,
      state: 'ok' as const,
      generation: 'tool-1',
      as_of: '2026-08-13T00:00:00Z',
    }],
    items: [{
      id: 'tool:market.quote',
      domain: 'tool' as const,
      type: 'agent_tool' as const,
      owner: 'agent-tools',
      provider: 'core',
      version: '1',
      source_generation: 'tool-1',
      as_of: '2026-08-13T00:00:00Z',
      registered: true,
      executable: true,
      display_name: 'Market quote',
    }],
    total: 1,
    executable_count: 1,
    non_executable_count: 0,
    unknown_executable_count: 0,
  };
}

describe('capabilitiesApi.list', () => {
  beforeEach(() => mockGet.mockReset());

  it('loads the read-only runtime inventory and preserves valid payloads', async () => {
    const payload = { ...response(), future_field: 'preserved' };
    mockGet.mockResolvedValue({ data: payload });

    const result = await capabilitiesApi.list();

    expect(mockGet).toHaveBeenCalledWith('/api/v1/capabilities');
    expect(result).toBe(payload);
    expect(result.items?.[0].id).toBe('tool:market.quote');
  });

  it('rejects response schema drift through the shared parsed error model', async () => {
    mockGet.mockResolvedValue({ data: { ...response(), total: -1 } });

    await expect(capabilitiesApi.list()).rejects.toSatisfy((error: unknown) => {
      const parsed = getParsedApiError(error);
      expect(parsed.code).toBe('api_response_validation_failed');
      expect(parsed.params).toMatchObject({ label: 'CapabilityListResponse' });
      return true;
    });
  });
});
