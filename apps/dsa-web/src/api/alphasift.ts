import { z } from 'zod';
import { parseCamelCasePayload } from './parseCamelCasePayload';
import type { components } from '../types/api.generated';
import apiClient from './index';
import { systemConfigApi } from './systemConfig';



type OpenApiAlphaSiftStatus = components['schemas']['AlphaSiftStatusResponse'];
type OpenApiAlphaSiftScreen = components['schemas']['AlphaSiftScreenResponse'];
type OpenApiAlphaSiftHotspots = components['schemas']['AlphaSiftHotspotsResponse'];
type OpenApiAlphaSiftStrategies = components['schemas']['AlphaSiftStrategiesResponse'];
type _AssertStatus = keyof OpenApiAlphaSiftStatus;
type _AssertScreen = keyof OpenApiAlphaSiftScreen;
type _AssertHotspots = keyof OpenApiAlphaSiftHotspots;
type _AssertStrategies = keyof OpenApiAlphaSiftStrategies;
const _statusAnchor: _AssertStatus = 'install_spec_is_default';
const _screenAnchor: _AssertScreen = 'candidate_count';
const _hotspotsAnchor: _AssertHotspots = 'hotspot_count';
const _strategiesAnchor: _AssertStrategies = 'strategy_count';
void _statusAnchor;
void _screenAnchor;
void _hotspotsAnchor;
void _strategiesAnchor;

const alphaSiftStatusSchema = z.object({
  available: z.boolean(),
  contractVersion: z.string().nullable().optional(),
  diagnostics: z.record(z.string(), z.unknown()).nullable().optional(),
  enabled: z.boolean(),
  installSpecIsDefault: z.boolean(),
  sourceHealth: z.record(z.string(), z.unknown()).nullable().optional(),
  strategyCount: z.number().nullable().optional(),
  version: z.string().nullable().optional(),
}).passthrough();

const alphaSiftInstallResponseSchema = z.object({
  alreadyInstalled: z.boolean(),
  installSpecIsDefault: z.boolean(),
  installed: z.boolean(),
}).passthrough();

const alphaSiftStrategiesResponseSchema = z.object({
  enabled: z.boolean(),
  strategies: z.array(z.record(z.string(), z.unknown())).optional(),
  strategyCount: z.number(),
}).passthrough();

const alphaSiftScreenResponseSchema = z.object({
  afterFilterCount: z.number().nullable().optional(),
  candidateCount: z.number(),
  candidates: z.array(z.record(z.string(), z.unknown())).optional(),
  dailyEnrichCount: z.number().nullable().optional(),
  dailyEnriched: z.boolean().nullable().optional(),
  deepAnalysisRequested: z.boolean().nullable().optional(),
  dsaEnrichment: z.record(z.string(), z.unknown()).nullable().optional(),
  enabled: z.boolean(),
  llmCoverage: z.number().nullable().optional(),
  llmMarketView: z.string().nullable().optional(),
  llmParseErrors: z.array(z.string()).optional(),
  llmPortfolioRisk: z.string().nullable().optional(),
  llmRanked: z.boolean().nullable().optional(),
  llmSelectionLogic: z.string().nullable().optional(),
  market: z.string().nullable().optional(),
  portfolioConcentrationNotes: z.array(z.string()).optional(),
  portfolioDiversityEnabled: z.boolean().nullable().optional(),
  postAnalyzers: z.array(z.string()).optional(),
  riskEnabled: z.boolean().nullable().optional(),
  runId: z.string().nullable().optional(),
  snapshotCount: z.number().nullable().optional(),
  snapshotSource: z.string().nullable().optional(),
  sourceErrors: z.array(z.string()).optional(),
  strategy: z.string().nullable().optional(),
  warnings: z.array(z.string()).optional(),
}).passthrough();

const alphaSiftScreenAcceptedSchema = z.object({
  market: z.string(),
  maxResults: z.number(),
  message: z.string(),
  messageCode: z.string().optional(),
  messageParams: z.record(z.string(), z.unknown()).optional(),
  status: z.string().optional(),
  strategy: z.string(),
  taskId: z.string(),
  traceId: z.string(),
}).passthrough();

