import type { LlmConnectionFieldSchema } from '../types/systemConfig';
import { SUPPORTED_CONNECTION_SCHEMA_KEYS } from '../components/settings/modelAccessFieldKey';
import {
  hasUnknownConfigContractCondition,
  isFieldEnabledByContract,
  isFieldVisibleByContract,
  resolveFieldRequirement,
} from './configConditions';

const IDENTITY_FIELD_KEYS = ['connection_name', 'provider_id'] as const;
const CONNECTION_SCHEMA_CORE_FIELD_KEYS = Array.from(SUPPORTED_CONNECTION_SCHEMA_KEYS);
const FIELD_DATA_TYPES = new Set(['string', 'boolean', 'array', 'json']);
const FIELD_REQUIREMENTS = new Set(['required', 'optional', 'inherited']);
const CONDITION_KEYS = ['requiredWhen', 'visibleWhen', 'enabledWhen'] as const;

export interface ConnectionFieldState {
  visible: boolean;
  enabled: boolean;
  required: boolean;
  unknownCondition: boolean;
  requiresConnectionTest: boolean;
}

export type ConnectionSchemaUnavailableReason =
  | 'empty'
  | 'malformed'
  | 'missing_identity'
  | 'missing_core'
  | 'identity_read_only'
  | 'unknown_condition'
  | 'unsupported_required_field';

export interface ConnectionSchemaDefinition {
  mode: 'legacy' | 'schema';
  usable: boolean;
  reason?: ConnectionSchemaUnavailableReason;
  missingIdentityFields: string[];
  missingCoreFields?: string[];
}

export interface ConnectionSchemaAuthority extends ConnectionSchemaDefinition {
  states: Record<string, ConnectionFieldState>;
}

