import { useState } from 'react';
import type React from 'react';
import { Trash2 } from 'lucide-react';
import { Badge, Button, CredentialInput, IconButton, Input, Select, Textarea, TimePicker } from '../common';
import type { ConfigValidationIssue, SystemConfigFieldSchema, SystemConfigItem } from '../../types/systemConfig';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { getSettingsHelpContent } from '../../locales/settingsHelp';
import { resolveSettingsFieldTitle } from '../../locales/settingsFieldTitle';
import { getFieldDescriptionZh, getFieldOptionLabel } from '../../utils/systemConfigI18n';
import type { UiLanguage, UiTextKey } from '../../i18n/uiText';
import { cn } from '../../utils/cn';
import { formatUiNumber, getUiColon } from '../../utils/uiLocale';
import { SettingsHelpButton } from './SettingsHelpButton';
import { MultiSelectDropdown } from './MultiSelectDropdown';
import { SettingsSwitch } from './SettingsSwitch';
import { SETTINGS_CONTROL_WIDTH_CLASS } from './settingsControlLayout';

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
  /** Restricts multi-enum options to those passing the filter (already-selected values always stay visible). */
  enumOptionFilter?: (value: string) => boolean;
  /** Rendered instead of the multi-enum control when the filter leaves no option and nothing is selected. */
  enumEmptyState?: React.ReactNode;
}

