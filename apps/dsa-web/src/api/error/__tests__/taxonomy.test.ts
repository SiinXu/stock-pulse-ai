// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { describe, expect, it, vi } from 'vitest';
import { createParsedApiError, resolveErrorRemediation } from '../index';
import {
  classifyErrorCode,
  classifyParsedApiError,
  docsUrlForPath,
  ERROR_CODE_TAXONOMY,
  isClassifiedErrorCode,
  isRetryableClassification,
  REGISTERED_TAXONOMY_CODES,
} from '../taxonomy';
import { STABLE_ERROR_TEXT } from '../catalog';

describe('error taxonomy', () => {
  it('classifies every STABLE_ERROR_TEXT code', () => {
    const missing = Object.keys(STABLE_ERROR_TEXT).filter((code) => !isClassifiedErrorCode(code));
    expect(missing).toEqual([]);
  });

  it('registers a non-empty taxonomy vocabulary', () => {
    expect(REGISTERED_TAXONOMY_CODES.length).toBeGreaterThan(40);
    expect(ERROR_CODE_TAXONOMY.llm_not_configured.defaultAction).toBe('settings');
    expect(ERROR_CODE_TAXONOMY.upstream_timeout.defaultAction).toBe('retry');
    expect(ERROR_CODE_TAXONOMY.not_changeable.defaultAction).toBe('docs');
  });

  it('preserves research pack remediation semantics', () => {
    expect(ERROR_CODE_TAXONOMY.research_pack_auth_required).toMatchObject({
      category: 'auth', severity: 'error', defaultAction: 'settings',
    });
    expect(ERROR_CODE_TAXONOMY.research_pack_export_disabled).toMatchObject({
      category: 'capability', severity: 'warning', defaultAction: 'settings',
    });
    expect(ERROR_CODE_TAXONOMY.research_pack_limit_exceeded).toMatchObject({
      category: 'capability', severity: 'warning', defaultAction: 'settings',
    });
  });

  it('requires a new preview for stale Futu import snapshots', () => {
    expect(ERROR_CODE_TAXONOMY.portfolio_import_preview_stale).toEqual({
      category: 'config_conflict',
      severity: 'warning',
      defaultAction: 'none',
    });
  });

  it('falls back to internal for unknown codes', () => {
    const unknown = classifyErrorCode('brand_new_code_not_registered');
    expect(unknown.category).toBe('internal');
    expect(isClassifiedErrorCode('brand_new_code_not_registered')).toBe(false);
  });

  it('prefers wire taxonomy category when present', () => {
    const error = createParsedApiError({
      title: 'x',
      message: 'y',
      code: 'custom_unregistered',
      category: 'http_error',
      taxonomyCategory: 'rate_quota',
      taxonomySeverity: 'warning',
    });
    const classification = classifyParsedApiError(error);
    expect(classification.category).toBe('rate_quota');
    expect(classification.severity).toBe('warning');
  });

  it('builds language-aware docs URLs', () => {
    expect(docsUrlForPath('docs/LLM_CONFIG_GUIDE.md', 'en')).toContain('LLM_CONFIG_GUIDE_EN.md');
    expect(docsUrlForPath('docs/LLM_CONFIG_GUIDE.md', 'zh')).toContain('LLM_CONFIG_GUIDE.md');
    expect(docsUrlForPath('docs/LLM_CONFIG_GUIDE.md', 'zh')).not.toContain('_EN');
  });

  it('requires onRetry for retry remediation CTAs', () => {
    const timeout = createParsedApiError({
      title: 'timeout',
      message: 'later',
      category: 'upstream_timeout',
      code: 'upstream_timeout',
    });
    expect(resolveErrorRemediation(timeout, 'en')).toMatchObject({
      actionKind: 'none',
    });
    const onRetry = vi.fn();
    const withRetry = resolveErrorRemediation(timeout, 'en', { onRetry });
    expect(withRetry).toMatchObject({
      actionKind: 'retry',
      actionLabel: 'Retry',
    });
    expect(isRetryableClassification(classifyParsedApiError(timeout))).toBe(true);
  });

  it('resolves docs remediation for docs-default codes', () => {
    const error = createParsedApiError({
      title: 'Cannot change',
      message: 'Use another path',
      code: 'not_changeable',
      category: 'http_error',
    });
    const remediation = resolveErrorRemediation(error, 'en');
    expect(remediation?.actionKind).toBe('docs');
    expect(remediation?.href).toMatch(/^https:\/\/github\.com\/SiinXu\/stock-pulse-ai\/blob\/main\//);
    expect(remediation?.actionLabel).toMatch(/Related docs|相关文档/);
  });

  it('resolves settings remediation for capability codes', () => {
    const error = createParsedApiError({
      title: 'No model',
      message: 'Configure',
      code: 'llm_not_configured',
      category: 'llm_not_configured',
    });
    const remediation = resolveErrorRemediation(error, 'en');
    expect(remediation?.actionKind).toBe('settings');
    expect(remediation?.href).toContain('/settings');
  });
});
