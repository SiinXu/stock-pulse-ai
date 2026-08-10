// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

/**
 * API reason → user-actionable error mapping (issue #885 Phase 1).
 *
 * ## Purpose
 * Converge `code` / `details.reason` / envelope params into a single
 * `{ class, titleKey, messageKey, cta? }` contract so Settings, analysis,
 * run-now, notification tests, and security denials can share one renderer
 * in a later adoption phase. Analysis Workbench is the first adopter
 * (`ActionableApiErrorInline` + launch/batch paths); other surfaces may follow.
 *
 * ## Relationship to the error catalog
 * Reuses `ParsedApiError` from `apps/dsa-web/src/api/error.ts` as the sole
 * input type. Does **not** modify `STABLE_ERROR_TEXT` / `GENERIC_ERROR_TEXT`
 * (draft PR #793 may restructure that catalog; avoid concurrent edits).
 *
 * ## Contract
 * - **Input**: output of `getParsedApiError` / `parseApiError` /
 *   `createParsedApiError` (`ParsedApiError`).
 * - **Output**: {@link ActionableErrorMapping}.
 * - **Technical disclosure**: `technicalCode` and `technicalReason` always
 *   preserve the server code/reason when present so UI can show them under a
 *   collapsed “Technical details” section without replacing user copy.
 * - **i18n**: `titleKey` / `messageKey` reference **existing** resource keys
 *   only. Missing dedicated keys for some reasons are listed below; adoption
 *   may add them later (full en/zh + eight locale bundles).
 *
 * ## Known reason / code inventory (enumerated from backend + catalog)
 * Settings 409: `config_conflict`, `config_version_conflict`, `conflict`
 * Analysis / run-now busy: `duplicate_task`, `duplicate_market_review`,
 *   `scheduler_busy` (+ params/details reason `analysis_already_running`),
 *   `portfolio_busy`
 * LLM: `llm_not_configured`
 * Notification: `no_channels`, `notification_channel_test_failed`,
 *   `config_missing`, `config_invalid`, `send_failed`, plus classifier codes
 *   `timeout` / `network_error` / `unexpected_error` when used as test codes
 * Outbound policy (#876 class names): `local_only_mode_blocked`,
 *   `metadata_host_blocked`, `local_host_blocked`, `restricted_ip_blocked`,
 *   `private_ip_blocked`, `ssrf_blocked`, `private_dns_address`,
 *   `dns_resolution_failed`, `unexpected_dns_target`
 * Security / auth adjacent: `unauthorized`, `approval_auth_required`,
 *   `rate_limited`, `agent_disabled`, credential-ish password codes
 *
 * ## Missing i18n keys (do not invent here; leave for adoption phase)
 * - Dedicated outbound-policy user title/message (currently falls back to
 *   `api.error.GENERIC_ERROR_TEXT.upstream_network.*`)
 * - Dedicated LOCAL_ONLY_MODE title/message beyond
 *   `i18n.uiText.UI_TEXT.settings.outboundActivityModeOn` +
 *   `…outboundActivityModeHint`
 * - Dedicated keys for `notification_channel_test_failed` / `send_failed` /
 *   `config_missing` / `config_invalid` as STABLE_ERROR_TEXT entries
 *   (title currently reuses `settings.notificationTestFailure` + generic
 *   message for channel test failures)
 * - Dedicated #876 class badge labels (credential / capability / HITL)
 *
 * ## Fallback
 * Unknown code → `class: 'generic'`, generic http/unknown keys, technical
 * code retained on the mapping for disclosure.
 */

import type { ApiErrorCategory, ParsedApiError } from '../api/error';
import {
  APP_ROUTE_PATHS,
  SETTINGS_SECTION_IDS,
  SETTINGS_VIEW_IDS,
  buildSettingsHref,
} from '../routing/routes';

/** UX failure classes aligned with #885 and #876 taxonomies. */
export type ActionableErrorClass =
  | 'config_conflict'
  | 'busy'
  | 'llm_not_configured'
  | 'outbound_policy'
  | 'local_only_mode'
  | 'credential'
  | 'network'
  | 'capability'
  | 'hitl_pending'
  | 'rate_quota'
  | 'notification'
  | 'auth'
  | 'validation'
  | 'not_found'
  | 'generic';

/**
 * CTA kinds are structural hints for adopters; `target` is a route path or
 * settings deep-link string when navigation is required.
 */
export type ActionableErrorCtaKind =
  | 'navigate'
  | 'reload'
  | 'retry';

