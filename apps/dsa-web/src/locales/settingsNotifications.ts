// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { createUiLanguageRecord } from '../i18n/createUiLanguageRecord';
import type { UiLanguage } from '../i18n/uiText';

const zh = {
  configured: '已配置', unconfigured: '未配置',
  wechat: '企业微信', feishu: '飞书', telegram: 'Telegram', dingtalk: '钉钉', email: '邮件', discord: 'Discord', slack: 'Slack', pushplus: 'PushPlus', pushover: 'Pushover', ntfy: 'ntfy', gotify: 'Gotify', serverchan: 'Server酱', astrbot: 'AstrBot', custom_webhook: '自定义 Webhook',
  custom: '自定义 Webhook',
  dingtalkGroupWebhook: '群机器人 Webhook',
  dingtalkGroupWebhookDescription: '用于普通钉钉群机器人推送；签名密钥可选，取决于群机器人的安全设置。',
  dingtalkAppBot: '应用机器人 / Stream',
  dingtalkAppBotDescription: '用于钉钉应用机器人与长连接模式，不会替代群机器人 Webhook。',
  noRoutableChannels: '尚未配置任何通知渠道，配置成功后才能在这里选择接收渠道。',
  goConfigureChannels: '去配置通知渠道',
  eventRoutingTitle: '事件路由',
  eventRoutingDescription: '当前哪些事件会推送到哪些已配置渠道（只读呈现；在「告警与自动化 → 推送路由」中修改）。',
  eventReport: '分析报告',
  eventAlert: '告警触发',
  eventSystemError: '系统错误',
  eventAllConfigured: '全部已配置渠道',
  eventNone: '未指定',
  lastTestOk: '测试通过',
  lastTestFailed: '测试失败',
  lastTestNever: '未测试',
  bindVerified: '已验证',
  bindNeedsTest: '待验证',
  bindUnconfigured: '未配置',
  cardEventsLabel: '接收事件',
  sendChannelTest: '发送测试',
  testingChannel: '测试中…',
  testSuccessBindHint: '渠道可达。保存配置后，再到推送路由中绑定事件。',
  testFailureReviewHint: '请检查 Webhook / Token / 收件人等必填项后重试。',
  hintTimeout: '请求超时。请检查网络、代理，或增大测试超时秒数后重试。',
  hintNetwork: '无法连接通知端点。请核对 URL、防火墙与出站策略。',
  hintSendFailed: '渠道拒绝了消息。请核对密钥、签名、会话 ID 或机器人权限。',
  hintConfigMissing: '该渠道缺少必填配置。请补全字段后再测试。',
  hintConfigInvalid: '渠道配置格式无效。请核对 URL、Token 或 JSON 模板。',
  hintNoChannels: '尚未配置可用通知渠道。请先完成至少一个渠道的配置。',
  hintHttpError: '通知端点返回了错误。请查看 HTTP 状态与目标地址后调整配置。',
  technicalDetails: '技术详情',
  routesEmpty: '暂无事件绑定（空值表示使用全部已配置渠道的默认行为）。',
} as const;

const en: Record<keyof typeof zh, string> = {
  configured: 'Configured', unconfigured: 'Not configured',
  wechat: 'WeCom', feishu: 'Feishu', telegram: 'Telegram', dingtalk: 'DingTalk', email: 'Email', discord: 'Discord', slack: 'Slack', pushplus: 'PushPlus', pushover: 'Pushover', ntfy: 'ntfy', gotify: 'Gotify', serverchan: 'ServerChan', astrbot: 'AstrBot', custom_webhook: 'Custom Webhook',
  custom: 'Custom Webhook',
  dingtalkGroupWebhook: 'Group robot webhook',
  dingtalkGroupWebhookDescription: 'Used for DingTalk group robot delivery. The signing secret is optional and follows the robot security settings.',
  dingtalkAppBot: 'App bot / Stream',
  dingtalkAppBotDescription: 'Used for DingTalk application bots and Stream mode; it does not replace the group robot webhook.',
  noRoutableChannels: 'No notification channel is configured yet. Configure one before choosing where to send.',
  goConfigureChannels: 'Configure channels',
  eventRoutingTitle: 'Event routing',
  eventRoutingDescription: 'Which events currently fan out to which configured channels (read-only here; edit under Alerts & Automation → Push Routing).',
  eventReport: 'Analysis report',
  eventAlert: 'Alert fired',
  eventSystemError: 'System error',
  eventAllConfigured: 'All configured channels',
  eventNone: 'Not set',
  lastTestOk: 'Test passed',
  lastTestFailed: 'Test failed',
  lastTestNever: 'Not tested',
  bindVerified: 'Verified',
  bindNeedsTest: 'Needs test',
  bindUnconfigured: 'Not configured',
  cardEventsLabel: 'Events',
  sendChannelTest: 'Send test',
  testingChannel: 'Testing…',
  testSuccessBindHint: 'Channel is reachable. After saving, bind it to events under Push Routing.',
  testFailureReviewHint: 'Review required fields (webhook, token, recipients) and try again.',
  hintTimeout: 'The request timed out. Check network/proxy settings or raise the test timeout, then retry.',
  hintNetwork: 'Could not reach the notification endpoint. Verify the URL, firewall, and outbound policy.',
  hintSendFailed: 'The channel rejected the message. Check secrets, signing, chat IDs, or bot permissions.',
  hintConfigMissing: 'Required channel fields are missing. Complete the configuration, then retest.',
  hintConfigInvalid: 'Channel configuration is invalid. Check URLs, tokens, or JSON templates.',
  hintNoChannels: 'No usable notification channel is configured yet. Configure at least one channel first.',
  hintHttpError: 'The notification endpoint returned an error. Review the HTTP status and target URL.',
  technicalDetails: 'Technical details',
  routesEmpty: 'No explicit event bindings (empty means the default “all configured channels” behavior).',
};

export const SETTINGS_NOTIFICATION_TEXT: Record<UiLanguage, Record<keyof typeof zh, string>> = createUiLanguageRecord("locales.settingsNotifications.SETTINGS_NOTIFICATION_TEXT", { zh, en });

export type SettingsNotificationTextKey = keyof typeof zh;

export function getNotificationChannelLabel(id: string, language: UiLanguage): string {
  const labels = SETTINGS_NOTIFICATION_TEXT[language] as Record<string, string>;
  return labels[id] ?? id;
}

/** Map test/API error codes to actionable hub copy (paired with apiReasonMapper classification). */
export function getNotificationTestHint(
  errorCode: string | null | undefined,
  language: UiLanguage,
): string {
  const text = SETTINGS_NOTIFICATION_TEXT[language];
  const code = String(errorCode ?? '').trim().toLowerCase();
  switch (code) {
    case 'timeout':
      return text.hintTimeout;
    case 'network_error':
    case 'dns_error':
    case 'connection_refused':
    case 'tls_error':
      return text.hintNetwork;
    case 'send_failed':
    case 'notification_channel_test_failed':
      return text.hintSendFailed;
    case 'config_missing':
      return text.hintConfigMissing;
    case 'config_invalid':
      return text.hintConfigInvalid;
    case 'no_channels':
      return text.hintNoChannels;
    default:
      if (code.startsWith('http_')) {
        return text.hintHttpError;
      }
      return text.testFailureReviewHint;
  }
}
