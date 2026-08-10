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
  eventRoutingDescription: '按已保存配置解析的实际事件投递目标；无效或未配置目标会单独提示。',
  eventReport: '分析报告',
  eventAlert: '告警触发',
  eventSystemError: '系统错误',
  eventAllConfigured: '全部已配置渠道',
  eventNone: '未指定',
  lastTestOk: '测试通过',
  lastTestFailed: '测试失败',
  lastTestPartial: '部分成功',
  lastTestNever: '未测试',
  bindVerified: '已验证',
  bindDegraded: '部分可达',
  bindNeedsTest: '待验证',
  bindUnconfigured: '未配置',
  cardEventsLabel: '接收事件',
  sendChannelTest: '发送测试',
  testingChannel: '测试中…',
  testSuccessBindHint: '渠道可达。可在下方选择并绑定尚未接收的事件。',
  testPartialHint: '仅部分目标可达；修复失败目标并全部测试通过后才能绑定事件。',
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
  routeAuthorityUnknown: '有效路由未知（服务端未提供已配置渠道快照）',
  routeInvalid: '无效目标',
  routeUnconfigured: '未配置目标',
  routePendingDraft: '路由变更待保存',
  routePendingDescription: '这里仍显示已保存的实际路由；草稿保存成功后才会生效。',
  routePendingFailed: '路由草稿保存失败或发生冲突，当前投递路径未改变。',
  lastTestAt: '最近测试',
  testEvidenceSession: '仅当前会话有效，30 分钟后过期',
  bindEventsTitle: '绑定事件',
  bindEventsDescription: '仅完整通过测试且已保存的渠道可以新增事件绑定。',
  bindSelectedEvents: '绑定所选事件',
  bindingPending: '绑定已加入设置草稿，保存成功后才会成为实际投递路径。',
  noEligibleEvents: '该渠道已接收所有事件类型。',
  testDraftOnly: '草稿已测试',
  testDraftOnlyDescription: '当前测试针对未保存草稿；保存完成后需重新测试，才能绑定事件。',
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
  eventRoutingDescription: 'Effective delivery targets resolved from saved configuration, with invalid and unconfigured targets called out separately.',
  eventReport: 'Analysis report',
  eventAlert: 'Alert fired',
  eventSystemError: 'System error',
  eventAllConfigured: 'All configured channels',
  eventNone: 'Not set',
  lastTestOk: 'Test passed',
  lastTestFailed: 'Test failed',
  lastTestPartial: 'Partially passed',
  lastTestNever: 'Not tested',
  bindVerified: 'Verified',
  bindDegraded: 'Partially reachable',
  bindNeedsTest: 'Needs test',
  bindUnconfigured: 'Not configured',
  cardEventsLabel: 'Events',
  sendChannelTest: 'Send test',
  testingChannel: 'Testing…',
  testSuccessBindHint: 'The channel is reachable. You can bind events it does not receive below.',
  testPartialHint: 'Only some targets are reachable. Fix every failed target and pass a complete test before binding events.',
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
  routeAuthorityUnknown: 'Effective routes unknown (the server did not provide its configured-channel snapshot)',
  routeInvalid: 'Invalid targets',
  routeUnconfigured: 'Unconfigured targets',
  routePendingDraft: 'Routing changes pending',
  routePendingDescription: 'This view still shows saved effective routes. Draft changes take effect only after a successful save.',
  routePendingFailed: 'The routing draft failed to save or conflicted; the current delivery path is unchanged.',
  lastTestAt: 'Last tested',
  testEvidenceSession: 'current session only; expires after 30 minutes',
  bindEventsTitle: 'Bind events',
  bindEventsDescription: 'Only fully tested, saved channels can receive new event bindings.',
  bindSelectedEvents: 'Bind selected events',
  bindingPending: 'Bindings were added to the settings draft and become effective only after a successful save.',
  noEligibleEvents: 'This channel already receives every event type.',
  testDraftOnly: 'Draft tested',
  testDraftOnlyDescription: 'This test covered an unsaved draft. Save and retest before binding events.',
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