export interface ActionableErrorCta {
  kind: ActionableErrorCtaKind;
  /** Route path, settings query, or other adopter-resolved target. */
  target?: string;
}

export interface ActionableErrorMapping {
  class: ActionableErrorClass;
  /** Existing i18n resource key for the title. */
  titleKey: string;
  /** Existing i18n resource key for the body message. */
  messageKey: string;
  /** Server envelope `error` / `code` when present. */
  technicalCode?: string;
  /** `details.reason` / `params.reason` / outbound reason token when present. */
  technicalReason?: string;
  cta?: ActionableErrorCta;
}

/** Stable i18n key prefixes already present in locale bundles. */
const STABLE = 'api.error.STABLE_ERROR_TEXT' as const;
const GENERIC = 'api.error.GENERIC_ERROR_TEXT' as const;
const UI = 'i18n.uiText.UI_TEXT' as const;

function stableKeys(code: string): Pick<ActionableErrorMapping, 'titleKey' | 'messageKey'> {
  return {
    titleKey: `${STABLE}.${code}.title`,
    messageKey: `${STABLE}.${code}.message`,
  };
}

function genericKeys(category: string): Pick<ActionableErrorMapping, 'titleKey' | 'messageKey'> {
  return {
    titleKey: `${GENERIC}.${category}.title`,
    messageKey: `${GENERIC}.${category}.message`,
  };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null;
}

function pickTrimmedString(...values: unknown[]): string | undefined {
  for (const value of values) {
    if (typeof value === 'string') {
      const trimmed = value.trim();
      if (trimmed) return trimmed;
    }
  }
  return undefined;
}

/**
 * Resolve the most specific reason token from ParsedApiError fields.
 * Backend may place reason on `details.reason`, top-level params (e.g.
 * scheduler run-now), or only in diagnostic text for OutboundPolicyError.
 */
export function extractApiErrorReason(error: ParsedApiError): string | undefined {
  const fromDetails = (() => {
    if (!isRecord(error.details)) {
      return pickTrimmedString(error.details);
    }
    return pickTrimmedString(error.details.reason, error.details.blocked_error_reason);
  })();

  const fromParams = error.params
    ? pickTrimmedString(error.params.reason, error.params.blocked_error_reason)
    : undefined;

  if (fromDetails) return fromDetails;
  if (fromParams) return fromParams;

  const haystack = [error.rawMessage, error.message, error.title]
    .filter((part): part is string => typeof part === 'string' && part.length > 0)
    .join(' | ');

  for (const token of KNOWN_OUTBOUND_REASONS) {
    if (haystack.includes(token)) return token;
  }
  if (/LOCAL_ONLY_MODE/i.test(haystack)) return 'local_only_mode_blocked';

  return undefined;
}

/** Outbound policy reason tokens from `src/security/outbound_policy.py`. */
export const KNOWN_OUTBOUND_REASONS = [
  'local_only_mode_blocked',
  'metadata_host_blocked',
  'local_host_blocked',
  'restricted_ip_blocked',
  'private_ip_blocked',
  'ssrf_blocked',
  'private_dns_address',
  'dns_resolution_failed',
  'unexpected_dns_target',
] as const;

export type KnownOutboundReason = (typeof KNOWN_OUTBOUND_REASONS)[number];

const OUTBOUND_REASON_SET = new Set<string>(KNOWN_OUTBOUND_REASONS);

/** Codes that mean “another job is already running”. */
const BUSY_CODES = new Set([
  'duplicate_task',
  'duplicate_market_review',
  'scheduler_busy',
  'portfolio_busy',
]);

const CONFIG_CONFLICT_CODES = new Set([
  'config_conflict',
  'config_version_conflict',
  'conflict',
  'idempotency_conflict',
]);

const CREDENTIAL_CODES = new Set([
  'password_required',
  'current_required',
  'password_mismatch',
  'password_already_set',
  'invalid_password',
  'not_changeable',
]);

const AUTH_CODES = new Set([
  'unauthorized',
  'auth_disabled',
  'security_audit_auth_required',
]);

const VALIDATION_CODES = new Set([
  'validation_error',
  'invalid_params',
  'validation_failed',
  'invalid_import_file',
  'unsupported_alert_type',
  'operation_id_mismatch',
]);

const NOTIFICATION_TEST_CODES = new Set([
  'no_channels',
  'notification_channel_test_failed',
  'config_missing',
  'config_invalid',
  'send_failed',
]);