function renderFieldControl(
  item: SystemConfigItem,
  fieldTitle: string,
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
  enumOptionFilter?: (optionValue: string) => boolean,
  enumEmptyState?: React.ReactNode,
) {
  const schema = item.schema;
  const controlType = schema?.uiControl ?? 'text';
  const isMultiValue = isMultiValueField(item);
  const optionValues = (schema?.options ?? []).map((option) => (
    typeof option === 'string' ? option : option.value
  ));
  const isBooleanControl = controlType === 'switch'
    || schema?.dataType === 'boolean'
    || (
      optionValues.length === 2
      && optionValues.some((option) => option.toLowerCase() === 'true')
      && optionValues.some((option) => option.toLowerCase() === 'false')
    );

  // Multi-value enums (finite options + multi_value validation) render as a
  // collapsed multi-select dropdown so users pick from the catalog instead of
  // typing a comma-separated string. Stored values outside the catalog stay
  // visible and deselectable so saving never silently drops them.
  if (schema?.options?.length && isMultiValue) {
    const normalizedOptions = normalizeSelectOptions(item.key, schema.options, language);
    const selectedValues = value.split(',').map((entry) => entry.trim()).filter(Boolean);
    const visibleOptions = enumOptionFilter
      ? normalizedOptions.filter(
          (option) => enumOptionFilter(option.value) || selectedValues.includes(option.value),
        )
      : normalizedOptions;
    const validation = (schema.validation ?? {}) as Record<string, unknown>;
    const isOrdered = Boolean(validation.ordered);

    if (enumEmptyState && visibleOptions.length === 0 && selectedValues.length === 0) {
      return (
        <div data-testid={`multi-enum-empty-${item.key}`}>
          {enumEmptyState}
        </div>
      );
    }

    return (
      <MultiSelectDropdown
        id={controlId}
        testId={`multi-enum-${item.key}`}
        options={visibleOptions}
        selected={selectedValues}
        onChange={(next) => onChange(next.join(','))}
        ordered={isOrdered}
        disabled={disabled || !schema.isEditable}
        hasError={hasError}
        ariaDescribedBy={ariaDescribedBy}
        language={language}
      />
    );
  }

  if (isBooleanControl) {
    const checked = value.trim().toLowerCase() === 'true';
    const isDisabled = disabled || !schema?.isEditable;
    return (
      <div className="flex items-center gap-2 md:w-full md:justify-end">
        <SettingsSwitch
          id={controlId}
          checked={checked}
          disabled={isDisabled}
          onCheckedChange={(next) => onChange(next ? 'true' : 'false')}
          visualTestId={`${controlId}-switch-visual`}
          aria-invalid={hasError}
          aria-describedby={ariaDescribedBy}
        />
      </div>
    );
  }

  // Any field that declares a finite set of options is an enum: render a Select
  // regardless of the backend ui_control hint, so a stray ui_control=text never
  // degrades an enum into a free-text Input.
  if (schema?.options?.length && !isMultiValue) {
    const options = normalizeSelectOptions(item.key, schema.options, language).map((option) => {
      if (item.key !== 'MARKET_REVIEW_COLOR_SCHEME') {
        return option;
      }
      return {
        ...option,
        swatch: option.value === 'green_up'
          ? { start: 'success' as const, end: 'danger' as const }
          : { start: 'danger' as const, end: 'success' as const },
      };
    });
    return (
      <Select
        id={controlId}
        value={value}
        onChange={onChange}
        options={options}
        disabled={disabled || !schema.isEditable}
        placeholder={t('common.selectPlaceholder')}
        error={hasError}
        ariaDescribedBy={ariaDescribedBy}
        className={`${SETTINGS_CONTROL_WIDTH_CLASS} md:ml-auto`}
        menuAlign="end"
        size="comfortable"
      />
    );
  }

  if (controlType === 'textarea') {
    return (
      <Textarea
        id={controlId}
        aria-invalid={hasError || undefined}
        aria-describedby={ariaDescribedBy}
        fieldClassName={SETTINGS_CONTROL_WIDTH_CLASS}
        className={cn(hasError && 'border-danger')}
        value={value}
        disabled={disabled || !schema?.isEditable}
        onChange={(event) => onChange(event.target.value)}
      />
    );
  }

  if (controlType === 'time') {
    return (
      <TimePicker
        id={controlId}
        value={value}
        onChange={onChange}
        disabled={disabled || !schema?.isEditable}
        className={`${SETTINGS_CONTROL_WIDTH_CLASS} md:ml-auto`}
        size="comfortable"
        aria-invalid={hasError || undefined}
        aria-describedby={ariaDescribedBy}
      />
    );
  }

  if (controlType === 'password') {
    const iconType = inferPasswordIconType(item.key);

    if (isMultiValue) {
      const values = parseMultiValues(value);

      return (
        <div className="space-y-2">
          {values.map((entry, index) => {
            const rowLabel = `${fieldTitle} ${formatUiNumber(index + 1, language)}`;
            return (
              <div className="flex items-center gap-2" key={`${item.key}-${index}`}>
                <div className="flex-1">
                  <CredentialInput
                    purpose="configuration-secret"
                    credentialId={`${item.key}-${index + 1}`}
                    allowTogglePassword
                    passwordToggleLabel={rowLabel}
                    iconType={iconType}
                    id={index === 0 ? controlId : `${controlId}-${index}`}
                    aria-label={rowLabel}
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
                <IconButton
                  type="button"
                  variant="danger"
                  size="comfortable"
                  className="text-muted-text shadow-none hover:text-danger"
                  aria-label={`${t('settings.fieldDelete')}${getUiColon(language)}${rowLabel}`}
                  disabled={disabled || !schema?.isEditable || values.length <= 1}
                  onClick={() => {
                    const nextValues = values.filter((_, rowIndex) => rowIndex !== index);
                    onChange(serializeMultiValues(nextValues.length ? nextValues : ['']));
                  }}
                >
                  <Trash2 aria-hidden="true" className="h-4 w-4" />
                </IconButton>
              </div>
            );
          })}

          <div className="flex items-center gap-2">
            <Button
              type="button"
              variant="secondary"
              size="default"
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
      <CredentialInput
        purpose="configuration-secret"
        credentialId={item.key}
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

  const inputType = controlType === 'number' ? 'number' : 'text';
  const validation = (schema?.validation ?? {}) as Record<string, unknown>;
  const numberProps = controlType === 'number'
    ? {
        min: typeof validation.min === 'number' ? validation.min : undefined,
        max: typeof validation.max === 'number' ? validation.max : undefined,
        step: schema?.dataType === 'number' ? 0.1 : 1,
      }
    : {};

  const unit = schema?.unit?.trim() || null;
  return (
    <Input
      id={controlId}
      type={inputType}
      aria-invalid={hasError || undefined}
      aria-describedby={ariaDescribedBy}
      fieldClassName={SETTINGS_CONTROL_WIDTH_CLASS}
      className={cn(
        'block md:ml-auto md:w-full',
        hasError && 'border-danger/40 focus:border-danger',
      )}
      value={value}
      disabled={disabled || !schema?.isEditable}
      onChange={(event) => onChange(event.target.value)}
      trailingAction={unit ? (
        <span aria-hidden="true" className="pointer-events-none pr-3 text-xs text-muted-text">
          {unit}
        </span>
      ) : undefined}
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
  enumOptionFilter,
  enumEmptyState,
}) => {
  const { language, t } = useUiLanguage();
  const schema = item.schema;
  const isMultiEnum = Boolean(schema?.options?.length && isMultiValueField(item));
  const isTextarea = schema?.uiControl === 'textarea' && !isMultiEnum;
  const helpContent = getSettingsHelpContent(schema?.helpKey, schema?.description, language);
  const localizationKey = schema?.key ?? item.key;
  const fallbackTitle = schema?.title ?? item.key;
  const title = resolveSettingsFieldTitle({
    itemKey: item.key,
    schemaKey: schema?.key,
    fallbackTitle,
    language,
  });
  const description = language === 'zh'
    ? getFieldDescriptionZh(localizationKey, getFieldDescriptionZh(item.key, schema?.description))
    : helpContent?.summary ?? schema?.description ?? '';
  const hasError = issues.some((issue) => issue.severity === 'error');
  const [isPasswordEditable, setIsPasswordEditable] = useState(false);
  const controlId = `setting-${item.key}`;
  const issueDescriptionIds = issues.map((_, index) => `${controlId}-issue-${index}`);
  const ariaDescribedBy = issueDescriptionIds.join(' ') || undefined;
  const displayValue = resolveDisplayValue(item, value);

  return (
    <div
      data-settings-field-row="true"
      data-testid={`settings-field-${item.key}`}
      className={cn(
        'grid gap-2 px-2 py-1.5 transition-colors duration-200',
        isTextarea ? 'md:gap-2' : 'md:grid-cols-[minmax(0,1fr)_240px] md:items-center md:gap-4',
        hasError ? 'bg-danger/5' : '',
      )}
    >
      <div className="min-w-0 space-y-1">
        <div className="flex flex-wrap items-center gap-2">
          <label className="text-sm font-normal text-foreground" htmlFor={controlId}>
            {title}
          </label>
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
        {/* External docs links and raw KEY=value examples stay out of everyday fields. */}
        {readOnlyDiagnostic ? (
          <p className="text-xs text-warning" data-testid={`settings-schema-diagnostic-${item.key}`}>
            {readOnlyDiagnostic}
          </p>
        ) : null}
      </div>

      <div data-settings-control-column="true" className={cn('min-w-0', !isTextarea && 'md:w-full md:justify-self-end')}>
        {renderFieldControl(
          item,
          title,
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
          enumOptionFilter,
          enumEmptyState,
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