const alphaSiftScreenTaskStatusSchema = z.object({
  error: z.string().nullable().optional(),
  message: z.string().nullable().optional(),
  messageCode: z.string().optional(),
  messageParams: z.record(z.string(), z.unknown()).optional(),
  progress: z.number().optional(),
  result: z.record(z.string(), z.unknown()).nullable().optional(),
  status: z.string(),
  taskId: z.string(),
  traceId: z.string().nullable().optional(),
}).passthrough();

const alphaSiftHotspotsResponseSchema = z.object({
  cacheUsed: z.boolean().nullable().optional(),
  cachedAt: z.string().nullable().optional(),
  details: z.record(z.string(), z.unknown()).nullable().optional(),
  enabled: z.boolean(),
  fallbackUsed: z.boolean().nullable().optional(),
  hotspotCount: z.number(),
  hotspots: z.array(z.record(z.string(), z.unknown())).optional(),
  message: z.string().nullable().optional(),
  provider: z.string(),
  providerUsed: z.string().nullable().optional(),
  sourceErrors: z.array(z.string()).nullable().optional(),
  stale: z.boolean().nullable().optional(),
  staleAgeHours: z.number().nullable().optional(),
}).passthrough();

const alphaSiftHotspotDetailSchema = z.object({
  aliases: z.array(z.string()).nullable().optional(),
  cacheUsed: z.boolean().nullable().optional(),
  cachedAt: z.string().nullable().optional(),
  canonicalTopic: z.string().nullable().optional(),
  enabled: z.boolean(),
  fallbackUsed: z.boolean().nullable().optional(),
  leaderStocks: z.array(z.record(z.string(), z.unknown())).nullable().optional(),
  missingFields: z.array(z.string()).nullable().optional(),
  name: z.string().nullable().optional(),
  provider: z.string(),
  qualityStatus: z.string().nullable().optional(),
  resolverCandidates: z.array(z.unknown()).nullable().optional(),
  route: z.array(z.record(z.string(), z.unknown())).optional(),
  sourceErrors: z.array(z.string()).nullable().optional(),
  stale: z.boolean().nullable().optional(),
  staleAgeHours: z.number().nullable().optional(),
  stockCount: z.number(),
  stocks: z.array(z.record(z.string(), z.unknown())),
  summary: z.unknown().nullable().optional(),
  summaryDetail: z.record(z.string(), z.unknown()).nullable().optional(),
  timeline: z.array(z.record(z.string(), z.unknown())).nullable().optional(),
  topic: z.string(),
}).passthrough();
const ALPHASIFT_SCREEN_TIMEOUT_MS = 180000;
const ALPHASIFT_INSTALL_TIMEOUT_MS = 300000;
const REPRODUCIBLE_SOURCE_INSTALL_GUIDANCE = [
  'python -m pip install --upgrade --constraint constraints.txt pip',
  'python -m pip install --build-constraint build-constraints.txt -r requirements.txt',
  'python -m pip check',
].join('\n');
export const ALPHASIFT_CONFIG_CHANGED_EVENT = 'alphasift-config-changed';
export const SYSTEM_CONFIG_CHANGED_EVENT = 'dsa-system-config-changed';

export type AlphaSiftStatus = {
  enabled: boolean;
  available: boolean;
  installSpecIsDefault: boolean;
  contractVersion?: string | null;
  version?: string | null;
  strategyCount?: number | null;
  sourceHealth?: Record<string, Record<string, Record<string, unknown>>>;
  diagnostics?: Record<string, string>;
};

export type AlphaSiftInstallResponse = {
  installed: boolean;
  alreadyInstalled: boolean;
  installSpecIsDefault: boolean;
};