const NETWORKISH_TEST_CODES = new Set([
  'timeout',
  'network_error',
  'dns_error',
  'connection_refused',
  'tls_error',
]);

const RATE_QUOTA_CODES = new Set([
  'rate_limited',
  'quota_exceeded',
  'insufficient_balance',
  'rate_limit',
]);

const CAPABILITY_CODES = new Set([
  'agent_disabled',
  'alphasift_disabled',
  'alphasift_unavailable',
  'capability_unsupported',
  'model_tool_incompatible',
  'invalid_tool_call',
]);

/**
 * Map a parsed API error into a stable actionable mapping.
 * Pure function; no i18n runtime lookup — callers resolve keys.
 */
export function mapApiErrorToActionable(error: ParsedApiError): ActionableErrorMapping {
  const code = pickTrimmedString(error.code);
  const reason = extractApiErrorReason(error);
  const technical: Pick<ActionableErrorMapping, 'technicalCode' | 'technicalReason'> = {
    technicalCode: code,
    technicalReason: reason,
  };

  // --- LOCAL_ONLY_MODE (subset of outbound, more specific) ---
  if (
    reason === 'local_only_mode_blocked'
    || code === 'local_only_mode_blocked'
    || (reason && /local_only_mode/i.test(reason))
  ) {
    return {
      class: 'local_only_mode',
      titleKey: `${UI}.settings.outboundActivityModeOn`,
      messageKey: `${UI}.settings.outboundActivityModeHint`,
      cta: { kind: 'navigate', target: APP_ROUTE_PATHS.settings },
      ...technical,
    };
  }

  // --- Outbound policy denials (#876: outbound_policy) ---
  if (
    (reason && OUTBOUND_REASON_SET.has(reason))
    || (code && OUTBOUND_REASON_SET.has(code))
    || code === 'ssrf_blocked'
    || code === 'request_blocked'
    || code === 'provider_blocked'
  ) {
    return {
      class: 'outbound_policy',
      ...genericKeys('upstream_network'),
      cta: { kind: 'navigate', target: APP_ROUTE_PATHS.settings },
      ...technical,
    };
  }

  // --- Settings / config 409 conflicts ---
  if (code && CONFIG_CONFLICT_CODES.has(code)) {
    const keys = code === 'conflict' || code === 'idempotency_conflict'
      ? stableKeys(code === 'idempotency_conflict' ? 'idempotency_conflict' : 'conflict')
      : stableKeys(code === 'config_version_conflict' ? 'config_version_conflict' : 'config_conflict');
    return {
      class: 'config_conflict',
      ...keys,
      cta: { kind: 'reload', target: 'page' },
      ...technical,
    };
  }

  // --- Analysis / run-now / portfolio busy ---
  if (
    (code && BUSY_CODES.has(code))
    || reason === 'analysis_already_running'
  ) {
    const busyCode = code && BUSY_CODES.has(code)
      ? code
      : 'scheduler_busy';
    const keys = stableKeys(
      busyCode === 'duplicate_task'
        || busyCode === 'duplicate_market_review'
        || busyCode === 'scheduler_busy'
        || busyCode === 'portfolio_busy'
        ? busyCode
        : 'scheduler_busy',
    );
    return {
      class: 'busy',
      ...keys,
      cta: { kind: 'retry' },
      ...technical,
    };
  }

  // --- LLM not configured ---
  if (code === 'llm_not_configured' || error.category === 'llm_not_configured') {
    return {
      class: 'llm_not_configured',
      ...stableKeys('llm_not_configured'),
      // Deep-link into Model Sources so operators land on the fix surface.
      cta: {
        kind: 'navigate',
        target: buildSettingsHref({
          section: SETTINGS_SECTION_IDS.aiModels,
          view: SETTINGS_VIEW_IDS.aiModels.connections,
        }),
      },
      ...technical,
    };
  }

  // --- Notification channel / test failures ---
  if (code && NOTIFICATION_TEST_CODES.has(code)) {
    if (code === 'no_channels') {
      return {
        class: 'notification',
        ...stableKeys('no_channels'),
        cta: { kind: 'navigate', target: APP_ROUTE_PATHS.settings },
        ...technical,
      };
    }
    // Missing dedicated STABLE keys for notification_channel_test_failed etc.
    return {
      class: 'notification',
      titleKey: `${UI}.settings.notificationTestFailure`,
      messageKey: genericKeys('http_error').messageKey,
      cta: { kind: 'navigate', target: APP_ROUTE_PATHS.settings },
      ...technical,
    };
  }

  // --- HITL / approvals (#876) ---
  if (code === 'approval_auth_required') {
    return {
      class: 'hitl_pending',
      ...stableKeys('approval_auth_required'),
      cta: { kind: 'navigate', target: APP_ROUTE_PATHS.approvals },
      ...technical,
    };
  }

  // --- Rate / quota (#876) ---
  if (code && RATE_QUOTA_CODES.has(code)) {
    const keys = code === 'rate_limited'
      ? stableKeys('rate_limited')
      : genericKeys('http_error');
    return {
      class: 'rate_quota',
      ...keys,
      cta: { kind: 'retry' },
      ...technical,
    };
  }

  // --- Credential (#876) ---
  if (code && CREDENTIAL_CODES.has(code)) {
    return {
      class: 'credential',
      ...stableKeys(code),
      cta: { kind: 'retry' },
      ...technical,
    };
  }

  // --- Auth session ---
  if (code && AUTH_CODES.has(code)) {
    return {
      class: 'auth',
      ...stableKeys(code),
      cta: code === 'unauthorized'
        ? { kind: 'navigate', target: APP_ROUTE_PATHS.login }
        : { kind: 'navigate', target: APP_ROUTE_PATHS.settings },
      ...technical,
    };
  }

  // --- Capability / feature gates (#876) ---
  if (
    (code && CAPABILITY_CODES.has(code))
    || error.category === 'agent_disabled'
    || error.category === 'model_tool_incompatible'
    || error.category === 'invalid_tool_call'
  ) {
    if (code === 'agent_disabled' || error.category === 'agent_disabled') {
      return {
        class: 'capability',
        ...stableKeys('agent_disabled'),
        cta: { kind: 'navigate', target: APP_ROUTE_PATHS.settings },
        ...technical,
      };
    }
    if (code === 'alphasift_disabled' || code === 'alphasift_unavailable') {
      return {
        class: 'capability',
        ...stableKeys(code),
        cta: { kind: 'navigate', target: APP_ROUTE_PATHS.settings },
        ...technical,
      };
    }
    return {
      class: 'capability',
      ...genericKeys(
        error.category === 'model_tool_incompatible'
          ? 'model_tool_incompatible'
          : error.category === 'invalid_tool_call'
            ? 'invalid_tool_call'
            : 'http_error',
      ),
      cta: { kind: 'navigate', target: APP_ROUTE_PATHS.settings },
      ...technical,
    };
  }

  // --- Validation ---
  if (code && VALIDATION_CODES.has(code)) {
    return {
      class: 'validation',
      ...stableKeys(code),
      cta: { kind: 'retry' },
      ...technical,
    };
  }

  // --- Not found ---
  if (code === 'not_found' || error.status === 404) {
    return {
      class: 'not_found',
      ...stableKeys('not_found'),
      ...technical,
    };
  }

  // --- Network / timeout categories from parser heuristics ---
  if (
    (code && NETWORKISH_TEST_CODES.has(code))
    || error.category === 'upstream_timeout'
    || error.category === 'upstream_network'
    || error.category === 'local_connection_failed'
  ) {
    const category =
      error.category === 'upstream_timeout'
      || error.category === 'upstream_network'
      || error.category === 'local_connection_failed'
        ? error.category
        : code === 'timeout'
          ? 'upstream_timeout'
          : 'upstream_network';
    return {
      class: 'network',
      ...genericKeys(category),
      cta: { kind: 'retry' },
      ...technical,
    };
  }

  if (error.category === 'upstream_llm_400') {
    return {
      class: 'credential',
      ...genericKeys('upstream_llm_400'),
      cta: { kind: 'navigate', target: APP_ROUTE_PATHS.settings },
      ...technical,
    };
  }

  // --- Known stable catalog codes not covered above: keep catalog keys ---
  if (code && KNOWN_STABLE_CODES.has(code)) {
    return {
      class: 'generic',
      ...stableKeys(code),
      ...technical,
    };
  }

  // --- Fallback: preserve technical code, generic class ---
  if (error.category === 'http_error') {
    return {
      class: 'generic',
      ...genericKeys('http_error'),
      ...technical,
    };
  }

  return {
    class: 'generic',
    ...genericKeys('unknown'),
    ...technical,
  };
}

