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

describe('reportExportApi', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  const fullCapabilities = {
    formats: {
      md: {
        available: true,
        status: 'ready',
        media_type: 'text/markdown',
        dependency_installed: true,
      },
      html: {
        available: true,
        status: 'ready',
        media_type: 'text/html',
        dependency_installed: true,
      },
      pdf: {
        available: false,
        status: 'dependency_missing',
        media_type: 'application/pdf',
        dependency_installed: false,
        dependency: 'weasyprint',
      },
    },
    requested_language: 'en',
    supported_query_formats: ['md', 'html', 'pdf'],
    office_formats_status: 'html_only',
    chart_handling: 'markdown_images_omitted_without_destinations',
    pdf_limits: {
      max_input_bytes: 1_000_000,
      max_pages: 50,
      max_table_rows: 500,
      max_table_columns: 20,
      max_output_bytes: 5_000_000,
      max_render_seconds: 30,
      max_concurrency: 1,
    },
  };

  it('maps html capability and download format onto the history export API', async () => {
    vi.mocked(apiClient.get).mockResolvedValueOnce({
      data: fullCapabilities,
    });

    const caps = await reportExportApi.getCapabilities('en');
    expect(caps.formats.html.available).toBe(true);
    expect(caps.formats.pdf.available).toBe(false);

    const createObjectURL = vi.fn(() => 'blob:html-export');
    const revokeObjectURL = vi.fn();
    Object.defineProperty(URL, 'createObjectURL', { configurable: true, value: createObjectURL });
    Object.defineProperty(URL, 'revokeObjectURL', { configurable: true, value: revokeObjectURL });
    const click = vi.fn();
    const anchor = {
      href: '',
      download: '',
      rel: '',
      click,
      remove: vi.fn(),
    } as unknown as HTMLAnchorElement;
    vi.spyOn(document, 'createElement').mockReturnValue(anchor);
    vi.spyOn(document.body, 'appendChild').mockImplementation((node) => node);

    vi.mocked(apiClient.get).mockResolvedValueOnce({
      data: new Blob(['<!DOCTYPE html><html></html>'], { type: 'text/html' }),
      headers: {
        'content-type': 'text/html; charset=utf-8',
        'content-disposition': 'attachment; filename="stockpulse-report-3.html"',
      },
    });

    await expect(reportExportApi.download(3, 'html')).resolves.toEqual({
      filename: 'stockpulse-report-3.html',
    });
    expect(apiClient.get).toHaveBeenLastCalledWith(
      '/api/v1/history/3/export',
      expect.objectContaining({ params: { format: 'html' }, responseType: 'blob' }),
    );
    expect(anchor.download).toBe('stockpulse-report-3.html');
    expect(click).toHaveBeenCalled();
  });

  it('surfaces capability shape mismatches through ParsedApiError', async () => {
    vi.mocked(apiClient.get).mockResolvedValueOnce({
      data: {
        formats: {
          md: { available: true },
        },
      },
    });
    await expect(reportExportApi.getCapabilities('en')).rejects.toMatchObject({
      name: 'ApiRequestError',
    });
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
