// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { useMemo, useState } from 'react';
import type React from 'react';
import type {
  PluginSettingField,
  PluginSettingValue,
  PluginSettingsResponse,
} from '../../api/plugins';
import type { UiTextKey } from '../../i18n/uiText';
import {
  Button,
  CredentialInput,
  InlineAlert,
  Input,
  Modal,
  Select,
  Textarea,
} from '../common';
import { SettingsSwitch } from './SettingsSwitch';

type PluginSettingsModalProps = {
  pluginName: string;
  settings: PluginSettingsResponse;
  disabled?: boolean;
  saveError?: string | null;
  onClose: () => void;
  onSave: (values: Record<string, PluginSettingValue>) => Promise<void>;
  t: (key: UiTextKey, params?: Record<string, string | number>) => string;
};

type DraftValues = Record<string, PluginSettingValue>;

function serializedOptionValue(value: PluginSettingValue): string {
  return `${typeof value}:${JSON.stringify(value)}`;
}

function initialDraft(settings: PluginSettingsResponse): DraftValues {
  const values: DraftValues = {};
  settings.schema.forEach((field) => {
    const current = settings.values[field.key] ?? field.defaultValue;
    if (current !== null && current !== undefined) values[field.key] = current;
  });
  return values;
}

function parseDraft(
  schema: PluginSettingField[],
  draft: DraftValues,
): { values: DraftValues; issues: Record<string, string> } {
  const values: DraftValues = {};
  const issues: Record<string, string> = {};
  schema.forEach((field) => {
    const raw = draft[field.key];
    if (raw === undefined || raw === null || (typeof raw === 'string' && raw === '')) {
      if (field.isRequired) issues[field.key] = 'required';
      return;
    }
    if (field.dataType === 'integer' || field.dataType === 'number') {
      const numeric = typeof raw === 'number' ? raw : Number(raw);
      if (!Number.isFinite(numeric) || (field.dataType === 'integer' && !Number.isInteger(numeric))) {
        issues[field.key] = field.dataType;
        return;
      }
      const minimum = field.validation.minimum;
      const maximum = field.validation.maximum;
      if (typeof minimum === 'number' && numeric < minimum) {
        issues[field.key] = 'range';
        return;
      }
      if (typeof maximum === 'number' && numeric > maximum) {
        issues[field.key] = 'range';
        return;
      }
      values[field.key] = numeric;
      return;
    }
    values[field.key] = raw;
  });
  return { values, issues };
}

