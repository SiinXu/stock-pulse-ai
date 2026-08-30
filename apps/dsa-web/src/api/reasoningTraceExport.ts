// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import axios from 'axios';
import apiClient from './index';
import { createApiError, getParsedApiError } from './error';

import type { operations } from '../types/api.generated';

/** Query shape of the generated ``exportReasoningTrace`` operation. */
type OpenApiReasoningTraceQuery = NonNullable<operations['exportReasoningTrace']['parameters']['query']>;
/** Fails to compile if the OpenAPI ``format`` enum stops matching this module. */
type _AssertReasoningTraceFormat = ReasoningTraceExportFormat extends NonNullable<OpenApiReasoningTraceQuery['format']>
  ? NonNullable<OpenApiReasoningTraceQuery['format']> extends ReasoningTraceExportFormat
    ? true
    : never
  : never;
const _reasoningTraceFormatAnchor: _AssertReasoningTraceFormat = true;
void _reasoningTraceFormatAnchor;

export type ReasoningTraceExportFormat = 'json' | 'markdown';

export type ReasoningTraceDownloadResult = {
  filename: string;
  truncated: boolean;
  contentType: string;
  byteLength: number;
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

function headerValue(headers: Record<string, unknown> | undefined, name: string): string {
  if (!headers) return '';
  const lower = name.toLowerCase();
  for (const [key, value] of Object.entries(headers)) {
    if (key.toLowerCase() === lower) {
      return String(value ?? '');
    }
  }
  return '';
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

/**
 * Download a redacted reasoning-trace package as a browser file.
 *
 * Uses blob streaming so large traces are not parsed into React state.
 * Truncation is reported via the backend `X-Reasoning-Trace-Truncated` header.
 */
export const reasoningTraceExportApi = {
  download: async (
    recordId: number | string,
    format: ReasoningTraceExportFormat = 'json',
    options: { includeMarkdown?: boolean } = {},
  ): Promise<ReasoningTraceDownloadResult> => {
    try {
      const response = await apiClient.get<Blob>(
        `/api/v1/reasoning-trace/${encodeURIComponent(String(recordId))}`,
        {
          params: {
            format,
            include_markdown: options.includeMarkdown === true,
          },
          responseType: 'blob',
        },
      );

      const contentType = String(response.headers?.['content-type'] ?? '');
      // Guard: some gateways may return error JSON with a misleading 2xx + blob.
      // Markdown is text/markdown; only treat application/json as an error envelope
      // when the client asked for markdown.
      if (format === 'markdown' && contentType.includes('application/json')) {
        const text = await response.data.text();
        let data: unknown;
        try {
          data = text ? JSON.parse(text) : undefined;
        } catch {
          data = { message: text };
        }
        throw createApiError(getParsedApiError({ response: { status: 500, data } }));
      }

      const extension = format === 'markdown' ? 'md' : 'json';
      const fallback = `reasoning-trace-${recordId}.${extension}`;
      const filename = filenameFromDisposition(
        headerValue(response.headers as Record<string, unknown> | undefined, 'content-disposition'),
        fallback,
      );
      const truncatedHeader = headerValue(
        response.headers as Record<string, unknown> | undefined,
        'x-reasoning-trace-truncated',
      );
      const truncated = truncatedHeader === '1' || truncatedHeader.toLowerCase() === 'true';

      triggerBrowserDownload(response.data, filename);
      return {
        filename,
        truncated,
        contentType,
        byteLength: response.data.size,
      };
    } catch (error) {
      throw await rethrowExportBlobError(error);
    }
  },
};
