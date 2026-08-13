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
  /** Wire taxonomy category from the API envelope when present. */
  taxonomyCategory?: string;
  /** Wire taxonomy severity from the API envelope when present. */
  taxonomySeverity?: string;
}

/**
 * Structured, user-facing next step for a known error code or category.
 *
 * Retry actions never invent a handler: `actionKind: 'retry'` is only emitted
 * when the caller supplies `onRetry` to `resolveErrorRemediation`.
 */
export interface ErrorRemediation {
  actionLabel: string;
  /** Optional secondary guidance shown under the primary message. */
  hint?: string;
  /** In-app deep link or absolute docs URL. Not localized. */
  href?: string;
  /** Structural action kind for adopters and ApiErrorAlert. */
  actionKind?: 'retry' | 'settings' | 'login' | 'docs' | 'none';
  /** Taxonomy category used to select the remediation. */
  taxonomyCategory?: string;
  /** Taxonomy severity for tone / priority hints. */
  severity?: string;
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
  taxonomyCategory?: string;
  taxonomySeverity?: string;
};

export type ErrorEnvelope = {
  error: string;
  message?: string;
  params: Record<string, unknown>;
  details?: unknown;
  traceId?: string;
  category?: string;
  severity?: string;
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
