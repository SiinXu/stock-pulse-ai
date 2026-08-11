// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { beforeEach, describe, expect, it, vi } from 'vitest';
import apiClient from '../index';
import { reasoningTraceExportApi } from '../reasoningTraceExport';

vi.mock('../index', () => ({
  default: {
    get: vi.fn(),
  },
}));

describe('reasoningTraceExportApi', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    if (!URL.createObjectURL) {
      URL.createObjectURL = vi.fn(() => 'blob:test') as typeof URL.createObjectURL;
    }
    if (!URL.revokeObjectURL) {
      URL.revokeObjectURL = vi.fn() as typeof URL.revokeObjectURL;
    }
  });

  it('downloads a JSON blob and reports truncation from response headers', async () => {
    const blob = new Blob(['{"schema_version":"reasoning-trace-v1"}'], { type: 'application/json' });
    vi.mocked(apiClient.get).mockResolvedValue({
      data: blob,
      headers: {
        'content-type': 'application/json',
        'content-disposition': 'attachment; filename="reasoning-trace-42.json"',
        'x-reasoning-trace-truncated': '1',
      },
    });

    const result = await reasoningTraceExportApi.download(42, 'json');

    expect(apiClient.get).toHaveBeenCalledWith(
      '/api/v1/reasoning-trace/42',
      expect.objectContaining({
        params: { format: 'json', include_markdown: false },
        responseType: 'blob',
      }),
    );
    expect(result.filename).toBe('reasoning-trace-42.json');
    expect(result.truncated).toBe(true);
    expect(result.byteLength).toBe(blob.size);
  });

  it('rehydrates JSON error blobs into ApiRequestError with code', async () => {
    const axios = await import('axios');
    const errorBlob = new Blob(
      [JSON.stringify({ error: 'reasoning_trace_export_disabled', message: 'not enabled' })],
      { type: 'application/json' },
    );
    const axiosError = new axios.AxiosError('Request failed');
    axiosError.response = {
      status: 404,
      statusText: 'Not Found',
      headers: { 'content-type': 'application/json' },
      config: {} as never,
      data: errorBlob,
    };
    vi.mocked(apiClient.get).mockRejectedValue(axiosError);

    await expect(reasoningTraceExportApi.download(7, 'json')).rejects.toMatchObject({
      name: 'ApiRequestError',
    });
  });
});
