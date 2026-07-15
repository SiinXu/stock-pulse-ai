import { describe, expect, it } from 'vitest';

import { getSettingsSaveGroup, mergeSaveGroupItems } from '../settingsSaveGroups';

describe('settings save groups', () => {
  it('keeps model access and task routing in one atomic group', () => {
    expect(getSettingsSaveGroup({ key: 'LLM_OPENAI_API_KEY', value: 'secret' })).toBe('ai.model_graph');
    expect(getSettingsSaveGroup({ key: 'LITELLM_MODEL', value: 'modelref:v1:one:route' })).toBe('ai.model_graph');
    expect(getSettingsSaveGroup({ key: 'VISION_MODEL', value: 'modelref:v1:two:route' })).toBe('ai.model_graph');
  });

  it('prefers backend-authored group metadata', () => {
    expect(getSettingsSaveGroup({
      key: 'CUSTOM_SETTING',
      value: 'one',
      rawValueExists: true,
      isMasked: false,
      schema: {
        key: 'CUSTOM_SETTING',
        category: 'system',
        dataType: 'string',
        uiControl: 'text',
        isSensitive: false,
        isRequired: false,
        isEditable: true,
        options: [],
        validation: {},
        displayOrder: 1,
        saveGroup: 'system.custom',
      },
    })).toBe('system.custom');
  });

  it('lets the dedicated editor own duplicate keys', () => {
    expect(mergeSaveGroupItems(
      [{ key: 'LLM_CHANNELS', value: 'old' }],
      [{ key: 'LLM_CHANNELS', value: 'new' }, { key: 'LLM_NEW_MODELS', value: 'gpt' }],
    )).toEqual([
      { key: 'LLM_CHANNELS', value: 'new' },
      { key: 'LLM_NEW_MODELS', value: 'gpt' },
    ]);
  });
});
