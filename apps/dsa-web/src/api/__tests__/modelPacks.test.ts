import { beforeEach, describe, expect, it, vi } from 'vitest';

import { modelPacksApi } from '../modelPacks';


const RUNTIME_IDENTITY = 'b26993598dffd1f14aed97def57ef67f753518a9b773d8a12033c82b4fa545ca';
const { get, post } = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
}));

vi.mock('../index', () => ({
  default: { get, post },
}));

describe('modelPacksApi', () => {
  beforeEach(() => {
    get.mockReset();
    post.mockReset();
  });

  it('uploads one file and maps the queued import contract', async () => {
    post.mockResolvedValue({
      data: {
        status: 'accepted',
        task_id: 'pack-1',
        message: 'queued',
        message_code: 'local_model.import.queued',
      },
    });
    const file = new File(['pack'], 'finance.modelpack', { type: 'application/zip' });

    await expect(modelPacksApi.startImport(file)).resolves.toMatchObject({
      taskId: 'pack-1',
      messageCode: 'local_model.import.queued',
    });

    expect(post).toHaveBeenCalledTimes(1);
    expect(post.mock.calls[0][0]).toBe('/api/v1/model-packs/import');
    expect(post.mock.calls[0][1]).toBeInstanceOf(FormData);
    expect((post.mock.calls[0][1] as FormData).get('file')).toBe(file);
  });

  it('polls status and activates a Desktop manifest without a caller target URL', async () => {
    get.mockResolvedValue({
      data: {
        task_id: 'pack-1',
        status: 'completed',
        progress: 100,
        result: { model_id: 'licensed/finance:q4', activated: true },
      },
    });
    post.mockResolvedValue({ data: { success: true, selected_primary: false } });

    await expect(modelPacksApi.getImport('pack/1')).resolves.toMatchObject({
      taskId: 'pack-1',
      result: { modelId: 'licensed/finance:q4' },
    });
    await modelPacksApi.activateDesktop(
      {
        modelId: 'licensed/finance:q4',
        displayName: 'Licensed Finance Q4',
        minimumMemoryGb: 16,
        licenseId: 'LicenseRef-Finance',
      },
      'config-1',
      RUNTIME_IDENTITY,
      'desktop-attestation',
    );

    expect(get).toHaveBeenCalledWith('/api/v1/model-packs/imports/pack%2F1');
    expect(post).toHaveBeenCalledWith('/api/v1/model-packs/desktop-activations', {
      model_id: 'licensed/finance:q4',
      display_name: 'Licensed Finance Q4',
      minimum_memory_gb: 16,
      license_id: 'LicenseRef-Finance',
      expected_config_version: 'config-1',
      expected_runtime_identity: RUNTIME_IDENTITY,
      desktop_attestation: 'desktop-attestation',
    });
    expect(JSON.stringify(post.mock.calls[0][1])).not.toContain('url');
  });
});
