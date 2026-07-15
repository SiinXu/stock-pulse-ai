import type { ConfigCondition, ConfigFieldContract } from '../types/systemConfig';

export type ConditionResult = 'met' | 'notMet' | 'unknown';
export type ConfigContractDiagnostic = 'unknown_condition';

function conditionHasKnownShape(condition: ConfigCondition): boolean {
  if (typeof condition.key !== 'string' || condition.key.trim().length === 0) {
    return false;
  }
  switch (condition.operator) {
    case 'equals':
    case 'notEquals':
      return typeof condition.value === 'string';
    case 'in':
      return Array.isArray(condition.value)
        && condition.value.every((value) => typeof value === 'string');
    case 'notEmpty':
      return true;
    default:
      return false;
  }
}

function contractConditions(contract: ConfigFieldContract): ConfigCondition[][] {
  return [contract.requiredWhen, contract.visibleWhen, contract.enabledWhen]
    .filter((conditions): conditions is ConfigCondition[] => Array.isArray(conditions));
}

/** Return a stable diagnostic when an older client cannot interpret a contract. */
export function getConfigContractDiagnostic(
  contract: ConfigFieldContract | undefined,
): ConfigContractDiagnostic | null {
  if (!contract) {
    return null;
  }
  return contractConditions(contract).some((conditions) => (
    conditions.some((condition) => !conditionHasKnownShape(condition))
  ))
    ? 'unknown_condition'
    : null;
}

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
  let hasUnmetCondition = false;
  for (const condition of conditions) {
    if (!conditionHasKnownShape(condition)) {
      return 'unknown';
    }
    const actual = values[condition.key.toUpperCase()] ?? '';
    let met: boolean;
    switch (condition.operator) {
      case 'equals':
        met = actual === condition.value;
        break;
      case 'notEquals':
        met = actual !== condition.value;
        break;
      case 'in':
        met = Array.isArray(condition.value) && condition.value.includes(actual);
        break;
      case 'notEmpty':
        met = actual.trim().length > 0;
        break;
      default:
        return 'unknown';
    }
    if (!met) {
      hasUnmetCondition = true;
    }
  }
  return hasUnmetCondition ? 'notMet' : 'met';
}

/** A field is visible unless its visibleWhen conditions are definitively not met. */
export function isFieldVisibleByContract(
  contract: ConfigFieldContract | undefined,
  values: Record<string, string>,
): boolean {
  if (getConfigContractDiagnostic(contract)) {
    return true;
  }
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
  if (getConfigContractDiagnostic(contract)) {
    return false;
  }
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
