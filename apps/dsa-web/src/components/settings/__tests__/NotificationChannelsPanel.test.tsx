import { fireEvent, render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { SystemConfigItem } from '../../../types/systemConfig';
import { NotificationChannelsPanel } from '../NotificationChannelsPanel';

function buildItem(overrides: Partial<SystemConfigItem> = {}): SystemConfigItem {
  return {
    key: 'FEISHU_DOMAIN',
    value: 'feishu',
    rawValueExists: false,
    isMasked: false,
    schema: {
      key: 'FEISHU_DOMAIN',
      title: 'Feishu domain',
      category: 'notification',
      dataType: 'string',
      uiControl: 'select',
      isSensitive: false,
      isRequired: false,
      isEditable: true,
      options: ['feishu', 'lark'],
      validation: {},
      displayOrder: 1,
      defaultValue: 'feishu',
    },
    ...overrides,
  };
}

describe('NotificationChannelsPanel', () => {
  it('uses the backend authority instead of treating schema defaults as configured', () => {
    render(
      <NotificationChannelsPanel
        items={[buildItem()]}
        configuredChannels={[]}
        disabled={false}
        onChange={vi.fn()}
        issueByKey={{}}
      />,
    );

    const trigger = screen.getByRole('button', { name: /飞书.*未配置/ });
    expect(screen.queryByTestId('settings-field-FEISHU_DOMAIN')).not.toBeInTheDocument();

    fireEvent.click(trigger);

    const dialog = screen.getByRole('dialog', { name: '飞书' });
    expect(within(dialog).getByTestId('settings-field-FEISHU_DOMAIN')).toBeInTheDocument();
  });

  it('shows only configured state for an authoritative masked channel', () => {
    const { container } = render(
      <NotificationChannelsPanel
        items={[buildItem({
          key: 'FEISHU_APP_SECRET',
          value: '******',
          rawValueExists: true,
          isMasked: true,
          schema: {
            ...buildItem().schema!,
            key: 'FEISHU_APP_SECRET',
            title: 'Feishu app secret',
            uiControl: 'password',
            isSensitive: true,
            options: [],
          },
        })]}
        configuredChannels={['feishu']}
        disabled={false}
        onChange={vi.fn()}
        issueByKey={{}}
      />,
    );

    expect(screen.getByRole('button', { name: /飞书.*已配置/ })).toBeInTheDocument();
    expect(container).not.toHaveTextContent('******');
  });
});
