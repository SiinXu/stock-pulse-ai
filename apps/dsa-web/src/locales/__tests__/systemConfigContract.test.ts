import { describe, expect, it } from 'vitest';
import {
  getSystemConfigContractDiagnosticText,
  SYSTEM_CONFIG_CONTRACT_TEXT,
} from '../systemConfigContract';

describe('system config contract diagnostics', () => {
  it('keeps Chinese and English diagnostic keys aligned', () => {
    expect(Object.keys(SYSTEM_CONFIG_CONTRACT_TEXT.en).sort()).toEqual(
      Object.keys(SYSTEM_CONFIG_CONTRACT_TEXT.zh).sort(),
    );
  });

  it('returns localized fail-safe diagnostics', () => {
    expect(getSystemConfigContractDiagnosticText('zh', 'missing_ai_ui_placement')).toContain('暂时只读');
    expect(getSystemConfigContractDiagnosticText('en', 'unknown_ui_placement')).toContain('read-only');
    expect(getSystemConfigContractDiagnosticText('en', 'unknown_condition')).toContain('remains visible');
  });
});
