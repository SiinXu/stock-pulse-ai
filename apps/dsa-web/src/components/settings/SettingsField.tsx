import { useState } from 'react';
import type React from 'react';
import { Info, Trash2 } from 'lucide-react';
import { Badge, Button, Select, Input, Tooltip } from '../common';
import type { ConfigValidationIssue, SystemConfigFieldSchema, SystemConfigItem } from '../../types/systemConfig';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { getSettingsHelpContent } from '../../locales/settingsHelp';
import { getFieldDescriptionZh, getFieldOptionLabel, getFieldTitleZh } from '../../utils/systemConfigI18n';
import type { UiLanguage, UiTextKey } from '../../i18n/uiText';
import { cn } from '../../utils/cn';
import { SettingsHelpButton } from './SettingsHelpButton';

function normalizeSelectOptions(key: string, options: SystemConfigFieldSchema['options'] = [], locale: UiLanguage) {
  return options.map((option) => {
    if (typeof option === 'string') {
      return { value: option, label: getFieldOptionLabel(key, option, undefined, locale) };
    }

    return {
      ...option,
      label: getFieldOptionLabel(key, option.value, option.label, locale),
    };
  });
}

function isMultiValueField(item: SystemConfigItem): boolean {
  const validation = (item.schema?.validation ?? {}) as Record<string, unknown>;
  return Boolean(validation.multiValue ?? validation.multi_value);
}

function parseMultiValues(value: string): string[] {
  if (!value) {
    return [''];
  }

  const values = value.split(',').map((entry) => entry.trim());
  return values.length ? values : [''];
}

function serializeMultiValues(values: string[]): string {
  return values.map((entry) => entry.trim()).join(',');
}

function inferPasswordIconType(key: string): 'password' | 'key' {
  return key.toUpperCase().includes('PASSWORD') ? 'password' : 'key';
}

function resolveDisplayValue(item: SystemConfigItem, value: string): string {
  const schema = item.schema;

  // Backfill the backend default for unset fields so the effective value is
  // visible instead of a blank control. Passwords are excluded so a secret-ish
  // default can never leak into a visible input.
  if (
    schema?.uiControl !== 'password'
    && !value
    && item.rawValueExists === false
    && schema?.defaultValue !== undefined
    && schema?.defaultValue !== null
    && schema.defaultValue !== ''
  ) {
    return schema.defaultValue;
  }

  return value;
}

interface SettingsFieldProps {
  item: SystemConfigItem;
  value: string;
  disabled?: boolean;
  onChange: (key: string, value: string) => void;
  issues?: ConfigValidationIssue[];
  /** Effective requirement from the field's schema contract. */
  requirement?: 'required' | 'optional' | 'inherited' | null;
  /** True when the field's enabledWhen conditions are not met (read-only). */
  dependencyLocked?: boolean;
  /** Fail-safe schema diagnostic that forces a field into read-only mode. */
  readOnlyDiagnostic?: string;
}

