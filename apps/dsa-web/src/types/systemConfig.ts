export type SystemConfigCategory =
  | 'base'
  | 'data_source'
  | 'ai_model'
  | 'notification'
  | 'system'
  | 'agent'
  | 'backtest'
  | 'uncategorized';

export type SystemConfigDataType =
  | 'string'
  | 'integer'
  | 'number'
  | 'boolean'
  | 'array'
  | 'json'
  | 'time';

export type SystemConfigUIControl =
  | 'text'
  | 'password'
  | 'number'
  | 'select'
  | 'textarea'
  | 'switch'
  | 'time';

export interface SystemConfigOption {
  label: string;
  value: string;
}

export interface SystemConfigDocLink {
  label: string;
  href: string;
}

export type ConfigConditionOperator = 'equals' | 'notEquals' | 'in' | 'notEmpty';

export interface ConfigCondition {
  key: string;
  operator: ConfigConditionOperator;
  value?: string | string[] | null;
}

export interface ConfigFieldContract {
  requirement?: 'required' | 'optional' | 'inherited';
  requiredWhen?: ConfigCondition[] | null;
  visibleWhen?: ConfigCondition[] | null;
  enabledWhen?: ConfigCondition[] | null;
  requiresConnectionTest?: boolean | null;
  restartRequired?: boolean | null;
}

/**
 * Backend-declared UI ownership for AI-model related fields. The Web renders a
 * field only in the surface its placement declares — it must not keep a second
 * hardcoded provider/key list:
 * - model_access: owned by the model-access connection manager
 * - task_routing: task model selectors and routing fields
 * - developer_diagnostics: advanced diagnostics, collapsed by default
 * - hidden_legacy: legacy provider keys; readable but never rendered as a
 *   generic editable settings field
 * - null/undefined: regular only for non-AI fields; AI fields fail safe to a
 *   read-only Advanced diagnostic during rolling upgrades
 */
export type SystemConfigUIPlacement =
  | 'model_access'
  | 'task_routing'
  | 'developer_diagnostics'
  | 'hidden_legacy';

export interface SystemConfigFieldSchema {
  key: string;
  title?: string;
  description?: string;
  category: SystemConfigCategory;
  dataType: SystemConfigDataType;
  uiControl: SystemConfigUIControl;
  isSensitive: boolean;
  isRequired: boolean;
  isEditable: boolean;
  defaultValue?: string | null;
  options: Array<string | SystemConfigOption>;
  validation: Record<string, unknown>;
  displayOrder: number;
  helpKey?: string | null;
  examples?: string[];
  docs?: SystemConfigDocLink[];
  warningCodes?: string[];
  contract?: ConfigFieldContract;
  uiPlacement?: SystemConfigUIPlacement | null;
}

export interface SystemConfigCategorySchema {
  category: SystemConfigCategory;
  title: string;
  description?: string;
  displayOrder: number;
  fields: SystemConfigFieldSchema[];
}

export interface SystemConfigSchemaResponse {
  schemaVersion: string;
  categories: SystemConfigCategorySchema[];
}

export interface SystemConfigItem {
  key: string;
  value: string;
  rawValueExists: boolean;
  isMasked: boolean;
  schema?: SystemConfigFieldSchema;
}

export interface SystemConfigResponse {
  configVersion: string;
  maskToken: string;
  items: SystemConfigItem[];
  updatedAt?: string;
}

export interface SetupStatusCheck {
  key: string;
  title: string;
  category: 'base' | 'ai_model' | 'agent' | 'notification' | 'system';
  required: boolean;
  status: 'configured' | 'inherited' | 'optional' | 'needs_action';
  message: string;
  nextStep?: string | null;
}

export interface SetupStatusResponse {
  isComplete: boolean;
  readyForSmoke: boolean;
  requiredMissingKeys: string[];
  nextStepKey?: string | null;
  checks: SetupStatusCheck[];
}

export type GenerationBackendHealthStatus = 'not_tested' | 'passed' | 'failed' | 'skipped';
export type GenerationBackendSmokeMode = 'text' | 'json';

export interface GenerationBackendStatus {
  backendId: string;
  backendType: 'litellm' | 'local_cli';
  providerId: string;
  available: boolean;
  healthStatus: GenerationBackendHealthStatus;
  supportsJson: boolean;
  supportsTools: boolean;
  supportsStream: boolean;
  supportsVision: boolean;
  isPrimary: boolean;
  fallbackTarget?: string | null;
  maxConcurrency: number;
  usageAvailable: boolean;
  lastErrorCode?: string | null;
  lastErrorMessage?: string | null;
}

