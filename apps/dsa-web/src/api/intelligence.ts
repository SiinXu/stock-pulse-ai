// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { z } from 'zod';
import { parseCamelCasePayload } from './parseCamelCasePayload';
import type { components } from '../types/api.generated';
import apiClient from './index';



type OpenApiIntelligenceSourceItem = components['schemas']['IntelligenceSourceItem'];
type OpenApiIntelligenceSourceListResponse = components['schemas']['IntelligenceSourceListResponse'];
type OpenApiIntelligenceFetchResponse = components['schemas']['IntelligenceFetchResponse'];
type _AssertSource = keyof OpenApiIntelligenceSourceItem;
type _AssertSourceList = keyof OpenApiIntelligenceSourceListResponse;
type _AssertFetch = keyof OpenApiIntelligenceFetchResponse;
const _sourceAnchor: _AssertSource = 'source_type';
const _sourceListAnchor: _AssertSourceList = 'page_size';
const _fetchAnchor: _AssertFetch = 'ok';
void _sourceAnchor;
void _sourceListAnchor;
void _fetchAnchor;

const intelligenceSourceSchema = z.object({
  createdAt: z.string().nullable().optional(),
  description: z.string().nullable().optional(),
  enabled: z.boolean(),
  id: z.number(),
  lastError: z.string().nullable().optional(),
  lastFetchedAt: z.string().nullable().optional(),
  lastStatus: z.string().nullable().optional(),
  market: z.string(),
  name: z.string(),
  scopeType: z.string(),
  scopeValue: z.string().nullable().optional(),
  sourceType: z.string(),
  updatedAt: z.string().nullable().optional(),
  url: z.string(),
}).passthrough();

const intelligenceSourceListResponseSchema = z.object({
  items: z.array(z.record(z.string(), z.unknown())).optional(),
  page: z.number(),
  pageSize: z.number(),
  total: z.number(),
}).passthrough();

const intelligenceSourceTemplateListResponseSchema = z.object({
  items: z.array(z.record(z.string(), z.unknown())).optional(),
  total: z.number(),
}).passthrough();

const intelligenceItemListResponseSchema = z.object({
  items: z.array(z.record(z.string(), z.unknown())).optional(),
  page: z.number(),
  pageSize: z.number(),
  total: z.number(),
}).passthrough();

const intelligenceDefaultSourceCreateResponseSchema = z.object({
  createdCount: z.number(),
  items: z.array(z.record(z.string(), z.unknown())).optional(),
  total: z.number(),
}).passthrough();

const intelligenceFetchResponseSchema = z.object({
  dryRun: z.boolean().nullable().optional(),
  error: z.string().nullable().optional(),
  fetchedCount: z.number().nullable().optional(),
  ok: z.boolean(),
  results: z.array(z.unknown()).nullable().optional(),
  retentionDeleted: z.number().nullable().optional(),
  sampleItems: z.array(z.record(z.string(), z.unknown())).optional(),
  savedCount: z.number().nullable().optional(),
  sourceCount: z.number().nullable().optional(),
  sourceId: z.number().nullable().optional(),
}).passthrough();

const intelligenceSourceTestResponseSchema = z.object({
  fetchedCount: z.number(),
  ok: z.boolean(),
  sampleItems: z.array(z.record(z.string(), z.unknown())).optional(),
  source: z.record(z.string(), z.unknown()),
}).passthrough();
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
    const parsed = parseCamelCasePayload<IntelligenceSourceListResponse>(
      response.data,
      intelligenceSourceListResponseSchema,
      'IntelligenceSourceListResponse',
      'intelligence',
    );
    if (!Array.isArray(parsed.items)) {
      return { ...parsed, items: [] };
    }
    return parsed;
  },

  async createSource(request: IntelligenceSourceCreateRequest): Promise<IntelligenceSource> {
    const response = await apiClient.post<Record<string, unknown>>(
      `${BASE}/sources`,
      toSourcePayload(request),
    );
    return parseCamelCasePayload<IntelligenceSource>(
      response.data,
      intelligenceSourceSchema,
      'IntelligenceSourceItem',
      'intelligence',
    );
  },

  async listTemplates(): Promise<IntelligenceSourceTemplateListResponse> {
    const response = await apiClient.get<Record<string, unknown>>(`${BASE}/sources/templates`);
    const parsed = parseCamelCasePayload<IntelligenceSourceTemplateListResponse>(
      response.data,
      intelligenceSourceTemplateListResponseSchema,
      'IntelligenceSourceTemplateListResponse',
      'intelligence',
    );
    if (!Array.isArray(parsed.items)) {
      return { ...parsed, items: [] };
    }
    return parsed;
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
    return parseCamelCasePayload<IntelligenceSource>(
      response.data,
      intelligenceSourceSchema,
      'IntelligenceSourceItem',
      'intelligence',
    );
  },

  async createDefaultSources(enabled?: boolean): Promise<IntelligenceDefaultSourceCreateResponse> {
    const response = await apiClient.post<Record<string, unknown>>(
      `${BASE}/sources/defaults`,
      { enabled },
    );
    const parsed = parseCamelCasePayload<IntelligenceDefaultSourceCreateResponse>(
      response.data,
      intelligenceDefaultSourceCreateResponseSchema,
      'IntelligenceDefaultSourceCreateResponse',
      'intelligence',
    );
    if (!Array.isArray(parsed.items)) {
      return { ...parsed, items: [] };
    }
    return parsed;
  },

  async testSource(request: IntelligenceSourceCreateRequest): Promise<IntelligenceSourceTestResponse> {
    const response = await apiClient.post<Record<string, unknown>>(
      `${BASE}/sources/test`,
      toSourcePayload(request),
    );
    const parsed = parseCamelCasePayload<IntelligenceSourceTestResponse>(
      response.data,
      intelligenceSourceTestResponseSchema,
      'IntelligenceSourceTestResponse',
      'intelligence',
    );
    if (!Array.isArray(parsed.sampleItems)) {
      return { ...parsed, sampleItems: [] };
    }
    return parsed;
  },

  async fetchSource(sourceId: number, dryRun = false): Promise<IntelligenceFetchResponse> {
    const response = await apiClient.post<Record<string, unknown>>(
      `${BASE}/sources/${sourceId}/fetch`,
      null,
      { params: { dry_run: dryRun } },
    );
    const parsed = parseCamelCasePayload<IntelligenceFetchResponse>(
      response.data,
      intelligenceFetchResponseSchema,
      'IntelligenceFetchResponse',
      'intelligence',
    );
    if (!Array.isArray(parsed.sampleItems)) {
      return { ...parsed, sampleItems: [] };
    }
    return parsed;
  },

  async fetchEnabledSources(): Promise<IntelligenceFetchResponse> {
    const response = await apiClient.post<Record<string, unknown>>(`${BASE}/sources/fetch-enabled`);
    const parsed = parseCamelCasePayload<IntelligenceFetchResponse>(
      response.data,
      intelligenceFetchResponseSchema,
      'IntelligenceFetchResponse',
      'intelligence',
    );
    if (!Array.isArray(parsed.sampleItems)) {
      return { ...parsed, sampleItems: [] };
    }
    return parsed;
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
    const parsed = parseCamelCasePayload<IntelligenceItemListResponse>(
      response.data,
      intelligenceItemListResponseSchema,
      'IntelligenceItemListResponse',
      'intelligence',
    );
    if (!Array.isArray(parsed.items)) {
      return { ...parsed, items: [] };
    }
    return parsed;
  },
};