function renderFieldControl(
  item: SystemConfigItem,
  value: string,
  disabled: boolean,
  onChange: (nextValue: string) => void,
  isPasswordEditable: boolean,
  onPasswordFocus: () => void,
  controlId: string,
  hasError: boolean,
  ariaDescribedBy: string | undefined,
  language: UiLanguage,
  t: (key: UiTextKey) => string,
) {
  const schema = item.schema;
  const commonClass = 'w-full rounded-lg border border-border bg-transparent px-3 text-xs text-foreground placeholder:text-muted-text transition-colors duration-200 focus:outline-none focus:border-muted-text disabled:cursor-not-allowed disabled:opacity-60';
  const controlType = schema?.uiControl ?? 'text';
  const isMultiValue = isMultiValueField(item);

  // Multi-value enums (finite options + multi_value validation) render as a
  // checkbox group so users pick from the catalog instead of typing a
  // comma-separated string. Stored values outside the catalog stay visible and
  // deselectable so saving never silently drops them.
  if (schema?.options?.length && isMultiValue) {
    const normalizedOptions = normalizeSelectOptions(item.key, schema.options, language);
    const selectedValues = value.split(',').map((entry) => entry.trim()).filter(Boolean);
    const knownValues = new Set(normalizedOptions.map((option) => option.value));
    const unknownValues = selectedValues.filter((entry) => !knownValues.has(entry));
    const isDisabled = disabled || !schema.isEditable;

    const toggleValue = (target: string) => {
      const selected = new Set(selectedValues);
      if (selected.has(target)) {
        selected.delete(target);
      } else {
        selected.add(target);
      }
      const orderedKnown = normalizedOptions
        .map((option) => option.value)
        .filter((candidate) => selected.has(candidate));
      const keptUnknown = unknownValues.filter((entry) => selected.has(entry));
      onChange([...orderedKnown, ...keptUnknown].join(','));
    };

    return (
      <div
        role="group"
        aria-invalid={hasError || undefined}
        aria-describedby={ariaDescribedBy}
        className="max-h-48 space-y-2 overflow-y-auto rounded-lg border border-border p-3"
        data-testid={`multi-enum-${item.key}`}
      >
        {normalizedOptions.map((option, index) => (
          <label key={option.value} className="flex min-h-11 items-center gap-2 text-xs text-secondary-text">
            <input
              id={index === 0 ? controlId : undefined}
              type="checkbox"
              checked={selectedValues.includes(option.value)}
              disabled={isDisabled}
              onChange={() => toggleValue(option.value)}
              className="settings-input-checkbox h-4 w-4 rounded border-border/70 bg-base"
            />
            <span className="min-w-0 truncate">{option.label}</span>
          </label>
        ))}
        {unknownValues.map((entry) => (
          <label key={`unknown-${entry}`} className="flex min-h-11 items-center gap-2 text-xs text-secondary-text">
            <input
              type="checkbox"
              checked
              disabled={isDisabled}
              onChange={() => toggleValue(entry)}
              className="settings-input-checkbox h-4 w-4 rounded border-border/70 bg-base"
            />
            <span className="min-w-0 truncate">{entry}</span>
          </label>
        ))}
      </div>
    );
  }

  // Any field that declares a finite set of options is an enum: render a Select
  // regardless of the backend ui_control hint, so a stray ui_control=text never
  // degrades an enum into a free-text Input.
  if (schema?.options?.length && !isMultiValue) {
    return (
        <Select
          id={controlId}
          value={value}
          onChange={onChange}
          options={normalizeSelectOptions(item.key, schema.options, language)}
          disabled={disabled || !schema.isEditable}
          placeholder={t('common.selectPlaceholder')}
          error={hasError}
          ariaDescribedBy={ariaDescribedBy}
          className="md:ml-auto"
          menuAlign="end"
        />
      );
  }

  if (controlType === 'textarea') {
    return (
      <textarea
        id={controlId}
        aria-invalid={hasError || undefined}
        aria-describedby={ariaDescribedBy}
        className={cn(commonClass, 'min-h-24 resize-y py-2', hasError && 'border-danger')}
        value={value}
        disabled={disabled || !schema?.isEditable}
        onChange={(event) => onChange(event.target.value)}
      />
    );
  }

  if (controlType === 'switch') {
    const checked = value.trim().toLowerCase() === 'true';
    const isDisabled = disabled || !schema?.isEditable;
    return (
      <div className="flex items-center gap-2 md:w-full md:justify-end">
        <button
          id={controlId}
          type="button"
          role="switch"
          aria-checked={checked}
          aria-invalid={hasError || undefined}
          aria-describedby={ariaDescribedBy}
          disabled={isDisabled}
          onClick={() => onChange(checked ? 'false' : 'true')}
          className={cn(
            'inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-lg transition-colors',
            isDisabled ? 'cursor-not-allowed opacity-60' : 'cursor-pointer',
          )}
        >
          <span
            className={cn(
              'relative inline-flex h-5 w-8 shrink-0 items-center rounded-full transition-colors',
              checked ? 'bg-foreground' : 'bg-border',
            )}
            data-testid={`${controlId}-switch-visual`}
            aria-hidden="true"
          >
            <span
              className={cn(
                'inline-block h-4 w-4 rounded-full bg-background shadow-sm transition-transform',
                checked ? 'translate-x-3' : 'translate-x-0.5',
              )}
            />
          </span>
        </button>
      </div>
    );
  }

  if (controlType === 'password') {
    const iconType = inferPasswordIconType(item.key);

    if (isMultiValue) {
      const values = parseMultiValues(value);

      return (
        <div className="space-y-2">
          {values.map((entry, index) => (
            <div className="flex items-center gap-2" key={`${item.key}-${index}`}>
              <div className="flex-1">
                <Input
                  type="password"
                  allowTogglePassword
                  iconType={iconType}
                  id={index === 0 ? controlId : `${controlId}-${index}`}
                  aria-invalid={hasError || undefined}
                  aria-describedby={ariaDescribedBy}
                  readOnly={!isPasswordEditable}
                  onFocus={onPasswordFocus}
                  value={entry}
                  disabled={disabled || !schema?.isEditable}
                  onChange={(event) => {
                    const nextValues = [...values];
                    nextValues[index] = event.target.value;
                    onChange(serializeMultiValues(nextValues));
                  }}
                />
              </div>
              <Button
                type="button"
                variant="settings-secondary"
                size="lg"
                className="px-3 text-muted-text shadow-none hover:text-danger"
                aria-label={t('settings.fieldDelete')}
                disabled={disabled || !schema?.isEditable || values.length <= 1}
                onClick={() => {
                  const nextValues = values.filter((_, rowIndex) => rowIndex !== index);
                  onChange(serializeMultiValues(nextValues.length ? nextValues : ['']));
                }}
              >
                <Trash2 aria-hidden="true" className="h-4 w-4" />
              </Button>
            </div>
          ))}

          <div className="flex items-center gap-2">
            <Button
              type="button"
              variant="settings-secondary"
              size="sm"
              className="text-xs shadow-none"
              disabled={disabled || !schema?.isEditable}
              onClick={() => onChange(serializeMultiValues([...values, '']))}
            >
              {t('settings.fieldAddKey')}
            </Button>
          </div>
        </div>
      );
    }

    return (
      <Input
        type="password"
        allowTogglePassword
        iconType={iconType}
        id={controlId}
        aria-invalid={hasError || undefined}
        aria-describedby={ariaDescribedBy}
        readOnly={!isPasswordEditable}
        onFocus={onPasswordFocus}
        value={value}
        disabled={disabled || !schema?.isEditable}
        onChange={(event) => onChange(event.target.value)}
      />
    );
  }

  const inputType = controlType === 'number' ? 'number' : controlType === 'time' ? 'time' : 'text';
  const validation = (schema?.validation ?? {}) as Record<string, unknown>;
  const numberProps = controlType === 'number'
    ? {
        min: typeof validation.min === 'number' ? validation.min : undefined,
        max: typeof validation.max === 'number' ? validation.max : undefined,
        step: schema?.dataType === 'number' ? 0.1 : 1,
      }
    : {};

  return (
    <input
      id={controlId}
      type={inputType}
      aria-invalid={hasError || undefined}
      aria-describedby={ariaDescribedBy}
      className={cn(commonClass, 'block h-11 md:ml-auto md:w-44', hasError && 'border-danger')}
      value={value}
      disabled={disabled || !schema?.isEditable}
      onChange={(event) => onChange(event.target.value)}
      {...numberProps}
    />
  );
}

