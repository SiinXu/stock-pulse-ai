// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
/**
 * Web-side mirror of `api/v1/error_taxonomy.py`.
 * Integrates existing stable error codes with category, severity, and default action.
 */
import { APP_ROUTE_PATHS, buildSettingsHref } from '../../routing/routes';
import type { ApiErrorCategory, ParsedApiError } from './types';

export type TaxonomyCategory =
  | 'auth' | 'credential' | 'rate_quota' | 'provider_network' | 'timeout'
  | 'validation' | 'busy' | 'config_conflict' | 'capability' | 'notification'
  | 'not_found' | 'outbound_policy' | 'internal';

export type TaxonomySeverity = 'info' | 'warning' | 'error' | 'critical';
export type TaxonomyAction = 'retry' | 'settings' | 'login' | 'docs' | 'none';

export interface ErrorClassification {
  category: TaxonomyCategory;
  severity: TaxonomySeverity;
  defaultAction: TaxonomyAction;
  docsPath?: string;
  href?: string;
}

const SETTINGS_AI = buildSettingsHref({ section: 'ai_models', view: 'connections' });
const SETTINGS_AGENT = buildSettingsHref({ section: 'agent_behavior', view: 'execution' });
const SETTINGS_AUTH = buildSettingsHref({ section: 'system_security', view: 'security' });
const SETTINGS_NOTIFY = buildSettingsHref({ section: 'notifications', view: 'channels' });
const SETTINGS_DATA = buildSettingsHref({ section: 'data_sources', view: 'sources' });
const SETTINGS_OVERVIEW = buildSettingsHref({ section: 'overview', view: 'readiness' });

function entry(
  category: TaxonomyCategory,
  severity: TaxonomySeverity,
  defaultAction: TaxonomyAction,
  extras: Pick<ErrorClassification, 'docsPath' | 'href'> = {},
): ErrorClassification {
  return { category, severity, defaultAction, ...extras };
}

