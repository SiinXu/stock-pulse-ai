import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { ReactNode } from 'react';
import { useUiLanguage, UiLanguageProvider } from '../../../contexts/UiLanguageContext';
import { UI_LANGUAGE_STORAGE_KEY } from '../../../utils/uiLanguage';
import { NotificationTestPanel } from '../NotificationTestPanel';
import { chooseOption, openListbox } from '../../../test-utils';

// jsdom does not implement scrollIntoView, while Select calls it to keep the active item visible when opening a dropdown.
if (!HTMLElement.prototype.scrollIntoView) {
  HTMLElement.prototype.scrollIntoView = () => {};
}

const testNotificationChannel = vi.hoisted(() => vi.fn());

vi.mock('../../../api/systemConfig', () => ({
  systemConfigApi: {
    testNotificationChannel,
  },
}));

describe('NotificationTestPanel', () => {
  beforeEach(() => {
    testNotificationChannel.mockReset();
    testNotificationChannel.mockResolvedValue({
      success: true,
      message: 'ok',
      errorCode: null,
      stage: 'notification_send',
      retryable: false,
      latencyMs: 12,
      attempts: [
        {
          channel: 'custom',
          success: true,
          message: 'sent',
          target: 'https://example.com/hook?token=***',
          errorCode: null,
          stage: 'notification_send',
          retryable: false,
          latencyMs: 12,
          httpStatus: 200,
        },
      ],
    });
  });

  it('submits draft notification items and renders attempt details', async () => {
    render(
      <NotificationTestPanel
        items={[{ key: 'CUSTOM_WEBHOOK_URLS', value: 'https://example.com/hook?token=secret' }]}
        maskToken="******"
      />,
    );

    expect(screen.getByTestId('settings-summary-notification-test-channel')).toHaveTextContent('企业微信');
    expect(screen.getByTestId('settings-summary-notification-test-timeout')).toHaveTextContent('20 s');
    expect(screen.queryByLabelText('渠道')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '配置' }));
    const channelSelect = screen.getByLabelText('渠道');
    const titleInput = screen.getByLabelText('标题');
    expect(channelSelect.parentElement?.parentElement).toHaveClass('w-full');
    expect(titleInput.parentElement?.parentElement).toHaveClass('w-full');
    const channelListbox = openListbox(channelSelect);
    expect(within(channelListbox).getByRole('option', { name: '钉钉' })).toBeInTheDocument();
    expect(within(channelListbox).getByRole('option', { name: 'ntfy' })).toBeInTheDocument();
    expect(within(channelListbox).getByRole('option', { name: 'Gotify' })).toBeInTheDocument();
    fireEvent.click(channelSelect);
    chooseOption(channelSelect, 'custom');
    fireEvent.click(screen.getByRole('button', { name: /发送测试/ }));

    await waitFor(() => expect(testNotificationChannel).toHaveBeenCalledWith(expect.objectContaining({
      channel: 'custom',
      items: [{ key: 'CUSTOM_WEBHOOK_URLS', value: 'https://example.com/hook?token=secret' }],
      maskToken: '******',
      timeoutSeconds: 20,
    })));
    expect(screen.queryByRole('dialog', { name: '通知测试' })).not.toBeInTheDocument();
    expect(await screen.findByText('测试成功')).toBeInTheDocument();
    expect(screen.getByText('HTTP 200')).toBeInTheDocument();
    expect(screen.getByText('https://example.com/hook?token=***')).toBeInTheDocument();
  });

  it('tests a DingTalk draft while preserving masked group robot secrets', async () => {
    testNotificationChannel.mockResolvedValueOnce({
      success: true,
      message: 'dingtalk 通知测试成功',
      errorCode: null,
      stage: 'notification_send',
      retryable: false,
      latencyMs: 9,
      attempts: [
        {
          channel: 'dingtalk',
          success: true,
          message: '通知测试发送成功',
          target: 'https://oapi.dingtalk.com/robot/send?access_token=***',
          errorCode: null,
          stage: 'notification_send',
          retryable: false,
          latencyMs: 9,
          httpStatus: 200,
        },
      ],
    });

    render(
      <NotificationTestPanel
        items={[
          { key: 'DINGTALK_WEBHOOK_URL', value: '******' },
          { key: 'DINGTALK_SECRET', value: '******' },
        ]}
        maskToken="******"
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: '配置' }));
    chooseOption(screen.getByLabelText('渠道'), 'dingtalk');
    fireEvent.click(screen.getByRole('button', { name: /发送测试/ }));

    await waitFor(() => expect(testNotificationChannel).toHaveBeenCalledWith(expect.objectContaining({
      channel: 'dingtalk',
      items: [
        { key: 'DINGTALK_WEBHOOK_URL', value: '******' },
        { key: 'DINGTALK_SECRET', value: '******' },
      ],
      maskToken: '******',
    })));
    expect(await screen.findByText('测试成功')).toBeInTheDocument();
    expect(screen.getByText('https://oapi.dingtalk.com/robot/send?access_token=***')).toBeInTheDocument();
  });

  it('renders a classified DingTalk API rejection without exposing secrets', async () => {
    testNotificationChannel.mockResolvedValueOnce({
      success: false,
      message: 'dingtalk 通知测试失败',
      errorCode: 'send_failed',
      stage: 'notification_send',
      retryable: false,
      latencyMs: 8,
      attempts: [
        {
          channel: 'dingtalk',
          success: false,
          message: '通知测试发送失败',
          target: 'https://oapi.dingtalk.com/robot/send?access_token=***',
          errorCode: 'send_failed',
          stage: 'notification_send',
          retryable: false,
          latencyMs: 8,
        },
      ],
    });

    render(
      <NotificationTestPanel
        items={[
          { key: 'DINGTALK_WEBHOOK_URL', value: '******' },
          { key: 'DINGTALK_SECRET', value: '******' },
        ]}
        maskToken="******"
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: '配置' }));
    chooseOption(screen.getByLabelText('渠道'), 'dingtalk');
    fireEvent.click(screen.getByRole('button', { name: /发送测试/ }));

    expect(await screen.findByText('测试失败')).toBeInTheDocument();
    expect(screen.getAllByText('send_failed').length).toBeGreaterThan(0);
    expect(
      screen.getByText('https://oapi.dingtalk.com/robot/send?access_token=***'),
    ).toBeInTheDocument();
    expect(document.body).not.toHaveTextContent('draft-token');
    expect(document.body).not.toHaveTextContent('SECdraft_signing_secret');
  });

  it('uses translated defaults when UI language changes and user has not edited fields', async () => {
    localStorage.setItem(UI_LANGUAGE_STORAGE_KEY, 'zh');

    const SwitchHarness = ({ children }: { children: ReactNode }) => {
      const { setLanguage } = useUiLanguage();
      return (
        <>
          {children}
          <button type="button" onClick={() => setLanguage('en')}>switch-language</button>
        </>
      );
    };

    render(
      <UiLanguageProvider>
        <SwitchHarness>
          <NotificationTestPanel
            items={[{ key: 'CUSTOM_WEBHOOK_URLS', value: 'https://example.com/hook?token=secret' }]}
            maskToken="******"
          />
        </SwitchHarness>
      </UiLanguageProvider>
    );

    fireEvent.click(screen.getByRole('button', { name: '配置' }));
    const titleInput = screen.getByLabelText('标题');
    const contentInput = screen.getByLabelText('正文');

    expect(titleInput).toHaveValue('StockPulse 通知测试');
    expect(contentInput).toHaveValue('这是一条来自 StockPulse Web 设置页的通知测试消息。');

    fireEvent.click(screen.getByText('switch-language'));

    await waitFor(() => {
      expect(titleInput).toHaveValue('StockPulse notification test');
      expect(contentInput).toHaveValue('This is a test notification from the StockPulse Web settings page.');
    });

    fireEvent.click(screen.getByRole('button', { name: /发送测试|Send test/ }));
    await waitFor(() => expect(testNotificationChannel).toHaveBeenCalledWith(expect.objectContaining({
      title: 'StockPulse notification test',
      content: 'This is a test notification from the StockPulse Web settings page.',
      timeoutSeconds: 20,
    })));
  });

  it('preserves user-edited notification defaults when language switches', async () => {
    localStorage.setItem(UI_LANGUAGE_STORAGE_KEY, 'zh');

    const SwitchHarness = ({ children }: { children: ReactNode }) => {
      const { setLanguage } = useUiLanguage();
      return (
        <>
          {children}
          <button type="button" onClick={() => setLanguage('en')}>switch-language</button>
        </>
      );
    };

    render(
      <UiLanguageProvider>
        <SwitchHarness>
          <NotificationTestPanel
            items={[{ key: 'CUSTOM_WEBHOOK_URLS', value: 'https://example.com/hook?token=secret' }]}
            maskToken="******"
          />
        </SwitchHarness>
      </UiLanguageProvider>
    );

    fireEvent.click(screen.getByRole('button', { name: '配置' }));
    const titleInput = screen.getByLabelText('标题');
    const contentInput = screen.getByLabelText('正文');

    fireEvent.change(titleInput, { target: { value: '自定义标题' } });
    fireEvent.change(contentInput, { target: { value: '自定义正文' } });

    fireEvent.click(screen.getByText('switch-language'));
    expect(titleInput).toHaveValue('自定义标题');
    expect(contentInput).toHaveValue('自定义正文');
  });

  it('renders custom webhook partial failure attempts', async () => {
    testNotificationChannel.mockResolvedValueOnce({
      success: true,
      message: '自定义 Webhook 通知测试部分成功（1/2）',
      errorCode: null,
      stage: 'notification_send',
      retryable: true,
      latencyMs: 35,
      attempts: [
        {
          channel: 'custom',
          success: false,
          message: 'HTTP 500',
          target: 'https://example.com/hook?token=***',
          errorCode: 'http_500',
          stage: 'notification_send',
          retryable: true,
          latencyMs: 12,
          httpStatus: 500,
        },
        {
          channel: 'custom',
          success: true,
          message: 'sent',
          target: 'https://example.com/second/***',
          errorCode: null,
          stage: 'notification_send',
          retryable: false,
          latencyMs: 23,
          httpStatus: 200,
        },
      ],
    });

    render(
      <NotificationTestPanel
        items={[{ key: 'CUSTOM_WEBHOOK_URLS', value: 'https://example.com/hook?token=secret' }]}
        maskToken="******"
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: '配置' }));
    chooseOption(screen.getByLabelText('渠道'), 'custom');
    fireEvent.click(screen.getByRole('button', { name: /发送测试/ }));

    expect(await screen.findByText('测试成功')).toBeInTheDocument();
    expect(screen.getByText(/部分成功/)).toBeInTheDocument();
    expect(screen.getAllByText('HTTP 500').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('HTTP 200')).toBeInTheDocument();
    expect(screen.getByText('http_500')).toHaveClass('text-warning');
    expect(screen.getByText('https://example.com/hook?token=***')).toBeInTheDocument();
  });

  it('renders retryable timeout diagnostics', async () => {
    testNotificationChannel.mockResolvedValueOnce({
      success: false,
      message: '通知测试异常: timeout',
      errorCode: 'timeout',
      stage: 'notification_send',
      retryable: true,
      latencyMs: null,
      attempts: [
        {
          channel: 'wechat',
          success: false,
          message: 'timeout',
          target: 'https://qyapi.example.com/cgi-bin/webhook/send?key=***',
          errorCode: 'timeout',
          stage: 'notification_send',
          retryable: true,
          latencyMs: null,
          httpStatus: null,
        },
      ],
    });

    render(
      <NotificationTestPanel
        items={[{ key: 'WECHAT_WEBHOOK_URL', value: 'https://qyapi.example.com/cgi-bin/webhook/send?key=secret' }]}
        maskToken="******"
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: '配置' }));
    fireEvent.click(screen.getByRole('button', { name: /发送测试/ }));

    expect(await screen.findByText('测试失败')).toBeInTheDocument();
    const timeoutEntries = screen.getAllByText('timeout');
    expect(timeoutEntries[0]).toBeInTheDocument();
    expect(screen.getByText('https://qyapi.example.com/cgi-bin/webhook/send?key=***')).toBeInTheDocument();
    expect(timeoutEntries[0]).toHaveClass('text-warning');
  });
});
