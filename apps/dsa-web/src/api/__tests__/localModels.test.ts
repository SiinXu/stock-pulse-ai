import { beforeEach, describe, expect, it, vi } from 'vitest';
import { localModelsApi } from '../localModels';

const { get, post, deleteRequest } = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  deleteRequest: vi.fn(),
}));

vi.mock('../index', () => ({
  default: {
    get,
    post,
    delete: deleteRequest,
  },
}));

describe('localModelsApi', () => {
  beforeEach(() => {
    get.mockReset();
    post.mockReset();
    deleteRequest.mockReset();
  });

  it('maps catalog and runtime payloads to the Web contract', async () => {
    get
      .mockResolvedValueOnce({
        data: {
          schema_version: 1,
          verified_at: '2026-07-23',
          models: [{
            id: 'qwen3-4b',
            recommended_ram_gb: 8,
            install: { ollama_tag: 'qwen3:4b' },
          }],
        },
      })
      .mockResolvedValueOnce({
        data: {
          runtime: 'ollama',
          status: 'running',
          installed_models: ['qwen3:4b'],
          manual_pull_supported: false,
          configuration: { config_version: 'v1', registered_models: ['qwen3:4b'] },
        },
      });

    const catalog = await localModelsApi.getCatalog();
    const runtime = await localModelsApi.getRuntime();

    expect(get).toHaveBeenNthCalledWith(1, '/api/v1/system/config/llm/local-models');
    expect(get).toHaveBeenNthCalledWith(2, '/api/v1/local-models/runtime');
    expect(catalog.models[0]).toMatchObject({
      recommendedRamGb: 8,
      install: { ollamaTag: 'qwen3:4b' },
    });
    expect(runtime).toMatchObject({
      installedModels: ['qwen3:4b'],
      configuration: { registeredModels: ['qwen3:4b'] },
    });
  });

  it('sends lifecycle identity, snapshot assertions, and an opaque recovery token', async () => {
    post.mockResolvedValue({ data: { task_id: 'task-1' } });
    deleteRequest.mockResolvedValue({ data: { success: true } });

    await localModelsApi.startPull('qwen3:4b');
    await localModelsApi.assign('qwen3:4b', 'agent');
    await localModelsApi.activateDesktop(
      'qwen3:4b',
      'config-1',
      'http://127.0.0.1:11434',
    );
    await localModelsApi.deleteModel('qwen3:4b');
    await localModelsApi.unregister(
      'qwen3:4b',
      'config-1',
      'http://127.0.0.1:11434',
    );
    await localModelsApi.restoreRegistration('qwen3:4b', 'recovery-2');
    await localModelsApi.finalizeUnregistration('qwen3:4b', 'recovery-3');

    expect(post).toHaveBeenNthCalledWith(1, '/api/v1/local-models/pulls', {
      model_id: 'qwen3:4b',
    });
    expect(post).toHaveBeenNthCalledWith(2, '/api/v1/local-models/assignments', {
      model_id: 'qwen3:4b',
      assignment: 'agent',
    });
    expect(post).toHaveBeenNthCalledWith(3, '/api/v1/local-models/desktop-activations', {
      model_id: 'qwen3:4b',
      expected_config_version: 'config-1',
      expected_runtime_base_url: 'http://127.0.0.1:11434',
    });
    expect(deleteRequest).toHaveBeenNthCalledWith(1, '/api/v1/local-models/models', {
      data: { model_id: 'qwen3:4b' },
    });
    expect(deleteRequest).toHaveBeenNthCalledWith(2, '/api/v1/local-models/registrations', {
      data: {
        model_id: 'qwen3:4b',
        expected_config_version: 'config-1',
        expected_runtime_base_url: 'http://127.0.0.1:11434',
      },
    });
    expect(post).toHaveBeenNthCalledWith(4, '/api/v1/local-models/registrations', {
      model_id: 'qwen3:4b',
      recovery_token: 'recovery-2',
    });
    expect(post).toHaveBeenNthCalledWith(
      5,
      '/api/v1/local-models/registration-recoveries/finalize',
      { model_id: 'qwen3:4b', recovery_token: 'recovery-3' },
    );
    const payloads = [...post.mock.calls, ...deleteRequest.mock.calls]
      .map((call) => call[1])
      .filter((payload) => payload && typeof payload === 'object');
    expect(payloads.some((payload) => Object.hasOwn(payload, 'base_url'))).toBe(false);
  });
});