const PluginField: React.FC<{
  field: PluginSettingField;
  value: PluginSettingValue | undefined;
  disabled: boolean;
  issue?: string;
  onChange: (value: PluginSettingValue) => void;
  t: PluginSettingsModalProps['t'];
}> = ({ field, value, disabled, issue, onChange, t }) => {
  const id = `plugin-setting-${field.key}`;
  const errorId = issue ? `${id}-error` : undefined;
  const inputValue = value === undefined || value === null ? '' : String(value);
  const commonProps = {
    id,
    disabled,
    'aria-invalid': Boolean(issue) || undefined,
    'aria-describedby': errorId,
  };

  let control: React.ReactNode;
  if (field.uiControl === 'switch') {
    control = (
      <SettingsSwitch
        id={id}
        checked={value === true}
        disabled={disabled}
        onCheckedChange={onChange}
        aria-label={field.title}
        aria-invalid={Boolean(issue) || undefined}
        aria-describedby={errorId}
      />
    );
  } else if (field.uiControl === 'select') {
    control = (
      <Select
        id={id}
        value={serializedOptionValue(value ?? null)}
        disabled={disabled}
        ariaLabel={field.title}
        ariaDescribedBy={errorId}
        error={Boolean(issue)}
        options={field.options.map((option) => ({
          label: option.label,
          value: serializedOptionValue(option.value),
        }))}
        onChange={(next) => {
          const selected = field.options.find(
            (option) => serializedOptionValue(option.value) === next,
          );
          if (selected) onChange(selected.value);
        }}
      />
    );
  } else if (field.uiControl === 'textarea') {
    control = (
      <Textarea
        {...commonProps}
        value={inputValue}
        onChange={(event) => onChange(event.target.value)}
      />
    );
  } else if (field.uiControl === 'password') {
    control = (
      <CredentialInput
        {...commonProps}
        purpose="configuration-secret"
        credentialId={`plugin-${field.key}`}
        allowTogglePassword
        passwordToggleLabel={field.title}
        value={inputValue}
        onChange={(event) => onChange(event.target.value)}
      />
    );
  } else {
    const minimum = field.validation.minimum;
    const maximum = field.validation.maximum;
    control = (
      <Input
        {...commonProps}
        type={field.uiControl === 'number' ? 'number' : 'text'}
        value={inputValue}
        min={typeof minimum === 'number' ? minimum : undefined}
        max={typeof maximum === 'number' ? maximum : undefined}
        step={field.dataType === 'integer' ? 1 : 'any'}
        minLength={typeof field.validation.minLength === 'number' ? field.validation.minLength : undefined}
        maxLength={typeof field.validation.maxLength === 'number' ? field.validation.maxLength : undefined}
        pattern={typeof field.validation.pattern === 'string' ? field.validation.pattern : undefined}
        onChange={(event) => onChange(event.target.value)}
      />
    );
  }

  return (
    <div className="space-y-1.5" data-testid={`plugin-settings-field-${field.key}`}>
      <div className="flex items-center justify-between gap-3">
        <label htmlFor={id} className="text-sm font-medium text-foreground">
          {field.title}
          {field.isRequired ? <span aria-hidden="true" className="ml-1 text-danger">*</span> : null}
        </label>
        {field.uiControl === 'switch' ? control : null}
      </div>
      {field.description ? <p className="text-xs leading-5 text-secondary-text">{field.description}</p> : null}
      {field.uiControl !== 'switch' ? control : null}
      {issue ? (
        <p id={errorId} className="text-xs text-danger">
          {t(issue === 'required'
            ? 'settings.pluginSettingsRequired'
            : 'settings.pluginSettingsInvalid')}
        </p>
      ) : null}
    </div>
  );
};

const PluginSettingsModal: React.FC<PluginSettingsModalProps> = ({
  pluginName,
  settings,
  disabled = false,
  saveError,
  onClose,
  onSave,
  t,
}) => {
  const [draft, setDraft] = useState<DraftValues>(() => initialDraft(settings));
  const [issues, setIssues] = useState<Record<string, string>>({});
  const [isSaving, setIsSaving] = useState(false);
  const sortedSchema = useMemo(
    () => [...settings.schema].sort((left, right) => left.displayOrder - right.displayOrder || left.key.localeCompare(right.key)),
    [settings.schema],
  );

  const submit = async () => {
    const parsed = parseDraft(sortedSchema, draft);
    setIssues(parsed.issues);
    if (Object.keys(parsed.issues).length > 0) return;
    setIsSaving(true);
    try {
      await onSave(parsed.values);
    } catch {
      // The parent keeps the dialog open and renders the locally parsed API error.
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <Modal
      isOpen
      onClose={onClose}
      closeDisabled={isSaving}
      title={t('settings.pluginSettingsTitle', { name: pluginName })}
      description={t('settings.pluginSettingsDescription')}
      footer={(
        <>
          <Button variant="ghost" disabled={isSaving} onClick={onClose}>
            {t('common.cancel')}
          </Button>
          <Button variant="primary" isLoading={isSaving} onClick={() => { void submit(); }}>
            {t('settings.pluginSettingsSave')}
          </Button>
        </>
      )}
    >
      <div className="space-y-4">
        {saveError ? (
          <InlineAlert
            variant="danger"
            title={t('settings.pluginSettingsSaveFailed')}
            message={saveError}
          />
        ) : null}
        {sortedSchema.map((field) => (
          <PluginField
            key={field.key}
            field={field}
            value={draft[field.key]}
            disabled={disabled || isSaving}
            issue={issues[field.key]}
            t={t}
            onChange={(next) => {
              setDraft((current) => ({ ...current, [field.key]: next }));
              setIssues((current) => {
                const nextIssues = { ...current };
                delete nextIssues[field.key];
                return nextIssues;
              });
            }}
          />
        ))}
      </div>
    </Modal>
  );
};

export default PluginSettingsModal;
