import { useState } from 'react';
import { fireEvent, render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type {
  ConfigValidationIssue,
  SystemConfigDataType,
  SystemConfigFieldSchema,
  SystemConfigItem,
  SystemConfigUIControl,
} from '../../../types/systemConfig';
import { UiLanguageProvider } from '../../../contexts/UiLanguageContext';
import { SettingsField } from '../SettingsField';

// jsdom does not implement scrollIntoView; Select uses it when opening.
if (!HTMLElement.prototype.scrollIntoView) {
  HTMLElement.prototype.scrollIntoView = () => {};
}

function openListbox(trigger: HTMLElement) {
  fireEvent.click(trigger);
  return document.getElementById(trigger.getAttribute('aria-controls')!)!;
}

function buildItem(partial: {
  key: string;
  value?: string;
  rawValueExists?: boolean;
  isMasked?: boolean;
  title?: string;
  category?: SystemConfigFieldSchema['category'];
  dataType: SystemConfigDataType;
  uiControl?: SystemConfigUIControl;
  options?: SystemConfigFieldSchema['options'];
  isSensitive?: boolean;
  validation?: Record<string, unknown>;
  defaultValue?: string | null;
}): SystemConfigItem {
  return {
    key: partial.key,
    value: partial.value ?? '',
    rawValueExists: partial.rawValueExists ?? true,
    isMasked: partial.isMasked ?? false,
    schema: {
      key: partial.key,
      title: partial.title ?? partial.key,
      category: partial.category ?? 'uncategorized',
      dataType: partial.dataType,
      uiControl: partial.uiControl ?? 'text',
      isSensitive: partial.isSensitive ?? false,
      isRequired: false,
      isEditable: true,
      defaultValue: partial.defaultValue,
      options: partial.options ?? [],
      validation: partial.validation ?? {},
      displayOrder: 9000,
    },
  };
}

/**
 * Interactive contract: given a field schema, SettingsField must mount the
 * control kind implied by dataType / options / sensitivity — never a free-text
 * box for typed fields — including when the field is uncategorized and
 * uiControl is wrong.
 */
describe('SettingsField control render contract', () => {
  it('renders boolean uncategorized keys as switch (not text), including wrong uiControl', () => {
    const onChange = vi.fn();
    render(
      <UiLanguageProvider initialLanguage="en">
        <SettingsField
          item={buildItem({
            key: 'CRYPTO_PROVIDER_ENABLED',
            value: 'false',
            dataType: 'boolean',
            uiControl: 'text',
            title: 'Crypto Provider Enabled',
          })}
          value="false"
          onChange={onChange}
        />
      </UiLanguageProvider>,
    );

    const toggle = screen.getByRole('switch', { name: 'Crypto Provider Enabled' });
    expect(toggle).toHaveAttribute('aria-checked', 'false');
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
    expect(screen.queryByRole('spinbutton')).not.toBeInTheDocument();
    fireEvent.click(toggle);
    expect(onChange).toHaveBeenCalledWith('CRYPTO_PROVIDER_ENABLED', 'true');
  });

  it('renders string options as select for uncategorized enums with uiControl=text', () => {
    const onChange = vi.fn();
    render(
      <UiLanguageProvider initialLanguage="en">
        <SettingsField
          item={buildItem({
            key: 'PROVIDER_MARKET_DATA_MODE',
            value: 'auto',
            dataType: 'string',
            uiControl: 'text',
            options: ['auto', 'live', 'cached'],
            title: 'Provider Market Data Mode',
          })}
          value="auto"
          onChange={onChange}
        />
      </UiLanguageProvider>,
    );

    const select = screen.getByRole('combobox', { name: 'Provider Market Data Mode' });
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
    const listbox = openListbox(select);
    fireEvent.click(within(listbox).getByRole('option', { name: 'live' }));
    expect(onChange).toHaveBeenCalledWith('PROVIDER_MARKET_DATA_MODE', 'live');
  });

  it('renders integer uncategorized keys as number with min/max range hints', () => {
    render(
      <UiLanguageProvider initialLanguage="en">
        <SettingsField
          item={buildItem({
            key: 'DATA_VALIDATION_MAX_RETRIES',
            value: '3',
            dataType: 'integer',
            uiControl: 'text',
            validation: { min: 0, max: 10 },
            title: 'Data Validation Max Retries',
          })}
          value="3"
          onChange={vi.fn()}
        />
      </UiLanguageProvider>,
    );

    const input = screen.getByRole('spinbutton', { name: 'Data Validation Max Retries' });
    expect(input).toHaveAttribute('type', 'number');
    expect(input).toHaveAttribute('min', '0');
    expect(input).toHaveAttribute('max', '10');
    expect(input).toHaveAttribute('step', '1');
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
  });

  it('renders sensitive uncategorized keys as masked password (no plaintext echo)', () => {
    render(
      <UiLanguageProvider initialLanguage="en">
        <SettingsField
          item={buildItem({
            key: 'MCP_SERVER_TOKEN',
            value: 'super-secret-token',
            dataType: 'string',
            uiControl: 'text',
            isSensitive: true,
            title: 'MCP Server Token',
          })}
          value="super-secret-token"
          onChange={vi.fn()}
        />
      </UiLanguageProvider>,
    );

    const input = screen.getByLabelText('MCP Server Token');
    // CredentialInput always uses type=password so the value is never shown as
    // a plain textbox; browser password managers stay off via autocomplete=off.
    expect(input).toHaveAttribute('type', 'password');
    expect(input).toHaveAttribute('data-credential-purpose', 'configuration-secret');
    expect(input).toHaveAttribute('autocomplete', 'off');
    expect(input).toHaveAttribute('readonly');
    // The DOM value is present for form binding but never presented as a
    // visible text input (type=password masks it; readonly blocks accidental edit).
    expect(input).toHaveValue('super-secret-token');
    expect(screen.queryByRole('textbox', { name: 'MCP Server Token' })).not.toBeInTheDocument();
  });

  it('masks already-masked server values without requiring isSensitive on the schema', () => {
    render(
      <UiLanguageProvider initialLanguage="en">
        <SettingsField
          item={buildItem({
            key: 'LEGACY_SECRET',
            value: '******',
            isMasked: true,
            dataType: 'string',
            uiControl: 'text',
            isSensitive: false,
            title: 'Legacy Secret',
          })}
          value="******"
          onChange={vi.fn()}
        />
      </UiLanguageProvider>,
    );

    const input = screen.getByLabelText('Legacy Secret');
    expect(input).toHaveAttribute('type', 'password');
    expect(input).toHaveValue('******');
  });
});

describe('SettingsField save-loop contract (change → commit display → reject invalid)', () => {
  function ControlledField({
    item,
    initialValue,
    issues = [],
  }: {
    item: SystemConfigItem;
    initialValue: string;
    issues?: ConfigValidationIssue[];
  }) {
    const [value, setValue] = useState(initialValue);
    return (
      <UiLanguageProvider initialLanguage="en">
        <SettingsField
          item={item}
          value={value}
          onChange={(_key, next) => setValue(next)}
          issues={issues}
        />
        <output data-testid="committed-value">{value}</output>
      </UiLanguageProvider>
    );
  }

  it('round-trips boolean switch changes into the committed draft value', () => {
    const item = buildItem({
      key: 'MCP_SERVER_ENABLED',
      value: 'false',
      dataType: 'boolean',
      uiControl: 'text',
      title: 'MCP Server Enabled',
    });

    render(<ControlledField item={item} initialValue="false" />);
    const toggle = screen.getByRole('switch', { name: 'MCP Server Enabled' });
    expect(toggle).toHaveAttribute('aria-checked', 'false');
    fireEvent.click(toggle);
    expect(toggle).toHaveAttribute('aria-checked', 'true');
    expect(screen.getByTestId('committed-value')).toHaveTextContent('true');
  });

  it('round-trips select changes into the committed draft value', () => {
    const item = buildItem({
      key: 'REPORT_MODE',
      value: 'brief',
      dataType: 'string',
      uiControl: 'text',
      options: ['brief', 'standard', 'research'],
      title: 'Report Mode',
    });

    render(<ControlledField item={item} initialValue="brief" />);
    const select = screen.getByRole('combobox', { name: 'Report Mode' });
    const listbox = openListbox(select);
    fireEvent.click(within(listbox).getByRole('option', { name: 'research' }));
    expect(screen.getByTestId('committed-value')).toHaveTextContent('research');
    expect(screen.getByRole('combobox', { name: 'Report Mode' })).toHaveAttribute(
      'data-value',
      'research',
    );
  });

  it('round-trips number input changes into the committed draft value', () => {
    const item = buildItem({
      key: 'DATA_VALIDATION_BATCH_SIZE',
      value: '10',
      dataType: 'integer',
      uiControl: 'text',
      validation: { min: 1, max: 100 },
      title: 'Data Validation Batch Size',
    });

    render(<ControlledField item={item} initialValue="10" />);
    const input = screen.getByRole('spinbutton', { name: 'Data Validation Batch Size' });
    fireEvent.change(input, { target: { value: '25' } });
    expect(screen.getByTestId('committed-value')).toHaveTextContent('25');
    expect(input).toHaveValue(25);
  });

  it('surfaces readable validation errors and marks the control invalid', () => {
    const item = buildItem({
      key: 'DATA_VALIDATION_BATCH_SIZE',
      value: '0',
      dataType: 'integer',
      uiControl: 'text',
      validation: { min: 1, max: 100 },
      title: 'Data Validation Batch Size',
    });
    const issues: ConfigValidationIssue[] = [
      {
        key: 'DATA_VALIDATION_BATCH_SIZE',
        code: 'min',
        message: 'Must be between 1 and 100',
        severity: 'error',
        expected: '>=1',
        actual: '0',
      },
    ];

    render(
      <ControlledField item={item} initialValue="0" issues={issues} />,
    );

    const issue = screen.getByText('Must be between 1 and 100');
    expect(issue).toHaveClass('text-danger');
    const input = screen.getByRole('spinbutton', { name: 'Data Validation Batch Size' });
    expect(input).toHaveAttribute('aria-invalid', 'true');
    expect(input).toHaveAttribute('aria-describedby', issue.id);
  });

  it('keeps password controls masked after a local edit until the user reveals them', () => {
    const item = buildItem({
      key: 'MCP_SERVER_TOKEN',
      value: '******',
      isMasked: true,
      dataType: 'string',
      uiControl: 'text',
      isSensitive: true,
      title: 'MCP Server Token',
    });

    function SecretField() {
      const [value, setValue] = useState('******');
      return (
        <UiLanguageProvider initialLanguage="en">
          <SettingsField
            item={item}
            value={value}
            onChange={(_key, next) => setValue(next)}
          />
        </UiLanguageProvider>
      );
    }

    render(<SecretField />);
    const input = screen.getByLabelText('MCP Server Token');
    expect(input).toHaveAttribute('type', 'password');
    fireEvent.focus(input);
    fireEvent.change(input, { target: { value: 'new-secret' } });
    // After edit the value updates but remains a password input (masked UI).
    expect(input).toHaveAttribute('type', 'password');
    expect(input).toHaveValue('new-secret');
    expect(screen.queryByDisplayValue('new-secret')).toBe(input);
    // No free-text textbox role for the secret.
    expect(screen.queryByRole('textbox', { name: 'MCP Server Token' })).not.toBeInTheDocument();
  });
});
