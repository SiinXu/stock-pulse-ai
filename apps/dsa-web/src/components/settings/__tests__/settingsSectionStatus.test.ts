import { describe, expect, it } from 'vitest';
import { computeSectionStatus } from '../settingsSectionStatus';

const itemsByCategory = {
  ai_model: [{ key: 'LITELLM_MODEL' }, { key: 'OPENAI_API_KEY' }],
  notification: [{ key: 'WECHAT_WEBHOOK_URL' }, { key: 'EVENT_MONITOR_ENABLED' }],
  data_source: [{ key: 'TUSHARE_TOKEN' }],
  system: [{ key: 'LOG_LEVEL' }],
};

describe('computeSectionStatus', () => {
  it('returns an empty map when nothing is dirty or errored', () => {
    expect(computeSectionStatus(itemsByCategory, [])).toEqual({});
  });

  it('lights up the AI & Models section for a dirty ai_model key', () => {
    const status = computeSectionStatus(itemsByCategory, ['LITELLM_MODEL']);
    expect(status.ai_models).toEqual({ isDirty: true });
    expect(status.notifications).toBeUndefined();
  });

  it('routes notification rule keys to Alerts and channel keys to Notifications', () => {
    const status = computeSectionStatus(itemsByCategory, ['WECHAT_WEBHOOK_URL', 'EVENT_MONITOR_ENABLED']);
    // Channel-scoped key -> Notifications; rule-scoped key -> Alerts & Automation.
    expect(status.notifications).toEqual({ isDirty: true });
    expect(status.alerts).toEqual({ isDirty: true });
  });

  it('marks a section as errored when a key has a validation error', () => {
    const status = computeSectionStatus(itemsByCategory, [], ['OPENAI_API_KEY']);
    expect(status.ai_models).toEqual({ hasError: true });
  });

  it('combines dirty and error flags on the same section', () => {
    const status = computeSectionStatus(
      itemsByCategory,
      ['LITELLM_MODEL'],
      ['OPENAI_API_KEY'],
    );
    expect(status.ai_models).toEqual({ isDirty: true, hasError: true });
  });

  it('maps data_source and system keys to their sections', () => {
    const status = computeSectionStatus(itemsByCategory, ['TUSHARE_TOKEN', 'LOG_LEVEL']);
    expect(status.data_sources).toEqual({ isDirty: true });
    expect(status.system_security).toEqual({ isDirty: true });
  });
});