export const SettingsField: React.FC<SettingsFieldProps> = ({
  item,
  value,
  disabled = false,
  onChange,
  issues = [],
  requirement = null,
  dependencyLocked = false,
  readOnlyDiagnostic,
}) => {
  const { language, t } = useUiLanguage();
  const schema = item.schema;
  const isTextarea = schema?.uiControl === 'textarea';
  const helpContent = getSettingsHelpContent(schema?.helpKey, schema?.description, language);
  const localizationKey = schema?.key ?? item.key;
  const fallbackTitle = schema?.title ?? item.key;
  const title = language === 'zh'
    ? getFieldTitleZh(localizationKey, getFieldTitleZh(item.key, fallbackTitle))
    : fallbackTitle;
  const description = language === 'en'
    ? helpContent?.summary ?? schema?.description ?? ''
    : getFieldDescriptionZh(localizationKey, getFieldDescriptionZh(item.key, schema?.description));
  const hasError = issues.some((issue) => issue.severity === 'error');
  const [isPasswordEditable, setIsPasswordEditable] = useState(false);
  const controlId = `setting-${item.key}`;
  const issueDescriptionIds = issues.map((_, index) => `${controlId}-issue-${index}`);
  const ariaDescribedBy = issueDescriptionIds.join(' ') || undefined;
  const displayValue = resolveDisplayValue(item, value);

  return (
    <div
      className={cn(
        'grid gap-3 px-3 py-2.5 transition-colors duration-200',
        isTextarea ? 'md:gap-2' : 'md:grid-cols-[minmax(0,1fr)_240px] md:gap-6',
        hasError ? 'bg-danger/5' : '',
      )}
    >
      <div className="min-w-0 space-y-2">
        <div className="flex flex-wrap items-center gap-2">
          <label className="text-sm font-normal text-foreground" htmlFor={controlId}>
            {title}
          </label>
          {description ? (
            <Tooltip content={description}>
              <span className="inline-flex cursor-help text-muted-text">
                <Info aria-hidden="true" className="h-3.5 w-3.5" />
              </span>
            </Tooltip>
          ) : null}
          <SettingsHelpButton
            fieldKey={localizationKey}
            title={title}
            schema={schema}
            description={description}
            rawValueExists={item.rawValueExists}
          />
          {!schema?.isEditable || readOnlyDiagnostic ? (
            <Badge variant="default" size="sm">
              {t('common.readOnly')}
            </Badge>
          ) : null}
          {requirement === 'required' ? (
            <Badge variant="warning" size="sm">{t('settings.fieldRequired')}</Badge>
          ) : requirement === 'inherited' ? (
            <Badge variant="default" size="sm">{t('settings.fieldInherited')}</Badge>
          ) : requirement === 'optional' ? (
            <Badge variant="default" size="sm">{t('settings.fieldOptional')}</Badge>
          ) : null}
          {dependencyLocked && requirement !== 'inherited' && !readOnlyDiagnostic ? (
            <Badge variant="default" size="sm">{t('settings.fieldDependencyLocked')}</Badge>
          ) : null}
          {schema?.warningCodes?.includes('restart_required') ? (
            <Badge variant="default" size="sm">{t('settings.fieldRestartRequired')}</Badge>
          ) : null}
        </div>
        {/* External docs links and raw KEY=value examples are intentionally not
            shown inline on everyday fields — they live in the field's help
            dialog instead, so the everyday path stays free of config jargon. */}
        {readOnlyDiagnostic ? (
          <p className="text-xs text-warning" data-testid={`settings-schema-diagnostic-${item.key}`}>
            {readOnlyDiagnostic}
          </p>
        ) : null}
      </div>

      <div className={cn('min-w-0', !isTextarea && 'md:justify-self-end md:w-full')}>
        {renderFieldControl(
          item,
          displayValue,
          disabled || dependencyLocked || Boolean(readOnlyDiagnostic),
          (nextValue) => onChange(item.key, nextValue),
          isPasswordEditable,
          () => setIsPasswordEditable(true),
          controlId,
          hasError,
          ariaDescribedBy,
          language,
          t,
        )}

        {issues.length ? (
          <div className="mt-2 space-y-1">
            {issues.map((issue, index) => (
              <p
                id={issueDescriptionIds[index]}
                key={`${issue.code}-${issue.key}-${index}`}
                className={issue.severity === 'error' ? 'text-xs text-danger' : 'text-xs text-warning'}
              >
                {issue.message}
              </p>
            ))}
          </div>
        ) : null}
      </div>
    </div>
  );
};
