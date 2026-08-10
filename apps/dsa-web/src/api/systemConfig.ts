import { z } from 'zod';
import apiClient from './index';
import {
  createApiError,
  createParsedApiError,
  getParsedApiError,
  type ParsedApiError,
} from './error';
import { toCamelCase } from './utils';
import type {
  AvailableModelsResponse,
  ConfigValidationIssue,
  DiscoverLLMChannelModelsRequest,
  DiscoverLLMChannelModelsResponse,
  ExportSystemConfigResponse,
  GenerationBackendStatusPreviewRequest,
  GenerationBackendStatusResponse,
  ImportSystemConfigRequest,
  KronosStatusResponse,
  RollbackSystemConfigRequest,
  LegacyChannelsMigrationPreview,
  LlmProviderCatalogResponse,
  LLMConfigModeStatus,
  SchedulerRunNowResponse,
  SchedulerStatusResponse,
  SetupStatusResponse,
  SystemConfigConflictResponse,
  SystemConfigResponse,
  SystemConfigSchemaResponse,
  SystemConfigValidationErrorResponse,
  TestLLMChannelRequest,
  TestLLMChannelResponse,
  TestGenerationBackendRequest,
  TestGenerationBackendResponse,
  TestNotificationChannelRequest,
  TestNotificationChannelResponse,
  UpdateSystemConfigRequest,
  UpdateSystemConfigResponse,
  ValidateSystemConfigRequest,
  ValidateSystemConfigResponse,
} from '../types/systemConfig';

import type { components } from '../types/api.generated';

type OpenApiSystemConfigResponse = components['schemas']['SystemConfigResponse'];
type OpenApiSystemConfigSchemaResponse = components['schemas']['SystemConfigSchemaResponse'];
type OpenApiUpdateSystemConfigResponse = components['schemas']['UpdateSystemConfigResponse'];
type OpenApiSetupStatusResponse = components['schemas']['SetupStatusResponse'];
type OpenApiExportSystemConfigResponse = components['schemas']['ExportSystemConfigResponse'];
type OpenApiValidateSystemConfigResponse = components['schemas']['ValidateSystemConfigResponse'];
type OpenApiGenerationBackendStatusResponse = components['schemas']['GenerationBackendStatusResponse'];
type OpenApiTestGenerationBackendResponse = components['schemas']['TestGenerationBackendResponse'];
type OpenApiLlmProviderCatalogResponse = components['schemas']['LLMProviderCatalogResponse'];
type OpenApiTestLLMChannelResponse = components['schemas']['TestLLMChannelResponse'];
type OpenApiTestNotificationChannelResponse = components['schemas']['TestNotificationChannelResponse'];
type OpenApiDiscoverLLMChannelModelsResponse = components['schemas']['DiscoverLLMChannelModelsResponse'];
type OpenApiWatchlistResponse = components['schemas']['WatchlistResponse'];
type OpenApiKronosStatusResponse = components['schemas']['KronosStatusResponse'];

type _AssertConfig = keyof OpenApiSystemConfigResponse;
type _AssertSchema = keyof OpenApiSystemConfigSchemaResponse;
type _AssertUpdate = keyof OpenApiUpdateSystemConfigResponse;
type _AssertSetup = keyof OpenApiSetupStatusResponse;
type _AssertExport = keyof OpenApiExportSystemConfigResponse;
type _AssertValidate = keyof OpenApiValidateSystemConfigResponse;
type _AssertGenStatus = keyof OpenApiGenerationBackendStatusResponse;
type _AssertGenSmoke = keyof OpenApiTestGenerationBackendResponse;
type _AssertCatalog = keyof OpenApiLlmProviderCatalogResponse;
type _AssertTestLlm = keyof OpenApiTestLLMChannelResponse;
type _AssertTestNotify = keyof OpenApiTestNotificationChannelResponse;
type _AssertDiscover = keyof OpenApiDiscoverLLMChannelModelsResponse;
type _AssertWatchlist = keyof OpenApiWatchlistResponse;
type _AssertKronos = keyof OpenApiKronosStatusResponse;
const _configAnchor: _AssertConfig = 'config_version';
const _schemaAnchor: _AssertSchema = 'schema_version';
const _updateAnchor: _AssertUpdate = 'applied_count';
const _setupAnchor: _AssertSetup = 'is_complete';
const _exportAnchor: _AssertExport = 'config_version';
const _validateAnchor: _AssertValidate = 'valid';
const _genStatusAnchor: _AssertGenStatus = 'primary_backend_id';
const _genSmokeAnchor: _AssertGenSmoke = 'status';
const _catalogAnchor: _AssertCatalog = 'connection_fields';
const _testLlmAnchor: _AssertTestLlm = 'success';
const _testNotifyAnchor: _AssertTestNotify = 'success';
const _discoverAnchor: _AssertDiscover = 'models';
const _watchlistAnchor: _AssertWatchlist = 'stock_codes';
const _kronosAnchor: _AssertKronos = 'weights_present';
void _configAnchor; void _schemaAnchor; void _updateAnchor; void _setupAnchor;
void _exportAnchor; void _validateAnchor; void _genStatusAnchor; void _genSmokeAnchor;
void _catalogAnchor; void _testLlmAnchor; void _testNotifyAnchor; void _discoverAnchor;
void _watchlistAnchor; void _kronosAnchor;