/**
 * Codes present in `STABLE_ERROR_TEXT` that this mapper does not give a
 * specialized class. Still returns stable title/message keys.
 * Keep in sync with apps/dsa-web/src/api/error.ts STABLE_ERROR_TEXT keys
 * that lack a dedicated ActionableErrorClass branch above.
 */
export const KNOWN_STABLE_CODES = new Set([
  'unauthorized',
  'approval_auth_required',
  'auth_disabled',
  'security_audit_auth_required',
  'security_audit_unavailable',
  'password_required',
  'current_required',
  'password_mismatch',
  'password_already_set',
  'invalid_password',
  'not_changeable',
  'rate_limited',
  'agent_disabled',
  'agent_chat_failed',
  'agent_research_failed',
  'agent_stream_failed',
  'agent_stream_timeout',
  'validation_error',
  'invalid_params',
  'not_found',
  'duplicate_task',
  'duplicate_market_review',
  'config_conflict',
  'config_version_conflict',
  'rollback_unavailable',
  'validation_failed',
  'scheduler_busy',
  'env_backup_access_denied',
  'invalid_import_file',
  'no_channels',
  'conflict',
  'unsupported_alert_type',
  'portfolio_oversell',
  'portfolio_busy',
  'idempotency_conflict',
  'operation_id_mismatch',
  'alphasift_disabled',
  'alphasift_unavailable',
  'alphasift_screen_task_not_found',
  'alphasift_screen_failed',
  'internal_error',
  'analysis_failed',
  'api_response_validation_failed',
  'llm_not_configured',
  'share_image_content_too_large',
  'share_image_unavailable',
]);

