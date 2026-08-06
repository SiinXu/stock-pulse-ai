// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { z } from 'zod';
import type { components } from '../types/api.generated';
import apiClient from './index';
import { createApiError, createParsedApiError } from './error';
import { toCamelCase } from './utils';

/** OpenAPI anchors — fail typecheck if PLUG-01 renames schema fields. */
type OpenApiPluginInfo = components['schemas']['PluginInfo'];
type OpenApiPluginListResponse = components['schemas']['PluginListResponse'];
type OpenApiPluginLifecycleRequest = components['schemas']['PluginLifecycleRequest'];
type OpenApiPluginLifecycleResponse = components['schemas']['PluginLifecycleResponse'];

type _AssertInfo = keyof OpenApiPluginInfo;
type _AssertList = keyof OpenApiPluginListResponse;
type _AssertRequest = keyof OpenApiPluginLifecycleRequest;
type _AssertResponse = keyof OpenApiPluginLifecycleResponse;

const _infoAnchor: _AssertInfo = 'desired_enabled';
const _listAnchor: _AssertList = 'total';
const _requestAnchor: _AssertRequest = 'action';
const _responseAnchor: _AssertResponse = 'restart_required';
void _infoAnchor;
void _listAnchor;
void _requestAnchor;
void _responseAnchor;

export type PluginLifecycleAction = OpenApiPluginLifecycleRequest['action'];
export type PluginLifecycleState = OpenApiPluginInfo['state'];
export type PluginSource = OpenApiPluginInfo['source'];

/** CamelCase view of PluginInfo after API boundary parsing. */
export type PluginInfo = {
  id: string;
  name: string;
  version: string;
  source: PluginSource;
  state: PluginLifecycleState;
  desiredEnabled: boolean;
  reloadable: boolean;
  packageRoot?: string | null;
  extensionPoints: string[];
  description: string;
  author: string;
};

export type PluginListResponse = {
  items: PluginInfo[];
  total: number;
};

export type PluginLifecycleResponse = {
  pluginId: string;
  action: PluginLifecycleAction;
  success: boolean;
  state: PluginLifecycleState;
  reloaded: boolean;
  restartRequired: boolean;
  errorCode?: string | null;
  message?: string | null;
  plugin?: PluginInfo | null;
};

const pluginInfoSchema = z.object({
  id: z.string(),
  name: z.string(),
  version: z.string(),
  source: z.enum(['builtin', 'external']),
  state: z.enum(['registered', 'enabled', 'disabled', 'failed']),
  desiredEnabled: z.boolean(),
  reloadable: z.boolean(),
  packageRoot: z.string().nullable().optional(),
  extensionPoints: z.array(z.string()).optional(),
  description: z.string().optional(),
  author: z.string().optional(),
}).passthrough();

const pluginListResponseSchema = z.object({
  items: z.array(pluginInfoSchema).optional(),
  total: z.number(),
}).passthrough();

const pluginLifecycleResponseSchema = z.object({
  pluginId: z.string(),
  action: z.enum(['enable', 'disable', 'reload']),
  success: z.boolean(),
  state: z.enum(['registered', 'enabled', 'disabled', 'failed']),
  reloaded: z.boolean().optional(),
  restartRequired: z.boolean().optional(),
  errorCode: z.string().nullable().optional(),
  message: z.string().nullable().optional(),
  plugin: pluginInfoSchema.nullable().optional(),
}).passthrough();

function parseCamelCasePayload<T>(data: unknown, schema: z.ZodTypeAny, label: string): T {
  const camel = toCamelCase<unknown>(data);
  const result = schema.safeParse(camel);
  if (!result.success) {
    const issueSummary = result.error.issues
      .slice(0, 5)
      .map((issue) => `${issue.path.join('.') || '(root)'}: ${issue.message}`)
      .join('; ');
    if (import.meta.env.DEV) {
      console.error(`[plugins] response validation failed (${label})`, result.error.issues);
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

function normalizePluginInfo(raw: z.infer<typeof pluginInfoSchema>): PluginInfo {
  return {
    id: raw.id,
    name: raw.name,
    version: raw.version,
    source: raw.source,
    state: raw.state,
    desiredEnabled: raw.desiredEnabled,
    reloadable: raw.reloadable,
    packageRoot: raw.packageRoot ?? null,
    extensionPoints: raw.extensionPoints ?? [],
    description: raw.description ?? '',
    author: raw.author ?? '',
  };
}

function normalizeList(raw: z.infer<typeof pluginListResponseSchema>): PluginListResponse {
  const items = (raw.items ?? []).map(normalizePluginInfo);
  return { items, total: raw.total };
}

function normalizeLifecycle(
  raw: z.infer<typeof pluginLifecycleResponseSchema>,
): PluginLifecycleResponse {
  return {
    pluginId: raw.pluginId,
    action: raw.action,
    success: raw.success,
    state: raw.state,
    reloaded: raw.reloaded ?? false,
    restartRequired: raw.restartRequired ?? false,
    errorCode: raw.errorCode ?? null,
    message: raw.message ?? null,
    plugin: raw.plugin ? normalizePluginInfo(raw.plugin) : null,
  };
}

export const pluginsApi = {
  async list(): Promise<PluginListResponse> {
    const response = await apiClient.get<Record<string, unknown>>('/api/v1/plugins');
    const parsed = parseCamelCasePayload<z.infer<typeof pluginListResponseSchema>>(
      response.data,
      pluginListResponseSchema,
      'PluginListResponse',
    );
    return normalizeList(parsed);
  },

  async updateLifecycle(
    pluginId: string,
    action: PluginLifecycleAction,
  ): Promise<PluginLifecycleResponse> {
    const response = await apiClient.post<Record<string, unknown>>(
      `/api/v1/plugins/${encodeURIComponent(pluginId)}/lifecycle`,
      { action } satisfies OpenApiPluginLifecycleRequest,
    );
    const parsed = parseCamelCasePayload<z.infer<typeof pluginLifecycleResponseSchema>>(
      response.data,
      pluginLifecycleResponseSchema,
      'PluginLifecycleResponse',
    );
    return normalizeLifecycle(parsed);
  },
};
