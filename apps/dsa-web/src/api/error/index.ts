// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
/**
 * Public API for structured API error parsing, catalog localization, and
 * actionable remediation. Import path remains `../api/error` / `./error`.
 */
export type {
  ApiErrorCategory,
  CreateParsedApiErrorOptions,
  ErrorRemediation,
  ParsedApiError,
} from './types';
export { isPermanentlyUnavailableResourceError } from './types';
export { resolveErrorRemediation } from './catalog';
export {
  formatErrorTemplate,
  formatParsedApiError,
  localizeParsedApiError,
} from './format';
export {
  attachParsedApiError,
  createApiError,
  createParsedApiError,
  extractErrorPayloadText,
  getParsedApiError,
  isApiRequestError,
  isAxiosApiError,
  isLocalConnectionFailure,
  isParsedApiError,
  parseApiError,
  toApiErrorMessage,
} from './parse';
