// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { describe, expect, it } from 'vitest';
import { createParsedApiError, type ParsedApiError } from '../../api/error';
import {
  ACTIONABLE_ERROR_CLASSES,
  extractApiErrorReason,
  KNOWN_OUTBOUND_REASONS,
  KNOWN_STABLE_CODES,
  mapApiErrorToActionable,
  type ActionableErrorClass,
  type ActionableErrorMapping,
} from '../apiReasonMapper';

function mapFrom(partial: Parameters<typeof createParsedApiError>[0]): ActionableErrorMapping {
  return mapApiErrorToActionable(createParsedApiError(partial));
}

describe('mapApiErrorToActionable', () => {
  describe('settings 409 config conflicts', () => {
    it.each([
      ['config_conflict', 'api.error.STABLE_ERROR_TEXT.config_conflict.title'],
      ['config_version_conflict', 'api.error.STABLE_ERROR_TEXT.config_version_conflict.title'],
      ['conflict', 'api.error.STABLE_ERROR_TEXT.conflict.title'],
    ] as const)('maps %s to config_conflict with reload CTA', (code, titleKey) => {
      const mapped = mapFrom({
        title: 'conflict',
        message: 'conflict',
        code,
        status: 409,
      });
      expect(mapped.class).toBe('config_conflict');
      expect(mapped.titleKey).toBe(titleKey);
      expect(mapped.messageKey).toContain(code === 'config_version_conflict' ? 'config_version_conflict' : code === 'conflict' ? 'conflict' : 'config_conflict');
      expect(mapped.cta).toEqual({ kind: 'reload', target: 'page' });
      expect(mapped.technicalCode).toBe(code);
    });
  });

  describe('analysis / run-now busy', () => {
    it.each([
      ['duplicate_task', 'api.error.STABLE_ERROR_TEXT.duplicate_task.title'],
      ['duplicate_market_review', 'api.error.STABLE_ERROR_TEXT.duplicate_market_review.title'],
      ['scheduler_busy', 'api.error.STABLE_ERROR_TEXT.scheduler_busy.title'],
      ['portfolio_busy', 'api.error.STABLE_ERROR_TEXT.portfolio_busy.title'],
    ] as const)('maps %s to busy with retry CTA', (code, titleKey) => {
      const mapped = mapFrom({
        title: 'busy',
        message: 'busy',
        code,
        status: 409,
        params: code === 'scheduler_busy' ? { reason: 'analysis_already_running' } : undefined,
      });
      expect(mapped.class).toBe('busy');
      expect(mapped.titleKey).toBe(titleKey);
      expect(mapped.cta).toEqual({ kind: 'retry' });
      if (code === 'scheduler_busy') {
        expect(mapped.technicalReason).toBe('analysis_already_running');
      }
    });

    it('maps analysis_already_running reason without busy code to scheduler_busy keys', () => {
      const mapped = mapFrom({
        title: 'busy',
        message: 'busy',
        status: 409,
        params: { reason: 'analysis_already_running' },
      });
      expect(mapped.class).toBe('busy');
      expect(mapped.titleKey).toBe('api.error.STABLE_ERROR_TEXT.scheduler_busy.title');
      expect(mapped.technicalReason).toBe('analysis_already_running');
    });
  });

  describe('llm_not_configured', () => {
    it('maps code and category to settings navigation', () => {
      const byCode = mapFrom({
        title: 'llm',
        message: 'llm',
        code: 'llm_not_configured',
        category: 'llm_not_configured',
        status: 422,
      });
      expect(byCode).toMatchObject({
        class: 'llm_not_configured',
        titleKey: 'api.error.STABLE_ERROR_TEXT.llm_not_configured.title',
        messageKey: 'api.error.STABLE_ERROR_TEXT.llm_not_configured.message',
        cta: { kind: 'navigate', target: '/settings' },
        technicalCode: 'llm_not_configured',
      });

      const byCategory = mapFrom({
        title: 'llm',
        message: 'llm',
        category: 'llm_not_configured',
      });
      expect(byCategory.class).toBe('llm_not_configured');
    });
  });

  describe('outbound policy reasons (#876)', () => {
    it.each([...KNOWN_OUTBOUND_REASONS])('maps outbound reason %s', (reason) => {
      const mapped = mapFrom({
        title: 'blocked',
        message: 'blocked',
        code: 'invalid_config',
        details: { reason },
        status: 400,
      });
      if (reason === 'local_only_mode_blocked') {
        expect(mapped.class).toBe('local_only_mode');
        expect(mapped.titleKey).toBe('i18n.uiText.UI_TEXT.settings.outboundActivityModeOn');
        expect(mapped.messageKey).toBe('i18n.uiText.UI_TEXT.settings.outboundActivityModeHint');
      } else {
        expect(mapped.class).toBe('outbound_policy');
        expect(mapped.titleKey).toBe('api.error.GENERIC_ERROR_TEXT.upstream_network.title');
      }
      expect(mapped.technicalReason).toBe(reason);
      expect(mapped.cta?.kind).toBe('navigate');
      expect(mapped.cta?.target).toBe('/settings');
    });

    it('detects LOCAL_ONLY_MODE text in rawMessage when reason is not structured', () => {
      const mapped = mapFrom({
        title: 'blocked',
        message: 'blocked',
        rawMessage: 'Outbound request rejected by LOCAL_ONLY_MODE (local_only_mode_blocked)',
      });
      expect(mapped.class).toBe('local_only_mode');
      expect(mapped.technicalReason).toBe('local_only_mode_blocked');
    });

    it('maps ssrf_blocked code to outbound_policy', () => {
      const mapped = mapFrom({
        title: 'blocked',
        message: 'blocked',
        code: 'ssrf_blocked',
      });
      expect(mapped.class).toBe('outbound_policy');
      expect(mapped.technicalCode).toBe('ssrf_blocked');
    });
  });

  describe('notification test failures', () => {
    it('maps no_channels with stable keys and settings CTA', () => {
      const mapped = mapFrom({
        title: 'channels',
        message: 'channels',
        code: 'no_channels',
      });
      expect(mapped.class).toBe('notification');
      expect(mapped.titleKey).toBe('api.error.STABLE_ERROR_TEXT.no_channels.title');
      expect(mapped.cta).toEqual({ kind: 'navigate', target: '/settings' });
    });

    it.each([
      'notification_channel_test_failed',
      'config_missing',
      'config_invalid',
      'send_failed',
    ] as const)('maps %s to notification class with existing failure title key', (code) => {
      const mapped = mapFrom({
        title: 'test failed',
        message: 'test failed',
        code,
      });
      expect(mapped.class).toBe('notification');
      expect(mapped.titleKey).toBe('i18n.uiText.UI_TEXT.settings.notificationTestFailure');
      expect(mapped.messageKey).toBe('api.error.GENERIC_ERROR_TEXT.http_error.message');
      expect(mapped.technicalCode).toBe(code);
      expect(mapped.cta?.target).toBe('/settings');
    });
  });

  describe('#876 adjacent classes', () => {
    it('maps approval_auth_required to hitl_pending → approvals', () => {
      const mapped = mapFrom({
        title: 'auth',
        message: 'auth',
        code: 'approval_auth_required',
        status: 403,
      });
      expect(mapped.class).toBe('hitl_pending');
      expect(mapped.cta).toEqual({ kind: 'navigate', target: '/approvals' });
    });

    it('maps rate_limited to rate_quota', () => {
      const mapped = mapFrom({
        title: 'rate',
        message: 'rate',
        code: 'rate_limited',
        status: 429,
      });
      expect(mapped.class).toBe('rate_quota');
      expect(mapped.cta).toEqual({ kind: 'retry' });
    });

    it('maps password codes to credential', () => {
      const mapped = mapFrom({
        title: 'pwd',
        message: 'pwd',
        code: 'invalid_password',
      });
      expect(mapped.class).toBe('credential');
      expect(mapped.titleKey).toBe('api.error.STABLE_ERROR_TEXT.invalid_password.title');
    });

    it('maps unauthorized to auth with login CTA', () => {
      const mapped = mapFrom({
        title: 'auth',
        message: 'auth',
        code: 'unauthorized',
        status: 401,
      });
      expect(mapped.class).toBe('auth');
      expect(mapped.cta).toEqual({ kind: 'navigate', target: '/login' });
    });

    it('maps agent_disabled to capability', () => {
      const mapped = mapFrom({
        title: 'agent',
        message: 'agent',
        code: 'agent_disabled',
        category: 'agent_disabled',
      });
      expect(mapped.class).toBe('capability');
      expect(mapped.cta?.target).toBe('/settings');
    });
  });

  describe('validation and not_found', () => {
    it('maps validation_error', () => {
      const mapped = mapFrom({
        title: 'v',
        message: 'v',
        code: 'validation_error',
        status: 422,
      });
      expect(mapped.class).toBe('validation');
      expect(mapped.titleKey).toBe('api.error.STABLE_ERROR_TEXT.validation_error.title');
    });

    it('maps not_found and HTTP 404', () => {
      const byCode = mapFrom({ title: 'n', message: 'n', code: 'not_found', status: 404 });
      expect(byCode.class).toBe('not_found');
      const byStatus = mapFrom({ title: 'n', message: 'n', status: 404 });
      expect(byStatus.class).toBe('not_found');
    });
  });

  describe('network categories', () => {
    it.each([
      ['upstream_timeout', 'api.error.GENERIC_ERROR_TEXT.upstream_timeout.title'],
      ['upstream_network', 'api.error.GENERIC_ERROR_TEXT.upstream_network.title'],
      ['local_connection_failed', 'api.error.GENERIC_ERROR_TEXT.local_connection_failed.title'],
    ] as const)('maps category %s', (category, titleKey) => {
      const mapped = mapFrom({
        title: 'net',
        message: 'net',
        category,
      });
      expect(mapped.class).toBe('network');
      expect(mapped.titleKey).toBe(titleKey);
      expect(mapped.cta).toEqual({ kind: 'retry' });
    });
  });

  describe('fallback', () => {
    it('keeps unknown technical codes under generic class', () => {
      const mapped = mapFrom({
        title: 'x',
        message: 'x',
        code: 'future_error_code',
        details: { reason: 'future' },
        status: 418,
        category: 'http_error',
      });
      expect(mapped.class).toBe('generic');
      expect(mapped.titleKey).toBe('api.error.GENERIC_ERROR_TEXT.http_error.title');
      expect(mapped.technicalCode).toBe('future_error_code');
      expect(mapped.technicalReason).toBe('future');
      expect(mapped.cta).toBeUndefined();
    });

    it('uses unknown keys when category is unknown', () => {
      const mapped = mapFrom({
        title: 'x',
        message: 'x',
        category: 'unknown',
      });
      expect(mapped.class).toBe('generic');
      expect(mapped.titleKey).toBe('api.error.GENERIC_ERROR_TEXT.unknown.title');
    });
  });
});

