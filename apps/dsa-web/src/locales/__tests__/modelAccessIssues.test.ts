import { beforeAll, describe, expect, it } from 'vitest';
import { loadAllUiLanguageTranslations } from '../../i18n/translations';
import {
  MODEL_ACCESS_ISSUES,
  localizeModelAccessIssue,
} from '../settingsModelAccess';

describe('localizeModelAccessIssue', () => {
  beforeAll(async () => {
    await loadAllUiLanguageTranslations();
  });

  it('localizes known validation codes in zh, en, and an additional locale', () => {
    expect(localizeModelAccessIssue('name_required', 'zh')).toBe('连接名称必填');
    expect(localizeModelAccessIssue({ code: 'name_required' }, 'en')).toBe('Connection name is required');
    expect(localizeModelAccessIssue({ code: 'missing_api_key' }, 'ja')).toBe(
      MODEL_ACCESS_ISSUES.ja.missing_api_key,
    );
    expect(MODEL_ACCESS_ISSUES.ja.missing_api_key).not.toBe(MODEL_ACCESS_ISSUES.en.missing_api_key);
    expect(MODEL_ACCESS_ISSUES.ja.missing_api_key).not.toBe(MODEL_ACCESS_ISSUES.zh.missing_api_key);
  });

  it('interpolates parameters on known templates', () => {
    expect(localizeModelAccessIssue({
      code: 'unknown',
      params: { code: 'name_required' },
    }, 'en')).toBe('Unexpected connection validation issue (name_required)');
    expect(localizeModelAccessIssue({
      code: 'unknown',
      params: { code: 'name_required' },
    }, 'zh')).toBe('连接校验出现未识别问题（name_required）');
    expect(localizeModelAccessIssue({
      code: 'unknown',
      params: { code: 'name_required' },
    }, 'ja')).toContain('name_required');
  });

  it('uses a localized fallback for unknown codes without exposing raw prose', () => {
    const chineseFallback = localizeModelAccessIssue('连接名称必填', 'en');
    expect(chineseFallback).toBe('Unexpected connection validation issue (unknown)');
    expect(chineseFallback).not.toContain('连接名称');

    const backendProse = localizeModelAccessIssue(
      'Provider rejected request: invalid_grant',
      'en',
    );
    expect(backendProse).toBe('Unexpected connection validation issue (unknown)');
    expect(backendProse).not.toContain('invalid_grant');
    expect(backendProse).not.toContain('Provider rejected');

    expect(localizeModelAccessIssue({ code: 'not_a_real_code' }, 'ja')).toBe(
      MODEL_ACCESS_ISSUES.ja.unknown.replace('{code}', 'not_a_real_code'),
    );
  });
});
