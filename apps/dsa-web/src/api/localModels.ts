import { z } from 'zod';
import { parseCamelCasePayload } from './parseCamelCasePayload';
import type { components } from '../types/api.generated';
import apiClient from './index';
import type {
  LocalModelAssignment,
  LocalModelCatalogResponse,
  LocalModelConfiguration,
  LocalModelMutationResponse,
  LocalModelPullAccepted,
  LocalModelPullStatus,
  LocalModelRuntimeState,
  LocalModelUnregistrationResponse,
} from '../types/localModels';

type OpenApiLocalModelCatalogResponse = components['schemas']['LocalModelCatalogResponse'];
type OpenApiLocalModelRuntimeResponse = components['schemas']['LocalModelRuntimeResponse'];
type OpenApiLocalModelPullAccepted = components['schemas']['LocalModelPullAccepted'];
type OpenApiLocalModelMutationResponse = components['schemas']['LocalModelMutationResponse'];
type _AssertCatalog = keyof OpenApiLocalModelCatalogResponse;
type _AssertRuntime = keyof OpenApiLocalModelRuntimeResponse;
type _AssertPull = keyof OpenApiLocalModelPullAccepted;
type _AssertMutation = keyof OpenApiLocalModelMutationResponse;
const _catalogAnchor: _AssertCatalog = 'schema_version';
const _runtimeAnchor: _AssertRuntime = 'configuration';
const _pullAnchor: _AssertPull = 'task_id';
const _mutationAnchor: _AssertMutation = 'model_id';
void _catalogAnchor;
void _runtimeAnchor;
void _pullAnchor;
void _mutationAnchor;

const localModelCatalogResponseSchema = z.object({
  models: z.array(z.record(z.string(), z.unknown())),
  schemaVersion: z.number(),
  verifiedAt: z.string(),
}).passthrough();

const localModelRuntimeStateSchema = z.object({
  configuration: z.record(z.string(), z.unknown()),
  installedModels: z.array(z.string()).optional(),
  localInstallPlatform: z.string().nullable().optional(),
  manualPullSupported: z.boolean().optional(),
  runtime: z.string().optional(),
  status: z.string(),
}).passthrough();

const localModelConfigurationSchema = z.object({
  agentModel: z.string().optional(),
  configVersion: z.string(),
  importedModels: z.array(z.record(z.string(), z.unknown())).optional(),
  primaryModel: z.string().optional(),
  registeredModels: z.array(z.string()).optional(),
}).passthrough();

const localModelPullAcceptedSchema = z.object({
  modelId: z.string(),
  status: z.string(),
  taskId: z.string(),
  traceId: z.string(),
}).passthrough();

