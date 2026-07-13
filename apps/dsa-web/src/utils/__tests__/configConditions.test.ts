import { describe, expect, it } from 'vitest';
import { evaluateConfigConditions, isFieldVisibleByContract, isFieldEnabledByContract } from '../configConditions';

describe('evaluateConfigConditions', () => {
  it('returns met for empty conditions', () => {
    expect(evaluateConfigConditions(undefined, {})).toBe('met');
    expect(evaluateConfigConditions([], {})).toBe('met');
  });

  it('evaluates equals / notEquals / in / notEmpty with AND semantics', () => {
    const values = { GENERATION_BACKEND: 'opencode_cli', AGENT_MODE: 'multi' };
    expect(evaluateConfigConditions([{ key: 'GENERATION_BACKEND', operator: 'equals', value: 'opencode_cli' }], values)).toBe('met');
    expect(evaluateConfigConditions([{ key: 'GENERATION_BACKEND', operator: 'equals', value: 'litellm' }], values)).toBe('notMet');
    expect(evaluateConfigConditions([{ key: 'GENERATION_BACKEND', operator: 'notEquals', value: 'litellm' }], values)).toBe('met');
    expect(evaluateConfigConditions([{ key: 'AGENT_MODE', operator: 'in', value: ['single', 'multi'] }], values)).toBe('met');
    expect(evaluateConfigConditions([{ key: 'GENERATION_BACKEND', operator: 'notEmpty' }], values)).toBe('met');
    expect(evaluateConfigConditions([{ key: 'MISSING', operator: 'notEmpty' }], values)).toBe('notMet');
    // AND: one unmet -> notMet
    expect(evaluateConfigConditions([
      { key: 'GENERATION_BACKEND', operator: 'equals', value: 'opencode_cli' },
      { key: 'AGENT_MODE', operator: 'equals', value: 'single' },
    ], values)).toBe('notMet');
  });

  it('fails safe to unknown for unknown operators', () => {
    expect(evaluateConfigConditions([{ key: 'X', operator: 'regex' as never }], {})).toBe('unknown');
  });

  it('keeps fields visible/editable on unknown conditions (fail-safe)', () => {
    const contract = { visibleWhen: [{ key: 'X', operator: 'regex' as never }] };
    expect(isFieldVisibleByContract(contract, {})).toBe(true);
    expect(isFieldEnabledByContract({ enabledWhen: [{ key: 'X', operator: 'regex' as never }] }, {})).toBe(true);
  });

  it('hides a field when visibleWhen is definitively not met', () => {
    const contract = { visibleWhen: [{ key: 'GENERATION_BACKEND', operator: 'equals' as const, value: 'opencode_cli' }] };
    expect(isFieldVisibleByContract(contract, { GENERATION_BACKEND: 'litellm' })).toBe(false);
    expect(isFieldVisibleByContract(contract, { GENERATION_BACKEND: 'opencode_cli' })).toBe(true);
  });
});
