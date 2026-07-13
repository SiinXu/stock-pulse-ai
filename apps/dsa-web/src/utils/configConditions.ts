import type { ConfigCondition, ConfigFieldContract } from '../types/systemConfig';

export type ConditionResult = 'met' | 'notMet' | 'unknown';

/**
 * Evaluate an AND-list of field conditions against a key -> value map.
 * An unknown operator returns 'unknown' so callers can fail-safe (keep the
 * field visible and still validated).
 */
export function evaluateConfigConditions(
  conditions: ConfigCondition[] | undefined,
  values: Record<string, string>,
): ConditionResult {
  if (!conditions || conditions.length === 0) {
    return 'met';
  }
  for (const condition of conditions) {
    const actual = values[condition.key.toUpperCase()] ?? '';
    let met: boolean;
    switch (condition.operator) {
      case 'equals':
        met = actual === String(condition.value ?? '');
        break;
      case 'notEquals':
        met = actual !== String(condition.value ?? '');
        break;
      case 'in':
        met = (Array.isArray(condition.value) ? condition.value : []).map(String).includes(actual);
        break;
      case 'notEmpty':
        met = actual.trim().length > 0;
        break;
      default:
        return 'unknown';
    }
    if (!met) {
      return 'notMet';
    }
  }
  return 'met';
}

/** A field is visible unless its visibleWhen conditions are definitively not met. */
export function isFieldVisibleByContract(
  contract: ConfigFieldContract | undefined,
  values: Record<string, string>,
): boolean {
  if (!contract?.visibleWhen) {
    return true;
  }
  return evaluateConfigConditions(contract.visibleWhen, values) !== 'notMet';
}

/** A field is editable unless its enabledWhen conditions are definitively not met. */
export function isFieldEnabledByContract(
  contract: ConfigFieldContract | undefined,
  values: Record<string, string>,
): boolean {
  if (!contract?.enabledWhen) {
    return true;
  }
  return evaluateConfigConditions(contract.enabledWhen, values) !== 'notMet';
}

export type FieldRequirement = 'required' | 'optional' | 'inherited';

/** Resolve the effective requirement, applying requiredWhen against current values. */
export function resolveFieldRequirement(
  contract: ConfigFieldContract | undefined,
  values: Record<string, string>,
): FieldRequirement | null {
  if (!contract) {
    return null;
  }
  if (contract.requirement === 'inherited') {
    return 'inherited';
  }
  if (contract.requirement === 'required') {
    return 'required';
  }
  if (contract.requiredWhen && evaluateConfigConditions(contract.requiredWhen, values) === 'met') {
    return 'required';
  }
  return 'optional';
}
