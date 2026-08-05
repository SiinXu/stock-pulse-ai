// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import axios from 'axios';
import type { UiLanguage } from '../../i18n/uiText';
import { STABLE_ERROR_TEXT } from './catalog';
import {
  buildMatchText,
  categorizeGenericHttpError,
  categorizeHeuristicError,
} from './categorize';
import { formatErrorTemplate, formatParsedApiError, localizeParsedApiError } from './format';
import { createParsedApiError } from './parseCore';
import type {
  ApiErrorCategory,
  CreateParsedApiErrorOptions,
  ErrorCarrier,
  ErrorEnvelope,
  ParsedApiError,
  ResponseLike,
} from './types';

export { createParsedApiError } from './parseCore';
export type { CreateParsedApiErrorOptions };

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null;
}

function pickString(...values: unknown[]): string | null {
  for (const value of values) {
    if (typeof value === 'string' && value.trim()) {
      return value.trim();
    }
  }
  return null;
}

function stringifyValue(value: unknown): string | null {
  if (value === null || value === undefined) {
    return null;
  }
  if (typeof value === 'string') {
    return value.trim() || null;
  }
  if (typeof value === 'number' || typeof value === 'boolean') {
    return String(value);
  }
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

function toErrorEnvelope(value: unknown): ErrorEnvelope | null {
  if (!isRecord(value)) {
    return null;
  }
  const nested = isRecord(value.detail) ? value.detail : null;
  const hasTopLevelError = typeof value.error === 'string' && Boolean(value.error.trim());
  const source = hasTopLevelError
    ? value
    : nested && typeof nested.error === 'string'
      ? nested
      : value;
  if (typeof source.error !== 'string' || !source.error.trim()) {
    return null;
  }
  const params = isRecord(source.params) ? { ...source.params } : {};
  const reserved = new Set(['error', 'code', 'message', 'params', 'details', 'detail', 'trace_id', 'traceId', 'type']);
  Object.entries(source).forEach(([key, entry]) => {
    if (!reserved.has(key) && params[key] === undefined) {
      params[key] = entry;
    }
  });
  const traceId = pickString(source.trace_id, source.traceId, value.trace_id, value.traceId) ?? undefined;
  return {
    error: source.error.trim(),
    message: pickString(source.message) ?? undefined,
    params,
    details: source.details !== undefined ? source.details : source.detail,
    traceId,
  };
}

function envelopeDiagnosticText(envelope: ErrorEnvelope): string {
  const parts = [
    envelope.message,
    stringifyValue(envelope.details),
    envelope.traceId ? `trace_id: ${envelope.traceId}` : null,
  ].filter((value): value is string => Boolean(value));
  return parts.join('\n') || envelope.error;
}

function getResponse(error: unknown): ResponseLike | undefined {
  if (!isRecord(error)) {
    return undefined;
  }
  const response = (error as ErrorCarrier).response;
  return response && typeof response === 'object' ? response : undefined;
}

function getErrorCode(error: unknown): string | undefined {
  return isRecord(error) && typeof (error as ErrorCarrier).code === 'string'
    ? (error as ErrorCarrier).code
    : undefined;
}

function getErrorMessage(error: unknown): string | null {
  if (typeof error === 'string') {
    return error.trim() || null;
  }
  if (error instanceof Error && error.message.trim()) {
    return error.message.trim();
  }
  if (isRecord(error) && typeof (error as ErrorCarrier).message === 'string') {
    const message = (error as ErrorCarrier).message?.trim();
    return message || null;
  }
  return null;
}

function getCauseMessage(error: unknown): string | null {
  if (!isRecord(error)) {
    return null;
  }
  return getErrorMessage((error as ErrorCarrier).cause);
}

function extractValidationDetail(detail: unknown): string | null {
  if (!Array.isArray(detail)) {
    return null;
  }
  const parts = detail
    .map((item) => {
      if (!isRecord(item)) {
        return stringifyValue(item);
      }
      const location = Array.isArray(item.loc)
        ? item.loc.map((segment) => String(segment)).join('.')
        : null;
      const message = pickString(item.msg, item.message, item.error);
      if (!location && !message) {
        return stringifyValue(item);
      }
      return [location, message].filter(Boolean).join(': ');
    })
    .filter((entry): entry is string => Boolean(entry));
  return parts.length > 0 ? parts.join('; ') : null;
}

function extractErrorCode(data: unknown): string | null {
  if (!isRecord(data)) {
    return null;
  }
  const detail = data.detail;
  if (isRecord(detail)) {
    return pickString(detail.error, detail.code, data.error, data.code);
  }
  return pickString(data.error, data.code);
}

export function extractErrorPayloadText(data: unknown): string | null {
  if (typeof data === 'string') {
    return data.trim() || null;
  }
  if (Array.isArray(data)) {
    return extractValidationDetail(data) ?? stringifyValue(data);
  }
  if (!isRecord(data)) {
    return stringifyValue(data);
  }
  const detail = data.detail;
  if (isRecord(detail)) {
    return (
      pickString(detail.message, detail.error)
      ?? extractValidationDetail(detail.detail)
      ?? stringifyValue(detail)
    );
  }
  return (
    pickString(
      detail,
      data.message,
      data.error,
      data.title,
      data.reason,
      data.description,
      data.msg,
    )
    ?? extractValidationDetail(detail)
    ?? stringifyValue(data)
  );
}

export function isParsedApiError(value: unknown): value is ParsedApiError {
  return isRecord(value)
    && typeof value.title === 'string'
    && typeof value.message === 'string'
    && typeof value.rawMessage === 'string'
    && typeof value.category === 'string';
}

export function isApiRequestError(
  value: unknown,
): value is Error & ErrorCarrier & { parsedError: ParsedApiError } {
  return value instanceof Error
    && isRecord(value)
    && isParsedApiError((value as ErrorCarrier).parsedError);
}

export function getParsedApiError(error: unknown, language: UiLanguage = 'zh'): ParsedApiError {
  if (isParsedApiError(error)) {
    return localizeParsedApiError(error, language);
  }
  if (isRecord(error) && isParsedApiError((error as ErrorCarrier).parsedError)) {
    return localizeParsedApiError((error as ErrorCarrier).parsedError as ParsedApiError, language);
  }
  return localizeParsedApiError(parseApiError(error), language);
}

export function createApiError(
  parsed: ParsedApiError,
  extra: { response?: ResponseLike; code?: string; cause?: unknown } = {},
): Error & ErrorCarrier & { status?: number; category: ApiErrorCategory; rawMessage: string } {
  const apiError = new Error(formatParsedApiError(parsed)) as Error & ErrorCarrier & {
    status?: number;
    category: ApiErrorCategory;
    rawMessage: string;
  };
  apiError.name = 'ApiRequestError';
  apiError.parsedError = parsed;
  apiError.response = extra.response;
  apiError.code = extra.code;
  apiError.status = parsed.status;
  apiError.category = parsed.category;
  apiError.rawMessage = parsed.rawMessage;
  if (extra.cause !== undefined) {
    apiError.cause = extra.cause;
  }
  return apiError;
}

export function attachParsedApiError(error: unknown): ParsedApiError {
  const parsed = parseApiError(error);
  if (isRecord(error)) {
    const carrier = error as ErrorCarrier;
    carrier.parsedError = parsed;
  }
  if (error instanceof Error) {
    error.name = 'ApiRequestError';
    error.message = formatParsedApiError(parsed);
  }
  return parsed;
}

export function isLocalConnectionFailure(error: unknown): boolean {
  return parseApiError(error).category === 'local_connection_failed';
}

export function parseApiError(error: unknown): ParsedApiError {
  const response = getResponse(error);
  const status = response?.status;
  const envelope = toErrorEnvelope(response?.data) ?? toErrorEnvelope(error);
  if (envelope) {
    const stable = STABLE_ERROR_TEXT[envelope.error];
    const localized = stable?.zh ?? { title: '请求失败', message: '请求未能完成，请稍后重试。' };
    return createParsedApiError({
      title: formatErrorTemplate(localized.title, envelope.params),
      message: formatErrorTemplate(localized.message, envelope.params),
      rawMessage: envelopeDiagnosticText(envelope),
      status,
      category: stable?.category ?? 'http_error',
      code: envelope.error,
      params: envelope.params,
      details: envelope.details,
      traceId: envelope.traceId,
    });
  }
  const payloadText = extractErrorPayloadText(response?.data);
  const errorCode = extractErrorCode(response?.data);
  const errorMessage = getErrorMessage(error);
  const causeMessage = getCauseMessage(error);
  const code = getErrorCode(error);
  const rawMessage = pickString(payloadText, response?.statusText, errorMessage, causeMessage, code)
    ?? '请求未成功完成，请稍后重试。';
  const matchText = buildMatchText([rawMessage, errorMessage, causeMessage, code, errorCode, response?.statusText]);

  const heuristic = categorizeHeuristicError({
    status,
    rawMessage,
    errorCode,
    transportCode: code,
    matchText,
    hasResponse: Boolean(response),
  });
  if (heuristic) {
    return heuristic;
  }
  return categorizeGenericHttpError({
    status,
    rawMessage,
    hasPayload: Boolean(payloadText),
  });
}

export function toApiErrorMessage(
  error: unknown,
  fallback = '请求未成功完成，请稍后重试。',
  language: UiLanguage = 'zh',
): string {
  const parsed = getParsedApiError(error, language);
  const message = formatParsedApiError(parsed);
  return message.trim() || fallback;
}

export function isAxiosApiError(error: unknown): boolean {
  return axios.isAxiosError(error);
}
