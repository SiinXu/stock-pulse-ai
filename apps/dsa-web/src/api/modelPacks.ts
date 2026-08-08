import { z } from 'zod';
import { parseCamelCasePayload } from './parseCamelCasePayload';
import type { components } from '../types/api.generated';
import apiClient from './index';
import type { AxiosProgressEvent } from 'axios';

import type {
  LocalModelMutationResponse,
  ModelPackImportAccepted,
  ModelPackImportResult,
  ModelPackImportStatus,
} from '../types/localModels';

type OpenApiModelPackImportAccepted = components['schemas']['ModelPackImportAccepted'];
type OpenApiModelPackImportStatus = components['schemas']['ModelPackImportStatus'];
type OpenApiLocalModelMutationResponse = components['schemas']['LocalModelMutationResponse'];
type _AssertAccepted = keyof OpenApiModelPackImportAccepted;
type _AssertStatus = keyof OpenApiModelPackImportStatus;
type _AssertMutation = keyof OpenApiLocalModelMutationResponse;
const _acceptedAnchor: _AssertAccepted = 'task_id';
const _statusAnchor: _AssertStatus = 'progress';
const _mutationAnchor: _AssertMutation = 'model_id';
void _acceptedAnchor;
void _statusAnchor;
void _mutationAnchor;

const modelPackImportAcceptedSchema = z.object({
  message: z.string(),
  messageCode: z.string().optional(),
  status: z.string().optional(),
  taskId: z.string(),
}).passthrough();

const modelPackImportStatusSchema = z.object({
  error: z.string().nullable().optional(),
  message: z.string().nullable().optional(),
  progress: z.number(),
  result: z.record(z.string(), z.unknown()).nullable().optional(),
  status: z.string(),
  taskId: z.string(),
}).passthrough();

const localModelMutationResponseSchema = z.object({
  agentModel: z.string().optional(),
  appliedCount: z.number().optional(),
  configVersion: z.string(),
  deleted: z.boolean().optional(),
  importedModels: z.array(z.record(z.string(), z.unknown())).optional(),
  modelId: z.string(),
  primaryModel: z.string().optional(),
  registeredModels: z.array(z.string()).optional(),
  reloadTriggered: z.boolean().optional(),
  selectedAgent: z.boolean().optional(),
  selectedPrimary: z.boolean().optional(),
  skippedMaskedCount: z.number().optional(),
  success: z.boolean().optional(),
  updatedKeys: z.array(z.string()).optional(),
  warnings: z.array(z.string()).optional(),
}).passthrough();

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
    return parseCamelCasePayload<ModelPackImportAccepted>(
      response.data,
      modelPackImportAcceptedSchema,
      'ModelPackImportAccepted',
      'modelPacks',
    );
  },

  async getImport(taskId: string): Promise<ModelPackImportStatus> {
    const response = await apiClient.get<Record<string, unknown>>(
      `/api/v1/model-packs/imports/${encodeURIComponent(taskId)}`,
    );
    return parseCamelCasePayload<ModelPackImportStatus>(
      response.data,
      modelPackImportStatusSchema,
      'ModelPackImportStatus',
      'modelPacks',
    );
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
    return parseCamelCasePayload<LocalModelMutationResponse>(
      response.data,
      localModelMutationResponseSchema,
      'LocalModelMutationResponse',
      'modelPacks',
    );
  },
};
