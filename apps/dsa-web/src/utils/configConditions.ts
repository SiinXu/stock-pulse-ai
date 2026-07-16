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
  if (conditions === undefined || conditions === null) {
    return 'met';
  }
  if (!Array.isArray(conditions)) {
    return 'unknown';
  }
  if (conditions.length === 0) {
    return 'met';
  }
  let allMet = true;
  for (const condition of conditions) {
    if (!condition || typeof condition.key !== 'string' || !condition.key.trim()) {
      return 'unknown';
    }
    const actual = values[condition.key.toUpperCase()] ?? '';
    let met: boolean;
    switch (condition.operator) {
      case 'equals':
        if (Array.isArray(condition.value)) return 'unknown';
        met = actual === String(condition.value ?? '');
        break;
      case 'notEquals':
        if (Array.isArray(condition.value)) return 'unknown';
        met = actual !== String(condition.value ?? '');
        break;
      case 'in':
        if (!Array.isArray(condition.value)) return 'unknown';
        met = condition.value.map(String).includes(actual);
        break;
      case 'notEmpty':
        met = actual.trim().length > 0;
        break;
      default:
        return 'unknown';
    }
    allMet = allMet && met;
  }
  return allMet ? 'met' : 'notMet';
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

/** Unknown condition operators must keep a field visible but prevent edits. */
export function hasUnknownConfigContractCondition(
  contract: ConfigFieldContract | undefined,
  values: Record<string, string>,
): boolean {
  if (!contract) {
    return false;
  }
  return [contract.requiredWhen, contract.visibleWhen, contract.enabledWhen]
    .some((conditions) => conditions && evaluateConfigConditions(conditions, values) === 'unknown');
}

/** A field is editable unless its enabledWhen conditions are definitively not met. */
export function isFieldEnabledByContract(
  contract: ConfigFieldContract | undefined,
  values: Record<string, string>,
): boolean {
  if (contract?.requirement === 'inherited' || hasUnknownConfigContractCondition(contract, values)) {
    return false;
  }
  if (!contract?.enabledWhen) {
    return true;
  }
  return evaluateConfigConditions(contract.enabledWhen, values) === 'met';
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
