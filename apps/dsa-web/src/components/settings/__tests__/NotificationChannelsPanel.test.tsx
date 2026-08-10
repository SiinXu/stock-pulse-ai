import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { SystemConfigItem } from '../../../types/systemConfig';
import { NotificationChannelsPanel } from '../NotificationChannelsPanel';
import {
  computeNotificationConfigurationFingerprint,
  resetNotificationChannelTestStatusForTests,
  setNotificationChannelTestRecord,
} from '../notificationChannelTestStatus';
import { buildNotificationEventRoutes } from '../notificationEventRoutes';

const testNotificationChannel = vi.hoisted(() => vi.fn());

vi.mock('../../../api/systemConfig', () => ({
  systemConfigApi: {
    testNotificationChannel,
  },
}));

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
  beforeEach(() => {
    resetNotificationChannelTestStatusForTests();
    testNotificationChannel.mockReset();
    testNotificationChannel.mockResolvedValue({
      success: true,
      message: 'ok',
      errorCode: null,
      stage: 'notification_send',
      retryable: false,
      latencyMs: 10,
      attempts: [],
    });
  });

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

  it('renders event routing overview and per-card event chips', () => {
    render(
      <NotificationChannelsPanel
        items={[buildItem()]}
        configuredChannels={['feishu']}
        disabled={false}
        onChange={vi.fn()}
        issueByKey={{}}
        eventRoutes={buildNotificationEventRoutes({
          NOTIFICATION_REPORT_CHANNELS: 'feishu',
          NOTIFICATION_ALERT_CHANNELS: 'email',
          NOTIFICATION_SYSTEM_ERROR_CHANNELS: '',
        }, ['feishu', 'email'])}
      />,
    );

    expect(screen.getByTestId('notification-event-routing')).toBeInTheDocument();
    expect(screen.getByTestId('notification-event-route-report')).toHaveTextContent('飞书');
    expect(screen.getByTestId('notification-event-route-alert')).toHaveTextContent('邮件');
    expect(screen.getByTestId('notification-event-route-system_error')).toHaveTextContent(/全部已配置渠道|All configured/);
    expect(screen.getByTestId('notification-channel-card-feishu')).toHaveTextContent(/分析报告|Analysis report/);
  });

  it('keeps saved effective routes authoritative while a draft is failed', () => {
    render(
      <NotificationChannelsPanel
        items={[buildItem()]}
        configuredChannels={['feishu', 'email']}
        disabled={false}
        onChange={vi.fn()}
        issueByKey={{}}
        eventRoutes={buildNotificationEventRoutes({
          NOTIFICATION_REPORT_CHANNELS: 'email',
        }, ['feishu', 'email'])}
        draftEventRoutes={buildNotificationEventRoutes({
          NOTIFICATION_REPORT_CHANNELS: 'feishu',
        }, ['feishu', 'email'])}
        hasPendingRoutes
        saveStatus="failed"
      />,
    );

    const reportRoute = screen.getByTestId('notification-event-route-report');
    expect(reportRoute).toHaveTextContent(/邮件|Email/);
    expect(reportRoute).not.toHaveTextContent(/飞书|Feishu/);
    expect(screen.getByText(/当前投递路径未改变|current delivery path is unchanged/)).toBeInTheDocument();
  });

  it('shows last test status on cards and supports test-to-bind from the channel modal', async () => {
    const webhookItem = buildItem({
      key: 'FEISHU_WEBHOOK_URL',
      value: 'https://example.com/hook',
      schema: {
        ...buildItem().schema!,
        key: 'FEISHU_WEBHOOK_URL',
        title: 'Feishu webhook',
        options: [],
      },
    });
    render(
      <NotificationChannelsPanel
        items={[webhookItem]}
        configuredChannels={['feishu']}
        disabled={false}
        onChange={vi.fn()}
        issueByKey={{}}
        configVersion="config-v1"
        persistedValuesByKey={{ FEISHU_WEBHOOK_URL: webhookItem.value }}
        maskToken="******"
      />,
    );

    const card = screen.getByTestId('notification-channel-card-feishu');
    expect(card).toHaveTextContent(/待验证|Needs test/);

    fireEvent.click(card);
    fireEvent.click(screen.getByTestId('notification-channel-send-test'));

    await waitFor(() => expect(testNotificationChannel).toHaveBeenCalledWith(expect.objectContaining({
      channel: 'feishu',
      maskToken: '******',
    })));
    expect(await screen.findByText(/测试成功|Test succeeded|Test success/i)).toBeInTheDocument();
    await waitFor(() => expect(screen.getByTestId('notification-channel-card-feishu')).toHaveTextContent(/已验证|Verified/));
  });

  it('separates DingTalk group webhook settings from app bot and Stream settings', () => {
    const groupWebhook = buildItem({
      key: 'DINGTALK_WEBHOOK_URL',
      value: '******',
      rawValueExists: true,
      isMasked: true,
      schema: {
        ...buildItem().schema!,
        key: 'DINGTALK_WEBHOOK_URL',
        title: 'DingTalk Group Webhook URL',
        uiControl: 'password',
        isSensitive: true,
        options: [],
      },
    });
    const signingSecret = buildItem({
      ...groupWebhook,
      key: 'DINGTALK_SECRET',
      schema: {
        ...groupWebhook.schema!,
        key: 'DINGTALK_SECRET',
        title: 'DingTalk signing secret',
      },
    });
    const appKey = buildItem({
      ...groupWebhook,
      key: 'DINGTALK_APP_KEY',
      schema: {
        ...groupWebhook.schema!,
        key: 'DINGTALK_APP_KEY',
        title: 'DingTalk App Key',
      },
    });

    const { container } = render(
      <NotificationChannelsPanel
        items={[groupWebhook, signingSecret, appKey]}
        configuredChannels={['dingtalk']}
        disabled={false}
        onChange={vi.fn()}
        issueByKey={{}}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: /钉钉.*已配置/ }));

    const dialog = screen.getByRole('dialog', { name: '钉钉' });
    expect(within(dialog).getByRole('heading', { name: '群机器人 Webhook' })).toBeInTheDocument();
    expect(within(dialog).getByRole('heading', { name: '应用机器人 / Stream' })).toBeInTheDocument();
    expect(within(dialog).getByTestId('settings-field-DINGTALK_WEBHOOK_URL')).toBeInTheDocument();
    expect(within(dialog).getByTestId('settings-field-DINGTALK_SECRET')).toBeInTheDocument();
    expect(within(dialog).getByTestId('settings-field-DINGTALK_APP_KEY')).toBeInTheDocument();
    expect(container).not.toHaveTextContent('******');
  });

  it('invalidates a verified badge immediately when a governed field is edited', async () => {
    const item = buildItem({
      key: 'FEISHU_WEBHOOK_URL',
      value: 'https://example.com/hook',
      schema: {
        ...buildItem().schema!,
        key: 'FEISHU_WEBHOOK_URL',
        title: 'Feishu webhook',
        options: [],
      },
    });
    const configFingerprint = await computeNotificationConfigurationFingerprint(
      'feishu',
      'config-v1',
      [{ key: item.key, value: item.value }],
    );
    setNotificationChannelTestRecord({
      channel: 'feishu',
      outcome: 'verified',
      message: 'ok',
      attempts: [],
      configVersion: 'config-v1',
      configFingerprint,
      at: Date.now(),
    });

    render(
      <NotificationChannelsPanel
        items={[item]}
        configuredChannels={['feishu']}
        disabled={false}
        onChange={vi.fn()}
        issueByKey={{}}
        configVersion="config-v1"
        persistedValuesByKey={{ FEISHU_WEBHOOK_URL: item.value }}
      />,
    );

    await waitFor(() => expect(screen.getByTestId('notification-channel-card-feishu')).toHaveTextContent(/已验证|Verified/));
    fireEvent.click(screen.getByTestId('notification-channel-card-feishu'));
    fireEvent.change(within(screen.getByRole('dialog', { name: '飞书' })).getByRole('textbox'), {
      target: { value: 'https://example.com/changed' },
    });
    expect(screen.getByTestId('notification-channel-card-feishu')).toHaveTextContent(/待验证|Needs test/);
  });

  it('shows partial custom delivery as degraded and withholds event binding', async () => {
    testNotificationChannel.mockResolvedValueOnce({
      success: true,
      message: 'partial',
      errorCode: null,
      stage: 'notification_send',
      retryable: true,
      latencyMs: 10,
      attempts: [
        { channel: 'custom', success: true, message: 'sent', target: 'first/***', stage: 'send', retryable: false },
        { channel: 'custom', success: false, message: 'failed', target: 'second/***', errorCode: 'timeout', stage: 'send', retryable: true },
      ],
    });
    const item = buildItem({
      key: 'CUSTOM_WEBHOOK_URLS',
      value: 'https://example.com/one,https://example.com/two',
      schema: {
        ...buildItem().schema!,
        key: 'CUSTOM_WEBHOOK_URLS',
        title: 'Custom webhooks',
        options: [],
      },
    });

    render(
      <NotificationChannelsPanel
        items={[item]}
        configuredChannels={['custom']}
        disabled={false}
        onChange={vi.fn()}
        issueByKey={{}}
        configVersion="config-v1"
        persistedValuesByKey={{ CUSTOM_WEBHOOK_URLS: item.value }}
        eventRoutes={buildNotificationEventRoutes({
          NOTIFICATION_REPORT_CHANNELS: 'email',
        }, ['custom', 'email'])}
        onBindEvents={vi.fn()}
        maskToken="******"
      />,
    );

    fireEvent.click(screen.getByTestId('notification-channel-card-custom_webhook'));
    fireEvent.click(screen.getByTestId('notification-channel-send-test'));
    expect((await screen.findAllByText(/部分成功|Partially passed/)).length).toBeGreaterThan(0);
    expect(screen.queryByTestId('notification-channel-bind-events')).not.toBeInTheDocument();
    expect(screen.getByTestId('notification-channel-card-custom_webhook')).toHaveTextContent(/部分可达|Partially reachable/);
  });

  it('binds selected events only after exact saved configuration is verified', async () => {
    const onBindEvents = vi.fn();
    const item = buildItem({
      key: 'FEISHU_WEBHOOK_URL',
      value: 'https://example.com/hook',
      schema: {
        ...buildItem().schema!,
        key: 'FEISHU_WEBHOOK_URL',
        title: 'Feishu webhook',
        options: [],
      },
    });
    render(
      <NotificationChannelsPanel
        items={[item]}
        configuredChannels={['feishu', 'email']}
        disabled={false}
        onChange={vi.fn()}
        issueByKey={{}}
        configVersion="config-v1"
        persistedValuesByKey={{ FEISHU_WEBHOOK_URL: item.value }}
        eventRoutes={buildNotificationEventRoutes({
          NOTIFICATION_REPORT_CHANNELS: 'email',
          NOTIFICATION_ALERT_CHANNELS: '',
          NOTIFICATION_SYSTEM_ERROR_CHANNELS: 'email',
        }, ['feishu', 'email'])}
        onBindEvents={onBindEvents}
        maskToken="******"
      />,
    );

    fireEvent.click(screen.getByTestId('notification-channel-card-feishu'));
    fireEvent.click(screen.getByTestId('notification-channel-send-test'));
    await screen.findByText(/测试成功|Test succeeded|Test success/i);
    fireEvent.click(screen.getByRole('checkbox', { name: /分析报告|Analysis report/ }));
    fireEvent.click(screen.getByTestId('notification-channel-bind-events'));
    expect(onBindEvents).toHaveBeenCalledWith('feishu', ['report']);
  });
});