const configConditionSchema = z.object({
  key: z.string(), operator: z.string(),
  value: z.union([z.string(), z.array(z.string()), z.null()]).optional(),
}).passthrough();
const configFieldContractSchema = z.object({
  requirement: z.string(),
  requiredWhen: z.array(configConditionSchema).nullable().optional(),
  visibleWhen: z.array(configConditionSchema).nullable().optional(),
  enabledWhen: z.array(configConditionSchema).nullable().optional(),
  requiresConnectionTest: z.boolean().nullable().optional(),
  restartRequired: z.boolean().nullable().optional(),
}).passthrough();
const systemConfigOptionSchema = z.object({ label: z.string(), value: z.string() }).passthrough();
const systemConfigDocLinkSchema = z.object({ label: z.string(), href: z.string() }).passthrough();
const systemConfigFieldSchema = z.object({
  key: z.string(), title: z.string().nullable().optional(), description: z.string().nullable().optional(),
  category: z.string(), dataType: z.string(), uiControl: z.string(),
  isSensitive: z.boolean(), isRequired: z.boolean(), isEditable: z.boolean(),
  defaultValue: z.string().nullable().optional(), unit: z.string().nullable().optional(),
  options: z.array(z.union([z.string(), systemConfigOptionSchema])).optional(),
  validation: z.record(z.string(), z.unknown()).optional(), displayOrder: z.number(),
  helpKey: z.string().nullable().optional(), examples: z.array(z.string()).optional(),
  docs: z.array(systemConfigDocLinkSchema).optional(), warningCodes: z.array(z.string()).optional(),
  deprecated: z.boolean().optional(), replacement: z.string().nullable().optional(),
  contract: configFieldContractSchema.nullable().optional(), uiPlacement: z.string().nullable().optional(),
}).passthrough();
const systemConfigCategorySchema = z.object({
  category: z.string(), title: z.string(), description: z.string().nullable().optional(),
  displayOrder: z.number(), fields: z.array(systemConfigFieldSchema),
}).passthrough();
const systemConfigSchemaResponseSchema = z.object({
  schemaVersion: z.string(), categories: z.array(systemConfigCategorySchema),
}).passthrough();
const systemConfigItemSchema = z.object({
  key: z.string(), value: z.string(), rawValueExists: z.boolean(), isMasked: z.boolean(),
  schema: systemConfigFieldSchema.nullable().optional(),
}).passthrough();
const systemConfigResponseSchema = z.object({
  configVersion: z.string(), maskToken: z.string(), items: z.array(systemConfigItemSchema),
  configuredNotificationChannels: z.array(z.string()).optional(), updatedAt: z.string().nullable().optional(),
}).passthrough();
const exportSystemConfigResponseSchema = z.object({
  content: z.string(), configVersion: z.string(), updatedAt: z.string().nullable().optional(),
}).passthrough();
const setupStatusCheckSchema = z.object({
  key: z.string(), title: z.string(), category: z.string(), required: z.boolean(),
  status: z.string(), message: z.string(), nextStep: z.string().nullable().optional(),
}).passthrough();
const setupStatusResponseSchema = z.object({
  isComplete: z.boolean(), readyForSmoke: z.boolean(),
  requiredMissingKeys: z.array(z.string()).optional(), nextStepKey: z.string().nullable().optional(),
  checks: z.array(setupStatusCheckSchema).optional(),
}).passthrough();
const generationBackendStatusSchema = z.object({
  backendId: z.string(), backendType: z.string(), providerId: z.string(), available: z.boolean(),
  healthStatus: z.string().optional(), supportsJson: z.boolean(), supportsTools: z.boolean(),
  supportsStream: z.boolean(), supportsVision: z.boolean(), isPrimary: z.boolean(),
  fallbackTarget: z.string().nullable().optional(), maxConcurrency: z.number(), usageAvailable: z.boolean(),
  lastErrorCode: z.string().nullable().optional(), lastErrorMessage: z.string().nullable().optional(),
}).passthrough();
const generationBackendStatusResponseSchema = z.object({
  primaryBackendId: z.string(), fallbackBackendId: z.string().nullable().optional(),
  primary: generationBackendStatusSchema, fallback: generationBackendStatusSchema.nullable().optional(),
  backends: z.array(generationBackendStatusSchema).optional(),
}).passthrough();
const testGenerationBackendResponseSchema = z.object({
  success: z.boolean(), mode: z.string(), message: z.string(), status: generationBackendStatusSchema,
}).passthrough();
const llmConfigModeStatusSchema = z.object({
  requestedMode: z.string(), effectiveMode: z.string().nullable(),
  detectedSources: z.array(z.string()), overriddenSources: z.array(z.string()),
  issues: z.array(z.object({
    key: z.string(), code: z.string(), severity: z.string(), message: z.string(),
    expected: z.string().optional(), actual: z.string().optional(),
  }).passthrough()),
}).passthrough();
const legacyChannelsMigrationPreviewSchema = z.object({
  channels: z.array(z.object({
    name: z.string(), protocol: z.string(), baseUrl: z.string(), model: z.string(),
  }).passthrough()),
}).passthrough();
const llmProviderCatalogEntrySchema = z.object({
  id: z.string(), label: z.string(), labelZh: z.string(), labelEn: z.string(),
  protocol: z.string(), defaultBaseUrl: z.string(),
  credentialUrl: z.string().nullable().optional(), consoleUrl: z.string().nullable().optional(),
  modelsUrl: z.string().nullable().optional(), docsUrl: z.string().nullable().optional(),
  capabilities: z.array(z.string()).optional(),
  requiresApiKey: z.boolean(), requiresBaseUrl: z.boolean(), supportsDiscovery: z.boolean(),
  isLocal: z.boolean(), isCustom: z.boolean(),
}).passthrough();
const llmConnectionFieldSchema = z.object({
  key: z.string(), envSuffix: z.string().nullable().optional(), dataType: z.string(),
  isSensitive: z.boolean(), isRequired: z.boolean(), contract: configFieldContractSchema,
}).passthrough();
const llmProviderCatalogResponseSchema = z.object({
  providers: z.array(llmProviderCatalogEntrySchema),
  connectionFields: z.array(llmConnectionFieldSchema),
  emptyApiKeyHosts: z.array(z.string()).optional(),
}).passthrough();
const availableModelEntrySchema = z.object({
  modelRef: z.string().optional(), route: z.string().optional(), display: z.string().optional(),
  connection: z.string().nullable().optional(), connectionId: z.string().nullable().optional(),
  connectionName: z.string().nullable().optional(), provider: z.string().nullable().optional(),
  providerId: z.string().nullable().optional(), providerLabel: z.string().nullable().optional(),
  available: z.boolean().optional(),
}).passthrough();
const availableModelsResponseSchema = z.object({ models: z.array(availableModelEntrySchema).optional() }).passthrough();
const schedulerStatusResponseSchema = z.object({
  enabled: z.boolean(), running: z.boolean(), scheduleTimes: z.array(z.string()),
  track: z.literal('legacy_day_batch').optional(), attached: z.boolean().optional(),
  processMode: z.enum(['serve', 'desktop', 'not_attached']).optional(),
  scheduleTimezone: z.string().optional(), runNowAvailable: z.boolean().optional(),
  runNowBlockReason: z.string().nullable().optional(),
  nextRunAt: z.string().nullable().optional(), lastRunAt: z.string().nullable().optional(),
  lastSuccessAt: z.string().nullable().optional(), lastError: z.string().nullable().optional(),
  lastSkippedAt: z.string().nullable().optional(), lastSkipReason: z.string().nullable().optional(),
  activeRunId: z.string().nullable().optional(), lastRunId: z.string().nullable().optional(),
  lastRunOutcome: z.enum(['succeeded', 'failed']).nullable().optional(),
}).passthrough();
const schedulerRunNowResponseSchema = z.object({
  accepted: z.boolean(), running: z.boolean(), reason: z.string().optional(),
  runId: z.string().optional(), startedAt: z.string().optional(),
}).passthrough();
const configValidationIssueSchema = z.object({
  key: z.string(), code: z.string(), message: z.string(), severity: z.string(),
  expected: z.string().nullable().optional(), actual: z.string().nullable().optional(),
  details: z.record(z.string(), z.unknown()).optional(),
}).passthrough();
const validateSystemConfigResponseSchema = z.object({
  valid: z.boolean(), issues: z.array(configValidationIssueSchema),
}).passthrough();
const updateSystemConfigResponseSchema = z.object({
  success: z.boolean(), configVersion: z.string(), appliedCount: z.number(),
  skippedMaskedCount: z.number(), reloadTriggered: z.boolean(), updatedKeys: z.array(z.string()),
  warnings: z.array(z.string()).optional(),
}).passthrough();
const testLLMChannelResponseSchema = z.object({
  success: z.boolean(), message: z.string(),
  error: z.string().nullable().optional(), errorCode: z.string().nullable().optional(),
  stage: z.string().nullable().optional(), retryable: z.boolean().nullable().optional(),
  details: z.record(z.string(), z.unknown()).optional(), resolvedProtocol: z.string().nullable().optional(),
  resolvedModel: z.string().nullable().optional(), latencyMs: z.number().nullable().optional(),
  capabilityResults: z.record(z.string(), z.unknown()).optional(),
}).passthrough();
const notificationTestAttemptSchema = z.object({
  channel: z.string(), success: z.boolean(), message: z.string(),
  target: z.string().nullable().optional(), errorCode: z.string().nullable().optional(),
  stage: z.string().optional(), retryable: z.boolean().optional(),
  latencyMs: z.number().nullable().optional(), httpStatus: z.number().nullable().optional(),
}).passthrough();
const testNotificationChannelResponseSchema = z.object({
  success: z.boolean(), message: z.string(),
  errorCode: z.string().nullable().optional(), stage: z.string().nullable().optional(),
  retryable: z.boolean().optional(), latencyMs: z.number().nullable().optional(),
  attempts: z.array(notificationTestAttemptSchema).optional(),
}).passthrough();
const discoverLLMChannelModelsResponseSchema = z.object({
  success: z.boolean(), message: z.string(),
  error: z.string().nullable().optional(), errorCode: z.string().nullable().optional(),
  stage: z.string().nullable().optional(), retryable: z.boolean().nullable().optional(),
  details: z.record(z.string(), z.unknown()).optional(), resolvedProtocol: z.string().nullable().optional(),
  models: z.array(z.string()).optional(), latencyMs: z.number().nullable().optional(),
}).passthrough();
const watchlistResponseSchema = z.object({
  message: z.string(), stockCodes: z.array(z.string()).optional(),
}).passthrough();
const kronosDependencyStatusSchema = z.object({ name: z.string(), available: z.boolean() }).passthrough();
const kronosStatusResponseSchema = z.object({
  enabled: z.boolean(), modelSize: z.string(), ready: z.boolean(), reason: z.string(),
  message: z.string(), nextStep: z.string(), dependenciesInstalled: z.boolean(), weightsPresent: z.boolean(),
  dependencies: z.array(kronosDependencyStatusSchema).optional(),
  downloadSizeHint: z.string().nullable().optional(), installSupported: z.boolean().optional(),
  modelDir: z.string().nullable().optional(), packagedDesktop: z.boolean().optional(),
  tokenizerDir: z.string().nullable().optional(), weightsDirConfigured: z.string().nullable().optional(),
  weightsDirResolved: z.string().nullable().optional(), weightsModifiedAt: z.string().nullable().optional(),
  weightsTotalBytes: z.number().nullable().optional(),
}).passthrough();

