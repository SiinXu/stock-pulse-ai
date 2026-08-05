// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type { UiLanguage } from '../../i18n/uiText';

export type ApiErrorCategory =
  | 'agent_disabled'
  | 'missing_params'
  | 'llm_not_configured'
  | 'model_tool_incompatible'
  | 'invalid_tool_call'
  | 'portfolio_oversell'
  | 'portfolio_busy'
  | 'upstream_llm_400'
  | 'upstream_timeout'
  | 'upstream_network'
  | 'local_connection_failed'
  | 'http_error'
  | 'unknown';

export interface ParsedApiError {
  title: string;
  message: string;
  rawMessage: string;
  status?: number;
  category: ApiErrorCategory;
  code?: string;
  params?: Record<string, unknown>;
  details?: unknown;
  traceId?: string;
}

/** Structured, user-facing next step for a known error code or category. */
export interface ErrorRemediation {
  actionLabel: string;
  /** Optional secondary guidance shown under the primary message. */
  hint?: string;
  /** In-app deep link (for example Settings section). Not localized. */
  href?: string;
}

export type ResponseLike = {
  status?: number;
  data?: unknown;
  statusText?: string;
};

export type ErrorCarrier = {
  response?: ResponseLike;
  code?: string;
  message?: string;
  parsedError?: ParsedApiError;
  cause?: unknown;
};

export type CreateParsedApiErrorOptions = {
  title: string;
  message: string;
  rawMessage?: string;
  status?: number;
  category?: ApiErrorCategory;
  code?: string;
  params?: Record<string, unknown>;
  details?: unknown;
  traceId?: string;
};

export type ErrorEnvelope = {
  error: string;
  message?: string;
  params: Record<string, unknown>;
  details?: unknown;
  traceId?: string;
};

export type StableErrorText = Record<UiLanguage, { title: string; message: string }> & {
  category?: ApiErrorCategory;
};

export function isPermanentlyUnavailableResourceError(
  error: ParsedApiError | null,
): error is ParsedApiError {
  return Boolean(
    error
    && (
      error.status === 401
      || error.status === 403
      || error.status === 404
      || error.code === 'unauthorized'
      || error.code === 'forbidden'
      || error.code === 'not_found'
    )
  );
}
