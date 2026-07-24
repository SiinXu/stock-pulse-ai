import apiClient from './index';
import { toCamelCase } from './utils';
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


const modelPayload = (modelId: string) => ({ model_id: modelId });

export const localModelsApi = {
  async getCatalog(): Promise<LocalModelCatalogResponse> {
    const response = await apiClient.get<Record<string, unknown>>(
      '/api/v1/system/config/llm/local-models',
    );
    return toCamelCase<LocalModelCatalogResponse>(response.data);
  },

  async getRuntime(): Promise<LocalModelRuntimeState> {
    const response = await apiClient.get<Record<string, unknown>>('/api/v1/local-models/runtime');
    return toCamelCase<LocalModelRuntimeState>(response.data);
  },

  async getConfiguration(): Promise<LocalModelConfiguration> {
    const response = await apiClient.get<Record<string, unknown>>(
      '/api/v1/local-models/configuration',
    );
    return toCamelCase<LocalModelConfiguration>(response.data);
  },

  async startPull(modelId: string): Promise<LocalModelPullAccepted> {
    const response = await apiClient.post<Record<string, unknown>>(
      '/api/v1/local-models/pulls',
      modelPayload(modelId),
    );
    return toCamelCase<LocalModelPullAccepted>(response.data);
  },

  async getPull(taskId: string): Promise<LocalModelPullStatus> {
    const response = await apiClient.get<Record<string, unknown>>(
      `/api/v1/local-models/pulls/${encodeURIComponent(taskId)}`,
    );
    return toCamelCase<LocalModelPullStatus>(response.data);
  },

  async assign(modelId: string, assignment: LocalModelAssignment): Promise<LocalModelMutationResponse> {
    const response = await apiClient.post<Record<string, unknown>>(
      '/api/v1/local-models/assignments',
      { ...modelPayload(modelId), assignment },
    );
    return toCamelCase<LocalModelMutationResponse>(response.data);
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
    return toCamelCase<LocalModelMutationResponse>(response.data);
  },

  async deleteModel(modelId: string): Promise<LocalModelMutationResponse> {
    const response = await apiClient.delete<Record<string, unknown>>(
      '/api/v1/local-models/models',
      { data: modelPayload(modelId) },
    );
    return toCamelCase<LocalModelMutationResponse>(response.data);
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
    return toCamelCase<LocalModelUnregistrationResponse>(response.data);
  },

  async restoreRegistration(
    modelId: string,
    recoveryToken: string,
  ): Promise<LocalModelMutationResponse> {
    const response = await apiClient.post<Record<string, unknown>>(
      '/api/v1/local-models/registrations',
      { ...modelPayload(modelId), recovery_token: recoveryToken },
    );
    return toCamelCase<LocalModelMutationResponse>(response.data);
  },

  async finalizeUnregistration(
    modelId: string,
    recoveryToken: string,
  ): Promise<LocalModelMutationResponse> {
    const response = await apiClient.post<Record<string, unknown>>(
      '/api/v1/local-models/registration-recoveries/finalize',
      { ...modelPayload(modelId), recovery_token: recoveryToken },
    );
    return toCamelCase<LocalModelMutationResponse>(response.data);
  },
};