export interface GenerationBackendStatusResponse {
  primaryBackendId: string;
  fallbackBackendId?: string | null;
  primary: GenerationBackendStatus;
  fallback?: GenerationBackendStatus | null;
  backends: GenerationBackendStatus[];
}

export type LLMConfigMode = 'auto' | 'channels' | 'yaml' | 'legacy';
export type LLMConfigModeSource = 'yaml' | 'channels' | 'legacy';

export interface LLMConfigModeStatus {
  requestedMode: LLMConfigMode;
  effectiveMode: LLMConfigModeSource | null;
  detectedSources: LLMConfigModeSource[];
  overriddenSources: LLMConfigModeSource[];
  issues: Array<{
    key: string;
    code: string;
    severity: string;
    message: string;
    expected?: string;
    actual?: string;
  }>;
}

export interface LlmProviderCatalogEntry {
  id: string;
  /** @deprecated Chinese compatibility label; select labelZh/labelEn for UI. */
  label: string;
  labelZh?: string;
  labelEn?: string;
  protocol: string;
  defaultBaseUrl: string;
  credentialUrl?: string | null;
  consoleUrl?: string | null;
  modelsUrl?: string | null;
  docsUrl?: string | null;
  capabilities: string[];
  requiresApiKey: boolean;
  requiresBaseUrl: boolean;
  supportsDiscovery: boolean;
  isLocal: boolean;
  isCustom: boolean;
}

export interface LlmConnectionFieldSchema {
  key: string;
  envSuffix?: string | null;
  dataType: 'string' | 'boolean' | 'array' | 'json';
  isSensitive: boolean;
  /** @deprecated Unconditional compatibility projection; contract is authoritative. */
  isRequired: boolean;
  contract: ConfigFieldContract;
}

export interface LlmProviderCatalogResponse {
  providers: LlmProviderCatalogEntry[];
  /** Undefined only for rolling upgrades from a backend predating this schema. */
  connectionFields?: LlmConnectionFieldSchema[];
  /**
   * Hostnames whose endpoints may run without an API key, mirroring the
   * backend `channel_allows_empty_api_key` contract. The Web applies this
   * list instead of hardcoding its own localhost heuristic.
   */
  emptyApiKeyHosts?: string[];
}

export interface AvailableModelEntry {
  /** Stable Connection-aware identity stored by task routing. */
  modelRef: string;
  /** Canonical runtime route resolved only when the model is executed. */
  route: string;
  /** User-facing display name. */
  display: string;
  /** Owning connection name (best-effort grouping), null if unknown. */
  connection: string | null;
  /** Stable connection id (equals the connection name), null if unknown. */
  connectionId: string | null;
  /** User-facing connection name returned by the backend. */
  connectionName: string | null;
  /** Protocol of the owning connection, null if unknown (back-compat). */
  provider: string | null;
  /** Authoritative catalog provider id of the owning connection. */
  providerId: string | null;
  /** Authoritative catalog provider display label. */
  providerLabel: string | null;
  /** True when the route is declared by an enabled connection (routable now). */
  available: boolean;
}

export interface AvailableModelsResponse {
  models: AvailableModelEntry[];
}

export interface LegacyChannelsMigrationPreview {
  channels: Array<{
    name: string;
    protocol: string;
    baseUrl: string;
    model: string;
  }>;
}

export interface ExportSystemConfigResponse {
  content: string;
  configVersion: string;
  updatedAt?: string;
}

export interface SystemConfigUpdateItem {
  key: string;
  value: string;
}

/**
 * One field's three-way state after a save was rejected with a config-version
 * conflict (409): the value we submitted against (`base`), the newer value the
 * server now holds (`server`), and the user's still-pending edit (`local`).
 * Sensitive fields never carry displayable plaintext to the UI beyond status.
 */
export interface ConfigConflictField {
  key: string;
  base: string;
  server: string;
  local: string;
  isSensitive: boolean;
  title?: string;
  category?: string;
}

export interface ConfigConflictState {
  fields: ConfigConflictField[];
  serverVersion: string;
}

export interface GenerationBackendStatusPreviewRequest {
  items?: SystemConfigUpdateItem[];
  maskToken?: string;
}

export interface TestGenerationBackendRequest {
  backendId?: string | null;
  mode?: GenerationBackendSmokeMode;
  items?: SystemConfigUpdateItem[];
  maskToken?: string;
  timeoutSeconds?: number | null;
}

export interface TestGenerationBackendResponse {
  success: boolean;
  mode: GenerationBackendSmokeMode;
  message: string;
  status: GenerationBackendStatus;
}

export interface UpdateSystemConfigRequest {
  configVersion: string;
  maskToken?: string;
  reloadNow?: boolean;
  items: SystemConfigUpdateItem[];
}

