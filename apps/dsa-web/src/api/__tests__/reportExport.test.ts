// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { beforeEach, describe, expect, it, vi } from 'vitest';
import apiClient from '../index';
import { reportExportApi } from '../reportExport';

vi.mock('../index', () => ({
  default: {
    get: vi.fn(),
  },
}));

describe('reportExportApi.download', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('rehydrates JSON error blobs so callers get a parseable ApiRequestError', async () => {
    const blob = new Blob(
      [JSON.stringify({ detail: 'PDF dependency missing', code: 'export_pdf_dependency_missing' })],
      { type: 'application/json' },
    );
    // axios.isAxiosError checks payload.isAxiosError === true
    const error = {
      isAxiosError: true,
      name: 'AxiosError',
      message: 'Request failed',
      response: {
        status: 503,
        headers: { 'content-type': 'application/json' },
        data: blob,
      },
      code: 'ERR_BAD_RESPONSE',
      toJSON: () => ({}),
    };
    vi.mocked(apiClient.get).mockRejectedValue(error);

    await expect(reportExportApi.download(9, 'pdf')).rejects.toMatchObject({
      name: 'ApiRequestError',
    });
  });
});
