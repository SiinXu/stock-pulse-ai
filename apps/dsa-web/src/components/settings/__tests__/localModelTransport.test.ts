import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { LocalModelConfiguration } from '../../../types/localModels';
import {
  __localModelTransportTest,
  createLocalModelTransport,
  LocalModelTransportError,
  type DesktopLocalModelBridge,
} from '../localModelTransport';

const api = vi.hoisted(() => ({
  getRuntime: vi.fn(),
  getConfiguration: vi.fn(),
  startPull: vi.fn(),
  getPull: vi.fn(),
  assign: vi.fn(),
  deleteModel: vi.fn(),
  unregister: vi.fn(),
}));

vi.mock('../../../api/localModels', () => ({ localModelsApi: api }));

const CONFIGURATION: LocalModelConfiguration = {
  configVersion: 'config-1',
  registeredModels: [],
  primaryModel: '',
  agentModel: '',
};

function createDesktopBridge(): DesktopLocalModelBridge {
  return {
    getState: vi.fn().mockResolvedValue({ status: 'running' }),
    detect: vi.fn().mockResolvedValue({
      status: 'running',
      installedModels: ['qwen3:4b'],
      totalMemoryGb: 24,
    }),
    start: vi.fn().mockResolvedValue({ status: 'running' }),
    stop: vi.fn().mockResolvedValue({ status: 'stopped' }),
    pull: vi.fn().mockResolvedValue({ ok: true, modelId: 'qwen3:4b' }),
    remove: vi.fn().mockResolvedValue({ ok: true, modelId: 'qwen3:4b' }),
    openInstallGuide: vi.fn().mockResolvedValue(true),
    onStateChange: vi.fn().mockReturnValue(() => undefined),
  };
}

describe('localModelTransport', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    delete window.stockPulseLocalModels;
    api.getConfiguration.mockResolvedValue(CONFIGURATION);
  });

  it('uses the backend task contract and emits polled progress in Web mode', async () => {
    vi.useFakeTimers();
    try {
      api.startPull.mockResolvedValue({ taskId: 'pull-1', status: 'pending' });
      api.getPull
        .mockResolvedValueOnce({
          taskId: 'pull-1',
          status: 'processing',
          progress: 41,
          modelId: 'qwen3:4b',
        })
        .mockResolvedValueOnce({
          taskId: 'pull-1',
          status: 'completed',
          progress: 100,
          modelId: 'qwen3:4b',
          result: { modelId: 'qwen3:4b', activated: true, selectedPrimary: true },
        });
      const progress = vi.fn();

      const resultPromise = __localModelTransportTest.createWebTransport()
        .pull('qwen3:4b', progress);
      await vi.advanceTimersByTimeAsync(750);

      await expect(resultPromise).resolves.toEqual({
        modelId: 'qwen3:4b',
        activated: true,
        selectedPrimary: true,
      });
      expect(api.startPull).toHaveBeenCalledWith('qwen3:4b');
      expect(progress).toHaveBeenCalledWith({
        modelId: 'qwen3:4b',
        percent: 41,
        status: 'processing',
      });
    } finally {
      vi.useRealTimers();
    }
  });

  it('returns a safe manual command when the Web runtime request fails', async () => {
    api.startPull.mockRejectedValue(new Error('private runtime details'));

    await expect(
      __localModelTransportTest.createWebTransport().pull('qwen3:4b', () => undefined),
    ).rejects.toMatchObject({
      code: 'local_model_runtime_unavailable',
      manualCommand: 'ollama pull qwen3:4b',
    } satisfies Partial<LocalModelTransportError>);
  });

  it('selects desktop IPC, reports host memory, and activates through the backend authority', async () => {
    const bridge = createDesktopBridge();
    window.stockPulseLocalModels = bridge;
    api.assign.mockResolvedValue({ selectedPrimary: false });
    const transport = createLocalModelTransport();

    await expect(transport.getRuntime()).resolves.toMatchObject({
      status: 'running',
      installedModels: ['qwen3:4b'],
      totalMemoryGb: 24,
      configuration: CONFIGURATION,
    });
    await expect(transport.pull('qwen3:4b', () => undefined)).resolves.toEqual({
      modelId: 'qwen3:4b',
      activated: true,
      selectedPrimary: false,
    });
    expect(bridge.pull).toHaveBeenCalledWith('qwen3:4b');
    expect(api.assign).toHaveBeenCalledWith('qwen3:4b', 'auto');
  });

  it('validates and unregisters before asking desktop IPC to delete model weights', async () => {
    const bridge = createDesktopBridge();
    const mutation = {
      ...CONFIGURATION,
      success: true,
      modelId: 'qwen3:4b',
      selectedPrimary: false,
      selectedAgent: false,
      deleted: true,
      updatedKeys: ['LLM_OLLAMA_MODELS'],
      warnings: [],
      appliedCount: 1,
      skippedMaskedCount: 0,
      reloadTriggered: true,
    };
    api.unregister.mockResolvedValue(mutation);

    await expect(
      __localModelTransportTest.createDesktopTransport(bridge).remove('qwen3:4b'),
    ).resolves.toEqual(mutation);
    expect(api.unregister).toHaveBeenCalledWith('qwen3:4b');
    expect(bridge.remove).toHaveBeenCalledWith('qwen3:4b');
    expect(api.unregister.mock.invocationCallOrder[0]).toBeLessThan(
      vi.mocked(bridge.remove).mock.invocationCallOrder[0],
    );
  });

  it('does not mutate desktop weights when backend active-model validation fails', async () => {
    const bridge = createDesktopBridge();
    api.unregister.mockRejectedValue(new Error('model in use'));

    await expect(
      __localModelTransportTest.createDesktopTransport(bridge).remove('qwen3:4b'),
    ).rejects.toThrow('model in use');
    expect(bridge.remove).not.toHaveBeenCalled();
  });
});
