import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { useSystemConfig } from '../useSystemConfig';

const { getConfig, validate, update, ConflictError } = vi.hoisted(() => ({
  getConfig: vi.fn(),
  validate: vi.fn(),
  update: vi.fn(),
  ConflictError: class extends Error {
    parsedError = {
      title: 'conflict',
      message: 'conflict',
      rawMessage: 'conflict',
      status: 409,
      category: 'http_error' as const,
    };
  },
}));

vi.mock('../../api/systemConfig', () => ({
  systemConfigApi: {
    getConfig,
    validate,
    update,
  },
  SystemConfigConflictError: ConflictError,
  SystemConfigValidationError: class extends Error {
    issues: unknown[] = [];
    parsedError = {
      title: 'validation error',
      message: 'validation error',
      rawMessage: 'validation error',
      category: 'http_error',
    };
  },
}));

const sampleConfig = {
  configVersion: 'v1',
  maskToken: '******',
  items: [
    {
      key: 'STOCK_LIST',
      value: 'SH600000',
      rawValueExists: true,
      isMasked: false,
      schema: {
        key: 'STOCK_LIST',
        category: 'base',
        dataType: 'string',
        uiControl: 'textarea',
        isSensitive: false,
        isRequired: false,
        isEditable: true,
        options: [],
        validation: {},
        displayOrder: 1,
      },
    },
  ],
};

const sampleLlmConfig = {
  ...sampleConfig,
  items: [
    ...sampleConfig.items,
    {
      key: 'LLM_CHANNELS',
      value: 'primary',
      rawValueExists: true,
      isMasked: false,
      schema: {
        key: 'LLM_CHANNELS',
        category: 'ai_model',
        dataType: 'string',
        uiControl: 'textarea',
        isSensitive: false,
        isRequired: false,
        isEditable: true,
        options: [],
        validation: {},
        displayOrder: 10,
      },
    },
    {
      key: 'LITELLM_MODEL',
      value: 'gpt-5.0',
      rawValueExists: true,
      isMasked: false,
      schema: {
        key: 'LITELLM_MODEL',
        category: 'ai_model',
        dataType: 'string',
        uiControl: 'text',
        isSensitive: false,
        isRequired: false,
        isEditable: true,
        options: [],
        validation: {},
        displayOrder: 20,
      },
    },
    {
      key: 'OPENAI_BASE_URL',
      value: 'https://api.openai.com/v1',
      rawValueExists: true,
      isMasked: false,
      schema: {
        key: 'OPENAI_BASE_URL',
        category: 'ai_model',
        dataType: 'string',
        uiControl: 'text',
        isSensitive: false,
        isRequired: false,
        isEditable: true,
        options: [],
        validation: {},
        displayOrder: 30,
      },
    },
    {
      key: 'OPENAI_VISION_MODEL',
      value: 'gpt-4o-vision',
      rawValueExists: true,
      isMasked: false,
      schema: {
        key: 'OPENAI_VISION_MODEL',
        category: 'ai_model',
        dataType: 'string',
        uiControl: 'text',
        isSensitive: false,
        isRequired: false,
        isEditable: true,
        options: [],
        validation: {},
        displayOrder: 35,
      },
    },
  ],
};

