export type LocalModelSection = 'general' | 'finance';
export type LocalModelMemoryTier = 'light' | 'standard' | 'high';
export type LocalModelInstallMethod = 'ollama_pull' | 'planned_ollama_package' | 'guided_import';
export type LocalModelInstallStatus = 'available' | 'conversion_required' | 'license_review_required';

export interface LocalizedCatalogText {
  en: string;
  zh: string;
}

export interface LocalModelCatalogEntry {
  id: string;
  section: LocalModelSection;
  displayName: LocalizedCatalogText;
  capabilitySummary: LocalizedCatalogText;
  capabilities: string[];
  q4: {
    quantization: 'Q4_K_M';
    sizeBytes: number;
    sourceKind: 'official_ollama' | 'community_gguf';
    sourceUrl: string;
    sourceRevision: string;
  };
  memoryTier: LocalModelMemoryTier;
  recommendedRamGb: number;
  license: {
    identifier: string;
    name: string;
    evidenceUrl: string;
    redistribution: 'allowed_with_notice' | 'guided_only';
    standaloneLicenseFile: boolean;
  };
  upstream: {
    primaryUrl: string;
    huggingfaceUrl?: string | null;
    modelscopeUrl?: string | null;
    revision: string;
  };
  install: {
    method: LocalModelInstallMethod;
    status: LocalModelInstallStatus;
    ollamaTag?: string | null;
    plannedOllamaTag?: string | null;
    downloadUrl: string;
    hostedByStockpulse: boolean;
    minimumRuntimeVersion?: string | null;
  };
  desktop: {
    recommended: boolean;
    role?: 'lightweight' | 'default' | 'high_performance' | 'reasoning' | null;
    guidanceEn: string;
  };
}

export interface LocalModelCatalogResponse {
  schemaVersion: 1;
  verifiedAt: string;
  models: LocalModelCatalogEntry[];
}

export interface LocalModelConfiguration {
  configVersion: string;
  registeredModels: string[];
  primaryModel: string;
  agentModel: string;
}

export type LocalModelRuntimeStatus =
  | 'unknown'
  | 'running'
  | 'unavailable'
  | 'not-installed'
  | 'stopped'
  | 'starting'
  | 'error';

export interface LocalModelRuntimeState {
  runtime: 'ollama';
  status: LocalModelRuntimeStatus;
  installedModels: string[];
  manualPullSupported: boolean;
  configuration: LocalModelConfiguration;
  managed?: boolean;
  operation?: string | null;
  totalMemoryGb?: number | null;
  progress?: LocalModelProgress | null;
}

export interface LocalModelProgress {
  modelId: string;
  percent: number | null;
  status: string;
}

export interface LocalModelPullAccepted {
  taskId: string;
  traceId: string;
  status: 'pending' | 'processing' | 'cancel_requested';
  modelId: string;
}

export interface LocalModelPullResult {
  modelId: string;
  activated: boolean;
  selectedPrimary: boolean;
}

export interface LocalModelPullStatus {
  taskId: string;
  status: 'pending' | 'processing' | 'cancel_requested' | 'completed' | 'failed' | 'cancelled' | 'interrupted';
  progress: number;
  modelId: string;
  error?: string | null;
  result?: LocalModelPullResult | null;
}

export type LocalModelAssignment = 'auto' | 'primary' | 'agent';

export interface LocalModelMutationResponse extends LocalModelConfiguration {
  success: boolean;
  modelId: string;
  selectedPrimary: boolean;
  selectedAgent: boolean;
  deleted: boolean;
  updatedKeys: string[];
  warnings: string[];
  appliedCount: number;
  skippedMaskedCount: number;
  reloadTriggered: boolean;
}