describe('extractApiErrorReason', () => {
  it('prefers details.reason over params.reason', () => {
    const error: ParsedApiError = createParsedApiError({
      title: 't',
      message: 'm',
      details: { reason: 'from_details' },
      params: { reason: 'from_params' },
    });
    expect(extractApiErrorReason(error)).toBe('from_details');
  });

  it('falls back to params.reason', () => {
    const error = createParsedApiError({
      title: 't',
      message: 'm',
      params: { reason: 'analysis_already_running' },
    });
    expect(extractApiErrorReason(error)).toBe('analysis_already_running');
  });
});

describe('type completeness', () => {
  it('lists every ActionableErrorClass exactly once', () => {
    const unique = new Set(ACTIONABLE_ERROR_CLASSES);
    expect(unique.size).toBe(ACTIONABLE_ERROR_CLASSES.length);
    // Compile-time-ish: every class is assignable; runtime: non-empty union coverage
    const required: ActionableErrorClass[] = [
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
    ];
    for (const cls of required) {
      expect(ACTIONABLE_ERROR_CLASSES).toContain(cls);
    }
  });

  it('exposes the stable catalog code set for adopter checks', () => {
    expect(KNOWN_STABLE_CODES.has('llm_not_configured')).toBe(true);
    expect(KNOWN_STABLE_CODES.has('scheduler_busy')).toBe(true);
    expect(KNOWN_STABLE_CODES.has('config_version_conflict')).toBe(true);
    expect(KNOWN_STABLE_CODES.has('no_channels')).toBe(true);
  });

  it('covers every class via at least one mapping path', () => {
    const seen = new Set<ActionableErrorClass>();
    const samples: Array<Parameters<typeof createParsedApiError>[0]> = [
      { title: 'a', message: 'a', code: 'config_conflict' },
      { title: 'a', message: 'a', code: 'duplicate_task' },
      { title: 'a', message: 'a', code: 'llm_not_configured' },
      { title: 'a', message: 'a', details: { reason: 'private_ip_blocked' } },
      { title: 'a', message: 'a', details: { reason: 'local_only_mode_blocked' } },
      { title: 'a', message: 'a', code: 'invalid_password' },
      { title: 'a', message: 'a', category: 'upstream_timeout' },
      { title: 'a', message: 'a', code: 'agent_disabled', category: 'agent_disabled' },
      { title: 'a', message: 'a', code: 'approval_auth_required' },
      { title: 'a', message: 'a', code: 'rate_limited' },
      { title: 'a', message: 'a', code: 'no_channels' },
      { title: 'a', message: 'a', code: 'unauthorized' },
      { title: 'a', message: 'a', code: 'validation_error' },
      { title: 'a', message: 'a', code: 'not_found' },
      { title: 'a', message: 'a', code: 'future_x', category: 'unknown' },
    ];
    for (const sample of samples) {
      seen.add(mapApiErrorToActionable(createParsedApiError(sample)).class);
    }
    for (const cls of ACTIONABLE_ERROR_CLASSES) {
      expect(seen.has(cls), `missing mapping sample for class ${cls}`).toBe(true);
    }
  });
});
