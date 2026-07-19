// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import apiClient from './index';
import { toCamelCase } from './utils';

const BASE = '/api/v1/intelligence';

export interface IntelligenceSource {
  id: number;
  name: string;
  sourceType: string;
  url: string;
  enabled: boolean;
  scopeType: string;
  scopeValue?: string | null;
  market: string;
  description?: string | null;
  lastStatus?: string | null;
  lastError?: string | null;
  lastFetchedAt?: string | null;
  createdAt?: string | null;
  updatedAt?: string | null;
}

export interface IntelligenceSourceTemplate {
  templateId: string;
  name: string;
  sourceType: string;
  url: string;
  scopeType: string;
  scopeValue?: string | null;
  market: string;
  description?: string | null;
}

export interface IntelligenceItem {
  id: number;
  sourceId?: number | null;
  sourceName?: string | null;
  sourceType: string;
  title: string;
  summary?: string | null;
  url: string;
  source?: string | null;
  publishedAt?: string | null;
  fetchedAt?: string | null;
  scopeType: string;
  scopeValue?: string | null;
  market: string;
}

export interface IntelligenceSampleItem {
  title: string;
  summary?: string | null;
  url: string;
  source?: string | null;
  publishedAt?: string | null;
}

export interface IntelligenceSourceListResponse {
  items: IntelligenceSource[];
  total: number;
  page: number;
  pageSize: number;
}

export interface IntelligenceSourceTemplateListResponse {
  items: IntelligenceSourceTemplate[];
  total: number;
}

export interface IntelligenceItemListResponse {
  items: IntelligenceItem[];
  total: number;
  page: number;
  pageSize: number;
}

export interface IntelligenceDefaultSourceResult {
  created: boolean;
  source: IntelligenceSource;
}

export interface IntelligenceDefaultSourceCreateResponse {
  items: IntelligenceDefaultSourceResult[];
  createdCount: number;
  total: number;
}

export interface IntelligenceFetchResponse {
  ok: boolean;
  sourceId?: number | null;
  sourceCount?: number | null;
  fetchedCount?: number | null;
  savedCount?: number | null;
  retentionDeleted?: number | null;
  dryRun?: boolean | null;
  sampleItems: IntelligenceSampleItem[];
  results?: Array<Record<string, unknown>> | null;
  error?: string | null;
}

export interface IntelligenceSourceTestResponse {
  ok: boolean;
  source: Record<string, unknown>;
  fetchedCount: number;
  sampleItems: IntelligenceSampleItem[];
}

export interface IntelligenceSourceCreateRequest {
  name: string;
  url: string;
  sourceType?: string;
  enabled?: boolean;
  scopeType?: string;
  scopeValue?: string | null;
  market?: string;
  description?: string | null;
}

export interface IntelligenceSourceTemplateCreateRequest {
  name?: string;
  enabled?: boolean;
  scopeType?: string;
  scopeValue?: string | null;
  market?: string;
  description?: string | null;
}

export interface ListSourcesParams {
  enabled?: boolean;
  sourceType?: string;
  scopeType?: string;
  market?: string;
  page?: number;
  pageSize?: number;
}

export interface ListItemsParams {
  sourceId?: number;
  scopeType?: string;
  market?: string;
  page?: number;
  pageSize?: number;
}

function toSourcePayload(
  request: IntelligenceSourceCreateRequest,
): Record<string, unknown> {
  return {
    name: request.name,
    url: request.url,
    source_type: request.sourceType,
    enabled: request.enabled,
    scope_type: request.scopeType,
    scope_value: request.scopeValue,
    market: request.market,
    description: request.description,
  };
}

/**
 * Typed client for the read/create/test/fetch surface the backend exposes at
 * `/api/v1/intelligence`. It deliberately omits update/delete/enable/disable,
 * which the backend does not implement.
 */
export const intelligenceApi = {
  async listSources(params: ListSourcesParams = {}): Promise<IntelligenceSourceListResponse> {
    const response = await apiClient.get<Record<string, unknown>>(`${BASE}/sources`, {
      params: {
        enabled: params.enabled,
        source_type: params.sourceType,
        scope_type: params.scopeType,
        market: params.market,
        page: params.page,
        page_size: params.pageSize,
      },
    });
    return toCamelCase<IntelligenceSourceListResponse>(response.data);
  },

  async createSource(request: IntelligenceSourceCreateRequest): Promise<IntelligenceSource> {
    const response = await apiClient.post<Record<string, unknown>>(
      `${BASE}/sources`,
      toSourcePayload(request),
    );
    return toCamelCase<IntelligenceSource>(response.data);
  },

  async listTemplates(): Promise<IntelligenceSourceTemplateListResponse> {
    const response = await apiClient.get<Record<string, unknown>>(`${BASE}/sources/templates`);
    return toCamelCase<IntelligenceSourceTemplateListResponse>(response.data);
  },

  async createSourceFromTemplate(
    templateId: string,
    request: IntelligenceSourceTemplateCreateRequest = {},
  ): Promise<IntelligenceSource> {
    const response = await apiClient.post<Record<string, unknown>>(
      `${BASE}/sources/templates/${encodeURIComponent(templateId)}`,
      {
        name: request.name,
        enabled: request.enabled,
        scope_type: request.scopeType,
        scope_value: request.scopeValue,
        market: request.market,
        description: request.description,
      },
    );
    return toCamelCase<IntelligenceSource>(response.data);
  },

  async createDefaultSources(enabled?: boolean): Promise<IntelligenceDefaultSourceCreateResponse> {
    const response = await apiClient.post<Record<string, unknown>>(
      `${BASE}/sources/defaults`,
      { enabled },
    );
    return toCamelCase<IntelligenceDefaultSourceCreateResponse>(response.data);
  },

  async testSource(request: IntelligenceSourceCreateRequest): Promise<IntelligenceSourceTestResponse> {
    const response = await apiClient.post<Record<string, unknown>>(
      `${BASE}/sources/test`,
      toSourcePayload(request),
    );
    return toCamelCase<IntelligenceSourceTestResponse>(response.data);
  },

  async fetchSource(sourceId: number, dryRun = false): Promise<IntelligenceFetchResponse> {
    const response = await apiClient.post<Record<string, unknown>>(
      `${BASE}/sources/${sourceId}/fetch`,
      null,
      { params: { dry_run: dryRun } },
    );
    return toCamelCase<IntelligenceFetchResponse>(response.data);
  },

  async fetchEnabledSources(): Promise<IntelligenceFetchResponse> {
    const response = await apiClient.post<Record<string, unknown>>(`${BASE}/sources/fetch-enabled`);
    return toCamelCase<IntelligenceFetchResponse>(response.data);
  },

  async listItems(params: ListItemsParams = {}): Promise<IntelligenceItemListResponse> {
    const response = await apiClient.get<Record<string, unknown>>(`${BASE}/items`, {
      params: {
        source_id: params.sourceId,
        scope_type: params.scopeType,
        market: params.market,
        page: params.page,
        page_size: params.pageSize,
      },
    });
    return toCamelCase<IntelligenceItemListResponse>(response.data);
  },
};
