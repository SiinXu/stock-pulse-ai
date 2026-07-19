// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { createUiLanguageRecord } from '../i18n/createUiLanguageRecord';
import type { UiLanguage } from '../i18n/uiText';

const zh = {
  configured: '已配置', unconfigured: '未配置',
  wechat: '企业微信', feishu: '飞书', telegram: 'Telegram', dingtalk: '钉钉', email: '邮件', discord: 'Discord', slack: 'Slack', pushplus: 'PushPlus', pushover: 'Pushover', ntfy: 'ntfy', gotify: 'Gotify', serverchan: 'Server酱', astrbot: 'AstrBot', custom_webhook: '自定义 Webhook',
  custom: '自定义 Webhook',
  noRoutableChannels: '尚未配置任何通知渠道，配置成功后才能在这里选择接收渠道。',
  goConfigureChannels: '去配置通知渠道',
} as const;

const en: Record<keyof typeof zh, string> = {
  configured: 'Configured', unconfigured: 'Not configured',
  wechat: 'WeCom', feishu: 'Feishu', telegram: 'Telegram', dingtalk: 'DingTalk', email: 'Email', discord: 'Discord', slack: 'Slack', pushplus: 'PushPlus', pushover: 'Pushover', ntfy: 'ntfy', gotify: 'Gotify', serverchan: 'ServerChan', astrbot: 'AstrBot', custom_webhook: 'Custom Webhook',
  custom: 'Custom Webhook',
  noRoutableChannels: 'No notification channel is configured yet. Configure one before choosing where to send.',
  goConfigureChannels: 'Configure channels',
};

export const SETTINGS_NOTIFICATION_TEXT: Record<UiLanguage, Record<keyof typeof zh, string>> = createUiLanguageRecord("locales.settingsNotifications.SETTINGS_NOTIFICATION_TEXT", { zh, en });

export function getNotificationChannelLabel(id: string, language: UiLanguage): string {
  const labels = SETTINGS_NOTIFICATION_TEXT[language] as Record<string, string>;
  return labels[id] ?? id;
}