export const ERROR_CODE_TAXONOMY: Readonly<Record<string, ErrorClassification>> = {
  agent_chat_failed: entry('provider_network', 'error', 'retry'),
  agent_disabled: entry('capability', 'error', 'settings', { href: SETTINGS_AGENT }),
  agent_research_failed: entry('provider_network', 'error', 'retry'),
  agent_stream_failed: entry('provider_network', 'error', 'retry'),
  agent_stream_timeout: entry('timeout', 'warning', 'retry'),
  alphasift_adapter_unavailable: entry('capability', 'error', 'settings', { href: SETTINGS_DATA }),
  alphasift_disabled: entry('capability', 'error', 'settings', { href: SETTINGS_DATA }),
  alphasift_install_failed: entry('capability', 'error', 'settings', { href: SETTINGS_DATA }),
  alphasift_install_spec_missing: entry('capability', 'error', 'settings', { href: SETTINGS_DATA }),
  alphasift_install_spec_not_allowed: entry('capability', 'error', 'settings', { href: SETTINGS_DATA }),
  alphasift_screen_failed: entry('provider_network', 'error', 'retry'),
  alphasift_screen_task_not_found: entry('not_found', 'warning', 'retry'),
  alphasift_unavailable: entry('capability', 'error', 'settings', { href: SETTINGS_DATA }),
  analysis_batch_limit_exceeded: entry('validation', 'error', 'none'),
  analysis_failed: entry('internal', 'error', 'retry'),
  api_response_validation_failed: entry('validation', 'error', 'retry'),
  approval_auth_required: entry('auth', 'error', 'settings', { docsPath: 'docs/security-baseline.md', href: SETTINGS_AUTH }),
  auth_disabled: entry('auth', 'error', 'settings', { docsPath: 'docs/security-baseline.md', href: SETTINGS_AUTH }),
  capability_unsupported: entry('capability', 'error', 'docs', { docsPath: 'docs/beginner-client-setup.md' }),
  config_conflict: entry('config_conflict', 'warning', 'retry'),
  config_invalid: entry('notification', 'error', 'settings', { href: SETTINGS_NOTIFY }),
  config_missing: entry('notification', 'error', 'settings', { href: SETTINGS_NOTIFY }),
  config_version_conflict: entry('config_conflict', 'warning', 'retry'),
  conflict: entry('config_conflict', 'warning', 'retry'),
  connection_refused: entry('provider_network', 'error', 'retry'),
  current_required: entry('credential', 'error', 'retry'),
  dns_error: entry('provider_network', 'error', 'retry'),
  dns_resolution_failed: entry('outbound_policy', 'error', 'retry'),
  duplicate_market_review: entry('busy', 'warning', 'none'),
  duplicate_task: entry('busy', 'warning', 'none'),
  empty_stock_code: entry('validation', 'error', 'none'),
  env_backup_access_denied: entry('auth', 'error', 'settings', { href: SETTINGS_AUTH }),
  file_too_large: entry('validation', 'error', 'none'),
  idempotency_conflict: entry('config_conflict', 'warning', 'retry'),
  insufficient_balance: entry('rate_quota', 'error', 'docs', { docsPath: 'docs/LLM_CONFIG_GUIDE.md' }),
  internal_error: entry('internal', 'critical', 'retry'),
  invalid_import_file: entry('validation', 'error', 'none'),
  invalid_params: entry('validation', 'error', 'none'),
  invalid_password: entry('credential', 'error', 'login', { href: APP_ROUTE_PATHS.login }),
  invalid_stock_code: entry('validation', 'error', 'none'),
  invalid_stock_or_name: entry('validation', 'error', 'none'),
  invalid_tool_call: entry('capability', 'error', 'settings', { docsPath: 'docs/LLM_CONFIG_GUIDE.md', href: SETTINGS_AI }),
  llm_not_configured: entry('capability', 'error', 'settings', { docsPath: 'docs/LLM_CONFIG_GUIDE.md', href: SETTINGS_AI }),
  local_connection_failed: entry('provider_network', 'error', 'retry'),
  local_host_blocked: entry('outbound_policy', 'error', 'settings', { docsPath: 'docs/local-only-mode.md', href: SETTINGS_OVERVIEW }),
  local_only_mode_blocked: entry('outbound_policy', 'error', 'settings', { docsPath: 'docs/local-only-mode.md', href: SETTINGS_OVERVIEW }),
  metadata_host_blocked: entry('outbound_policy', 'error', 'settings', { docsPath: 'docs/local-only-mode.md', href: SETTINGS_OVERVIEW }),
  missing_import_text: entry('validation', 'error', 'none'),
  missing_stock_params: entry('validation', 'error', 'none'),
  missing_upload_file: entry('validation', 'error', 'none'),
  model_tool_incompatible: entry('capability', 'error', 'settings', { docsPath: 'docs/LLM_CONFIG_GUIDE.md', href: SETTINGS_AI }),
  network_error: entry('provider_network', 'error', 'retry'),
  no_channels: entry('notification', 'error', 'settings', { href: SETTINGS_NOTIFY }),
  not_changeable: entry('credential', 'warning', 'docs', { docsPath: 'docs/beginner-client-setup.md' }),
  not_found: entry('not_found', 'warning', 'none'),
  notification_channel_test_failed: entry('notification', 'error', 'settings', { href: SETTINGS_NOTIFY }),
  operation_id_mismatch: entry('validation', 'error', 'none'),
  password_already_set: entry('credential', 'warning', 'settings', { href: SETTINGS_AUTH }),
  password_mismatch: entry('credential', 'error', 'retry'),
  password_required: entry('credential', 'error', 'retry'),
  portfolio_busy: entry('busy', 'warning', 'retry'),
  portfolio_oversell: entry('validation', 'error', 'none'),
  private_dns_address: entry('outbound_policy', 'error', 'settings', { docsPath: 'docs/local-only-mode.md', href: SETTINGS_OVERVIEW }),
  private_ip_blocked: entry('outbound_policy', 'error', 'settings', { docsPath: 'docs/local-only-mode.md', href: SETTINGS_OVERVIEW }),
  provider_blocked: entry('outbound_policy', 'error', 'settings', { docsPath: 'docs/local-only-mode.md', href: SETTINGS_OVERVIEW }),
  provider_failure: entry('provider_network', 'error', 'retry'),
  quota_exceeded: entry('rate_quota', 'error', 'docs', { docsPath: 'docs/LLM_CONFIG_GUIDE.md' }),
  rate_limit: entry('rate_quota', 'warning', 'retry'),
  rate_limited: entry('rate_quota', 'warning', 'retry'),
  reasoning_trace_auth_required: entry('auth', 'error', 'settings', { docsPath: 'docs/security-baseline.md', href: SETTINGS_AUTH }),
  reasoning_trace_export_disabled: entry('capability', 'warning', 'settings', { href: SETTINGS_AGENT }),
  request_blocked: entry('outbound_policy', 'error', 'settings', { docsPath: 'docs/security-baseline.md', href: SETTINGS_OVERVIEW }),
  restricted_ip_blocked: entry('outbound_policy', 'error', 'settings', { docsPath: 'docs/local-only-mode.md', href: SETTINGS_OVERVIEW }),
  rollback_unavailable: entry('capability', 'warning', 'none'),
  scheduler_busy: entry('busy', 'warning', 'retry'),
  security_audit_auth_required: entry('auth', 'error', 'settings', { docsPath: 'docs/security-baseline.md', href: SETTINGS_AUTH }),
  security_audit_unavailable: entry('not_found', 'error', 'retry'),
  send_failed: entry('notification', 'error', 'retry'),
  share_image_content_too_large: entry('capability', 'warning', 'settings', { href: SETTINGS_OVERVIEW }),
  share_image_unavailable: entry('capability', 'warning', 'docs', { docsPath: 'docs/beginner-client-setup.md' }),
  ssrf_blocked: entry('outbound_policy', 'error', 'settings', { docsPath: 'docs/security-baseline.md', href: SETTINGS_OVERVIEW }),
  sync_mode_batch_unsupported: entry('validation', 'error', 'none'),
  timeout: entry('timeout', 'warning', 'retry'),
  tls_error: entry('provider_network', 'error', 'retry'),
  unauthorized: entry('auth', 'error', 'login', { href: APP_ROUTE_PATHS.login }),
  unexpected_dns_target: entry('outbound_policy', 'error', 'settings', { docsPath: 'docs/security-baseline.md', href: SETTINGS_OVERVIEW }),
  unsupported_alert_type: entry('validation', 'error', 'none'),
  unsupported_content_type: entry('validation', 'error', 'none'),
  unsupported_type: entry('validation', 'error', 'none'),
  upstream_network: entry('provider_network', 'error', 'retry'),
  upstream_timeout: entry('timeout', 'warning', 'retry'),
  validation_error: entry('validation', 'error', 'none'),
  validation_failed: entry('validation', 'error', 'none'),
};