function parseCamelCasePayload<T>(data: unknown, schema: z.ZodTypeAny, label: string): T {
  const camel = toCamelCase<unknown>(data);
  const result = schema.safeParse(camel);
  if (!result.success) {
    const issueSummary = result.error.issues.slice(0, 5).map((issue) => `${issue.path.join('.') || '(root)'}: ${issue.message}`).join('; ');
    if (import.meta.env.DEV) {
      console.error(`[systemConfig] response validation failed (${label})`, result.error.issues);
    }
    throw createApiError(createParsedApiError({
      title: '响应校验失败',
      message: `接口响应未通过校验（${label}）。${issueSummary}`,
      rawMessage: result.error.message,
      category: 'unknown',
      code: 'api_response_validation_failed',
      params: { label, issues: issueSummary },
      details: result.error.issues,
    }));
  }
  return camel as T;
}

export class SystemConfigValidationError extends Error {
  issues: ConfigValidationIssue[];
  parsedError: ParsedApiError;

  constructor(message: string, issues: ConfigValidationIssue[], parsedError?: ParsedApiError) {
    super(message);
    this.name = 'SystemConfigValidationError';
    this.issues = issues;
    this.parsedError = parsedError ?? createParsedApiError({
      title: '配置校验失败',
      message,
      rawMessage: message,
      status: 400,
      category: 'http_error',
    });
  }
}