/** Exhaustive list of ActionableErrorClass values for type-completeness tests. */
export const ACTIONABLE_ERROR_CLASSES: readonly ActionableErrorClass[] = [
  'config_conflict',
  'busy',
  'llm_not_configured',
  'outbound_policy',
  'local_only_mode',
  'credential',
  'network',
  'capability',
  'hitl_pending',
  'rate_quota',
  'notification',
  'auth',
  'validation',
  'not_found',
  'generic',
] as const;

const STABLE_TITLE_KEY_RE = /^api\.error\.STABLE_ERROR_TEXT\.([^.]+)\.title$/;
const GENERIC_TITLE_KEY_RE = /^api\.error\.GENERIC_ERROR_TEXT\.([^.]+)\.title$/;
const UI_TEXT_KEY_RE = /^i18n\.uiText\.UI_TEXT\.(.+)$/;

/**
 * Align a ParsedApiError with the catalog code/category the mapper selected so
 * adopters can call `localizeParsedApiError` without inventing a second catalog.
 * UI_TEXT-backed mappings leave code/category unchanged (callers resolve via t()).
 */
export function alignParsedApiErrorWithMapping(
  error: ParsedApiError,
  mapping: ActionableErrorMapping = mapApiErrorToActionable(error),
): ParsedApiError {
  const stableMatch = mapping.titleKey.match(STABLE_TITLE_KEY_RE);
  if (stableMatch) {
    const alignedCode = stableMatch[1];
    if (alignedCode && alignedCode !== error.code) {
      return { ...error, code: alignedCode };
    }
    if (!error.code && alignedCode) {
      return { ...error, code: alignedCode };
    }
    return error;
  }

  const genericMatch = mapping.titleKey.match(GENERIC_TITLE_KEY_RE);
  if (genericMatch) {
    const category = genericMatch[1] as ApiErrorCategory;
    if (category && category !== error.category) {
      return { ...error, category };
    }
  }

  return error;
}

/** True when titleKey/messageKey come from `UI_TEXT` rather than the error catalog. */
export function isUiTextActionableKey(resourceKey: string): boolean {
  return UI_TEXT_KEY_RE.test(resourceKey);
}

/**
 * Strip the `i18n.uiText.UI_TEXT.` prefix to a short `useUiLanguage().t()` key.
 * Returns null when the resource key is not a UI_TEXT path.
 */
export function toUiTextKey(resourceKey: string): string | null {
  const match = resourceKey.match(UI_TEXT_KEY_RE);
  return match?.[1] ?? null;
}

/** Classes that should block duplicate analysis submission while the alert is visible. */
export function isBusyActionableErrorClass(errorClass: ActionableErrorClass): boolean {
  return errorClass === 'busy' || errorClass === 'config_conflict';
}

/** True when a parsed error maps to a busy/conflict class that should block re-submit. */
export function isBusyParsedApiError(error: ParsedApiError | null | undefined): boolean {
  return Boolean(error && isBusyActionableErrorClass(mapApiErrorToActionable(error).class));
}
