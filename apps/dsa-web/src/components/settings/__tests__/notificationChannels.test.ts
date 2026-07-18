// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { describe, expect, it } from 'vitest';
import {
  getConfiguredRoutingValues,
  isConfiguredChannelValue,
  NOTIFICATION_CHANNELS,
} from '../notificationChannels';

// Channels whose routing value (ROUTABLE_NOTIFICATION_CHANNELS) differs from
// the frontend config id. Every other channel routes by its own id.
const ROUTING_ALIASES: Record<string, string> = {
  serverchan: 'serverchan3',
  custom_webhook: 'custom',
};

describe('isConfiguredChannelValue', () => {
  it('treats empty and disabled-switch values as unconfigured', () => {
    expect(isConfiguredChannelValue('')).toBe(false);
    expect(isConfiguredChannelValue('   ')).toBe(false);
    expect(isConfiguredChannelValue('false')).toBe(false);
    expect(isConfiguredChannelValue('False')).toBe(false);
    expect(isConfiguredChannelValue(null)).toBe(false);
    expect(isConfiguredChannelValue(undefined)).toBe(false);
  });

  it('treats any other value as configured', () => {
    expect(isConfiguredChannelValue('true')).toBe(true);
    expect(isConfiguredChannelValue('https://example.com/webhook')).toBe(true);
    expect(isConfiguredChannelValue('0')).toBe(true);
  });
});

