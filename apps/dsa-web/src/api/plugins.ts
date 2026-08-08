// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { z } from 'zod';
import type { components } from '../types/api.generated';
import apiClient, { locallyRecoverableResourceConfig } from './index';
import { parseCamelCasePayload } from './parseCamelCasePayload';

type OpenApiPluginListResponse = components['schemas']['PluginListResponse'];
type OpenApiPluginInfo = components['schemas']['PluginInfo'];
type _AssertList = keyof OpenApiPluginListResponse;
type _AssertInfo = keyof OpenApiPluginInfo;
const _listAnchor: _AssertList = 'total';
const _infoAnchor: _AssertInfo = 'desired_enabled';
void _listAnchor;
void _infoAnchor;

export type PluginSource = 'builtin' | 'external';
export type PluginLifecycleState = 'registered' | 'enabled' | 'disabled' | 'failed';

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

function normalizePlugin(raw: z.infer<typeof pluginInfoSchema>): PluginInfo {
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

export const pluginsApi = {
  async list(): Promise<PluginListResponse> {
    const response = await apiClient.get<Record<string, unknown>>(
      '/api/v1/plugins',
      locallyRecoverableResourceConfig(),
    );
    const parsed = parseCamelCasePayload<z.infer<typeof pluginListResponseSchema>>(
      response.data,
      pluginListResponseSchema,
      'PluginListResponse',
      'plugins',
    );
    const items = (parsed.items ?? []).map(normalizePlugin);
    return { items, total: parsed.total };
  },
};
