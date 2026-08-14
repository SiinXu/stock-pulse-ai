// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import axios from 'axios';
import apiClient from './index';
import { createApiError, getParsedApiError } from './error';

export type EvidencePackFormat = 'zip' | 'json';
export type EvidencePackDownloadResult = {
  filename: string; truncated: boolean; contentType: string; byteLength: number;
};

function filenameFromDisposition(header: string | undefined, fallback: string): string {
  if (!header) return fallback;
  const utf8 = /filename\*=UTF-8''([^;]+)/i.exec(header);
  if (utf8?.[1]) { try { return decodeURIComponent(utf8[1]); } catch { /* fall through */ } }
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

export const evidencePackExportApi = {
  downloadEvidenceChain: async (recordId: number | string): Promise<EvidencePackDownloadResult> => {
    try {
      const response = await apiClient.get<Blob>(`/api/v1/history/${encodeURIComponent(String(recordId))}/evidence-chain`, { responseType: 'blob' });
      const contentType = String(response.headers?.['content-type'] ?? '');
      const filename = filenameFromDisposition(headerValue(response.headers as Record<string, unknown>, 'content-disposition'), `evidence-chain-${recordId}.json`);
      const truncatedHeader = headerValue(response.headers as Record<string, unknown>, 'x-evidence-chain-truncated');
      const truncated = truncatedHeader === '1' || truncatedHeader.toLowerCase() === 'true';
      triggerBrowserDownload(response.data, filename);
      return { filename, truncated, contentType, byteLength: response.data.size };
    } catch (error) { throw await rethrowExportBlobError(error); }
  },
  downloadAuditPackage: async (recordId: number | string, format: EvidencePackFormat = 'zip'): Promise<EvidencePackDownloadResult> => {
    try {
      const response = await apiClient.get<Blob>(`/api/v1/history/${encodeURIComponent(String(recordId))}/evidence-pack`, { params: { format }, responseType: 'blob' });
      const contentType = String(response.headers?.['content-type'] ?? '');
      const extension = format === 'json' ? 'json' : 'zip';
      const filename = filenameFromDisposition(headerValue(response.headers as Record<string, unknown>, 'content-disposition'), `audit-package-${recordId}.${extension}`);
      const truncatedHeader = headerValue(response.headers as Record<string, unknown>, 'x-audit-package-truncated');
      const truncated = truncatedHeader === '1' || truncatedHeader.toLowerCase() === 'true';
      triggerBrowserDownload(response.data, filename);
      return { filename, truncated, contentType, byteLength: response.data.size };
    } catch (error) { throw await rethrowExportBlobError(error); }
  },
};
