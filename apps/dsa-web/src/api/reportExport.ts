// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
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
      const fallback = `stockpulse-report-${recordId}.${format === 'pdf' ? 'pdf' : 'md'}`;
      const filename = filenameFromDisposition(
        response.headers?.['content-disposition'] as string | undefined,
        fallback,
      );
      triggerBrowserDownload(response.data, filename);
      return { filename };
    } catch (error) {
      throw createApiError(getParsedApiError(error), { cause: error });
    }
  },
};