export class SystemConfigConflictError extends Error {
  currentConfigVersion?: string;
  parsedError: ParsedApiError;

  constructor(message: string, currentConfigVersion?: string, parsedError?: ParsedApiError) {
    super(message);
    this.name = 'SystemConfigConflictError';
    this.currentConfigVersion = currentConfigVersion;
    this.parsedError = parsedError ?? createParsedApiError({
      title: '配置版本冲突',
      message,
      rawMessage: message,
      status: 409,
      category: 'http_error',
    });
  }
}

function toSnakeUpdatePayload(payload: UpdateSystemConfigRequest): Record<string, unknown> {
  return {
    config_version: payload.configVersion,
    mask_token: payload.maskToken ?? '******',
    reload_now: payload.reloadNow ?? true,
    items: payload.items.map((item) => ({
      key: item.key,
      value: item.value,
    })),
  };
}

function toSnakeValidatePayload(payload: ValidateSystemConfigRequest): Record<string, unknown> {
  return {
    items: payload.items.map((item) => ({
      key: item.key,
      value: item.value,
    })),
  };
}

function toSnakeImportPayload(payload: ImportSystemConfigRequest): Record<string, unknown> {
  return {
    config_version: payload.configVersion,
    content: payload.content,
    reload_now: payload.reloadNow ?? true,
  };
}

