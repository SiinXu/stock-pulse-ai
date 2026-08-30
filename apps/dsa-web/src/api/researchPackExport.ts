// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import axios from 'axios';
import apiClient from './index';
import { createApiError, getParsedApiError } from './error';

import type { operations } from '../types/api.generated';

/** Query shape of the generated ``exportResearchPack`` operation. */
type OpenApiResearchPackQuery = NonNullable<operations['exportResearchPack']['parameters']['query']>;
/** Fails to compile if the OpenAPI ``format`` enum stops matching this module. */
type _AssertResearchPackFormat = ResearchPackExportFormat extends NonNullable<OpenApiResearchPackQuery['format']>
  ? NonNullable<OpenApiResearchPackQuery['format']> extends ResearchPackExportFormat
    ? true
    : never
  : never;
const _researchPackFormatAnchor: _AssertResearchPackFormat = true;
void _researchPackFormatAnchor;

export type ResearchPackExportFormat = 'zip' | 'json';
export type ResearchPackDownloadResult = {
  filename: string; truncated: boolean; contentType: string; byteLength: number; progressHeader: string;
};

function filenameFromDisposition(header: string | undefined, fallback: string): string {
  if (!header) return fallback;
  const utf8 = /filename\*=UTF-8''([^;]+)/i.exec(header);
  if (utf8?.[1]) { try { return decodeURIComponent(utf8[1]); } catch { /* fall */ } }
  const plain = /filename="?([^";]+)"?/i.exec(header);
  return plain?.[1]?.trim() || fallback;
}
function headerValue(headers: Record<string, unknown> | undefined, name: string): string {
  if (!headers) return '';
  const lower = name.toLowerCase();
  for (const [key, value] of Object.entries(headers)) {
    if (key.toLowerCase() === lower) return String(value ?? '');
  }
  return '';
}
function triggerBrowserDownload(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url; anchor.download = filename; anchor.rel = 'noopener';
  document.body.appendChild(anchor); anchor.click(); anchor.remove(); URL.revokeObjectURL(url);
}
async function rethrowExportBlobError(error: unknown): Promise<never> {
  if (axios.isAxiosError(error) && error.response?.data instanceof Blob) {
    const contentType = String(error.response.headers?.['content-type'] ?? '');
    if (contentType.includes('json') || contentType.includes('text') || error.response.status >= 400) {
      try {
        const bodyText = await error.response.data.text();
        const data = bodyText ? JSON.parse(bodyText) as unknown : undefined;
        const hydrated = { ...error, response: { ...error.response, data } };
        throw createApiError(getParsedApiError(hydrated), { response: hydrated.response, code: error.code, cause: error });
      } catch (e) {
        if (e instanceof Error && e.name === 'ApiRequestError') throw e;
      }
    }
  }
  throw createApiError(getParsedApiError(error), { cause: error });
}

export const researchPackExportApi = {
  download: async (recordId: number | string, format: ResearchPackExportFormat = 'zip', options: { language?: 'en' | 'zh' } = {}): Promise<ResearchPackDownloadResult> => {
    try {
      const response = await apiClient.get<Blob>(`/api/v1/history/${encodeURIComponent(String(recordId))}/research-pack`, {
        params: { format, language: options.language ?? 'en' }, responseType: 'blob',
      });
      const contentType = String(response.headers?.['content-type'] ?? '');
      if (format === 'zip' && contentType.includes('application/json')) {
        const text = await response.data.text();
        let data: unknown; try { data = text ? JSON.parse(text) : undefined; } catch { data = { message: text }; }
        throw createApiError(getParsedApiError({ response: { status: 500, data, headers: response.headers } }));
      }
      const headers = response.headers as Record<string, unknown>;
      const filename = filenameFromDisposition(headerValue(headers, 'content-disposition'), `research-pack-${recordId}.${format === 'json' ? 'json' : 'zip'}`);
      const truncated = headerValue(headers, 'x-research-pack-truncated') === '1';
      const progressHeader = headerValue(headers, 'x-research-pack-progress');
      const byteLength = Number.parseInt(headerValue(headers, 'x-research-pack-bytes'), 10);
      triggerBrowserDownload(response.data, filename);
      return { filename, truncated, contentType, byteLength: Number.isFinite(byteLength) ? byteLength : response.data.size, progressHeader };
    } catch (error) {
      return rethrowExportBlobError(error);
    }
  },
};