export type AlphaSiftCandidate = {
  rank: number;
  code: string;
  name: string;
  score?: number | null;
  screenScore?: number | null;
  reason: string;
  riskLevel?: string;
  riskFlags?: string[];
  llmScore?: number | null;
  llmConfidence?: number | null;
  llmSector?: string;
  llmTheme?: string;
  llmTags?: string[];
  llmThesis?: string;
  llmCatalysts?: string[];
  llmRisks?: string[];
  llmWatchItems?: string[];
  llmInvalidators?: string[];
  llmStyleFit?: string;
  price?: number | null;
  changePct?: number | null;
  amount?: number | null;
  industry?: string;
  factorScores?: Record<string, number>;
  postAnalysisSummaries?: Record<string, string>;
  postAnalysisTags?: string[];
  dsaContext?: {
    enriched?: boolean;
    quote?: Record<string, unknown>;
    fundamentals?: Record<string, unknown>;
    news?: {
      success?: boolean;
      query?: string;
      provider?: string;
      results?: Array<Record<string, unknown>>;
      error?: string | null;
    };
    warnings?: string[];
  };
  dsaNews?: Array<{
    title?: string;
    snippet?: string;
    url?: string;
    source?: string;
    publishedDate?: string | null;
  }>;
  dsaAnalysisSummary?: string;
  raw: Record<string, unknown>;
};

export type AlphaSiftStrategy = {
  id: string;
  name: string;
  nameZh?: string;
  nameEn?: string;
  title?: string;
  titleZh?: string;
  titleEn?: string;
  description: string;
  descriptionZh?: string;
  descriptionEn?: string;
  version?: string;
  category?: string;
  categoryZh?: string;
  categoryEn?: string;
  tag?: string;
  tags?: string[];
  marketScope?: string[];
  market?: string;
};

export type AlphaSiftStrategiesResponse = {
  enabled: boolean;
  strategies: AlphaSiftStrategy[];
  strategyCount: number;
};

export type AlphaSiftHotspot = {
  topic: string;
  name?: string;
  source?: string;
  rank?: number | null;
  changePct?: number | null;
  heatScore?: number | null;
  trendScore?: number | null;
  persistenceScore?: number | null;
  coolingScore?: number | null;
  observations?: number | null;
  state?: string;
  stage?: string;
  sampleStockCount?: number | null;
  leaders?: string[];
  providerUsed?: string;
  fallbackUsed?: boolean;
  cacheUsed?: boolean;
  cachedAt?: string | null;
  sourceErrors?: string[];
  stale?: boolean;
  staleAgeHours?: number | null;
};

export type AlphaSiftHotspotRouteItem = {
  title: string;
  description: string;
  source?: string;
  date?: string;
  time?: string;
  publishedAt?: string;
  url?: string;
};

export type AlphaSiftHotspotStock = {
  code?: string;
  name?: string;
  changePct?: number | null;
  amount?: number | null;
  turnoverRate?: number | null;
  volumeRatio?: number | null;
  role?: string;
  hotStockScore?: number | null;
  source?: string;
  sourceConfidence?: number | null;
  fallbackUsed?: boolean;
};

export type AlphaSiftHotspotDetail = {
  enabled: boolean;
  provider: string;
  topic: string;
  name?: string;
  canonicalTopic?: string;
  aliases?: string[];
  summary?: string;
  summaryDetail?: Record<string, unknown>;
  route: AlphaSiftHotspotRouteItem[];
  timeline?: AlphaSiftHotspotRouteItem[];
  stocks: AlphaSiftHotspotStock[];
  leaderStocks?: AlphaSiftHotspotStock[];
  stockCount: number;
  sourceErrors?: string[];
  qualityStatus?: 'available' | 'partial' | 'stale' | 'failed' | string;
  missingFields?: string[];
  fallbackUsed?: boolean;
  stale?: boolean;
  staleAgeHours?: number | null;
  cacheUsed?: boolean;
  cachedAt?: string | null;
  resolverCandidates?: Record<string, unknown>[];
};

export type AlphaSiftHotspotsResponse = {
  enabled: boolean;
  provider: string;
  providerUsed?: string;
  fallbackUsed?: boolean;
  cacheUsed?: boolean;
  cachedAt?: string | null;
  sourceErrors?: string[];
  stale?: boolean;
  staleAgeHours?: number | null;
  message?: string | null;
  hotspots: AlphaSiftHotspot[];
  hotspotCount: number;
  details?: Record<string, AlphaSiftHotspotDetail>;
};

