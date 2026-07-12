import { describe, expect, it } from 'vitest';
import { NOTIFICATION_CHANNELS } from '../notificationChannels';
import { DATA_PROVIDERS } from '../dataProviders';
import { MODEL_PROVIDERS } from '../modelProviders';
import { getCategoryFieldGroupId } from '../categoryFieldGroups';
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

  it('splits ai_model into model + providers tabs', () => {
    const subs = getSubCategories('ai_model')?.map((sub) => sub.id);
    expect(subs).toEqual(['model', 'providers']);
  });

  it('splits data_source into source + providers tabs', () => {
    const subs = getSubCategories('data_source')?.map((sub) => sub.id);
    expect(subs).toEqual(['source', 'providers']);
  });

  it('splits notification into channels + rules tabs', () => {
    const subs = getSubCategories('notification')?.map((sub) => sub.id);
    expect(subs).toEqual(['channels', 'rules']);
  });

  it('routes provider keys to the merged providers tab', () => {
    expect(getSubCategoryOfKey('ai_model', 'OPENAI_API_KEY')).toBe('providers');
    expect(getSubCategoryOfKey('ai_model', 'ANTHROPIC_API_KEY')).toBe('providers');
    expect(getSubCategoryOfKey('ai_model', 'AIHUBMIX_KEY')).toBe('providers');
  });

  it('scopes model provider configured keys to their own provider group', () => {
    for (const provider of MODEL_PROVIDERS) {
      expect(provider.configuredKeys.length, provider.id).toBeGreaterThan(0);
      for (const key of provider.configuredKeys) {
        // The configured badge must read this provider's own ai_model fields,
        // not another provider's or an unrelated (e.g. data-source) credential.
        expect(getCategoryFieldGroupId('ai_model', key), key).toBe(provider.id);
        expect(getSubCategoryOfKey('ai_model', key), key).toBe('providers');
      }
    }
  });

  it('routes non-provider ai_model keys to the model tab', () => {
    expect(getSubCategoryOfKey('ai_model', 'GENERATION_BACKEND')).toBe('model');
    expect(getSubCategoryOfKey('ai_model', 'LLM_CHANNELS')).toBe('model');
    expect(getSubCategoryOfKey('ai_model', 'LLM_PROMPT_CACHE_HINTS_ENABLED')).toBe('model');
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
      ai_model: [
        { key: 'GENERATION_BACKEND' },
        { key: 'LLM_CHANNELS' },
        { key: 'OPENAI_API_KEY' },
      ],
    };
    expect(getSubCategoryCount('ai_model', 'model', itemsByCategory)).toBe(2);
    expect(getSubCategoryCount('ai_model', 'providers', itemsByCategory)).toBe(1);

    const visible = getVisibleSubCategories('ai_model', itemsByCategory).map((sub) => sub.id);
    expect(visible).toEqual(['model', 'providers']);
  });

  it('keeps channels + providers tabs visible even without matching items', () => {
    const notif = getVisibleSubCategories('notification', { notification: [{ key: 'REPORT_TYPE' }] }).map((s) => s.id);
    expect(notif).toContain('channels');
    expect(notif).toContain('rules');

    const ai = getVisibleSubCategories('ai_model', { ai_model: [{ key: 'GENERATION_BACKEND' }] }).map((s) => s.id);
    expect(ai).toContain('providers');

    const data = getVisibleSubCategories('data_source', { data_source: [{ key: 'NEWS_MAX_AGE_DAYS' }] }).map((s) => s.id);
    expect(data).toEqual(['source', 'providers']);
  });

  it('defaults to the first visible tab', () => {
    expect(getDefaultSubCategory('base')).toBeNull();
    expect(getDefaultSubCategory('system')).toBeNull();
    expect(getDefaultSubCategory('ai_model')).toBe('model');
    expect(getDefaultSubCategory('data_source')).toBe('source');
    expect(getDefaultSubCategory('notification')).toBe('channels');
  });
});