describe('useSystemConfig', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.useRealTimers();
    getConfig.mockResolvedValue(sampleConfig);
    validate.mockResolvedValue({ valid: true, issues: [] });
    update.mockResolvedValue({ warnings: [] });
  });

  const sensitiveConfig = {
    ...sampleConfig,
    items: [
      ...sampleConfig.items,
      {
        key: 'OPENAI_API_KEY',
        value: '',
        rawValueExists: false,
        isMasked: false,
        schema: {
          key: 'OPENAI_API_KEY',
          category: 'ai_model',
          dataType: 'string',
          uiControl: 'password',
          isSensitive: true,
          isRequired: false,
          isEditable: true,
          options: [],
          validation: {},
          displayOrder: 5,
        },
      },
    ],
  };

  it('keeps load callback stable after a successful load', async () => {
    const { result } = renderHook(() => useSystemConfig());
    const firstLoad = result.current.load;

    await act(async () => {
      await result.current.load();
    });

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    expect(getConfig).toHaveBeenCalledTimes(1);
    expect(result.current.load).toBe(firstLoad);
  });

  it('normalizes STOCK_LIST separators before saving', async () => {
    const savedConfig = {
      ...sampleConfig,
      items: sampleConfig.items.map((item) => (
        item.key === 'STOCK_LIST'
          ? { ...item, value: 'SH600000,SH600519,AAPL' }
          : item
      )),
    };

    getConfig.mockResolvedValueOnce(sampleConfig);
    getConfig.mockResolvedValueOnce(savedConfig);

    const { result } = renderHook(() => useSystemConfig());

    await act(async () => {
      await result.current.load();
    });

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    act(() => {
      result.current.setDraftValue('STOCK_LIST', 'SH600000，SH600519\nAAPL');
    });

    await act(async () => {
      await result.current.save();
    });

    expect(validate).toHaveBeenCalledWith({
      items: [{ key: 'STOCK_LIST', value: 'SH600000,SH600519,AAPL' }],
    });
    expect(update).toHaveBeenCalledWith({
      configVersion: 'v1',
      maskToken: '******',
      reloadNow: true,
      items: [{ key: 'STOCK_LIST', value: 'SH600000,SH600519,AAPL' }],
    });
  });

  it('keeps legacy LLM provider fields in save payload without hidden-field migration', async () => {
    const savedConfig = {
      ...sampleLlmConfig,
      items: sampleLlmConfig.items.map((item) => {
        if (item.key === 'LITELLM_MODEL') {
          return { ...item, value: 'qwen/qwen2.5' };
        }
        if (item.key === 'OPENAI_BASE_URL') {
          return { ...item, value: 'https://api.example.org/v1' };
        }
        if (item.key === 'OPENAI_VISION_MODEL') {
          return { ...item, value: 'gpt-4o-mini-vision' };
        }
        return item;
      }),
    };

    getConfig.mockResolvedValueOnce(sampleLlmConfig);
    getConfig.mockResolvedValueOnce(savedConfig);

    const { result } = renderHook(() => useSystemConfig());

    await act(async () => {
      await result.current.load();
    });

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    act(() => {
      result.current.setDraftValue('LITELLM_MODEL', 'qwen/qwen2.5');
      result.current.setDraftValue('OPENAI_BASE_URL', 'https://api.example.org/v1');
      result.current.setDraftValue('OPENAI_VISION_MODEL', 'gpt-4o-mini-vision');
    });

    expect(result.current.hasDirty).toBe(true);

    await act(async () => {
      await result.current.save();
    });

    expect(validate).toHaveBeenCalledTimes(1);
    expect(validate).toHaveBeenCalledWith({
      items: [
        { key: 'LITELLM_MODEL', value: 'qwen/qwen2.5' },
        { key: 'OPENAI_BASE_URL', value: 'https://api.example.org/v1' },
        { key: 'OPENAI_VISION_MODEL', value: 'gpt-4o-mini-vision' },
      ],
    });
    expect(update).toHaveBeenCalledTimes(1);
    expect(update).toHaveBeenCalledWith({
      configVersion: 'v1',
      maskToken: '******',
      reloadNow: true,
      items: [
        { key: 'LITELLM_MODEL', value: 'qwen/qwen2.5' },
        { key: 'OPENAI_BASE_URL', value: 'https://api.example.org/v1' },
        { key: 'OPENAI_VISION_MODEL', value: 'gpt-4o-mini-vision' },
      ],
    });
    expect(result.current.serverItems.find((item) => item.key === 'OPENAI_BASE_URL')?.value).toBe('https://api.example.org/v1');
    expect(result.current.serverItems.find((item) => item.key === 'OPENAI_VISION_MODEL')?.value).toBe('gpt-4o-mini-vision');
    expect(result.current.hasDirty).toBe(false);
    expect(result.current.dirtyCount).toBe(0);
  });

  it('only resets local draft edits without mutating server values for LLM fields', async () => {
    const current = sampleLlmConfig;
    getConfig.mockResolvedValueOnce(current);

    const { result } = renderHook(() => useSystemConfig());

    await act(async () => {
      await result.current.load();
    });

    act(() => {
      result.current.setDraftValue('LITELLM_MODEL', 'qwen/qwen2.5');
      result.current.setDraftValue('OPENAI_BASE_URL', 'https://api.example.org/v1');
    });

    expect(result.current.hasDirty).toBe(true);
    expect(result.current.dirtyCount).toBe(2);

    act(() => {
      result.current.resetDraft();
    });

    expect(result.current.hasDirty).toBe(false);
    expect(result.current.dirtyCount).toBe(0);

    await act(async () => {
      await result.current.save();
    });

    expect(validate).not.toHaveBeenCalled();
    expect(update).not.toHaveBeenCalled();
  });

  it('preserves unrelated runtime model fields when saving non-runtime config keys', async () => {
    const stockUpdatedConfig = {
      ...sampleLlmConfig,
      items: sampleLlmConfig.items.map((item) => {
        if (item.key === 'STOCK_LIST') {
          return { ...item, value: 'SH600000,SH600519' };
        }
        return item;
      }),
    };

    getConfig.mockResolvedValueOnce(sampleLlmConfig);
    getConfig.mockResolvedValueOnce(stockUpdatedConfig);

    const { result } = renderHook(() => useSystemConfig());

    await act(async () => {
      await result.current.load();
    });

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    act(() => {
      result.current.setDraftValue('STOCK_LIST', 'SH600000,SH600519');
    });

    expect(result.current.hasDirty).toBe(true);
    expect(result.current.dirtyCount).toBe(1);

    await act(async () => {
      await result.current.save();
    });

    expect(validate).toHaveBeenCalledTimes(1);
    expect(validate).toHaveBeenCalledWith({
      items: [{ key: 'STOCK_LIST', value: 'SH600000,SH600519' }],
    });
    expect(update).toHaveBeenCalledTimes(1);
    expect(update).toHaveBeenCalledWith({
      configVersion: 'v1',
      maskToken: '******',
      reloadNow: true,
      items: [{ key: 'STOCK_LIST', value: 'SH600000,SH600519' }],
    });

    expect(result.current.serverItems.find((item) => item.key === 'LITELLM_MODEL')?.value).toBe('gpt-5.0');
    expect(result.current.serverItems.find((item) => item.key === 'OPENAI_BASE_URL')?.value).toBe('https://api.openai.com/v1');
    expect(result.current.serverItems.find((item) => item.key === 'OPENAI_VISION_MODEL')?.value).toBe('gpt-4o-vision');
    expect(result.current.hasDirty).toBe(false);
    expect(result.current.dirtyCount).toBe(0);
  });

  it('does not persist edits without an explicit save (no autosave)', async () => {
    getConfig.mockResolvedValue(sampleLlmConfig);

    const { result } = renderHook(() => useSystemConfig());
    await act(async () => {
      await result.current.load();
    });

    vi.useFakeTimers();
    act(() => {
      result.current.setDraftValue('LITELLM_MODEL', 'qwen/qwen2.5');
      result.current.setDraftValue('OPENAI_BASE_URL', 'https://api.example.org/v1');
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000);
    });
    vi.useRealTimers();

    // Editing only changes local dirty state; nothing is validated or persisted.
    expect(validate).not.toHaveBeenCalled();
    expect(update).not.toHaveBeenCalled();
    expect(result.current.hasDirty).toBe(true);
  });

  it('keeps sensitive fields as draft until an explicit save', async () => {
    getConfig.mockResolvedValue(sensitiveConfig);

    const { result } = renderHook(() => useSystemConfig());
    await act(async () => {
      await result.current.load();
    });

    vi.useFakeTimers();
    act(() => {
      result.current.setDraftValue('OPENAI_API_KEY', 'sk-secret-value');
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000);
    });
    vi.useRealTimers();

    expect(update).not.toHaveBeenCalled();
    expect(result.current.hasDirty).toBe(true);
  });

  it('persists all dirty fields on an explicit save', async () => {
    const savedConfig = {
      ...sampleLlmConfig,
      items: sampleLlmConfig.items.map((item) => (
        item.key === 'LITELLM_MODEL' ? { ...item, value: 'qwen/qwen2.5' } : item
      )),
    };
    getConfig.mockResolvedValueOnce(sampleLlmConfig);
    getConfig.mockResolvedValueOnce(savedConfig);

    const { result } = renderHook(() => useSystemConfig());
    await act(async () => {
      await result.current.load();
    });

    act(() => {
      result.current.setDraftValue('LITELLM_MODEL', 'qwen/qwen2.5');
    });

    await act(async () => {
      await result.current.save();
    });

    expect(validate).toHaveBeenCalled();
    expect(update).toHaveBeenCalledWith(expect.objectContaining({
      items: [{ key: 'LITELLM_MODEL', value: 'qwen/qwen2.5' }],
    }));
    expect(result.current.hasDirty).toBe(false);
  });

  it('serializes duplicate save calls onto one in-flight transaction', async () => {
    let resolveUpdate: ((value: { warnings: string[] }) => void) | undefined;
    const pendingUpdate = new Promise<{ warnings: string[] }>((resolve) => {
      resolveUpdate = resolve;
    });
    const savedConfig = {
      ...sampleConfig,
      configVersion: 'v2',
      items: sampleConfig.items.map((item) => ({ ...item, value: 'SH600000,SH600519' })),
    };
    getConfig.mockResolvedValueOnce(sampleConfig).mockResolvedValueOnce(savedConfig);
    update.mockReturnValueOnce(pendingUpdate);

    const { result } = renderHook(() => useSystemConfig());
    await act(async () => { await result.current.load(); });
    act(() => result.current.setDraftValue('STOCK_LIST', 'SH600000,SH600519'));

    let first!: Promise<unknown>;
    let second!: Promise<unknown>;
    act(() => {
      first = result.current.save();
      second = result.current.save();
    });
    expect(first).toBe(second);
    await waitFor(() => expect(update).toHaveBeenCalledTimes(1));

    resolveUpdate?.({ warnings: [] });
    await act(async () => { await first; });
    expect(update).toHaveBeenCalledTimes(1);
  });

  it('preserves a newer edit made while the submitted value is saving', async () => {
    let resolveUpdate: ((value: { warnings: string[] }) => void) | undefined;
    const pendingUpdate = new Promise<{ warnings: string[] }>((resolve) => {
      resolveUpdate = resolve;
    });
    const savedConfig = {
      ...sampleConfig,
      configVersion: 'v2',
      items: sampleConfig.items.map((item) => ({ ...item, value: 'SH600000,SH600519' })),
    };
    getConfig.mockResolvedValueOnce(sampleConfig).mockResolvedValueOnce(savedConfig);
    update.mockReturnValueOnce(pendingUpdate);

    const { result } = renderHook(() => useSystemConfig());
    await act(async () => { await result.current.load(); });
    act(() => result.current.setDraftValue('STOCK_LIST', 'SH600000,SH600519'));
    let saving!: Promise<unknown>;
    act(() => { saving = result.current.save(); });
    await waitFor(() => expect(update).toHaveBeenCalledTimes(1));

    act(() => result.current.setDraftValue('STOCK_LIST', 'SH600000,SH600519,AAPL'));
    resolveUpdate?.({ warnings: [] });
    await act(async () => { await saving; });

    expect(result.current.itemsByCategory.base[0]?.value).toBe('SH600000,SH600519,AAPL');
    expect(result.current.hasDirty).toBe(true);
  });

  it('automatically rebases once when the server changed only unrelated fields', async () => {
    const latestConfig = {
      ...sampleConfig,
      configVersion: 'v2',
    };
    const savedConfig = {
      ...sampleConfig,
      configVersion: 'v3',
      items: sampleConfig.items.map((item) => ({ ...item, value: 'SH600000,SH600519' })),
    };
    getConfig
      .mockResolvedValueOnce(sampleConfig)
      .mockResolvedValueOnce(latestConfig)
      .mockResolvedValueOnce(savedConfig);
    update.mockRejectedValueOnce(new ConflictError('conflict')).mockResolvedValueOnce({ warnings: [] });

    const { result } = renderHook(() => useSystemConfig());
    await act(async () => { await result.current.load(); });
    act(() => result.current.setDraftValue('STOCK_LIST', 'SH600000,SH600519'));
    await act(async () => { await result.current.save(); });

    expect(update).toHaveBeenCalledTimes(2);
    expect(update.mock.calls[1]?.[0]).toEqual(expect.objectContaining({ configVersion: 'v2' }));
    expect(result.current.conflictState).toBeNull();
    expect(result.current.hasDirty).toBe(false);
  });

  it('surfaces a three-way conflict and adopts the selected server value', async () => {
    const latestConfig = {
      ...sampleConfig,
      configVersion: 'v2',
      items: sampleConfig.items.map((item) => ({ ...item, value: 'SH600000,AAPL' })),
    };
    getConfig.mockResolvedValueOnce(sampleConfig).mockResolvedValueOnce(latestConfig);
    update.mockRejectedValueOnce(new ConflictError('conflict'));

    const { result } = renderHook(() => useSystemConfig());
    await act(async () => { await result.current.load(); });
    act(() => result.current.setDraftValue('STOCK_LIST', 'SH600000,SH600519'));
    await act(async () => { await result.current.save(); });

    expect(result.current.conflictState?.fields).toEqual([
      expect.objectContaining({
        key: 'STOCK_LIST',
        base: 'SH600000',
        server: 'SH600000,AAPL',
        local: 'SH600000,SH600519',
        isSensitive: false,
      }),
    ]);
    act(() => result.current.resolveConflictField('STOCK_LIST', 'server'));
    expect(result.current.conflictState).toBeNull();
    expect(result.current.itemsByCategory.base[0]?.value).toBe('SH600000,AAPL');
    expect(result.current.hasDirty).toBe(false);
  });

  it('marks secret conflicts as sensitive without requiring UI plaintext', async () => {
    const latestConfig = {
      ...sensitiveConfig,
      configVersion: 'v2',
      items: sensitiveConfig.items.map((item) => (
        item.key === 'OPENAI_API_KEY'
          ? { ...item, value: '******', rawValueExists: true, isMasked: true }
          : item
      )),
    };
    getConfig.mockResolvedValueOnce(sensitiveConfig).mockResolvedValueOnce(latestConfig);
    update.mockRejectedValueOnce(new ConflictError('conflict'));

    const { result } = renderHook(() => useSystemConfig());
    await act(async () => { await result.current.load(); });
    act(() => result.current.setDraftValue('OPENAI_API_KEY', 'sk-local-secret'));
    await act(async () => { await result.current.save(); });

    expect(result.current.conflictState?.fields[0]).toEqual(expect.objectContaining({
      key: 'OPENAI_API_KEY',
      isSensitive: true,
    }));
  });

  it('includes channel dynamic keys in the three-way conflict', async () => {
    const channelKey = 'LLM_PRIMARY_MODELS';
    const withChannel = {
      ...sampleLlmConfig,
      items: [
        ...sampleLlmConfig.items,
        {
          key: channelKey,
          value: 'gpt-4o-mini',
          rawValueExists: true,
          isMasked: false,
          schema: {
            key: channelKey,
            category: 'ai_model',
            dataType: 'string',
            uiControl: 'text',
            isSensitive: false,
            isRequired: false,
            isEditable: true,
            options: [],
            validation: {},
            displayOrder: 40,
          },
        },
      ],
    };
    const latestConfig = {
      ...withChannel,
      configVersion: 'v2',
      items: withChannel.items.map((item) => (
        item.key === channelKey ? { ...item, value: 'gpt-4o' } : item
      )),
    };
    getConfig.mockResolvedValueOnce(withChannel).mockResolvedValueOnce(latestConfig);
    update.mockRejectedValueOnce(new ConflictError('conflict'));

    const { result } = renderHook(() => useSystemConfig());
    await act(async () => { await result.current.load(); });
    act(() => result.current.setDraftValue(channelKey, 'gpt-4o-mini,custom'));
    await act(async () => { await result.current.save(); });

    expect(result.current.conflictState?.fields).toEqual([
      expect.objectContaining({
        key: channelKey,
        base: 'gpt-4o-mini',
        server: 'gpt-4o',
        local: 'gpt-4o-mini,custom',
      }),
    ]);

    // Keeping the local value preserves the pending draft over the new base.
    act(() => result.current.resolveConflictField(channelKey, 'local'));
    expect(result.current.conflictState).toBeNull();
    const item = result.current.itemsByCategory.ai_model.find((entry) => entry.key === channelKey);
    expect(item?.value).toBe('gpt-4o-mini,custom');
    expect(result.current.hasDirty).toBe(true);
  });
});