export type AlphaSiftScreenResponse = {
  enabled: boolean;
  candidates: AlphaSiftCandidate[];
  candidateCount: number;
  runId?: string;
  strategy?: string;
  market?: string;
  snapshotCount?: number;
  snapshotSource?: string | null;
  afterFilterCount?: number;
  llmRanked?: boolean;
  llmMarketView?: string;
  llmSelectionLogic?: string;
  llmPortfolioRisk?: string;
  llmCoverage?: number | null;
  llmParseErrors?: string[];
  warnings?: string[];
  sourceErrors?: string[];
  dsaEnrichment?: {
    enabled?: boolean;
    maxCandidates?: number;
    requestedCount?: number;
    enrichedCount?: number;
    warnings?: string[];
  };
  deepAnalysisRequested?: boolean | null;
  postAnalyzers?: string[];
  dailyEnriched?: boolean | null;
  dailyEnrichCount?: number | null;
  riskEnabled?: boolean | null;
  portfolioDiversityEnabled?: boolean | null;
  portfolioConcentrationNotes?: string[];
};

export type AlphaSiftScreenAccepted = {
  taskId: string;
  traceId?: string | null;
  status: 'pending' | 'processing' | 'completed' | 'failed' | string;
  message: string;
  messageCode?: string;
  messageParams?: Record<string, unknown>;
  strategy: string;
  market: string;
  maxResults: number;
};

export type AlphaSiftScreenTaskStatus = {
  taskId: string;
  traceId?: string | null;
  status: 'pending' | 'processing' | 'completed' | 'failed' | string;
  progress?: number | null;
  message?: string | null;
  messageCode?: string | null;
  messageParams?: Record<string, unknown> | null;
  error?: string | null;
  result?: AlphaSiftScreenResponse | null;
};

export function notifyAlphaSiftConfigChanged(): void {
  window.dispatchEvent(new Event(ALPHASIFT_CONFIG_CHANGED_EVENT));
  notifySystemConfigChanged();
}

export function notifySystemConfigChanged(): void {
  window.dispatchEvent(new Event(SYSTEM_CONFIG_CHANGED_EVENT));
}

async function setAlphaSiftEnabled(value: 'true' | 'false'): Promise<void> {
  const config = await systemConfigApi.getConfig(false);
  await systemConfigApi.update({
    configVersion: config.configVersion,
    maskToken: config.maskToken,
    reloadNow: true,
    items: [{ key: 'ALPHASIFT_ENABLED', value }],
  });
  notifyAlphaSiftConfigChanged();
}