describe('getConfiguredRoutingValues', () => {
  it('returns routing values only for channels with a configured key', () => {
    const configured = getConfiguredRoutingValues({
      FEISHU_WEBHOOK_URL: 'https://open.feishu.cn/hook',
      TELEGRAM_BOT_TOKEN: '',
      WECHAT_ENABLED: 'false',
      UNRELATED_KEY: 'value',
    });

    expect(configured).toEqual(new Set(['feishu']));
  });

  it('maps config ids to routing values where they differ', () => {
    const configured = getConfiguredRoutingValues({
      SERVERCHAN3_SENDKEY: 'sctp123',
      CUSTOM_WEBHOOK_URLS: 'https://example.com/hook',
    });

    // Routing fields use serverchan3/custom, not the config ids.
    expect(configured).toEqual(new Set(['serverchan3', 'custom']));
  });

  it.each<[string, Record<string, string>]>([
    ['WeChat advanced field only', { WECHAT_MSG_TYPE: 'markdown' }],
    ['DingTalk secret only', { DINGTALK_SECRET: 'secret' }],
    ['Feishu advanced field only', { FEISHU_RECEIVE_ID_TYPE: 'chat_id' }],
    ['incomplete Feishu app credentials', { FEISHU_APP_ID: 'cli_123', FEISHU_APP_SECRET: 'secret' }],
    ['Telegram thread id only', { TELEGRAM_MESSAGE_THREAD_ID: '123' }],
    ['incomplete Telegram credentials', { TELEGRAM_BOT_TOKEN: 'token' }],
    ['email host only', { EMAIL_HOST: 'smtp.example.com' }],
    ['incomplete email credentials', { EMAIL_SENDER: 'sender@example.com' }],
    ['incomplete Pushover credentials', { PUSHOVER_USER_KEY: 'user-key' }],
    ['ntfy token only', { NTFY_TOKEN: 'token' }],
    ['ntfy server without a topic', { NTFY_URL: 'https://ntfy.sh' }],
    ['invalid ntfy scheme', { NTFY_URL: 'ftp://ntfy.example/topic' }],
    ['Gotify token only', { GOTIFY_TOKEN: 'token' }],
    ['incomplete Gotify credentials', { GOTIFY_URL: 'https://gotify.example.com' }],
    ['Gotify message endpoint', { GOTIFY_URL: 'https://gotify.example.com/message', GOTIFY_TOKEN: 'token' }],
    ['Gotify URL with query', { GOTIFY_URL: 'https://gotify.example.com?tenant=1', GOTIFY_TOKEN: 'token' }],
    ['PushPlus topic only', { PUSHPLUS_TOPIC: 'topic' }],
    ['custom webhook bearer token only', { CUSTOM_WEBHOOK_BEARER_TOKEN: 'token' }],
    ['custom webhook list without an endpoint', { CUSTOM_WEBHOOK_URLS: ' , , ' }],
    ['Discord public key only', { DISCORD_INTERACTIONS_PUBLIC_KEY: 'public-key' }],
    ['incomplete Discord bot credentials', { DISCORD_BOT_TOKEN: 'token' }],
    ['Slack channel id only', { SLACK_CHANNEL_ID: 'C123' }],
    ['incomplete Slack bot credentials', { SLACK_BOT_TOKEN: 'token' }],
    ['AstrBot token only', { ASTRBOT_TOKEN: 'token' }],
  ])('does not expose a route for %s', (_label, values) => {
    expect(getConfiguredRoutingValues(values)).toEqual(new Set());
  });

  it.each<[string, Record<string, string>, string]>([
    ['WeChat webhook', { WECHAT_WEBHOOK_URL: 'https://qyapi.weixin.qq.com/hook' }, 'wechat'],
    ['DingTalk webhook', { DINGTALK_WEBHOOK_URL: 'https://oapi.dingtalk.com/hook' }, 'dingtalk'],
    ['Feishu webhook', { FEISHU_WEBHOOK_URL: 'https://open.feishu.cn/hook' }, 'feishu'],
    [
      'Feishu app bot',
      { FEISHU_APP_ID: 'cli_123', FEISHU_APP_SECRET: 'secret', FEISHU_CHAT_ID: 'oc_123' },
      'feishu',
    ],
    [
      'Telegram bot',
      { TELEGRAM_BOT_TOKEN: 'token', TELEGRAM_CHAT_ID: '-100123' },
      'telegram',
    ],
    [
      'email sender',
      { EMAIL_SENDER: 'sender@example.com', EMAIL_PASSWORD: 'password' },
      'email',
    ],
    [
      'Pushover',
      { PUSHOVER_USER_KEY: 'user-key', PUSHOVER_API_TOKEN: 'api-token' },
      'pushover',
    ],
    ['ntfy topic endpoint', { NTFY_URL: 'https://ntfy.sh/stock-alerts' }, 'ntfy'],
    ['ntfy malformed but non-empty topic', { NTFY_URL: 'https://ntfy.sh/%E0%A4%A' }, 'ntfy'],
    [
      'Gotify server',
      { GOTIFY_URL: 'https://gotify.example.com/base', GOTIFY_TOKEN: 'token' },
      'gotify',
    ],
    ['Discord webhook', { DISCORD_WEBHOOK_URL: 'https://discord.com/api/webhooks/1/token' }, 'discord'],
    [
      'Discord bot with main channel',
      { DISCORD_BOT_TOKEN: 'token', DISCORD_MAIN_CHANNEL_ID: '123' },
      'discord',
    ],
    [
      'Discord bot with legacy channel alias',
      { DISCORD_BOT_TOKEN: 'token', DISCORD_CHANNEL_ID: '123' },
      'discord',
    ],
    ['Slack webhook', { SLACK_WEBHOOK_URL: 'https://hooks.slack.com/services/1/2/3' }, 'slack'],
    ['Slack bot', { SLACK_BOT_TOKEN: 'token', SLACK_CHANNEL_ID: 'C123' }, 'slack'],
    ['Slack credential text matching a disabled switch', { SLACK_BOT_TOKEN: 'false', SLACK_CHANNEL_ID: 'C123' }, 'slack'],
    ['PushPlus', { PUSHPLUS_TOKEN: 'token' }, 'pushplus'],
    ['ServerChan', { SERVERCHAN3_SENDKEY: 'send-key' }, 'serverchan3'],
    ['custom webhook', { CUSTOM_WEBHOOK_URLS: ' , https://example.com/hook, ' }, 'custom'],
    ['AstrBot', { ASTRBOT_URL: 'https://astrbot.example.com/webhook' }, 'astrbot'],
  ])('exposes the %s route when its minimal group is complete', (_label, values, routingValue) => {
    expect(getConfiguredRoutingValues(values)).toEqual(new Set([routingValue]));
  });

  it('keeps every declared routing alias consistent with the channel catalog', () => {
    for (const channel of NOTIFICATION_CHANNELS) {
      const expected = ROUTING_ALIASES[channel.id];
      expect(channel.routingValue).toBe(expected);
    }
  });
});