export const UNKNOWN_ERROR_CLASSIFICATION: ErrorClassification = entry('internal', 'error', 'retry');

const CATEGORY_TAXONOMY: Partial<Record<ApiErrorCategory, ErrorClassification>> = {
  agent_disabled: entry('capability', 'error', 'settings', { href: SETTINGS_AGENT }),
  missing_params: entry('validation', 'error', 'none'),
  llm_not_configured: entry('capability', 'error', 'settings', { href: SETTINGS_AI, docsPath: 'docs/LLM_CONFIG_GUIDE.md' }),
  model_tool_incompatible: entry('capability', 'error', 'settings', { href: SETTINGS_AI, docsPath: 'docs/LLM_CONFIG_GUIDE.md' }),
  invalid_tool_call: entry('capability', 'error', 'settings', { href: SETTINGS_AI, docsPath: 'docs/LLM_CONFIG_GUIDE.md' }),
  portfolio_oversell: entry('validation', 'error', 'none'),
  portfolio_busy: entry('busy', 'warning', 'retry'),
  upstream_llm_400: entry('capability', 'error', 'settings', { href: SETTINGS_AI, docsPath: 'docs/LLM_CONFIG_GUIDE.md' }),
  upstream_timeout: entry('timeout', 'warning', 'retry'),
  upstream_network: entry('provider_network', 'error', 'retry'),
  local_connection_failed: entry('provider_network', 'error', 'retry'),
  http_error: entry('internal', 'error', 'retry'),
  unknown: entry('internal', 'error', 'retry'),
};

