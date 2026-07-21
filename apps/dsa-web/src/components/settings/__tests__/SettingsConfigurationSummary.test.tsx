import { render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { SystemConfigItem } from '../../../types/systemConfig';
import { SettingsConfigurationSummary, SystemConfigSummary } from '../SettingsConfigurationSummary';

function buildItem(overrides: Partial<SystemConfigItem> = {}): SystemConfigItem {
  return {
    key: 'NEWS_STRATEGY_PROFILE',
    value: 'medium',
    rawValueExists: true,
    isMasked: false,
    schema: {
      key: 'NEWS_STRATEGY_PROFILE',
      title: 'News Strategy Profile',
      category: 'data_source',
      dataType: 'string',
      uiControl: 'select',
      isSensitive: false,
      isRequired: false,
      isEditable: true,
      options: ['ultra_short', 'short', 'medium', 'long'],
      validation: {},
      displayOrder: 1,
    },
    ...overrides,
  };
}

describe('SettingsConfigurationSummary', () => {
  it('renders compact read-only definition rows with stable identities', () => {
    const { container } = render(
      <SettingsConfigurationSummary
        entries={[
          { id: 'mode', label: 'Mode', value: 'Standard' },
          { id: 'timeout', label: 'Timeout', value: '600 seconds' },
        ]}
      />,
    );

    const modeRow = screen.getByTestId('settings-summary-mode');
    const timeoutRow = screen.getByTestId('settings-summary-timeout');
    const summary = modeRow.parentElement;

    expect(summary?.tagName).toBe('DL');
    expect(summary).toHaveClass(
      'overflow-hidden',
      'rounded-lg',
      'border',
      'bg-[var(--settings-surface)]',
      'p-1',
    );
    expect(modeRow).toHaveClass(
      'px-2',
      'py-1.5',
      'md:grid-cols-[minmax(0,1fr)_240px]',
      'md:items-center',
      'md:gap-4',
    );
    expect(modeRow).not.toHaveClass('sm:grid-cols-[minmax(0,1fr)_minmax(12rem,40%)]');
    expect(within(modeRow).getByText('Mode').tagName).toBe('DT');
    expect(within(modeRow).getByText('Standard').tagName).toBe('DD');
    expect(within(timeoutRow).getByText('Timeout').tagName).toBe('DT');
    expect(within(timeoutRow).getByText('600 seconds').tagName).toBe('DD');
    expect(container.querySelector('input, select, textarea, button')).toBeNull();
  });
});

describe('SystemConfigSummary', () => {
  it('reuses localized field titles and enum labels', () => {
    render(<SystemConfigSummary items={[buildItem()]} />);

    const row = screen.getByTestId('settings-summary-NEWS_STRATEGY_PROFILE');
    expect(within(row).getByText('新闻策略窗口档位')).toBeInTheDocument();
    expect(within(row).getByText('中期（7天）')).toBeInTheDocument();
    expect(within(row).queryByText('NEWS_STRATEGY_PROFILE')).not.toBeInTheDocument();
    expect(within(row).queryByText('medium')).not.toBeInTheDocument();
  });

  it('uses localized enabled, disabled, and unconfigured values', () => {
    const booleanSchema = {
      ...buildItem().schema!,
      key: 'FEATURE_ENABLED',
      title: 'Feature enabled',
      dataType: 'boolean' as const,
      uiControl: 'switch' as const,
      options: [],
    };

    render(
      <SystemConfigSummary
        items={[
          buildItem({ key: 'FEATURE_ON', value: 'true', schema: booleanSchema }),
          buildItem({ key: 'FEATURE_OFF', value: 'false', schema: booleanSchema }),
          buildItem({ key: 'EMPTY_VALUE', value: '', rawValueExists: false, schema: undefined }),
        ]}
      />,
    );

    expect(screen.getByTestId('settings-summary-FEATURE_ON')).toHaveTextContent('已启用');
    expect(screen.getByTestId('settings-summary-FEATURE_OFF')).toHaveTextContent('未启用');
    expect(screen.getByTestId('settings-summary-EMPTY_VALUE')).toHaveTextContent('未配置');
  });

  it('never exposes sensitive, password, masked, or mask-token values', () => {
    const baseSchema = buildItem().schema!;
    const formatValue = vi.fn((item: SystemConfigItem) => item.value);
    const { container } = render(
      <SystemConfigSummary
        maskToken="hidden-mask-token"
        formatValue={formatValue}
        items={[
          buildItem({
            key: 'SENSITIVE_VALUE',
            value: 'literal-sensitive-value',
            schema: { ...baseSchema, key: 'SENSITIVE_VALUE', isSensitive: true },
          }),
          buildItem({
            key: 'PASSWORD_VALUE',
            value: 'literal-password-value',
            schema: { ...baseSchema, key: 'PASSWORD_VALUE', uiControl: 'password' },
          }),
          buildItem({ key: 'MASKED_VALUE', value: 'literal-masked-value', isMasked: true, schema: undefined }),
          buildItem({ key: 'MASK_TOKEN_VALUE', value: 'hidden-mask-token', schema: undefined }),
          buildItem({ key: 'DEFAULT_MASK_VALUE', value: '******', schema: undefined }),
          buildItem({
            key: 'EMPTY_SECRET',
            value: '',
            rawValueExists: false,
            schema: { ...baseSchema, key: 'EMPTY_SECRET', isSensitive: true },
          }),
        ]}
      />,
    );

    expect(screen.getByTestId('settings-summary-SENSITIVE_VALUE')).toHaveTextContent('已配置');
    expect(screen.getByTestId('settings-summary-PASSWORD_VALUE')).toHaveTextContent('已配置');
    expect(screen.getByTestId('settings-summary-MASKED_VALUE')).toHaveTextContent('已配置');
    expect(screen.getByTestId('settings-summary-MASK_TOKEN_VALUE')).toHaveTextContent('已配置');
    expect(screen.getByTestId('settings-summary-DEFAULT_MASK_VALUE')).toHaveTextContent('已配置');
    expect(screen.getByTestId('settings-summary-EMPTY_SECRET')).toHaveTextContent('未配置');
    expect(container).not.toHaveTextContent(/literal-sensitive-value|literal-password-value|literal-masked-value|hidden-mask-token|\*\*\*\*\*\*/);
    expect(formatValue).not.toHaveBeenCalled();
  });
});
