import { describe, expect, it } from 'vitest';
import type { SystemConfigFieldSchema } from '../../types/systemConfig';
import { resolveSystemConfigFieldPlacement } from '../systemConfigSchemaCompatibility';

function field(overrides: Partial<SystemConfigFieldSchema> = {}): SystemConfigFieldSchema {
  return {
    key: 'LLM_UNKNOWN_SETTING',
    category: 'ai_model',
    dataType: 'string',
    uiControl: 'text',
    isSensitive: false,
    isRequired: false,
    isEditable: true,
    options: [],
    validation: {},
    displayOrder: 1,
    ...overrides,
  };
}

describe('resolveSystemConfigFieldPlacement', () => {
  it('keeps a regular legacy field in the generic editable form', () => {
    expect(resolveSystemConfigFieldPlacement(field({
      key: 'STOCK_LIST',
      category: 'base',
      uiPlacement: undefined,
    }))).toEqual({ placement: 'generic', readOnly: false, diagnostic: null });
  });

  it('moves an AI field with missing placement to read-only diagnostics', () => {
    expect(resolveSystemConfigFieldPlacement(field({ uiPlacement: undefined }))).toEqual({
      placement: 'developer_diagnostics',
      readOnly: true,
      diagnostic: 'missing_ai_ui_placement',
    });
  });

  it('moves an unknown placement to read-only diagnostics', () => {
    expect(resolveSystemConfigFieldPlacement(field({
      uiPlacement: 'future_surface' as never,
    }))).toEqual({
      placement: 'developer_diagnostics',
      readOnly: true,
      diagnostic: 'unknown_ui_placement',
    });
  });

  it('preserves a known backend-owned placement', () => {
    expect(resolveSystemConfigFieldPlacement(field({ uiPlacement: 'model_access' }))).toEqual({
      placement: 'model_access',
      readOnly: false,
      diagnostic: null,
    });
  });
});
