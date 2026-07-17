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

function createDeferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((promiseResolve, promiseReject) => {
    resolve = promiseResolve;
    reject = promiseReject;
  });
  return { promise, resolve, reject };
}

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

  it('keeps load callback stable and marks legacy notification status as unknown', async () => {
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
    expect(result.current.configuredNotificationChannels).toBeNull();
  });

  it('keeps server-configured notification channels when their values are masked', async () => {
    getConfig.mockResolvedValue({
      ...sampleConfig,
      configuredNotificationChannels: ['ntfy', 'gotify'],
      items: [
        ...sampleConfig.items,
        {
          key: 'NTFY_URL',
          value: '******',
          rawValueExists: true,
          isMasked: true,
        },
        {
          key: 'GOTIFY_URL',
          value: '******',
          rawValueExists: true,
          isMasked: true,
        },
        {
          key: 'GOTIFY_TOKEN',
          value: '******',
          rawValueExists: true,
          isMasked: true,
        },
      ],
    });
    const { result } = renderHook(() => useSystemConfig());

    await act(async () => {
      await result.current.load();
    });

    expect(result.current.configuredNotificationChannels).toEqual(['ntfy', 'gotify']);
  });

  it('keeps the latest config load when responses resolve out of order', async () => {
    const first = createDeferred<typeof sampleConfig>();
    const second = createDeferred<typeof sampleConfig>();
    const latest = {
      ...sampleConfig,
      configVersion: 'v2',
      items: sampleConfig.items.map((item) => ({ ...item, value: 'SH600519' })),
    };
    getConfig.mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise);
    const { result } = renderHook(() => useSystemConfig());

    let firstLoad!: Promise<boolean>;
    let secondLoad!: Promise<boolean>;
    act(() => {
      firstLoad = result.current.load();
      secondLoad = result.current.load();
    });
    await act(async () => {
      second.resolve(latest);
      await secondLoad;
    });
    await act(async () => {
      first.resolve(sampleConfig);
      await firstLoad;
    });

    expect(result.current.configVersion).toBe('v2');
    expect(result.current.serverItems[0]?.value).toBe('SH600519');
    expect(result.current.isLoading).toBe(false);
  });

  it('does not let an older external refresh overwrite a newer saved snapshot', async () => {
    const staleExternalRefresh = createDeferred<typeof sampleConfig & {
      configuredNotificationChannels: string[];
    }>();
    const savedConfig = {
      ...sampleConfig,
      configVersion: 'v2',
      configuredNotificationChannels: ['ntfy'],
      items: sampleConfig.items.map((item) => ({ ...item, value: 'SH600519' })),
    };
    const staleConfig = {
      ...sampleConfig,
      configuredNotificationChannels: ['wechat'],
    };
    getConfig
      .mockResolvedValueOnce(sampleConfig)
      .mockReturnValueOnce(staleExternalRefresh.promise)
      .mockResolvedValueOnce(savedConfig);
    const { result } = renderHook(() => useSystemConfig());

    await act(async () => {
      await result.current.load();
    });

    let externalRefresh!: Promise<void>;
    act(() => {
      externalRefresh = result.current.refreshAfterExternalSave([]);
      result.current.setDraftValue('STOCK_LIST', 'SH600519');
    });
    await act(async () => {
      await result.current.save();
    });

    expect(result.current.configVersion).toBe('v2');
    expect(result.current.serverItems[0]?.value).toBe('SH600519');
    expect(result.current.configuredNotificationChannels).toEqual(['ntfy']);

    await act(async () => {
      staleExternalRefresh.resolve(staleConfig);
      await externalRefresh;
    });

    expect(result.current.configVersion).toBe('v2');
    expect(result.current.serverItems[0]?.value).toBe('SH600519');
    expect(result.current.configuredNotificationChannels).toEqual(['ntfy']);
  });

  it('does not report a completed external save as failed when its superseded refresh rejects', async () => {
    const supersededExternalRefresh = createDeferred<typeof sampleConfig>();
    const latestConfig = {
      ...sampleConfig,
      configVersion: 'v4',
      configuredNotificationChannels: ['ntfy'],
      items: sampleConfig.items.map((item) => ({ ...item, value: 'SH600519' })),
    };
    getConfig
      .mockResolvedValueOnce(sampleConfig)
      .mockReturnValueOnce(supersededExternalRefresh.promise)
      .mockResolvedValueOnce(latestConfig);
    const { result } = renderHook(() => useSystemConfig());

    await act(async () => {
      await result.current.load();
    });
    let externalRefresh!: Promise<void>;
    act(() => {
      externalRefresh = result.current.refreshAfterExternalSave([]);
    });
    await act(async () => {
      await result.current.load();
    });

    await act(async () => {
      supersededExternalRefresh.reject(new Error('superseded external refresh failed'));
      await externalRefresh;
    });

    expect(result.current.configVersion).toBe('v4');
    expect(result.current.configuredNotificationChannels).toEqual(['ntfy']);
    expect(result.current.loadError).toBeNull();
  });

  it('does not report a committed save as failed when its superseded refresh rejects', async () => {
    const supersededSaveRefresh = createDeferred<typeof sampleConfig>();
    const latestConfig = {
      ...sampleConfig,
      configVersion: 'v3',
      configuredNotificationChannels: ['gotify'],
      items: sampleConfig.items.map((item) => ({ ...item, value: 'SH600519' })),
    };
    getConfig
      .mockResolvedValueOnce(sampleConfig)
      .mockReturnValueOnce(supersededSaveRefresh.promise)
      .mockResolvedValueOnce(latestConfig);
    const { result } = renderHook(() => useSystemConfig());

    await act(async () => {
      await result.current.load();
    });

    act(() => {
      result.current.setDraftValue('STOCK_LIST', 'SH600519');
    });
    expect(result.current.hasDirty).toBe(true);

    let savePromise!: ReturnType<typeof result.current.save>;
    act(() => {
      savePromise = result.current.save();
    });
    await waitFor(() => {
      expect(update).toHaveBeenCalledTimes(1);
      expect(getConfig).toHaveBeenCalledTimes(2);
    });

    await act(async () => {
      await result.current.load();
    });
    expect(result.current.configVersion).toBe('v3');
    expect(result.current.configuredNotificationChannels).toEqual(['gotify']);

    let saveResult: Awaited<ReturnType<typeof result.current.save>> | undefined;
    await act(async () => {
      supersededSaveRefresh.reject(new Error('superseded refresh failed'));
      saveResult = await savePromise;
    });

    expect(saveResult).toEqual({ success: true });
    expect(result.current.configVersion).toBe('v3');
    expect(result.current.serverItems[0]?.value).toBe('SH600519');
    expect(result.current.configuredNotificationChannels).toEqual(['gotify']);
    expect(result.current.saveError).toBeNull();
    expect(result.current.retryAction).toBeNull();
    expect(result.current.toast).toEqual({ type: 'success', message: '配置已更新' });
  });

  it('still reports a committed save as failed when its current refresh rejects', async () => {
    getConfig
      .mockResolvedValueOnce(sampleConfig)
      .mockRejectedValueOnce(new Error('current refresh failed'));
    const { result } = renderHook(() => useSystemConfig());

    await act(async () => {
      await result.current.load();
    });
    act(() => {
      result.current.setDraftValue('STOCK_LIST', 'SH600519');
    });

    let saveResult: Awaited<ReturnType<typeof result.current.save>> | undefined;
    await act(async () => {
      saveResult = await result.current.save();
    });

    expect(update).toHaveBeenCalledTimes(1);
    expect(saveResult).toEqual({ success: false, message: '保存失败' });
    expect(result.current.saveError).not.toBeNull();
    expect(result.current.retryAction).toBe('save');
  });

  it('reports an update POST failure without attempting a snapshot refresh', async () => {
    update.mockRejectedValueOnce(new Error('update failed'));
    const { result } = renderHook(() => useSystemConfig());

    await act(async () => {
      await result.current.load();
    });
    act(() => {
      result.current.setDraftValue('STOCK_LIST', 'SH600519');
    });

    let saveResult: Awaited<ReturnType<typeof result.current.save>> | undefined;
    await act(async () => {
      saveResult = await result.current.save();
    });

    expect(getConfig).toHaveBeenCalledTimes(1);
    expect(saveResult).toEqual({ success: false, message: '保存失败' });
    expect(result.current.saveError).not.toBeNull();
    expect(result.current.retryAction).toBe('save');
  });

  it('normalizes STOCK_LIST separators before saving', async () => {
    const savedConfig = {
      ...sampleConfig,
      configuredNotificationChannels: ['ntfy'],
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
    expect(result.current.configuredNotificationChannels).toEqual(['ntfy']);
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

  it('resets only the requested atomic group keys', async () => {
    getConfig.mockResolvedValueOnce(sampleLlmConfig);
    const { result } = renderHook(() => useSystemConfig());

    await act(async () => {
      await result.current.load();
    });
    act(() => {
      result.current.setDraftValue('STOCK_LIST', 'SH600519');
      result.current.setDraftValue('LITELLM_MODEL', 'qwen/qwen2.5');
    });
    expect(result.current.dirtyKeys).toEqual(['STOCK_LIST', 'LITELLM_MODEL']);

    act(() => {
      result.current.resetDraftKeys(['LITELLM_MODEL']);
    });

    expect(result.current.dirtyKeys).toEqual(['STOCK_LIST']);
    expect(result.current.itemsByCategory.ai_model?.find((item) => item.key === 'LITELLM_MODEL')?.value).toBe('gpt-5.0');
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

  it('adopts a committed value supplied by a dedicated editor outside draftValues', async () => {
    const savedConfig = {
      ...sampleConfig,
      configVersion: 'v2',
      items: sampleConfig.items.map((item) => ({ ...item, value: 'SH600000,SH600519' })),
    };
    getConfig.mockResolvedValueOnce(sampleConfig).mockResolvedValueOnce(savedConfig);

    const { result } = renderHook(() => useSystemConfig());
    await act(async () => { await result.current.load(); });
    await act(async () => {
      await result.current.save([{ key: 'STOCK_LIST', value: 'SH600000,SH600519' }]);
    });

    expect(result.current.itemsByCategory.base[0]?.value).toBe('SH600000,SH600519');
    expect(result.current.hasDirty).toBe(false);
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

  it('does not auto-replay a secret when both conflict snapshots are masked', async () => {
    const maskedSensitiveConfig = {
      ...sensitiveConfig,
      items: sensitiveConfig.items.map((item) => (
        item.key === 'OPENAI_API_KEY'
          ? { ...item, value: '******', rawValueExists: true, isMasked: true }
          : item
      )),
    };
    const latestConfig = {
      ...maskedSensitiveConfig,
      configVersion: 'v2',
      items: maskedSensitiveConfig.items.map((item) => ({ ...item })),
    };
    getConfig.mockResolvedValueOnce(maskedSensitiveConfig).mockResolvedValueOnce(latestConfig);
    update.mockRejectedValueOnce(new ConflictError('conflict'));

    const { result } = renderHook(() => useSystemConfig());
    await act(async () => { await result.current.load(); });
    act(() => result.current.setDraftValue('OPENAI_API_KEY', 'sk-local-secret'));
    await act(async () => { await result.current.save(); });

    expect(update).toHaveBeenCalledTimes(1);
    expect(result.current.conflictState?.fields).toEqual([
      expect.objectContaining({
        key: 'OPENAI_API_KEY',
        base: '******',
        server: '******',
        local: 'sk-local-secret',
        isSensitive: true,
      }),
    ]);
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