const TAXONOMY_CATEGORIES = new Set<string>([
  'auth', 'credential', 'rate_quota', 'provider_network', 'timeout', 'validation',
  'busy', 'config_conflict', 'capability', 'notification', 'not_found', 'outbound_policy', 'internal',
]);
const TAXONOMY_SEVERITIES = new Set<string>(['info', 'warning', 'error', 'critical']);

export function normalizeErrorCode(code: string | null | undefined): string {
  const trimmed = typeof code === 'string' ? code.trim() : '';
  return trimmed || 'unknown_error';
}

export function classifyErrorCode(code: string | null | undefined): ErrorClassification {
  const normalized = normalizeErrorCode(code);
  return ERROR_CODE_TAXONOMY[normalized] ?? UNKNOWN_ERROR_CLASSIFICATION;
}

export function isClassifiedErrorCode(code: string | null | undefined): boolean {
  return normalizeErrorCode(code) in ERROR_CODE_TAXONOMY;
}

export function classifyParsedApiError(error: ParsedApiError): ErrorClassification {
  if (error.code && isClassifiedErrorCode(error.code)) {
    return classifyErrorCode(error.code);
  }
  if (error.taxonomyCategory && TAXONOMY_CATEGORIES.has(error.taxonomyCategory)) {
    const fromCategory = CATEGORY_TAXONOMY[error.category];
    if (fromCategory) {
      return {
        ...fromCategory,
        category: error.taxonomyCategory as TaxonomyCategory,
        severity: (
          error.taxonomySeverity && TAXONOMY_SEVERITIES.has(error.taxonomySeverity)
            ? error.taxonomySeverity
            : fromCategory.severity
        ) as TaxonomySeverity,
      };
    }
    return {
      ...UNKNOWN_ERROR_CLASSIFICATION,
      category: error.taxonomyCategory as TaxonomyCategory,
      severity: (
        error.taxonomySeverity && TAXONOMY_SEVERITIES.has(error.taxonomySeverity)
          ? error.taxonomySeverity
          : 'error'
      ) as TaxonomySeverity,
    };
  }
  if (error.category && CATEGORY_TAXONOMY[error.category]) {
    return CATEGORY_TAXONOMY[error.category] as ErrorClassification;
  }
  return UNKNOWN_ERROR_CLASSIFICATION;
}

export function docsUrlForPath(docsPath: string, language: 'zh' | 'en' = 'en'): string {
  const normalized = docsPath.replace(/^\/+/, '');
  if (language === 'zh') {
    const base = normalized.replace(/_EN\.md$/i, '.md');
    return `https://github.com/SiinXu/stock-pulse-ai/blob/main/${base}`;
  }
  if (normalized === 'docs/LLM_CONFIG_GUIDE.md') {
    return 'https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/LLM_CONFIG_GUIDE_EN.md';
  }
  if (normalized === 'docs/beginner-client-setup.md') {
    return 'https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/beginner-client-setup_EN.md';
  }
  if (normalized === 'docs/local-only-mode.md') {
    return 'https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/local-only-mode_EN.md';
  }
  return `https://github.com/SiinXu/stock-pulse-ai/blob/main/${normalized}`;
}

export function isRetryableClassification(classification: ErrorClassification): boolean {
  return classification.defaultAction === 'retry';
}

export const REGISTERED_TAXONOMY_CODES: readonly string[] = Object.freeze(
  Object.keys(ERROR_CODE_TAXONOMY).sort(),
);