export const alphasiftApi = {
  async getStatus(): Promise<AlphaSiftStatus> {
    const response = await apiClient.get<Record<string, unknown>>('/api/v1/alphasift/status');
    return parseCamelCasePayload<AlphaSiftStatus>(
      response.data,
      alphaSiftStatusSchema,
      'AlphaSiftStatusResponse',
      'alphasift',
    );
  },

  async screen(payload: { market: string; strategy: string; maxResults: number }): Promise<AlphaSiftScreenResponse> {
    const response = await apiClient.post<Record<string, unknown>>('/api/v1/alphasift/screen', {
      market: payload.market,
      strategy: payload.strategy,
      max_results: payload.maxResults,
    }, { timeout: ALPHASIFT_SCREEN_TIMEOUT_MS });
    const parsed = parseCamelCasePayload<AlphaSiftScreenResponse>(
      response.data,
      alphaSiftScreenResponseSchema,
      'AlphaSiftScreenResponse',
      'alphasift',
    );
    if (!Array.isArray(parsed.candidates)) {
      return { ...parsed, candidates: [] };
    }
    return parsed;
  },

  async startScreen(payload: { market: string; strategy: string; maxResults: number }): Promise<AlphaSiftScreenAccepted> {
    const response = await apiClient.post<Record<string, unknown>>('/api/v1/alphasift/screen/tasks', {
      market: payload.market,
      strategy: payload.strategy,
      max_results: payload.maxResults,
    });
    return parseCamelCasePayload<AlphaSiftScreenAccepted>(
      response.data,
      alphaSiftScreenAcceptedSchema,
      'AlphaSiftScreenAccepted',
      'alphasift',
    );
  },

  async getScreenTask(taskId: string): Promise<AlphaSiftScreenTaskStatus> {
    const response = await apiClient.get<Record<string, unknown>>(`/api/v1/alphasift/screen/tasks/${encodeURIComponent(taskId)}`);
    const parsed = parseCamelCasePayload<AlphaSiftScreenTaskStatus>(
      response.data,
      alphaSiftScreenTaskStatusSchema,
      'AlphaSiftScreenTaskStatus',
      'alphasift',
    );
    if (parsed.result && !Array.isArray(parsed.result.candidates)) {
      parsed.result = { ...parsed.result, candidates: [] };
    }
    return parsed;
  },

  async getStrategies(): Promise<AlphaSiftStrategiesResponse> {
    const response = await apiClient.get<Record<string, unknown>>('/api/v1/alphasift/strategies', { timeout: ALPHASIFT_INSTALL_TIMEOUT_MS });
    const parsed = parseCamelCasePayload<AlphaSiftStrategiesResponse>(
      response.data,
      alphaSiftStrategiesResponseSchema,
      'AlphaSiftStrategiesResponse',
      'alphasift',
    );
    if (!Array.isArray(parsed.strategies)) {
      return { ...parsed, strategies: [] };
    }
    return parsed;
  },

  async getHotspots(payload: { provider?: string; top?: number; refresh?: boolean; includeDetails?: boolean } = {}): Promise<AlphaSiftHotspotsResponse> {
    const response = await apiClient.get<Record<string, unknown>>('/api/v1/alphasift/hotspots', {
      params: {
        provider: payload.provider || 'akshare',
        top: payload.top ?? 12,
        refresh: payload.refresh ?? false,
        include_details: payload.includeDetails ?? true,
      },
      timeout: ALPHASIFT_INSTALL_TIMEOUT_MS,
    });
    const normalized = parseCamelCasePayload<AlphaSiftHotspotsResponse>(
      response.data,
      alphaSiftHotspotsResponseSchema,
      'AlphaSiftHotspotsResponse',
      'alphasift',
    );
    if (!Array.isArray(normalized.hotspots)) {
      normalized.hotspots = [];
    }
    if (normalized.details) {
      const detailsByTopic: Record<string, AlphaSiftHotspotDetail> = {};
      Object.values(normalized.details).forEach((detail) => {
        if (detail?.topic) {
          detailsByTopic[detail.topic] = detail;
        }
      });
      normalized.details = { ...normalized.details, ...detailsByTopic };
    }
    return normalized;
  },

  async getHotspotDetail(payload: { topic: string; provider?: string; refresh?: boolean }): Promise<AlphaSiftHotspotDetail> {
    const response = await apiClient.get<Record<string, unknown>>(
      `/api/v1/alphasift/hotspots/${encodeURIComponent(payload.topic)}`,
      {
        params: { provider: payload.provider || 'akshare', refresh: payload.refresh ?? false },
        timeout: ALPHASIFT_INSTALL_TIMEOUT_MS,
      },
    );
    const detail = parseCamelCasePayload<AlphaSiftHotspotDetail>(
      response.data,
      alphaSiftHotspotDetailSchema,
      'AlphaSiftHotspotDetailResponse',
      'alphasift',
    );
    if (!Array.isArray(detail.route)) {
      return { ...detail, route: [] };
    }
    return detail;
  },

  async install(): Promise<AlphaSiftInstallResponse> {
    const response = await apiClient.post<Record<string, unknown>>('/api/v1/alphasift/install', {}, { timeout: ALPHASIFT_INSTALL_TIMEOUT_MS });
    return parseCamelCasePayload<AlphaSiftInstallResponse>(
      response.data,
      alphaSiftInstallResponseSchema,
      'AlphaSiftInstallResponse',
      'alphasift',
    );
  },

  async enable(): Promise<void> {
    await setAlphaSiftEnabled('true');
    try {
      const status = await alphasiftApi.getStatus();
      if (!status.available) {
        const reason = status.diagnostics?.reason ? `（${status.diagnostics.reason}）` : '';
        throw new Error(
          `AlphaSift 适配层不可用${reason}。请在仓库根目录运行受约束的安装流程：\n${REPRODUCIBLE_SOURCE_INSTALL_GUIDANCE}\n或重建 Docker/桌面后端。`,
        );
      }
    } catch (error) {
      try {
        await setAlphaSiftEnabled('false');
      } catch {
        // Preserve the original install/status failure for the caller.
      }
      throw error;
    }
  },
};
