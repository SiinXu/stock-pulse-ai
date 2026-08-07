import { beforeEach, describe, expect, it, vi } from 'vitest';
import { localModelsApi } from '../localModels';
import { getParsedApiError, isApiRequestError } from '../error';

const RUNTIME_IDENTITY = 'b26993598dffd1f14aed97def57ef67f753518a9b773d8a12033c82b4fa545ca';

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
            section: 'general',
            display_name: { en: 'Qwen3 4B', zh: 'Qwen3 4B' },
            capability_summary: { en: 'light', zh: '轻量' },
            capabilities: ['chat'],
            q4: {
              quantization: 'Q4_K_M',
              size_bytes: 1,
              source_kind: 'official_ollama',
              source_url: 'https://example.com',
              source_revision: 'main',
            },
            memory_tier: 'light',
            recommended_ram_gb: 8,
            license: {
              identifier: 'Apache-2.0',
              name: 'Apache 2.0',
              evidence_url: 'https://example.com/license',
              redistribution: 'allowed_with_notice',
              standalone_license_file: false,
            },
            upstream: {
              primary_url: 'https://example.com/model',
              revision: 'main',
            },
            install: {
              method: 'ollama_pull',
              status: 'available',
              ollama_tag: 'qwen3:4b',
              download_url: 'https://example.com/download',
              hosted_by_stockpulse: false,
            },
            desktop: {
              recommended: true,
              guidance_en: 'Use for local agent work.',
            },
          }],
        },
      })
      .mockResolvedValueOnce({
        data: {
          runtime: 'ollama',
          status: 'running',
          installed_models: ['qwen3:4b'],
          manual_pull_supported: false,
          local_install_platform: 'macos',
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
      localInstallPlatform: 'macos',
      configuration: { registeredModels: ['qwen3:4b'] },
    });
  });

  it('sends lifecycle identity, snapshot assertions, and an opaque recovery token', async () => {
    const mutationOk = {
      success: true,
      config_version: 'config-1',
      model_id: 'qwen3:4b',
      registered_models: ['qwen3:4b'],
      primary_model: 'qwen3:4b',
      agent_model: 'qwen3:4b',
      selected_primary: true,
      selected_agent: false,
      deleted: false,
      updated_keys: [],
      warnings: [],
      applied_count: 1,
      skipped_masked_count: 0,
      reload_triggered: false,
    };
    // Call order: startPull, assign, activateDesktop, restoreRegistration, finalizeUnregistration
    post
      .mockResolvedValueOnce({
        data: {
          task_id: 'task-1',
          trace_id: 'trace-1',
          status: 'pending',
          model_id: 'qwen3:4b',
        },
      })
      .mockResolvedValueOnce({ data: mutationOk })
      .mockResolvedValueOnce({ data: mutationOk })
      .mockResolvedValueOnce({ data: mutationOk })
      .mockResolvedValueOnce({ data: mutationOk });
    // Call order: deleteModel, unregister
    deleteRequest
      .mockResolvedValueOnce({ data: mutationOk })
      .mockResolvedValueOnce({ data: { ...mutationOk, recovery_token: 'recovery-out' } });

    await localModelsApi.startPull('qwen3:4b');
    await localModelsApi.assign('qwen3:4b', 'agent');
    await localModelsApi.activateDesktop(
      'qwen3:4b',
      'config-1',
      RUNTIME_IDENTITY,
    );
    await localModelsApi.deleteModel('qwen3:4b');
    await localModelsApi.unregister(
      'qwen3:4b',
      'config-1',
      RUNTIME_IDENTITY,
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
      expected_runtime_identity: RUNTIME_IDENTITY,
    });
    expect(deleteRequest).toHaveBeenNthCalledWith(1, '/api/v1/local-models/models', {
      data: { model_id: 'qwen3:4b' },
    });
    expect(deleteRequest).toHaveBeenNthCalledWith(2, '/api/v1/local-models/registrations', {
      data: {
        model_id: 'qwen3:4b',
        expected_config_version: 'config-1',
        expected_runtime_identity: RUNTIME_IDENTITY,
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
    expect(payloads.some((payload) => JSON.stringify(payload).includes('base_url'))).toBe(false);
  });

  it('preserves extra keys on valid pull accepted payloads (toCamelCase pass-through)', async () => {
    post.mockResolvedValueOnce({
      data: {
        task_id: 'task-2',
        trace_id: 'trace-2',
        status: 'pending',
        model_id: 'qwen3:4b',
        unexpected_server_field: 'keep-me',
      },
    });
    const accepted = await localModelsApi.startPull('qwen3:4b');
    expect(accepted).toEqual({
      taskId: 'task-2',
      traceId: 'trace-2',
      status: 'pending',
      modelId: 'qwen3:4b',
      unexpectedServerField: 'keep-me',
    });
  });

  it('surfaces pull accepted shape mismatches through ParsedApiError', async () => {
    post.mockResolvedValueOnce({
      data: {
        task_id: 'task-2',
        status: 'pending',
        model_id: 'qwen3:4b',
      },
    });
    await expect(localModelsApi.startPull('qwen3:4b')).rejects.toSatisfy((error: unknown) => {
      expect(isApiRequestError(error)).toBe(true);
      const parsed = getParsedApiError(error);
      expect(parsed.code).toBe('api_response_validation_failed');
      expect(parsed.message).toContain('LocalModelPullAccepted');
      return true;
    });
  });
});
