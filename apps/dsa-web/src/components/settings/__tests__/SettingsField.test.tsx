import { fireEvent, render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { ReactNode } from 'react';
import type { SystemConfigItem } from '../../../types/systemConfig';
import { UiLanguageProvider, useUiLanguage } from '../../../contexts/UiLanguageContext';
import { loadUiLanguageTranslations } from '../../../i18n/translations';
import { getFieldDescriptionZh, getFieldTitle, getFieldTitleZh } from '../../../utils/systemConfigI18n';
import { UI_LANGUAGE_STORAGE_KEY } from '../../../utils/uiLanguage';
import { SettingsField } from '../SettingsField';

// jsdom 未实现 scrollIntoView，而 Select 打开下拉时会调用它保持活动项可见。
if (!HTMLElement.prototype.scrollIntoView) {
  HTMLElement.prototype.scrollIntoView = () => {};
}

function openListbox(trigger: HTMLElement) {
  fireEvent.click(trigger);
  return document.getElementById(trigger.getAttribute('aria-controls')!)!;
}

function openHelpTooltip(title: string | RegExp) {
  const trigger = screen.getByRole('button', { name: title });
  fireEvent.mouseEnter(trigger.parentElement!);
  return screen.getByRole('tooltip');
}

describe('SettingsField', () => {
  it('forces a schema safety diagnostic into visible read-only mode', () => {
    const onChange = vi.fn();
    render(
      <SettingsField
        item={{
          key: 'UNSAFE_AI_FIELD',
          value: 'saved-value',
          rawValueExists: true,
          isMasked: false,
          schema: {
            key: 'UNSAFE_AI_FIELD',
            category: 'ai_model',
            dataType: 'string',
            uiControl: 'text',
            isSensitive: false,
            isRequired: false,
            isEditable: true,
            options: [],
            validation: {},
            displayOrder: 1,
          },
        }}
        value="saved-value"
        onChange={onChange}
        readOnlyDiagnostic="Diagnostics: schema_condition_unknown"
      />,
    );

    expect(screen.getByDisplayValue('saved-value')).toBeDisabled();
    expect(screen.getByText('只读')).toBeInTheDocument();
    expect(screen.getByTestId('settings-schema-diagnostic-UNSAFE_AI_FIELD')).toHaveTextContent(
      'schema_condition_unknown',
    );
  });

  it('prefers localized Chinese field titles over backend schema titles', () => {
    render(
      <SettingsField
        item={{
          key: 'STOCK_LIST',
          value: '600519',
          rawValueExists: true,
          isMasked: false,
          schema: {
            key: 'STOCK_LIST',
            title: 'Stock List',
            category: 'base',
            dataType: 'string',
            uiControl: 'text',
            isSensitive: false,
            isRequired: false,
            isEditable: true,
            options: [],
            validation: {},
            displayOrder: 1,
          },
        }}
        value="600519"
        onChange={vi.fn()}
      />
    );

    expect(screen.getByLabelText('自选股列表')).toBeInTheDocument();
    expect(screen.queryByLabelText('Stock List')).not.toBeInTheDocument();
  });

  it.each(['de', 'ja', 'zh-TW'] as const)(
    'keeps distinct per-field %s titles when fields share one help key',
    async (language) => {
      await loadUiLanguageTranslations(language);
      const senderTitle = getFieldTitle('EMAIL_SENDER', undefined, language);
      const passwordTitle = getFieldTitle('EMAIL_PASSWORD', undefined, language);

      render(
        <UiLanguageProvider initialLanguage={language}>
          <SettingsField
            item={{
              key: 'EMAIL_SENDER',
              value: 'sender@example.com',
              rawValueExists: true,
              isMasked: false,
              schema: {
                key: 'EMAIL_SENDER',
                title: 'Email Sender',
                category: 'notification',
                dataType: 'string',
                uiControl: 'text',
                isSensitive: false,
                isRequired: false,
                isEditable: true,
                options: [],
                validation: {},
                displayOrder: 1,
                helpKey: 'settings.notification.email',
              },
            }}
            value="sender@example.com"
            onChange={vi.fn()}
          />
          <SettingsField
            item={{
              key: 'EMAIL_PASSWORD',
              value: 'secret',
              rawValueExists: true,
              isMasked: false,
              schema: {
                key: 'EMAIL_PASSWORD',
                title: 'Email Password',
                category: 'notification',
                dataType: 'string',
                uiControl: 'password',
                isSensitive: true,
                isRequired: false,
                isEditable: true,
                options: [],
                validation: {},
                displayOrder: 2,
                helpKey: 'settings.notification.email',
              },
            }}
            value="secret"
            onChange={vi.fn()}
          />
        </UiLanguageProvider>,
      );

      expect(senderTitle).not.toBe(passwordTitle);
      expect(senderTitle).not.toBe('Email Sender');
      expect(passwordTitle).not.toBe('Email Password');
      expect(screen.getByLabelText(senderTitle)).toBeInTheDocument();
      expect(screen.getByLabelText(passwordTitle)).toBeInTheDocument();
    },
  );

  it('localizes a known field without a help key in an additional UI language', async () => {
    const language = 'de';
    await loadUiLanguageTranslations(language);
    const expectedTitle = getFieldTitle('OPENAI_VISION_MODEL', undefined, language);

    render(
      <UiLanguageProvider initialLanguage={language}>
        <SettingsField
          item={{
            key: 'OPENAI_VISION_MODEL',
            value: 'gpt-4o',
            rawValueExists: true,
            isMasked: false,
            schema: {
              key: 'OPENAI_VISION_MODEL',
              title: 'OpenAI Vision Model',
              category: 'ai_model',
              dataType: 'string',
              uiControl: 'text',
              isSensitive: false,
              isRequired: false,
              isEditable: true,
              options: [],
              validation: {},
              displayOrder: 1,
            },
          }}
          value="gpt-4o"
          onChange={vi.fn()}
        />
      </UiLanguageProvider>,
    );

    expect(expectedTitle).not.toBe('OpenAI Vision Model');
    expect(screen.getByLabelText(expectedTitle)).toBeInTheDocument();
  });

  it('preserves the live backend schema title for English', () => {
    render(
      <UiLanguageProvider initialLanguage="en">
        <SettingsField
          item={{
            key: 'STOCK_LIST',
            value: 'AAPL',
            rawValueExists: true,
            isMasked: false,
            schema: {
              key: 'STOCK_LIST',
              title: 'Backend-owned watchlist title',
              category: 'base',
              dataType: 'string',
              uiControl: 'text',
              isSensitive: false,
              isRequired: false,
              isEditable: true,
              options: [],
              validation: {},
              displayOrder: 1,
            },
          }}
          value="AAPL"
          onChange={vi.fn()}
        />
      </UiLanguageProvider>,
    );

    expect(screen.getByLabelText('Backend-owned watchlist title')).toBeInTheDocument();
    expect(screen.queryByLabelText('Stock List')).not.toBeInTheDocument();
  });

  it('flags a field that only takes effect after a restart', () => {
    const { rerender } = render(
      <SettingsField
        item={{
          key: 'WEBUI_PORT',
          value: '8000',
          rawValueExists: true,
          isMasked: false,
          schema: {
            key: 'WEBUI_PORT',
            category: 'system',
            dataType: 'integer',
            uiControl: 'number',
            isSensitive: false,
            isRequired: false,
            isEditable: true,
            options: [],
            validation: {},
            displayOrder: 1,
            warningCodes: ['port_mapping_required', 'restart_required'],
          },
        }}
        value="8000"
        onChange={vi.fn()}
      />
    );
    expect(screen.getByText('重启生效')).toBeInTheDocument();

    // A field without the restart warning code shows no badge.
    rerender(
      <SettingsField
        item={{
          key: 'LOG_LEVEL',
          value: 'INFO',
          rawValueExists: true,
          isMasked: false,
          schema: {
            key: 'LOG_LEVEL',
            category: 'system',
            dataType: 'string',
            uiControl: 'text',
            isSensitive: false,
            isRequired: false,
            isEditable: true,
            options: [],
            validation: {},
            displayOrder: 1,
            warningCodes: [],
          },
        }}
        value="INFO"
        onChange={vi.fn()}
      />
    );
    expect(screen.queryByText('重启生效')).not.toBeInTheDocument();
  });

  it('localizes TickFlow field descriptions instead of falling back to backend English schema', () => {
    render(
      <SettingsField
        item={{
          key: 'TICKFLOW_PRIORITY',
          value: '2',
          rawValueExists: false,
          isMasked: false,
          schema: {
            key: 'TICKFLOW_PRIORITY',
            title: 'TickFlow Priority',
            description: 'Priority for TickFlow daily K-line fetcher. Lower numbers are tried earlier.',
            category: 'data_source',
            dataType: 'integer',
            uiControl: 'number',
            isSensitive: false,
            isRequired: false,
            isEditable: true,
            options: [],
            validation: { min: 0, max: 99 },
            displayOrder: 16,
            helpKey: 'settings.data_source.TICKFLOW_PRIORITY',
          },
        }}
        value="2"
        onChange={vi.fn()}
      />
    );

    expect(screen.getByLabelText('TickFlow 日 K 优先级')).toBeInTheDocument();
    expect(openHelpTooltip(/TickFlow 日 K 优先级/)).toHaveTextContent(/控制 TickFlow 在 A 股日 K 数据源回退链中的尝试顺序/);
    expect(screen.queryByText(/Priority for TickFlow daily K-line fetcher/)).not.toBeInTheDocument();
  });
  it('uses schema key for TickFlow localization when the runtime item key differs', () => {
    render(
      <SettingsField
        item={{
          key: 'runtime.tickflow.priority',
          value: '2',
          rawValueExists: false,
          isMasked: false,
          schema: {
            key: 'TICKFLOW_PRIORITY',
            title: 'TickFlow Priority',
            description: 'Priority for TickFlow daily K-line fetcher. Lower numbers are tried earlier.',
            category: 'data_source',
            dataType: 'integer',
            uiControl: 'number',
            isSensitive: false,
            isRequired: false,
            isEditable: true,
            options: [],
            validation: { min: 0, max: 99 },
            displayOrder: 16,
            helpKey: 'settings.data_source.TICKFLOW_PRIORITY',
          },
        }}
        value="2"
        onChange={vi.fn()}
      />
    );

    expect(screen.getByLabelText(getFieldTitleZh('TICKFLOW_PRIORITY', ''))).toBeInTheDocument();
    expect(openHelpTooltip(/TickFlow 日 K 优先级/)).toHaveTextContent(getFieldDescriptionZh('TICKFLOW_PRIORITY', ''));
    expect(screen.queryByLabelText('TickFlow Priority')).not.toBeInTheDocument();
    expect(screen.queryByText(/Priority for TickFlow daily K-line fetcher/)).not.toBeInTheDocument();
  });
  it('renders sensitive field metadata and validation errors', () => {
    const onChange = vi.fn();

    render(
      <SettingsField
        item={{
          key: 'OPENAI_API_KEY',
          value: 'secret',
          rawValueExists: true,
          isMasked: false,
          schema: {
            key: 'OPENAI_API_KEY',
            category: 'ai_model',
            dataType: 'string',
            uiControl: 'password',
            isSensitive: true,
            isRequired: true,
            isEditable: true,
            options: [],
            validation: {},
            displayOrder: 1,
          },
        }}
        value="secret"
        onChange={onChange}
        issues={[
          {
            key: 'OPENAI_API_KEY',
            code: 'required',
            message: 'API Key 必填',
            severity: 'error',
          },
        ]}
      />
    );

    const issue = screen.getByText('API Key 必填');
    expect(issue).toBeInTheDocument();

    const input = screen.getByLabelText('OpenAI API Key');
    expect(input).toHaveAttribute('aria-invalid', 'true');
    expect(input).toHaveAttribute('aria-describedby', issue.id);
    fireEvent.focus(input);
    fireEvent.change(input, {
      target: { value: 'updated-secret' },
    });

    expect(onChange).toHaveBeenCalledWith('OPENAI_API_KEY', 'updated-secret');
  });

  it('renders multi-value sensitive fields with external delete actions', () => {
    const onChange = vi.fn();

    render(
      <SettingsField
        item={{
          key: 'OPENAI_API_KEYS',
          value: 'secret-a,secret-b',
          rawValueExists: true,
          isMasked: false,
          schema: {
            key: 'OPENAI_API_KEYS',
            category: 'ai_model',
            dataType: 'string',
            uiControl: 'password',
            isSensitive: true,
            isRequired: false,
            isEditable: true,
            options: [],
            validation: { multiValue: true },
            displayOrder: 1,
          },
        }}
        value="secret-a,secret-b"
        onChange={onChange}
      />
    );

    expect(screen.getAllByRole('button', { name: '显示内容' })).toHaveLength(2);
    expect(screen.getAllByRole('button', { name: '删除' })).toHaveLength(2);
  });

  it('allows optional select fields to be cleared when schema provides an empty option', () => {
    const onChange = vi.fn();

    render(
      <SettingsField
        item={{
          key: 'NOTIFICATION_MIN_SEVERITY',
          value: 'warning',
          rawValueExists: true,
          isMasked: false,
          schema: {
            key: 'NOTIFICATION_MIN_SEVERITY',
            title: 'Notification Minimum Severity',
            category: 'notification',
            dataType: 'string',
            uiControl: 'select',
            isSensitive: false,
            isRequired: false,
            isEditable: true,
            options: [
              { label: 'Not set', value: '' },
              { label: 'info', value: 'info' },
              { label: 'warning', value: 'warning' },
              { label: 'error', value: 'error' },
              { label: 'critical', value: 'critical' },
            ],
            validation: { enum: ['', 'info', 'warning', 'error', 'critical'] },
            displayOrder: 69,
          },
        }}
        value="warning"
        onChange={onChange}
      />
    );

    const select = screen.getByLabelText('最小通知级别');
    const listbox = openListbox(select);
    expect(within(listbox).getByRole('option', { name: '未设置' })).toBeInTheDocument();
    expect(within(listbox).queryByRole('option', { name: '请选择' })).not.toBeInTheDocument();

    fireEvent.click(within(listbox).getByRole('option', { name: '未设置' }));

    expect(onChange).toHaveBeenCalledWith('NOTIFICATION_MIN_SEVERITY', '');
  });

  it('renders true/false option sets as a switch instead of a select', () => {
    const onChange = vi.fn();
    render(
      <SettingsField
        item={{
          key: 'BOOLISH_FIELD',
          value: 'true',
          rawValueExists: true,
          isMasked: false,
          schema: {
            key: 'BOOLISH_FIELD',
            title: 'Boolean field',
            category: 'system',
            dataType: 'string',
            uiControl: 'select',
            isSensitive: false,
            isRequired: false,
            isEditable: true,
            options: ['true', 'false'],
            validation: { enum: ['true', 'false'] },
            displayOrder: 1,
          },
        }}
        value="true"
        onChange={onChange}
      />,
    );

    const toggle = screen.getByRole('switch', { name: 'Boolean field' });
    expect(toggle).toHaveAttribute('aria-checked', 'true');
    expect(screen.queryByRole('combobox')).not.toBeInTheDocument();
    fireEvent.click(toggle);
    expect(onChange).toHaveBeenCalledWith('BOOLISH_FIELD', 'false');
  });

  it('shows the schema default for select fields when no explicit env value exists', () => {
    const onChange = vi.fn();

    render(
      <SettingsField
        item={{
          key: 'GENERATION_BACKEND',
          value: '',
          rawValueExists: false,
          isMasked: false,
          schema: {
            key: 'GENERATION_BACKEND',
            title: 'Generation Backend',
            category: 'ai_model',
            dataType: 'string',
            uiControl: 'select',
            isSensitive: false,
            isRequired: false,
            isEditable: true,
            defaultValue: 'litellm',
            options: [{ label: 'Default model settings', value: 'litellm' }],
            validation: { enum: ['litellm'] },
            displayOrder: 1,
          },
        }}
        value=""
        onChange={onChange}
      />
    );

    expect(screen.getByLabelText('分析生成方式')).toHaveAttribute('data-value', 'litellm');
    expect(onChange).not.toHaveBeenCalled();
  });

  it('renders localized labels for real system config select options', () => {
    const selectCases = [
      {
        key: 'NEWS_STRATEGY_PROFILE',
        category: 'data_source',
        options: ['ultra_short', 'short', 'medium', 'long'],
        expectedLabels: ['超短线（1天）', '短期（3天）', '中期（7天）', '长期（30天）'],
      },
      {
        key: 'REPORT_TYPE',
        category: 'notification',
        options: ['simple', 'full', 'brief'],
        expectedLabels: ['简洁', '完整', '简报'],
      },
      {
        key: 'LOG_LEVEL',
        category: 'system',
        options: ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
        expectedLabels: ['调试', '信息', '警告', '错误', '严重'],
      },
    ] as const;

    selectCases.forEach(({ key, category, options, expectedLabels }) => {
      const { unmount } = render(
        <SettingsField
          item={{
            key,
            value: options[0],
            rawValueExists: true,
            isMasked: false,
            schema: {
              key,
              title: key,
              category,
              dataType: 'string',
              uiControl: 'select',
              isSensitive: false,
              isRequired: false,
              isEditable: true,
              options: [...options],
              validation: {},
              displayOrder: 1,
            },
          }}
          value={options[0]}
          onChange={() => undefined}
        />
      );

      const listbox = openListbox(screen.getByRole('combobox'));

      expectedLabels.forEach((label) => {
        expect(within(listbox).getByRole('option', { name: label })).toBeInTheDocument();
      });

      options.forEach((rawOption) => {
        expect(within(listbox).queryByRole('option', { name: rawOption })).not.toBeInTheDocument();
      });

      unmount();
    });
  });

  it('renders MARKET_REVIEW_REGION as a multi-value enum checkbox group', () => {
    const onChange = vi.fn();

    render(
      <SettingsField
        item={{
          key: 'MARKET_REVIEW_REGION',
          value: 'cn,jp',
          rawValueExists: true,
          isMasked: false,
          schema: {
            key: 'MARKET_REVIEW_REGION',
            category: 'system',
            dataType: 'string',
            uiControl: 'text',
            isSensitive: false,
            isRequired: false,
            isEditable: true,
            defaultValue: 'cn',
            options: ['cn', 'hk', 'us', 'jp', 'kr', 'both'],
            validation: {
              allowed_values: ['cn', 'hk', 'us', 'jp', 'kr', 'both'],
              multi_value: true,
              delimiter: ',',
            },
            displayOrder: 48,
          },
        }}
        value="cn,jp"
        onChange={onChange}
      />
    );

    // Multi-value enums must not degrade into a single-choice Select or a
    // free-text input.
    expect(screen.queryByRole('combobox')).not.toBeInTheDocument();
    const group = screen.getByTestId('multi-enum-MARKET_REVIEW_REGION');

    // Collapsed by default: catalog options stay behind the dropdown trigger.
    expect(within(group).queryAllByRole('checkbox')).toHaveLength(0);

    // The field label stays associated with the dropdown trigger.
    const trigger = screen.getByLabelText('大盘复盘市场');
    expect(trigger).toHaveAttribute('aria-haspopup', 'listbox');
    expect(trigger).toHaveTextContent('已选 2 / 6');

    fireEvent.click(trigger);
    const checkboxes = screen.getAllByRole('checkbox');
    expect(checkboxes).toHaveLength(6);
    for (const checkbox of checkboxes) {
      expect(checkbox.closest('label')).toHaveClass('min-h-11');
      expect(checkbox).toHaveClass('h-6', 'w-6');
    }
    expect(checkboxes[0]).toBeChecked(); // cn
    expect(checkboxes[3]).toBeChecked(); // jp
    expect(checkboxes[1]).not.toBeChecked(); // hk

    // Selecting kr serializes in catalog order, not click order.
    fireEvent.click(checkboxes[4]);
    expect(onChange).toHaveBeenCalledWith('MARKET_REVIEW_REGION', 'cn,jp,kr');
  });

  it('keeps unknown stored values visible and deselectable in multi-value enums', () => {
    const onChange = vi.fn();

    render(
      <SettingsField
        item={{
          key: 'NOTIFICATION_REPORT_CHANNELS',
          value: 'email,legacy_channel',
          rawValueExists: true,
          isMasked: false,
          schema: {
            key: 'NOTIFICATION_REPORT_CHANNELS',
            category: 'notification',
            dataType: 'array',
            uiControl: 'textarea',
            isSensitive: false,
            isRequired: false,
            isEditable: true,
            options: [
              { label: 'email', value: 'email' },
              { label: 'feishu', value: 'feishu' },
            ],
            validation: { allowed_values: ['email', 'feishu'], multi_value: true, delimiter: ',' },
            displayOrder: 62,
          },
        }}
        value="email,legacy_channel"
        onChange={onChange}
      />
    );

    const group = screen.getByTestId('multi-enum-NOTIFICATION_REPORT_CHANNELS');
    expect(group.parentElement?.parentElement).toHaveClass('md:grid-cols-[minmax(0,1fr)_240px]');

    // The unknown stored value counts toward the collapsed summary without
    // expanding the trigger into selected chips.
    const trigger = within(group).getByText(/已选/).closest('button')!;
    expect(trigger).toHaveTextContent('已选 2 / 3');
    expect(within(group).queryByText('legacy_channel')).not.toBeInTheDocument();

    fireEvent.click(trigger);
    const checkboxes = screen.getAllByRole('checkbox');
    // 2 catalog options + 1 unknown stored value that must stay visible.
    expect(checkboxes).toHaveLength(3);
    expect(checkboxes[2]).toBeChecked();

    // Enabling feishu keeps the unknown stored value at the tail.
    fireEvent.click(checkboxes[1]);
    expect(onChange).toHaveBeenCalledWith('NOTIFICATION_REPORT_CHANNELS', 'email,feishu,legacy_channel');

    // Deselecting the unknown value drops it explicitly (never silently).
    fireEvent.click(checkboxes[2]);
    expect(onChange).toHaveBeenCalledWith('NOTIFICATION_REPORT_CHANNELS', 'email');
  });

  it('filters multi-enum options and falls back to the empty state guidance', () => {
    const buildItem = (): SystemConfigItem => ({
      key: 'NOTIFICATION_REPORT_CHANNELS',
      value: '',
      rawValueExists: false,
      isMasked: false,
      schema: {
        key: 'NOTIFICATION_REPORT_CHANNELS',
        category: 'notification',
        dataType: 'array',
        uiControl: 'textarea',
        isSensitive: false,
        isRequired: false,
        isEditable: true,
        options: [
          { label: 'email', value: 'email' },
          { label: 'feishu', value: 'feishu' },
        ],
        validation: { allowed_values: ['email', 'feishu'], multi_value: true, delimiter: ',' },
        displayOrder: 62,
      },
    });

    // Filtered-out options disappear, but an already-selected value must stay
    // visible so the stored config never silently loses entries.
    const { rerender } = render(
      <SettingsField
        item={buildItem()}
        value="email"
        onChange={vi.fn()}
        enumOptionFilter={(optionValue) => optionValue === 'feishu'}
        enumEmptyState={<p>去配置通知渠道</p>}
      />
    );
    const group = screen.getByTestId('multi-enum-NOTIFICATION_REPORT_CHANNELS');
    fireEvent.click(within(group).getByText(/已选/).closest('button')!);
    const labels = screen.getAllByRole('option').map((option) => option.textContent);
    expect(labels).toEqual(['email', 'feishu']);

    // No selectable option and nothing selected → guidance replaces the control.
    rerender(
      <SettingsField
        item={buildItem()}
        value=""
        onChange={vi.fn()}
        enumOptionFilter={() => false}
        enumEmptyState={<p>去配置通知渠道</p>}
      />
    );
    expect(screen.queryByTestId('multi-enum-NOTIFICATION_REPORT_CHANNELS')).not.toBeInTheDocument();
    const emptyState = screen.getByTestId('multi-enum-empty-NOTIFICATION_REPORT_CHANNELS');
    expect(within(emptyState).getByText('去配置通知渠道')).toBeInTheDocument();
  });

  it('serializes ordered multi-enums in selection order instead of catalog order', () => {
    const onChange = vi.fn();

    render(
      <SettingsField
        item={{
          key: 'REALTIME_SOURCE_PRIORITY',
          value: 'efinance,tencent',
          rawValueExists: true,
          isMasked: false,
          schema: {
            key: 'REALTIME_SOURCE_PRIORITY',
            category: 'data_source',
            dataType: 'string',
            uiControl: 'text',
            isSensitive: false,
            isRequired: false,
            isEditable: true,
            defaultValue: 'tencent,akshare_sina,efinance,akshare_em',
            options: [
              { label: 'tencent', value: 'tencent' },
              { label: 'akshare_sina', value: 'akshare_sina' },
              { label: 'efinance', value: 'efinance' },
            ],
            validation: { multi_value: true, delimiter: ',', ordered: true },
            displayOrder: 20,
          },
        }}
        value="efinance,tencent"
        onChange={onChange}
      />
    );

    const group = screen.getByTestId('multi-enum-REALTIME_SOURCE_PRIORITY');
    fireEvent.click(within(group).getByText(/已选/).closest('button')!);
    const checkboxes = screen.getAllByRole('checkbox');
    // Picking akshare_sina appends to the priority tail; catalog order would
    // have produced tencent,akshare_sina,efinance instead.
    fireEvent.click(checkboxes[1]);
    expect(onChange).toHaveBeenCalledWith('REALTIME_SOURCE_PRIORITY', 'efinance,tencent,akshare_sina');
  });

  it('applies min/max/step from schema validation to number inputs', () => {
    const { rerender } = render(
      <SettingsField
        item={{
          key: 'TICKFLOW_PRIORITY',
          value: '2',
          rawValueExists: true,
          isMasked: false,
          schema: {
            key: 'TICKFLOW_PRIORITY',
            category: 'data_source',
            dataType: 'integer',
            uiControl: 'number',
            isSensitive: false,
            isRequired: false,
            isEditable: true,
            options: [],
            validation: { min: 0, max: 99 },
            displayOrder: 16,
          },
        }}
        value="2"
        onChange={vi.fn()}
      />
    );

    const integerInput = screen.getByLabelText('TickFlow 日 K 优先级');
    expect(integerInput).toHaveClass('h-9');
    expect(integerInput).toHaveAttribute('min', '0');
    expect(integerInput).toHaveAttribute('max', '99');
    expect(integerInput).toHaveAttribute('step', '1');

    rerender(
      <SettingsField
        item={{
          key: 'LLM_TEMPERATURE',
          value: '0.7',
          rawValueExists: true,
          isMasked: false,
          schema: {
            key: 'LLM_TEMPERATURE',
            category: 'ai_model',
            dataType: 'number',
            uiControl: 'number',
            isSensitive: false,
            isRequired: false,
            isEditable: true,
            options: [],
            validation: { min: 0, max: 2 },
            displayOrder: 20,
          },
        }}
        value="0.7"
        onChange={vi.fn()}
      />
    );

    const floatInput = screen.getByRole('spinbutton');
    expect(floatInput).toHaveAttribute('min', '0');
    expect(floatInput).toHaveAttribute('max', '2');
    expect(floatInput).toHaveAttribute('step', '0.1');
  });

  it('shows seconds as a trailing unit for the orchestrator timeout', () => {
    render(
      <SettingsField
        item={{
          key: 'AGENT_ORCHESTRATOR_TIMEOUT_S',
          value: '600',
          rawValueExists: true,
          isMasked: false,
          schema: {
            key: 'AGENT_ORCHESTRATOR_TIMEOUT_S',
            category: 'agent',
            dataType: 'integer',
            uiControl: 'number',
            isSensitive: false,
            isRequired: false,
            isEditable: true,
            unit: 's',
            options: [],
            validation: { min: 0 },
            displayOrder: 1,
          },
        }}
        value="600"
        onChange={vi.fn()}
      />,
    );

    const input = screen.getByRole('spinbutton', { name: 'Agent 超时（秒）' });
    expect(input).toHaveClass('pr-8');
    expect(input.parentElement).toHaveTextContent('s');
  });

  it('backfills the schema default for unset non-select controls', () => {
    render(
      <>
        <SettingsField
          item={{
            key: 'NOTIFICATION_DEDUP_TTL_SECONDS',
            value: '',
            rawValueExists: false,
            isMasked: false,
            schema: {
              key: 'NOTIFICATION_DEDUP_TTL_SECONDS',
              category: 'notification',
              dataType: 'integer',
              uiControl: 'number',
              isSensitive: false,
              isRequired: false,
              isEditable: true,
              defaultValue: '300',
              options: [],
              validation: { min: 0 },
              displayOrder: 65,
            },
          }}
          value=""
          onChange={vi.fn()}
        />
        <SettingsField
          item={{
            key: 'ENABLE_MARKET_REVIEW',
            value: '',
            rawValueExists: false,
            isMasked: false,
            schema: {
              key: 'ENABLE_MARKET_REVIEW',
              category: 'system',
              dataType: 'boolean',
              uiControl: 'switch',
              isSensitive: false,
              isRequired: false,
              isEditable: true,
              defaultValue: 'true',
              options: [],
              validation: {},
              displayOrder: 47,
            },
          }}
          value=""
          onChange={vi.fn()}
        />
      </>
    );

    // Unset fields show the effective backend default instead of a blank control.
    expect(screen.getByRole('spinbutton')).toHaveValue(300);
    const toggle = screen.getByRole('switch');
    expect(toggle).toHaveAttribute('aria-checked', 'true');
    expect(toggle).toHaveClass('h-11', 'w-11');
    expect(screen.getByTestId('setting-ENABLE_MARKET_REVIEW-switch-visual')).toHaveClass('h-6', 'w-10');
  });

  it('never backfills defaults into password controls', () => {
    render(
      <SettingsField
        item={{
          key: 'SMTP_PASSWORD',
          value: '',
          rawValueExists: false,
          isMasked: false,
          schema: {
            key: 'SMTP_PASSWORD',
            category: 'notification',
            dataType: 'string',
            uiControl: 'password',
            isSensitive: true,
            isRequired: false,
            isEditable: true,
            defaultValue: 'should-not-render',
            options: [],
            validation: {},
            displayOrder: 40,
          },
        }}
        value=""
        onChange={vi.fn()}
      />
    );

    expect(screen.queryByDisplayValue('should-not-render')).not.toBeInTheDocument();
  });

  it('renders context compression profile options with Chinese labels', () => {
    const onChange = vi.fn();

    render(
      <SettingsField
        item={{
          key: 'AGENT_CONTEXT_COMPRESSION_PROFILE',
          value: 'balanced',
          rawValueExists: true,
          isMasked: false,
          schema: {
            key: 'AGENT_CONTEXT_COMPRESSION_PROFILE',
            category: 'agent',
            dataType: 'string',
            uiControl: 'select',
            isSensitive: false,
            isRequired: false,
            isEditable: true,
            options: [
              { label: '成本优先', value: 'cost' },
              { label: '均衡推荐', value: 'balanced' },
              { label: '长上下文原文优先', value: 'long_context_raw_first' },
            ],
            validation: {
              enum: ['cost', 'balanced', 'long_context_raw_first'],
            },
            displayOrder: 72,
          },
        }}
        value="balanced"
        onChange={onChange}
      />
    );

    const profileSelect = screen.getByLabelText('上下文压缩策略');
    expect(profileSelect).toBeInTheDocument();
    const listbox = openListbox(profileSelect);
    expect(within(listbox).getByRole('option', { name: '成本优先' })).toBeInTheDocument();
    expect(within(listbox).getByRole('option', { name: '均衡推荐' })).toBeInTheDocument();
    expect(within(listbox).getByRole('option', { name: '长上下文原文优先' })).toBeInTheDocument();
  });

  it('renders blank-value preset guidance for context compression numeric fields', () => {
    const onChange = vi.fn();

    render(
      <>
        <SettingsField
          item={{
            key: 'AGENT_CONTEXT_COMPRESSION_TRIGGER_TOKENS',
            value: '',
            rawValueExists: false,
            isMasked: false,
            schema: {
              key: 'AGENT_CONTEXT_COMPRESSION_TRIGGER_TOKENS',
              category: 'agent',
              dataType: 'integer',
              uiControl: 'number',
              isSensitive: false,
              isRequired: false,
              isEditable: true,
              options: [],
              validation: { min: 1000 },
              displayOrder: 73,
            },
          }}
          value=""
          onChange={onChange}
        />
        <SettingsField
          item={{
            key: 'AGENT_CONTEXT_PROTECTED_TURNS',
            value: '',
            rawValueExists: false,
            isMasked: false,
            schema: {
              key: 'AGENT_CONTEXT_PROTECTED_TURNS',
              category: 'agent',
              dataType: 'integer',
              uiControl: 'number',
              isSensitive: false,
              isRequired: false,
              isEditable: true,
              options: [],
              validation: { min: 1 },
              displayOrder: 74,
            },
          }}
          value=""
          onChange={onChange}
        />
      </>
    );

    expect(screen.getByLabelText('压缩触发阈值（tokens）')).toBeInTheDocument();
    expect(screen.getByLabelText('原文保护轮次')).toBeInTheDocument();

    const helpButtons = screen.getAllByRole('button', { name: /配置说明/ });
    expect(helpButtons).toHaveLength(2);
    fireEvent.mouseEnter(helpButtons[0].parentElement!);
    expect(screen.getByRole('tooltip')).toHaveTextContent(/估算历史 token 超过该值时触发摘要/);
    expect(screen.getByRole('tooltip')).toHaveTextContent('留空则跟随当前上下文压缩策略 profile 默认值');
    fireEvent.mouseLeave(helpButtons[0].parentElement!);
    fireEvent.mouseEnter(helpButtons[1].parentElement!);
    expect(screen.getByRole('tooltip')).toHaveTextContent(/压缩时最近 N 个用户轮次及其后的回复保持原文/);
    expect(screen.getByRole('tooltip')).toHaveTextContent('留空则跟随当前上下文压缩策略 profile 默认值');
  });

  it('renders localized custom webhook body template guidance', () => {
    const onChange = vi.fn();

    render(
      <SettingsField
        item={{
          key: 'CUSTOM_WEBHOOK_BODY_TEMPLATE',
          value: '',
          rawValueExists: false,
          isMasked: false,
          schema: {
            key: 'CUSTOM_WEBHOOK_BODY_TEMPLATE',
            category: 'notification',
            dataType: 'string',
            uiControl: 'textarea',
            isSensitive: false,
            isRequired: false,
            isEditable: true,
            options: [],
            validation: {},
            displayOrder: 52,
          },
        }}
        value=""
        onChange={onChange}
      />
    );

    expect(screen.getByLabelText('自定义 Webhook Body 模板')).toBeInTheDocument();
    const tooltip = openHelpTooltip(/自定义 Webhook Body 模板/);
    expect(tooltip).toHaveTextContent(/会先于 Bark、Slack、Discord 等自动 payload 生效/);
    expect(tooltip).toHaveTextContent(/裸 \$content \/ \$title 不做 JSON 转义/);
  });

  it('shows concise field help without examples, docs, or value-source metadata', () => {
    render(
      <SettingsField
        item={{
          key: 'STOCK_LIST',
          value: '600519,300750',
          rawValueExists: true,
          isMasked: false,
          schema: {
            key: 'STOCK_LIST',
            category: 'base',
            dataType: 'array',
            uiControl: 'textarea',
            isSensitive: false,
            isRequired: false,
            isEditable: true,
            options: [],
            validation: {},
            displayOrder: 1,
            helpKey: 'settings.base.STOCK_LIST',
            examples: ['STOCK_LIST=600519,300750,002594'],
            docs: [
              {
                label: '完整指南',
                href: 'https://example.com/full-guide',
              },
            ],
            warningCodes: [],
          },
        }}
        value="600519,300750"
        onChange={() => undefined}
      />
    );

    const helpTrigger = screen.getByRole('button', { name: '查看 自选股列表 配置说明' });
    expect(helpTrigger).toHaveClass('h-11', 'w-11');
    fireEvent.mouseEnter(helpTrigger.parentElement!);

    const tooltip = screen.getByRole('tooltip');
    expect(tooltip).toHaveTextContent('推荐使用英文逗号分隔股票代码');
    expect(tooltip).toHaveTextContent('保存后的 STOCK_LIST 会统一写成英文逗号分隔');
    expect(tooltip).not.toHaveTextContent('STOCK_LIST=600519,300750,002594');
    expect(tooltip).not.toHaveTextContent('当前取值来源');
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: /完整指南/ })).not.toBeInTheDocument();
  });

  it('does not render inline external doc links or KEY=value examples on the field body', () => {
    render(
      <SettingsField
        item={{
          key: 'OPENAI_API_KEY',
          value: '',
          rawValueExists: false,
          isMasked: false,
          schema: {
            key: 'OPENAI_API_KEY',
            category: 'ai_model',
            dataType: 'string',
            uiControl: 'password',
            isSensitive: true,
            isRequired: false,
            isEditable: true,
            options: [],
            validation: {},
            displayOrder: 1,
            examples: ['sk-example-token'],
            docs: [
              { label: '获取 API Key', href: 'https://platform.openai.com/api-keys' },
            ],
          },
        }}
        value=""
        onChange={() => undefined}
      />,
    );

    // Everyday fields do not surface external links or raw KEY=value examples.
    expect(screen.queryByRole('link', { name: '获取 API Key' })).not.toBeInTheDocument();
    expect(screen.queryByText(/sk-example-token/)).not.toBeInTheDocument();
  });

  it('renders a Select for an enum field even when ui_control is text', () => {
    render(
      <SettingsField
        item={{
          key: 'REPORT_TYPE',
          value: 'markdown',
          rawValueExists: true,
          isMasked: false,
          schema: {
            key: 'REPORT_TYPE',
            category: 'notification',
            dataType: 'string',
            uiControl: 'text',
            isSensitive: false,
            isRequired: false,
            isEditable: true,
            options: ['markdown', 'html'],
            validation: {},
            displayOrder: 1,
          },
        }}
        value="markdown"
        onChange={() => undefined}
      />,
    );
    // A finite option set must render a Select (combobox trigger), never a
    // free-text Input.
    expect(screen.getByRole('combobox')).toBeInTheDocument();
  });

  it('keeps generation channel help user-facing without env key or examples', () => {
    render(
      <SettingsField
        item={{
          key: 'GENERATION_BACKEND',
          value: 'litellm',
          rawValueExists: true,
          isMasked: false,
          schema: {
            key: 'GENERATION_BACKEND',
            title: 'Generation Backend',
            category: 'ai_model',
            dataType: 'string',
            uiControl: 'select',
            isSensitive: false,
            isRequired: false,
            isEditable: true,
            options: [{ label: 'Default model settings', value: 'litellm' }],
            validation: { enum: ['litellm'] },
            displayOrder: 1,
            helpKey: 'settings.ai_model.GENERATION_BACKEND',
            examples: ['GENERATION_BACKEND=litellm'],
            warningCodes: [],
          },
        }}
        value="litellm"
        onChange={() => undefined}
      />
    );

    const tooltip = openHelpTooltip('查看 分析生成方式 配置说明');
    expect(tooltip).toHaveTextContent('用于个股分析、大盘复盘和普通文本生成');
    expect(tooltip).toHaveTextContent('想恢复默认行为，选择“默认模型配置”并保存配置');
    expect(tooltip).not.toHaveTextContent('GENERATION_BACKEND=litellm');
    expect(tooltip).not.toHaveTextContent('配置样例');
    expect(tooltip).not.toHaveTextContent('Phase 1');
  });

  it('describes agent auto generation without exposing implementation labels as the primary UI copy', () => {
    render(
      <SettingsField
        item={{
          key: 'AGENT_GENERATION_BACKEND',
          value: 'auto',
          rawValueExists: true,
          isMasked: false,
          schema: {
            key: 'AGENT_GENERATION_BACKEND',
            title: 'Agent Generation Backend',
            category: 'agent',
            dataType: 'string',
            uiControl: 'select',
            isSensitive: false,
            isRequired: false,
            isEditable: true,
            options: [
              { label: 'Auto', value: 'auto' },
              { label: 'Default model settings', value: 'litellm' },
            ],
            validation: { enum: ['auto', 'litellm'] },
            displayOrder: 1,
            helpKey: 'settings.agent.AGENT_GENERATION_BACKEND',
            examples: [],
            warningCodes: [],
          },
        }}
        value="auto"
        onChange={() => undefined}
      />
    );

    const tooltip = openHelpTooltip('查看 问股生成方式 配置说明');
    expect(tooltip).toHaveTextContent('通常保持“自动”');
    expect(tooltip).toHaveTextContent('想恢复默认行为，选择“自动”并保存配置');
    expect(tooltip).not.toHaveTextContent('高级说明');
    expect(tooltip).not.toHaveTextContent('LiteLLM');
  });

  it('uses per-field schema titles even when helpKey is shared by multiple fields', () => {
    const restoreLanguage = localStorage.getItem(UI_LANGUAGE_STORAGE_KEY);
    localStorage.setItem(UI_LANGUAGE_STORAGE_KEY, 'en');

    try {
      const SchemaTitleSwitcher = ({ children }: { children: ReactNode }) => {
        const { setLanguage } = useUiLanguage();
        return (
          <div>
            <button type="button" onClick={() => setLanguage('en')}>
              switch-en
            </button>
            {children}
          </div>
        );
      };

      render(
        <UiLanguageProvider>
          <SchemaTitleSwitcher>
            <SettingsField
              item={{
                key: 'OPENAI_MODEL',
                value: 'gemini/gemini-3.1-pro-preview',
                rawValueExists: true,
                isMasked: false,
                schema: {
                  key: 'OPENAI_MODEL',
                  category: 'ai_model',
                  dataType: 'string',
                  uiControl: 'text',
                  isSensitive: false,
                  isRequired: false,
                  isEditable: true,
                  options: [],
                  validation: {},
                  displayOrder: 10,
                  title: 'Primary model',
                  helpKey: 'settings.llm_channel.primary_model',
                  description: 'Primary model description',
                },
              }}
              value="gemini/gemini-3.1-pro-preview"
              onChange={vi.fn()}
            />
            <SettingsField
              item={{
                key: 'OPENAI_VISION_MODEL',
                value: 'gemini/gemini-2.0-flash',
                rawValueExists: true,
                isMasked: false,
                schema: {
                  key: 'OPENAI_VISION_MODEL',
                  category: 'ai_model',
                  dataType: 'string',
                  uiControl: 'text',
                  isSensitive: false,
                  isRequired: false,
                  isEditable: true,
                  options: [],
                  validation: {},
                  displayOrder: 11,
                  title: 'Vision model',
                  helpKey: 'settings.llm_channel.primary_model',
                  description: 'Vision model description',
                },
              }}
              value="gemini/gemini-2.0-flash"
              onChange={vi.fn()}
            />
          </SchemaTitleSwitcher>
        </UiLanguageProvider>
      );

      fireEvent.click(screen.getByRole('button', { name: 'switch-en' }));

      expect(screen.getByLabelText('Primary model')).toBeInTheDocument();
      expect(screen.getByLabelText('Vision model')).toBeInTheDocument();
    } finally {
      if (restoreLanguage) {
        localStorage.setItem(UI_LANGUAGE_STORAGE_KEY, restoreLanguage);
      } else {
        localStorage.removeItem(UI_LANGUAGE_STORAGE_KEY);
      }
    }
  });
});
