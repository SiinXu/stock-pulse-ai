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
      SERVERCHAN3_SEND_KEY: 'sctp123',
      CUSTOM_WEBHOOK_URLS: 'https://example.com/hook',
    });

    // Routing fields use serverchan3/custom, not the config ids.
    expect(configured).toEqual(new Set(['serverchan3', 'custom']));
  });

  it('keeps every declared routing alias consistent with the channel catalog', () => {
    for (const channel of NOTIFICATION_CHANNELS) {
      const expected = ROUTING_ALIASES[channel.id];
      expect(channel.routingValue).toBe(expected);
    }
  });
});
