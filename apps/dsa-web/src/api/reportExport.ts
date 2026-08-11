// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import axios from 'axios';
import apiClient from './index';
import { createApiError, getParsedApiError } from './error';

export type ReportExportFormat = 'md' | 'pdf';

export type ReportExportCapabilities = {
  formats: {
    md: { available: boolean };
    pdf: { available: boolean; reason?: string | null };
  };
};

function filenameFromDisposition(header: string | undefined, fallback: string): string {
  if (!header) return fallback;
  const utf8 = /filename\*=UTF-8''([^;]+)/i.exec(header);
  if (utf8?.[1]) {
    try {
      return decodeURIComponent(utf8[1]);
    } catch {
      // fall through
    }
  }
  const plain = /filename="?([^";]+)"?/i.exec(header);
  return plain?.[1]?.trim() || fallback;
}

function triggerBrowserDownload(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  anchor.rel = 'noopener';
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

/** responseType:blob turns error bodies into Blobs; rehydrate JSON for ParsedApiError. */
async function rethrowExportBlobError(error: unknown): Promise<never> {
  if (axios.isAxiosError(error) && error.response?.data instanceof Blob) {
    const contentType = String(error.response.headers?.['content-type'] ?? '');
    const looksJson = contentType.includes('json') || contentType.includes('text');
    if (looksJson || error.response.status >= 400) {
      try {
        const bodyText = await error.response.data.text();
        const data = bodyText ? JSON.parse(bodyText) as unknown : undefined;
        const hydrated = {
          ...error,
          response: {
            ...error.response,
            data,
          },
        };
        throw createApiError(getParsedApiError(hydrated), {
          response: hydrated.response,
          code: error.code,
          cause: error,
        });
      } catch (parseOrApiError) {
        if (parseOrApiError instanceof Error && parseOrApiError.name === 'ApiRequestError') {
          throw parseOrApiError;
        }
        // Fall through when the body is not JSON.
      }
    }
  }
  throw createApiError(getParsedApiError(error), { cause: error });
}

export const reportExportApi = {
  getCapabilities: async (language: 'zh' | 'en' = 'en'): Promise<ReportExportCapabilities> => {
    try {
      const response = await apiClient.get<Record<string, unknown>>('/api/v1/history/export/capabilities', {
        params: { language },
      });
      const data = response.data as {
        formats?: {
          md?: { available?: boolean };
          pdf?: { available?: boolean; reason?: string | null };
        };
      };
      return {
        formats: {
          md: { available: data.formats?.md?.available !== false },
          pdf: {
            available: Boolean(data.formats?.pdf?.available),
            reason: data.formats?.pdf?.reason ?? null,
          },
        },
      };
    } catch (error) {
      throw createApiError(getParsedApiError(error), { cause: error });
    }
  },

  download: async (
    recordId: number | string,
    format: ReportExportFormat,
  ): Promise<{ filename: string }> => {
    try {
      const response = await apiClient.get<Blob>(`/api/v1/history/${encodeURIComponent(String(recordId))}/export`, {
        params: { format },
        responseType: 'blob',
      });
      // Guard against error JSON returned with 2xx + blob (should not happen; keep download safe).
      const contentType = String(response.headers?.['content-type'] ?? '');
      if (contentType.includes('json')) {
        const text = await response.data.text();
        let data: unknown;
        try {
          data = text ? JSON.parse(text) : undefined;
        } catch {
          data = { message: text };
        }
        throw createApiError(getParsedApiError({ response: { status: 500, data } }));
      }
      const fallback = `stockpulse-report-${recordId}.${format === 'pdf' ? 'pdf' : 'md'}`;
      const filename = filenameFromDisposition(
        response.headers?.['content-disposition'] as string | undefined,
        fallback,
      );
      triggerBrowserDownload(response.data, filename);
      return { filename };
    } catch (error) {
      throw await rethrowExportBlobError(error);
    }
  },
};