const localModelPullStatusSchema = z.object({
  error: z.string().nullable().optional(),
  modelId: z.string(),
  progress: z.number().optional(),
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

const localModelUnregistrationResponseSchema = z.object({
  agentModel: z.string().optional(),
  appliedCount: z.number().optional(),
  configVersion: z.string(),
  deleted: z.boolean().optional(),
  importedModels: z.array(z.record(z.string(), z.unknown())).optional(),
  modelId: z.string(),
  primaryModel: z.string().optional(),
  recoveryToken: z.string(),
  registeredModels: z.array(z.string()).optional(),
  reloadTriggered: z.boolean().optional(),
  selectedAgent: z.boolean().optional(),
  selectedPrimary: z.boolean().optional(),
  skippedMaskedCount: z.number().optional(),
  success: z.boolean().optional(),
  updatedKeys: z.array(z.string()).optional(),
  warnings: z.array(z.string()).optional(),
}).passthrough();


const modelPayload = (modelId: string) => ({ model_id: modelId });

export const localModelsApi = {
  async getCatalog(): Promise<LocalModelCatalogResponse> {
    const response = await apiClient.get<Record<string, unknown>>(
      '/api/v1/system/config/llm/local-models',
    );
    return parseCamelCasePayload<LocalModelCatalogResponse>(
      response.data,
      localModelCatalogResponseSchema,
      'LocalModelCatalogResponse',
      'localModels',
    );
  },

  async getRuntime(): Promise<LocalModelRuntimeState> {
    const response = await apiClient.get<Record<string, unknown>>('/api/v1/local-models/runtime');
    return parseCamelCasePayload<LocalModelRuntimeState>(
      response.data,
      localModelRuntimeStateSchema,
      'LocalModelRuntimeResponse',
      'localModels',
    );
  },

  async getConfiguration(): Promise<LocalModelConfiguration> {
    const response = await apiClient.get<Record<string, unknown>>(
      '/api/v1/local-models/configuration',
    );
    return parseCamelCasePayload<LocalModelConfiguration>(
      response.data,
      localModelConfigurationSchema,
      'LocalModelConfigurationResponse',
      'localModels',
    );
  },

  async startPull(modelId: string): Promise<LocalModelPullAccepted> {
    const response = await apiClient.post<Record<string, unknown>>(
      '/api/v1/local-models/pulls',
      modelPayload(modelId),
    );
    return parseCamelCasePayload<LocalModelPullAccepted>(
      response.data,
      localModelPullAcceptedSchema,
      'LocalModelPullAccepted',
      'localModels',
    );
  },

  async getPull(taskId: string): Promise<LocalModelPullStatus> {
    const response = await apiClient.get<Record<string, unknown>>(
      `/api/v1/local-models/pulls/${encodeURIComponent(taskId)}`,
    );
    return parseCamelCasePayload<LocalModelPullStatus>(
      response.data,
      localModelPullStatusSchema,
      'LocalModelPullStatus',
      'localModels',
    );
  },

  async assign(modelId: string, assignment: LocalModelAssignment): Promise<LocalModelMutationResponse> {
    const response = await apiClient.post<Record<string, unknown>>(
      '/api/v1/local-models/assignments',
      { ...modelPayload(modelId), assignment },
    );
    return parseCamelCasePayload<LocalModelMutationResponse>(
      response.data,
      localModelMutationResponseSchema,
      'LocalModelMutationResponse',
      'localModels',
    );
  },

  async activateDesktop(
    modelId: string,
    expectedConfigVersion: string,
    expectedRuntimeIdentity: string,
  ): Promise<LocalModelMutationResponse> {
    const response = await apiClient.post<Record<string, unknown>>(
      '/api/v1/local-models/desktop-activations',
      {
        ...modelPayload(modelId),
        expected_config_version: expectedConfigVersion,
        expected_runtime_identity: expectedRuntimeIdentity,
      },
    );
    return parseCamelCasePayload<LocalModelMutationResponse>(
      response.data,
      localModelMutationResponseSchema,
      'LocalModelMutationResponse',
      'localModels',
    );
  },

  async deleteModel(modelId: string): Promise<LocalModelMutationResponse> {
    const response = await apiClient.delete<Record<string, unknown>>(
      '/api/v1/local-models/models',
      { data: modelPayload(modelId) },
    );
    return parseCamelCasePayload<LocalModelMutationResponse>(
      response.data,
      localModelMutationResponseSchema,
      'LocalModelMutationResponse',
      'localModels',
    );
  },

  async unregister(
    modelId: string,
    expectedConfigVersion: string,
    expectedRuntimeIdentity: string,
  ): Promise<LocalModelUnregistrationResponse> {
    const response = await apiClient.delete<Record<string, unknown>>(
      '/api/v1/local-models/registrations',
      {
        data: {
          ...modelPayload(modelId),
          expected_config_version: expectedConfigVersion,
          expected_runtime_identity: expectedRuntimeIdentity,
        },
      },
    );
    return parseCamelCasePayload<LocalModelUnregistrationResponse>(
      response.data,
      localModelUnregistrationResponseSchema,
      'LocalModelUnregistrationResponse',
      'localModels',
    );
  },

  async restoreRegistration(
    modelId: string,
    recoveryToken: string,
  ): Promise<LocalModelMutationResponse> {
    const response = await apiClient.post<Record<string, unknown>>(
      '/api/v1/local-models/registrations',
      { ...modelPayload(modelId), recovery_token: recoveryToken },
    );
    return parseCamelCasePayload<LocalModelMutationResponse>(
      response.data,
      localModelMutationResponseSchema,
      'LocalModelMutationResponse',
      'localModels',
    );
  },

  async finalizeUnregistration(
    modelId: string,
    recoveryToken: string,
  ): Promise<LocalModelMutationResponse> {
    const response = await apiClient.post<Record<string, unknown>>(
      '/api/v1/local-models/registration-recoveries/finalize',
      { ...modelPayload(modelId), recovery_token: recoveryToken },
    );
    return parseCamelCasePayload<LocalModelMutationResponse>(
      response.data,
      localModelMutationResponseSchema,
      'LocalModelMutationResponse',
      'localModels',
    );
  },
};
