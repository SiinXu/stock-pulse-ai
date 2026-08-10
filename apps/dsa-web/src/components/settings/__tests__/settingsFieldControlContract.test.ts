import { describe, expect, it } from 'vitest';
import type {
  SystemConfigDataType,
  SystemConfigFieldSchema,
  SystemConfigUIControl,
} from '../../../types/systemConfig';
import {
  numberControlBounds,
  resolveSettingsFieldControl,
  type ResolvedSettingsControl,
} from '../settingsFieldControl';

/**
 * Schema → control contract for the Settings field renderer.
 *
 * These pure-function assertions are the guardrail that keeps boolean / enum /
 * number / sensitive fields from degrading to free-text when uiControl is wrong
 * or missing (typical for uncategorized / auto-inferred keys).
 */

function schema(partial: {
  dataType: SystemConfigDataType;
  uiControl?: SystemConfigUIControl;
  options?: SystemConfigFieldSchema['options'];
  isSensitive?: boolean;
  validation?: Record<string, unknown>;
}): Pick<
  SystemConfigFieldSchema,
  'uiControl' | 'dataType' | 'options' | 'isSensitive' | 'validation'
> {
  return {
    dataType: partial.dataType,
    uiControl: partial.uiControl ?? 'text',
    options: partial.options ?? [],
    isSensitive: partial.isSensitive ?? false,
    validation: partial.validation ?? {},
  };
}

describe('settingsFieldControl contract (schema → control)', () => {
  it.each([
    {
      name: 'boolean dataType → switch even when uiControl is text',
      input: schema({ dataType: 'boolean', uiControl: 'text' }),
      expected: 'switch' as ResolvedSettingsControl,
    },
    {
      name: 'explicit switch uiControl → switch',
      input: schema({ dataType: 'boolean', uiControl: 'switch' }),
      expected: 'switch' as ResolvedSettingsControl,
    },
    {
      name: 'true/false option pair → switch even when marked select',
      input: schema({
        dataType: 'string',
        uiControl: 'select',
        options: ['true', 'false'],
      }),
      expected: 'switch' as ResolvedSettingsControl,
    },
    {
      name: 'string with options → select even when uiControl is text',
      input: schema({
        dataType: 'string',
        uiControl: 'text',
        options: ['a', 'b', 'c'],
      }),
      expected: 'select' as ResolvedSettingsControl,
    },
    {
      name: 'multi-value options → multi-select even when uiControl is text',
      input: schema({
        dataType: 'string',
        uiControl: 'text',
        options: ['cn', 'hk', 'us'],
        validation: { multi_value: true },
      }),
      expected: 'multi-select' as ResolvedSettingsControl,
    },
    {
      name: 'integer dataType → number even when uiControl is text',
      input: schema({
        dataType: 'integer',
        uiControl: 'text',
        validation: { min: 0, max: 99 },
      }),
      expected: 'number' as ResolvedSettingsControl,
    },
    {
      name: 'number dataType → number even when uiControl is text',
      input: schema({ dataType: 'number', uiControl: 'text' }),
      expected: 'number' as ResolvedSettingsControl,
    },
    {
      name: 'isSensitive → password even when uiControl is text',
      input: schema({
        dataType: 'string',
        uiControl: 'text',
        isSensitive: true,
      }),
      expected: 'password' as ResolvedSettingsControl,
    },
    {
      name: 'password uiControl → password',
      input: schema({ dataType: 'string', uiControl: 'password' }),
      expected: 'password' as ResolvedSettingsControl,
    },
    {
      name: 'time dataType → time even when uiControl is text',
      input: schema({ dataType: 'time', uiControl: 'text' }),
      expected: 'time' as ResolvedSettingsControl,
    },
    {
      name: 'array dataType → textarea even when uiControl is text',
      input: schema({ dataType: 'array', uiControl: 'text' }),
      expected: 'textarea' as ResolvedSettingsControl,
    },
    {
      name: 'json dataType → textarea even when uiControl is text',
      input: schema({ dataType: 'json', uiControl: 'text' }),
      expected: 'textarea' as ResolvedSettingsControl,
    },
    {
      name: 'plain string with no options → text',
      input: schema({ dataType: 'string', uiControl: 'text' }),
      expected: 'text' as ResolvedSettingsControl,
    },
  ])('$name', ({ input, expected }) => {
    expect(resolveSettingsFieldControl(input)).toBe(expected);
  });

  it('masks isMasked items as password even without schema.isSensitive', () => {
    expect(
      resolveSettingsFieldControl(
        schema({ dataType: 'string', uiControl: 'text', isSensitive: false }),
        { isMasked: true },
      ),
    ).toBe('password');
  });

  it('falls back to text when schema is absent, password when only isMasked', () => {
    expect(resolveSettingsFieldControl(undefined)).toBe('text');
    expect(resolveSettingsFieldControl(null, { isMasked: true })).toBe('password');
  });

  it('does not let a wrong text uiControl defeat uncategorized typed fields', () => {
    // Uncategorized keys often arrive with category=uncategorized and a default
    // ui_control=text; the renderer must still follow dataType / sensitivity.
    const uncategorizedCases: Array<{
      dataType: SystemConfigDataType;
      isSensitive?: boolean;
      options?: string[];
      expected: ResolvedSettingsControl;
    }> = [
      { dataType: 'boolean', expected: 'switch' },
      { dataType: 'integer', expected: 'number' },
      { dataType: 'number', expected: 'number' },
      { dataType: 'string', options: ['auto', 'manual'], expected: 'select' },
      { dataType: 'string', isSensitive: true, expected: 'password' },
      { dataType: 'time', expected: 'time' },
      { dataType: 'array', expected: 'textarea' },
    ];

    for (const entry of uncategorizedCases) {
      const resolved = resolveSettingsFieldControl(
        schema({
          dataType: entry.dataType,
          uiControl: 'text',
          options: entry.options,
          isSensitive: entry.isSensitive,
        }),
      );
      expect(resolved, `uncategorized ${entry.dataType} should map to ${entry.expected}`).toBe(
        entry.expected,
      );
    }
  });

  it('exposes min/max/step range hints for integer and float number fields', () => {
    expect(
      numberControlBounds(
        schema({
          dataType: 'integer',
          uiControl: 'number',
          validation: { min: 0, max: 99 },
        }),
      ),
    ).toEqual({ min: 0, max: 99, step: 1 });

    expect(
      numberControlBounds(
        schema({
          dataType: 'number',
          uiControl: 'number',
          validation: { min: 0, max: 2 },
        }),
      ),
    ).toEqual({ min: 0, max: 2, step: 0.1 });
  });
});
