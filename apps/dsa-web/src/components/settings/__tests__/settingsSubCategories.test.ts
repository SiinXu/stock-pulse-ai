// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { describe, expect, it } from 'vitest';
import { NOTIFICATION_CHANNELS } from '../notificationChannels';
import { DATA_PROVIDERS } from '../dataProviders';
import {
  getDefaultSubCategory,
  getSubCategories,
  getSubCategoryCount,
  getSubCategoryOfKey,
  getVisibleSubCategories,
} from '../settingsSubCategories';

describe('settingsSubCategories', () => {
  it('returns null for single-tab categories', () => {
    expect(getSubCategories('base')).toBeNull();
    expect(getSubCategories('backtest')).toBeNull();
    expect(getSubCategories('system')).toBeNull();
    expect(getSubCategories('agent')).toBeNull();
  });

  it('keeps ai_model a single tab — no separate providers entry', () => {
    // Model Access is the only entry for provider credentials (no second
    // "model providers" sub-tab).
    expect(getSubCategories('ai_model')).toBeNull();
    expect(getDefaultSubCategory('ai_model')).toBeNull();
  });

  it('splits data_source into source + providers tabs', () => {
    const subs = getSubCategories('data_source')?.map((sub) => sub.id);
    expect(subs).toEqual(['source', 'providers']);
  });

  it('splits notification into channels + rules tabs', () => {
    const subs = getSubCategories('notification')?.map((sub) => sub.id);
    expect(subs).toEqual(['channels', 'rules']);
  });

  it('never routes an ai_model key to a providers sub', () => {
    for (const key of ['OPENAI_API_KEY', 'ANTHROPIC_API_KEY', 'AIHUBMIX_KEY', 'GENERATION_BACKEND', 'LLM_CHANNELS']) {
      expect(getSubCategoryOfKey('ai_model', key)).not.toBe('providers');
    }
  });

  it('routes every data provider key to the merged providers tab', () => {
    const seen = new Set<string>();
    for (const provider of DATA_PROVIDERS) {
      for (const key of provider.keys) {
        expect(seen.has(key), `duplicate provider key: ${key}`).toBe(false);
        seen.add(key);
        expect(getSubCategoryOfKey('data_source', key), key).toBe('providers');
      }
      for (const key of provider.configuredKeys) {
        expect(provider.keys).toContain(key);
      }
    }
  });

  it('routes general + news data_source keys to the source tab', () => {
    expect(getSubCategoryOfKey('data_source', 'REALTIME_SOURCE_PRIORITY')).toBe('source');
    expect(getSubCategoryOfKey('data_source', 'ENABLE_REALTIME_QUOTE')).toBe('source');
    expect(getSubCategoryOfKey('data_source', 'STOCK_INDEX_REMOTE_UPDATE_ENABLED')).toBe('source');
    expect(getSubCategoryOfKey('data_source', 'NEWS_MAX_AGE_DAYS')).toBe('source');
    expect(getSubCategoryOfKey('data_source', 'BIAS_THRESHOLD')).toBe('source');
  });

  it('routes notification keys to channels or rules', () => {
    const channelKey = `${NOTIFICATION_CHANNELS[0].prefixes[0]}WEBHOOK_URL`;
    expect(getSubCategoryOfKey('notification', channelKey)).toBe('channels');
    expect(getSubCategoryOfKey('notification', 'REPORT_TYPE')).toBe('rules');
    expect(getSubCategoryOfKey('notification', 'NOTIFICATION_REPORT_CHANNELS')).toBe('rules');
  });

  it('counts items per tab and keeps companion tabs visible', () => {
    const itemsByCategory = {
      data_source: [
        { key: 'NEWS_MAX_AGE_DAYS' },
        { key: 'REALTIME_SOURCE_PRIORITY' },
        { key: 'TICKFLOW_API_KEY' },
      ],
    };
    expect(getSubCategoryCount('data_source', 'source', itemsByCategory)).toBe(2);
    expect(getSubCategoryCount('data_source', 'providers', itemsByCategory)).toBe(1);

    const visible = getVisibleSubCategories('data_source', itemsByCategory).map((sub) => sub.id);
    expect(visible).toEqual(['source', 'providers']);
  });

  it('keeps channels + providers tabs visible even without matching items', () => {
    const notif = getVisibleSubCategories('notification', { notification: [{ key: 'REPORT_TYPE' }] }).map((s) => s.id);
    expect(notif).toContain('channels');
    expect(notif).toContain('rules');

    const data = getVisibleSubCategories('data_source', { data_source: [{ key: 'NEWS_MAX_AGE_DAYS' }] }).map((s) => s.id);
    expect(data).toEqual(['source', 'providers']);
  });

  it('defaults to the first visible tab', () => {
    expect(getDefaultSubCategory('base')).toBeNull();
    expect(getDefaultSubCategory('system')).toBeNull();
    expect(getDefaultSubCategory('data_source')).toBe('source');
    expect(getDefaultSubCategory('notification')).toBe('channels');
  });
});