function toSnakeTestChannelPayload(payload: TestLLMChannelRequest): Record<string, unknown> {
  const request: Record<string, unknown> = {
    name: payload.name,
    provider_id: payload.providerId,
    protocol: payload.protocol,
    base_url: payload.baseUrl ?? '',
    api_key: payload.apiKey ?? '',
    models: payload.models,
    enabled: payload.enabled ?? true,
    timeout_seconds: payload.timeoutSeconds ?? 20,
    use_saved_secret: payload.useSavedSecret ?? false,
  };
  if (payload.capabilityChecks && payload.capabilityChecks.length > 0) {
    request.capability_checks = payload.capabilityChecks;
  }
  return request;
}

function toSnakeNotificationTestPayload(payload: TestNotificationChannelRequest): Record<string, unknown> {
  return {
    channel: payload.channel,
    items: (payload.items || []).map((item) => ({
      key: item.key,
      value: item.value,
    })),
    mask_token: payload.maskToken ?? '******',
    title: payload.title ?? 'StockPulse 通知测试',
    content: payload.content ?? '这是一条来自 StockPulse Web 设置页的通知测试消息。',
    timeout_seconds: payload.timeoutSeconds ?? 20,
  };
}

function toSnakeDiscoverModelsPayload(payload: DiscoverLLMChannelModelsRequest): Record<string, unknown> {
  return {
    name: payload.name,
    provider_id: payload.providerId,
    protocol: payload.protocol,
    base_url: payload.baseUrl ?? '',
    api_key: payload.apiKey ?? '',
    models: payload.models,
    timeout_seconds: payload.timeoutSeconds ?? 20,
    use_saved_secret: payload.useSavedSecret ?? false,
  };
}

function toSnakeGenerationBackendStatusPreviewPayload(
  payload: GenerationBackendStatusPreviewRequest = {},
): Record<string, unknown> {
  return {
    items: (payload.items || []).map((item) => ({
      key: item.key,
      value: item.value,
    })),
    mask_token: payload.maskToken ?? '******',
  };
}