export interface UpdateSystemConfigResponse {
  success: boolean;
  configVersion: string;
  appliedCount: number;
  skippedMaskedCount: number;
  reloadTriggered: boolean;
  updatedKeys: string[];
  warnings: string[];
}

export interface ValidateSystemConfigRequest {
  items: SystemConfigUpdateItem[];
}

export interface ImportSystemConfigRequest {
  configVersion: string;
  content: string;
  reloadNow?: boolean;
}

export interface ConfigValidationIssue {
  key: string;
  code: string;
  message: string;
  severity: 'error' | 'warning';
  expected?: string;
  actual?: string;
}

export interface ValidateSystemConfigResponse {
  valid: boolean;
  issues: ConfigValidationIssue[];
}

export interface SchedulerStatusResponse {
  enabled: boolean;
  running: boolean;
  scheduleTimes: string[];
  nextRunAt?: string | null;
  lastRunAt?: string | null;
  lastSuccessAt?: string | null;
  lastError?: string | null;
  lastSkippedAt?: string | null;
  lastSkipReason?: string | null;
}

export interface SchedulerRunNowResponse {
  accepted: boolean;
  running: boolean;
  reason?: string;
}

export interface TestLLMChannelRequest {
  name: string;
  providerId: string;
  protocol: string;
  baseUrl?: string;
  apiKey?: string;
  models: string[];
  enabled?: boolean;
  timeoutSeconds?: number;
  capabilityChecks?: LLMCapabilityCheck[];
  useSavedSecret?: boolean;
}

export type LLMCapabilityCheck = 'json' | 'tools' | 'vision' | 'stream';

export interface LLMCapabilityCheckResult {
  status: 'passed' | 'failed' | 'skipped';
  message: string;
  errorCode?: string | null;
  stage: string;
  retryable?: boolean | null;
  latencyMs?: number | null;
  details?: Record<string, unknown>;
}

export interface TestLLMChannelResponse {
  success: boolean;
  message: string;
  error?: string | null;
  errorCode?: string | null;
  stage?: string | null;
  retryable?: boolean | null;
  details?: Record<string, unknown>;
  resolvedProtocol?: string | null;
  resolvedModel?: string | null;
  latencyMs?: number | null;
  capabilityResults?: Partial<Record<LLMCapabilityCheck, LLMCapabilityCheckResult>>;
}

export type NotificationTestChannel =
  | 'wechat'
  | 'feishu'
  | 'telegram'
  | 'email'
  | 'pushover'
  | 'ntfy'
  | 'gotify'
  | 'pushplus'
  | 'serverchan3'
  | 'custom'
  | 'discord'
  | 'slack'
  | 'astrbot';

export interface NotificationTestAttempt {
  channel: NotificationTestChannel;
  success: boolean;
  message: string;
  target?: string | null;
  errorCode?: string | null;
  stage: string;
  retryable: boolean;
  latencyMs?: number | null;
  httpStatus?: number | null;
}

export interface TestNotificationChannelRequest {
  channel: NotificationTestChannel;
  items?: SystemConfigUpdateItem[];
  maskToken?: string;
  title?: string;
  content?: string;
  timeoutSeconds?: number;
}

export interface TestNotificationChannelResponse {
  success: boolean;
  message: string;
  errorCode?: string | null;
  stage?: string | null;
  retryable: boolean;
  latencyMs?: number | null;
  attempts: NotificationTestAttempt[];
}

export interface DiscoverLLMChannelModelsRequest {
  name: string;
  providerId: string;
  protocol: string;
  baseUrl?: string;
  apiKey?: string;
  models?: string[];
  timeoutSeconds?: number;
  useSavedSecret?: boolean;
}

export interface DiscoverLLMChannelModelsResponse {
  success: boolean;
  message: string;
  error?: string | null;
  errorCode?: string | null;
  stage?: string | null;
  retryable?: boolean | null;
  details?: Record<string, unknown>;
  resolvedProtocol?: string | null;
  models: string[];
  latencyMs?: number | null;
}

export interface SystemConfigValidationErrorResponse {
  error: string;
  message: string;
  issues?: ConfigValidationIssue[];
  params?: { issues?: ConfigValidationIssue[] };
  details?: unknown;
  /** @deprecated Read-only server alias of details during the compatibility window. */
  detail?: unknown;
  traceId?: string | null;
}

export interface SystemConfigConflictResponse {
  error: string;
  message: string;
  currentConfigVersion?: string;
  params?: { currentConfigVersion?: string };
  details?: unknown;
  /** @deprecated Read-only server alias of details during the compatibility window. */
  detail?: unknown;
  traceId?: string | null;
}
