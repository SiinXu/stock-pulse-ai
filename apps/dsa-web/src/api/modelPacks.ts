import type { AxiosProgressEvent } from 'axios';

import type {
  LocalModelMutationResponse,
  ModelPackImportAccepted,
  ModelPackImportResult,
  ModelPackImportStatus,
} from '../types/localModels';
import apiClient from './index';
import { toCamelCase } from './utils';


const MODEL_PACK_UPLOAD_TIMEOUT_MS = 2 * 60 * 60 * 1000;

interface ModelPackUploadOptions {
  signal?: AbortSignal;
  onUploadProgress?: (event: AxiosProgressEvent) => void;
}

export const modelPacksApi = {
  async startImport(
    file: File,
    options: ModelPackUploadOptions = {},
  ): Promise<ModelPackImportAccepted> {
    const payload = new FormData();
    payload.append('file', file);
    const response = await apiClient.post<Record<string, unknown>>(
      '/api/v1/model-packs/import',
      payload,
      {
        headers: { 'Content-Type': 'multipart/form-data' },
        timeout: MODEL_PACK_UPLOAD_TIMEOUT_MS,
        signal: options.signal,
        onUploadProgress: options.onUploadProgress,
      },
    );
    return toCamelCase<ModelPackImportAccepted>(response.data);
  },

  async getImport(taskId: string): Promise<ModelPackImportStatus> {
    const response = await apiClient.get<Record<string, unknown>>(
      `/api/v1/model-packs/imports/${encodeURIComponent(taskId)}`,
    );
    return toCamelCase<ModelPackImportStatus>(response.data);
  },

  async activateDesktop(
    result: Pick<
      ModelPackImportResult,
      'modelId' | 'displayName' | 'minimumMemoryGb' | 'licenseId'
    >,
    expectedConfigVersion: string,
    expectedRuntimeIdentity: string,
    desktopAttestation: string,
  ): Promise<LocalModelMutationResponse> {
    const response = await apiClient.post<Record<string, unknown>>(
      '/api/v1/model-packs/desktop-activations',
      {
        model_id: result.modelId,
        display_name: result.displayName,
        minimum_memory_gb: result.minimumMemoryGb,
        license_id: result.licenseId,
        expected_config_version: expectedConfigVersion,
        expected_runtime_identity: expectedRuntimeIdentity,
        desktop_attestation: desktopAttestation,
      },
    );
    return toCamelCase<LocalModelMutationResponse>(response.data);
  },
};