function toSnakeGenerationBackendSmokePayload(payload: TestGenerationBackendRequest = {}): Record<string, unknown> {
  const request: Record<string, unknown> = {
    mode: payload.mode ?? 'json',
    items: (payload.items || []).map((item) => ({
      key: item.key,
      value: item.value,
    })),
    mask_token: payload.maskToken ?? '******',
  };
  if (payload.backendId) {
    request.backend_id = payload.backendId;
  }
  if (payload.timeoutSeconds !== undefined && payload.timeoutSeconds !== null) {
    request.timeout_seconds = payload.timeoutSeconds;
  }
  return request;
}

export const systemConfigApi = {
  async getConfig(includeSchema = true): Promise<SystemConfigResponse> {
    const response = await apiClient.get<Record<string, unknown>>('/api/v1/system/config', {
      params: { include_schema: includeSchema },
    });
    return parseCamelCasePayload<SystemConfigResponse>(response.data, systemConfigResponseSchema, 'SystemConfigResponse');
  },

  async exportEnv(): Promise<ExportSystemConfigResponse> {
    const response = await apiClient.get<Record<string, unknown>>('/api/v1/system/config/export');
    return parseCamelCasePayload<ExportSystemConfigResponse>(response.data, exportSystemConfigResponseSchema, 'ExportSystemConfigResponse');
  },

  async exportDesktopEnv(): Promise<ExportSystemConfigResponse> {
    return this.exportEnv();
  },

  async getSchema(): Promise<SystemConfigSchemaResponse> {
    const response = await apiClient.get<Record<string, unknown>>('/api/v1/system/config/schema');
    return parseCamelCasePayload<SystemConfigSchemaResponse>(response.data, systemConfigSchemaResponseSchema, 'SystemConfigSchemaResponse');
  },

  async getSetupStatus(): Promise<SetupStatusResponse> {
    const response = await apiClient.get<Record<string, unknown>>('/api/v1/system/config/setup/status');
    return parseCamelCasePayload<SetupStatusResponse>(response.data, setupStatusResponseSchema, 'SetupStatusResponse');
  },

  async getGenerationBackendStatus(): Promise<GenerationBackendStatusResponse> {
    const response = await apiClient.get<Record<string, unknown>>(
      '/api/v1/system/config/generation-backends/status',
    );
    return parseCamelCasePayload<GenerationBackendStatusResponse>(response.data, generationBackendStatusResponseSchema, 'GenerationBackendStatusResponse');
  },

  async getKronosStatus(): Promise<KronosStatusResponse> {
    const response = await apiClient.get<Record<string, unknown>>(
      '/api/v1/system/config/kronos/status',
    );
    return parseCamelCasePayload<KronosStatusResponse>(response.data, kronosStatusResponseSchema, 'KronosStatusResponse');
  },

  async getLlmConfigModeStatus(): Promise<LLMConfigModeStatus> {
    const response = await apiClient.get<Record<string, unknown>>(
      '/api/v1/system/config/llm/mode-status',
    );
    return parseCamelCasePayload<LLMConfigModeStatus>(response.data, llmConfigModeStatusSchema, 'LLMConfigModeStatus');
  },

  async previewLegacyChannelsMigration(): Promise<LegacyChannelsMigrationPreview> {
    const response = await apiClient.get<Record<string, unknown>>(
      '/api/v1/system/config/llm/legacy-migration/preview',
    );
    return parseCamelCasePayload<LegacyChannelsMigrationPreview>(response.data, legacyChannelsMigrationPreviewSchema, 'LegacyChannelsMigrationPreview');
  },

  async applyLegacyChannelsMigration(configVersion: string): Promise<UpdateSystemConfigResponse> {
    const response = await apiClient.post<Record<string, unknown>>(
      '/api/v1/system/config/llm/legacy-migration/apply',
      { config_version: configVersion },
    );
    return parseCamelCasePayload<UpdateSystemConfigResponse>(response.data, updateSystemConfigResponseSchema, 'UpdateSystemConfigResponse');
  },

  async getLlmProviderCatalog(): Promise<LlmProviderCatalogResponse> {
    const response = await apiClient.get<Record<string, unknown>>('/api/v1/system/config/llm/providers');
    return parseCamelCasePayload<LlmProviderCatalogResponse>(response.data, llmProviderCatalogResponseSchema, 'LLMProviderCatalogResponse');
  },

  async getLlmAvailableModels(): Promise<AvailableModelsResponse> {
    const response = await apiClient.get<Record<string, unknown>>('/api/v1/system/config/llm/available-models');
    const parsed = parseCamelCasePayload<AvailableModelsResponse>(
      response.data,
      availableModelsResponseSchema,
      'AvailableModelsResponse',
    );
    return {
      ...parsed,
      models: (parsed.models ?? []).map((entry) => ({
        ...entry,
        // Rolling-upgrade compatibility for servers predating ModelRef.
        modelRef: entry.modelRef || entry.route,
      })),
    };
  },

  async previewGenerationBackendStatus(
    payload: GenerationBackendStatusPreviewRequest = {},
  ): Promise<GenerationBackendStatusResponse> {
    const response = await apiClient.post<Record<string, unknown>>(
      '/api/v1/system/config/generation-backends/status/preview',
      toSnakeGenerationBackendStatusPreviewPayload(payload),
    );
    return parseCamelCasePayload<GenerationBackendStatusResponse>(response.data, generationBackendStatusResponseSchema, 'GenerationBackendStatusResponse');
  },

  async testGenerationBackend(payload: TestGenerationBackendRequest = {}): Promise<TestGenerationBackendResponse> {
    const response = await apiClient.post<Record<string, unknown>>(
      '/api/v1/system/config/generation-backends/smoke-test',
      toSnakeGenerationBackendSmokePayload(payload),
    );
    return parseCamelCasePayload<TestGenerationBackendResponse>(response.data, testGenerationBackendResponseSchema, 'TestGenerationBackendResponse');
  },

  async getSchedulerStatus(): Promise<SchedulerStatusResponse> {
    const response = await apiClient.get<Record<string, unknown>>('/api/v1/system/scheduler/status');
    return parseCamelCasePayload<SchedulerStatusResponse>(response.data, schedulerStatusResponseSchema, 'SchedulerStatusResponse');
  },

  async runSchedulerNow(): Promise<SchedulerRunNowResponse> {
    const response = await apiClient.post<Record<string, unknown>>('/api/v1/system/scheduler/run-now');
    return parseCamelCasePayload<SchedulerRunNowResponse>(response.data, schedulerRunNowResponseSchema, 'SchedulerRunNowResponse');
  },

  async validate(payload: ValidateSystemConfigRequest): Promise<ValidateSystemConfigResponse> {
    const response = await apiClient.post<Record<string, unknown>>(
      '/api/v1/system/config/validate',
      toSnakeValidatePayload(payload),
    );
    return parseCamelCasePayload<ValidateSystemConfigResponse>(response.data, validateSystemConfigResponseSchema, 'ValidateSystemConfigResponse');
  },

  async importEnv(payload: ImportSystemConfigRequest): Promise<UpdateSystemConfigResponse> {
    const response = await apiClient.post<Record<string, unknown>>(
      '/api/v1/system/config/import',
      toSnakeImportPayload(payload),
    );
    return parseCamelCasePayload<UpdateSystemConfigResponse>(response.data, updateSystemConfigResponseSchema, 'UpdateSystemConfigResponse');
  },

  async importDesktopEnv(payload: ImportSystemConfigRequest): Promise<UpdateSystemConfigResponse> {
    return this.importEnv(payload);
  },

  async rollback(payload: RollbackSystemConfigRequest): Promise<UpdateSystemConfigResponse> {
    try {
      const response = await apiClient.post<Record<string, unknown>>(
        '/api/v1/system/config/rollback',
        { config_version: payload.configVersion },
      );
      return parseCamelCasePayload<UpdateSystemConfigResponse>(response.data, updateSystemConfigResponseSchema, 'UpdateSystemConfigResponse');
    } catch (error: unknown) {
      const parsed = getParsedApiError(error);
      if (error && typeof error === 'object' && 'response' in error) {
        const status = (error as { response?: { status?: number } }).response?.status;
        const payloadData = (error as { response?: { data?: unknown } }).response?.data;
        if (status === 409 && parsed.code === 'config_version_conflict') {
          const conflict = toCamelCase<SystemConfigConflictResponse>(payloadData ?? {});
          const parsedCurrentVersion = (
            parsed.params?.currentConfigVersion
            ?? parsed.params?.current_config_version
          );
          throw new SystemConfigConflictError(
            parsed.message || conflict.message || '配置版本冲突',
            conflict.params?.currentConfigVersion
              || conflict.currentConfigVersion
              || (typeof parsedCurrentVersion === 'string' ? parsedCurrentVersion : undefined),
            parsed,
          );
        }
      }
      throw error;
    }
  },

  async testLLMChannel(payload: TestLLMChannelRequest): Promise<TestLLMChannelResponse> {
    const response = await apiClient.post<Record<string, unknown>>(
      '/api/v1/system/config/llm/test-channel',
      toSnakeTestChannelPayload(payload),
    );
    return parseCamelCasePayload<TestLLMChannelResponse>(response.data, testLLMChannelResponseSchema, 'TestLLMChannelResponse');
  },

  async testNotificationChannel(payload: TestNotificationChannelRequest): Promise<TestNotificationChannelResponse> {
    const response = await apiClient.post<Record<string, unknown>>(
      '/api/v1/system/config/notification/test-channel',
      toSnakeNotificationTestPayload(payload),
    );
    return parseCamelCasePayload<TestNotificationChannelResponse>(response.data, testNotificationChannelResponseSchema, 'TestNotificationChannelResponse');
  },

  async discoverLLMChannelModels(
    payload: DiscoverLLMChannelModelsRequest,
  ): Promise<DiscoverLLMChannelModelsResponse> {
    const response = await apiClient.post<Record<string, unknown>>(
      '/api/v1/system/config/llm/discover-models',
      toSnakeDiscoverModelsPayload(payload),
    );
    const parsedDiscover = parseCamelCasePayload<DiscoverLLMChannelModelsResponse>(response.data, discoverLLMChannelModelsResponseSchema, 'DiscoverLLMChannelModelsResponse');
    return { ...parsedDiscover, models: parsedDiscover.models ?? [] };
  },

  async update(payload: UpdateSystemConfigRequest): Promise<UpdateSystemConfigResponse> {
    try {
      const response = await apiClient.put<Record<string, unknown>>(
        '/api/v1/system/config',
        toSnakeUpdatePayload(payload),
      );
      return parseCamelCasePayload<UpdateSystemConfigResponse>(response.data, updateSystemConfigResponseSchema, 'UpdateSystemConfigResponse');
    } catch (error: unknown) {
      const parsed = getParsedApiError(error);
      if (error && typeof error === 'object' && 'response' in error) {
        const status = (error as { response?: { status?: number } }).response?.status;
        const payloadData = (error as { response?: { data?: unknown } }).response?.data;

        if (status === 400) {
          const validationError = toCamelCase<SystemConfigValidationErrorResponse>(payloadData ?? {});
          throw new SystemConfigValidationError(
            parsed.message || validationError.message || '配置校验失败',
            validationError.params?.issues || validationError.issues || [],
            parsed,
          );
        }

        if (status === 409) {
          const conflict = toCamelCase<SystemConfigConflictResponse>(payloadData ?? {});
          throw new SystemConfigConflictError(
            parsed.message || conflict.message || '配置版本冲突',
            conflict.params?.currentConfigVersion || conflict.currentConfigVersion,
            parsed,
          );
        }
      }

      throw error;
    }
  },

  /**
   * Get a list of codes for watchlist stocks
   */
  getWatchlist: async (): Promise<string[]> => {
    const response = await apiClient.get<Record<string, unknown>>('/api/v1/stocks/watchlist');
    const data = parseCamelCasePayload<{ stockCodes?: string[]; message: string }>(
      response.data,
      watchlistResponseSchema,
      'WatchlistResponse',
    );
    return data.stockCodes || [];
  },

  /**
   * Add stocks to watchlist queue
   */
  addToWatchlist: async (stockCode: string): Promise<string[]> => {
    const response = await apiClient.post<Record<string, unknown>>('/api/v1/stocks/watchlist/add', {
      stock_code: stockCode,
    });
    const data = parseCamelCasePayload<{ stockCodes?: string[]; message: string }>(
      response.data,
      watchlistResponseSchema,
      'WatchlistResponse',
    );
    return data.stockCodes || [];
  },

  /**
   * Remove stocks from watchlist queue.
   */
  removeFromWatchlist: async (stockCode: string): Promise<string[]> => {
    const response = await apiClient.post<Record<string, unknown>>('/api/v1/stocks/watchlist/remove', {
      stock_code: stockCode,
    });
    const data = parseCamelCasePayload<{ stockCodes?: string[]; message: string }>(
      response.data,
      watchlistResponseSchema,
      'WatchlistResponse',
    );
    return data.stockCodes || [];
  },
};
