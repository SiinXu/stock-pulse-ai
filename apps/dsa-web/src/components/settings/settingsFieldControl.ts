import type { SystemConfigFieldSchema } from '../../types/systemConfig';

/**
 * Resolved interactive control for a Settings field.
 *
 * The mapping is the Web-side contract that keeps boolean / enum / number /
 * sensitive fields usable even when the backend `uiControl` hint is missing
 * or wrong (common for auto-inferred uncategorized keys).
 */
export type ResolvedSettingsControl =
  | 'multi-select'
  | 'switch'
  | 'select'
  | 'textarea'
  | 'time'
  | 'password'
  | 'number'
  | 'text';

export type SettingsFieldControlSchema = Pick<
  SystemConfigFieldSchema,
  'uiControl' | 'dataType' | 'options' | 'isSensitive' | 'validation'
>;

export function isMultiValueValidation(
  validation: Record<string, unknown> | undefined | null,
): boolean {
  if (!validation) {
    return false;
  }
  return Boolean(validation.multiValue ?? validation.multi_value);
}

function optionValues(
  options: SystemConfigFieldSchema['options'] | undefined,
): string[] {
  return (options ?? []).map((option) => (
    typeof option === 'string' ? option : option.value
  ));
}

/** True when the option set is exactly a boolean pair (order independent). */
export function isBooleanishOptionSet(
  options: SystemConfigFieldSchema['options'] | undefined,
): boolean {
  const values = optionValues(options);
  if (values.length !== 2) {
    return false;
  }
  const lowered = values.map((value) => value.toLowerCase());
  return lowered.includes('true') && lowered.includes('false');
}

/**
 * Resolve the control kind from field schema.
 *
 * Precedence (first match wins):
 * 1. multi-value enum options → multi-select
 * 2. switch / boolean dataType / true|false options → switch
 * 3. finite options → select
 * 4. textarea / json / array dataType → textarea
 * 5. time control or dataType → time
 * 6. password / isSensitive / isMasked → password
 * 7. number control or integer|number dataType → number
 * 8. text
 *
 * `dataType`, options, and sensitivity intentionally override a mismatched
 * `uiControl` so uncategorized / auto-inferred fields still render correctly.
 */
export function resolveSettingsFieldControl(
  schema: SettingsFieldControlSchema | undefined | null,
  options?: { isMasked?: boolean },
): ResolvedSettingsControl {
  if (!schema) {
    return options?.isMasked ? 'password' : 'text';
  }

  const validation = (schema.validation ?? {}) as Record<string, unknown>;
  const multiValue = isMultiValueValidation(validation);
  const hasOptions = Boolean(schema.options?.length);

  if (hasOptions && multiValue) {
    return 'multi-select';
  }

  if (
    schema.uiControl === 'switch'
    || schema.dataType === 'boolean'
    || isBooleanishOptionSet(schema.options)
  ) {
    return 'switch';
  }

  if (hasOptions) {
    return 'select';
  }

  if (
    schema.uiControl === 'textarea'
    || schema.dataType === 'json'
    || schema.dataType === 'array'
  ) {
    return 'textarea';
  }

  if (schema.uiControl === 'time' || schema.dataType === 'time') {
    return 'time';
  }

  if (
    schema.uiControl === 'password'
    || schema.isSensitive
    || options?.isMasked
  ) {
    return 'password';
  }

  if (
    schema.uiControl === 'number'
    || schema.dataType === 'integer'
    || schema.dataType === 'number'
  ) {
    return 'number';
  }

  return 'text';
}

/** min / max / step attributes for number controls from schema validation. */
export function numberControlBounds(
  schema: Pick<SystemConfigFieldSchema, 'dataType' | 'validation'> | undefined | null,
): { min?: number; max?: number; step: number } {
  const validation = (schema?.validation ?? {}) as Record<string, unknown>;
  return {
    min: typeof validation.min === 'number' ? validation.min : undefined,
    max: typeof validation.max === 'number' ? validation.max : undefined,
    step: schema?.dataType === 'number' ? 0.1 : 1,
  };
}