function normalizeContractValues(values: Record<string, string>): Record<string, string> {
  return Object.fromEntries(
    Object.entries(values).map(([key, value]) => [key.toUpperCase(), value]),
  );
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function isConditionList(value: unknown): boolean {
  if (value === undefined || value === null) {
    return true;
  }
  if (!Array.isArray(value)) {
    return false;
  }
  return value.every((condition) => {
    if (
      !isRecord(condition)
      || typeof condition.key !== 'string'
      || !condition.key.trim()
      || condition.key !== condition.key.trim()
      || typeof condition.operator !== 'string'
      || !condition.operator.trim()
    ) {
      return false;
    }
    return condition.value === undefined
      || condition.value === null
      || typeof condition.value === 'string'
      || (Array.isArray(condition.value) && condition.value.every((entry) => typeof entry === 'string'));
  });
}

function isConnectionFieldSchema(value: unknown): value is LlmConnectionFieldSchema {
  if (
    !isRecord(value)
    || typeof value.key !== 'string'
    || !value.key.trim()
    || value.key !== value.key.trim()
    || typeof value.dataType !== 'string'
    || !FIELD_DATA_TYPES.has(value.dataType)
    || typeof value.isSensitive !== 'boolean'
    || typeof value.isRequired !== 'boolean'
    || !isRecord(value.contract)
    || typeof value.contract.requirement !== 'string'
    || !FIELD_REQUIREMENTS.has(value.contract.requirement)
  ) {
    return false;
  }
  if (
    value.envSuffix !== undefined
    && value.envSuffix !== null
    && typeof value.envSuffix !== 'string'
  ) {
    return false;
  }
  if (
    value.contract.requiresConnectionTest !== undefined
    && value.contract.requiresConnectionTest !== null
    && typeof value.contract.requiresConnectionTest !== 'boolean'
  ) {
    return false;
  }
  if (
    value.contract.restartRequired !== undefined
    && value.contract.restartRequired !== null
    && typeof value.contract.restartRequired !== 'boolean'
  ) {
    return false;
  }
  const contract = value.contract;
  return CONDITION_KEYS.every((key) => isConditionList(contract[key]));
}

function isConnectionFieldSchemaArray(value: unknown): value is LlmConnectionFieldSchema[] {
  return Array.isArray(value) && value.every(isConnectionFieldSchema);
}

function identityFieldIsUnconditionallyWritable(
  fields: LlmConnectionFieldSchema[],
  key: typeof IDENTITY_FIELD_KEYS[number],
): boolean {
  const field = fields.find((candidate) => candidate.key === key);
  if (!field || field.contract.requirement === 'inherited') {
    return false;
  }
  // Identity establishes the Connection namespace, so it cannot depend on
  // values that only become authoritative after the Connection is writable.
  return (field.contract.visibleWhen?.length ?? 0) === 0
    && (field.contract.enabledWhen?.length ?? 0) === 0;
}

function hasUnsupportedRequiredVisibleField(
  fields: LlmConnectionFieldSchema[],
  states: Record<string, ConnectionFieldState>,
): boolean {
  return fields.some((field) => {
    const state = states[field.key];
    return !SUPPORTED_CONNECTION_SCHEMA_KEYS.has(field.key)
      && state?.visible === true
      && state.required;
  });
}

function hasUnsupportedStaticallyRequiredVisibleField(
  fields: LlmConnectionFieldSchema[],
): boolean {
  return fields.some((field) => {
    if (SUPPORTED_CONNECTION_SCHEMA_KEYS.has(field.key)) {
      return false;
    }
    const { requirement, requiredWhen, visibleWhen } = field.contract;
    const staticallyVisible = visibleWhen == null || visibleWhen.length === 0;
    const staticallyRequired = requirement === 'required'
      || (requirement === 'optional' && Array.isArray(requiredWhen) && requiredWhen.length === 0);
    return staticallyVisible && staticallyRequired;
  });
}

/** Evaluate field contracts with the same fail-safe condition semantics as the backend. */
export function evaluateConnectionFieldStates(
  values: Record<string, string>,
  fields: LlmConnectionFieldSchema[],
): Record<string, ConnectionFieldState> {
  const normalizedValues = normalizeContractValues(values);
  return Object.fromEntries(fields.map((field) => {
    const unknownCondition = hasUnknownConfigContractCondition(field.contract, normalizedValues);
    const visible = isFieldVisibleByContract(field.contract, normalizedValues);
    const requirement = resolveFieldRequirement(field.contract, normalizedValues);
    return [field.key, {
      visible,
      enabled: isFieldEnabledByContract(field.contract, normalizedValues),
      required: visible && requirement === 'required',
      unknownCondition,
      requiresConnectionTest: Boolean(field.contract?.requiresConnectionTest),
    }];
  }));
}

/**
 * Classify the Catalog payload before any Connection values are considered.
 * Only an omitted property is legacy-compatible; every present invalid schema
 * remains present and unavailable.
 */
export function inspectConnectionSchemaDefinition(
  fields: unknown,
): ConnectionSchemaDefinition {
  if (fields === undefined) {
    return { mode: 'legacy', usable: true, missingIdentityFields: [] };
  }
  if (!Array.isArray(fields)) {
    return { mode: 'schema', usable: false, reason: 'malformed', missingIdentityFields: [] };
  }
  if (fields.length === 0) {
    return { mode: 'schema', usable: false, reason: 'empty', missingIdentityFields: [...IDENTITY_FIELD_KEYS] };
  }

  if (!isConnectionFieldSchemaArray(fields)) {
    return { mode: 'schema', usable: false, reason: 'malformed', missingIdentityFields: [] };
  }

  const keys = fields.map((field) => field.key.trim());
  if (new Set(keys).size !== keys.length) {
    return { mode: 'schema', usable: false, reason: 'malformed', missingIdentityFields: [] };
  }
  const missingIdentityFields = IDENTITY_FIELD_KEYS.filter((key) => !keys.includes(key));
  if (missingIdentityFields.length > 0) {
    return { mode: 'schema', usable: false, reason: 'missing_identity', missingIdentityFields };
  }
  const missingCoreFields = CONNECTION_SCHEMA_CORE_FIELD_KEYS.filter((key) => !keys.includes(key));
  if (missingCoreFields.length > 0) {
    return {
      mode: 'schema',
      usable: false,
      reason: 'missing_core',
      missingIdentityFields: [],
      missingCoreFields,
    };
  }
  const states = evaluateConnectionFieldStates({}, fields);
  if (Object.values(states).some((state) => state.unknownCondition)) {
    return { mode: 'schema', usable: false, reason: 'unknown_condition', missingIdentityFields: [] };
  }
  if (hasUnsupportedStaticallyRequiredVisibleField(fields)) {
    return {
      mode: 'schema',
      usable: false,
      reason: 'unsupported_required_field',
      missingIdentityFields: [],
    };
  }
  if (IDENTITY_FIELD_KEYS.some((key) => !identityFieldIsUnconditionallyWritable(fields, key))) {
    return { mode: 'schema', usable: false, reason: 'identity_read_only', missingIdentityFields: [] };
  }
  return { mode: 'schema', usable: true, missingIdentityFields: [] };
}

/** Resolve the one authority used by edit, test, discovery, serialization and save. */
export function evaluateConnectionSchemaAuthority(
  values: Record<string, string>,
  fields: unknown,
): ConnectionSchemaAuthority {
  const definition = inspectConnectionSchemaDefinition(fields);
  if (definition.mode === 'legacy') {
    return { ...definition, states: {} };
  }

  if (
    !isConnectionFieldSchemaArray(fields)
    || (!definition.usable && definition.reason !== 'unknown_condition')
  ) {
    return { ...definition, states: {} };
  }
  const states = evaluateConnectionFieldStates(values, fields);
  if (Object.values(states).some((state) => state.unknownCondition)) {
    return {
      mode: 'schema',
      usable: false,
      reason: 'unknown_condition',
      missingIdentityFields: [],
      states,
    };
  }
  if (hasUnsupportedRequiredVisibleField(fields, states)) {
    return {
      mode: 'schema',
      usable: false,
      reason: 'unsupported_required_field',
      missingIdentityFields: [],
      states,
    };
  }
  return { ...definition, states };
}

export function isConnectionSchemaFieldWritable(
  authority: ConnectionSchemaAuthority,
  key: string,
): boolean {
  if (!authority.usable) {
    return false;
  }
  if (authority.mode === 'legacy') {
    return true;
  }
  const state = authority.states[key];
  return Boolean(state?.visible && state.enabled && !state.unknownCondition);
}

/** Return missing visible fields in backend schema order. */
export function validateConnectionContractValues(
  values: Record<string, string>,
  fields: unknown,
): string[] {
  if (!isConnectionFieldSchemaArray(fields)) {
    return [];
  }
  const states = evaluateConnectionFieldStates(values, fields);
  return fields
    .filter((field) => states[field.key]?.required && !values[field.key]?.trim())
    .map((field) => field.key);
}

export function hasUnknownConnectionFieldCondition(
  values: Record<string, string>,
  fields: unknown,
): boolean {
  if (!isConnectionFieldSchemaArray(fields)) {
    return false;
  }
  return Object.values(evaluateConnectionFieldStates(values, fields))
    .some((state) => state.unknownCondition);
}

export function isConnectionModelDiscoveryEnabled(
  values: Record<string, string>,
  fields: unknown,
): boolean {
  if (!isConnectionFieldSchemaArray(fields)) {
    return false;
  }
  const authority = evaluateConnectionSchemaAuthority(values, fields);
  if (!authority.usable || authority.mode !== 'schema') {
    return false;
  }
  const modelsState = authority.states.models;
  if (!modelsState?.visible || !modelsState.enabled || modelsState.unknownCondition) {
    return false;
  }
  return fields.every((field) => {
    const state = authority.states[field.key];
    if (field.key === 'models' || !state?.visible || !state.requiresConnectionTest) {
      return true;
    }
    return !state.required || Boolean(values[field.key]?.trim());
  });
}
