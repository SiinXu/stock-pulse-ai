// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { z } from 'zod';
import type { components } from '../types/api.generated';
import apiClient, { locallyRecoverableResourceConfig } from './index';
import { parseCamelCasePayload } from './parseCamelCasePayload';

type OpenApiPluginInfo = components['schemas']['PluginInfo'];
type OpenApiPluginListResponse = components['schemas']['PluginListResponse'];
type OpenApiPluginLifecycleRequest = components['schemas']['PluginLifecycleRequest'];
type OpenApiPluginLifecycleResponse = components['schemas']['PluginLifecycleResponse'];
type OpenApiPluginSettingsResponse = components['schemas']['PluginSettingsResponse'];
type OpenApiPluginSettingsUpdateRequest = components['schemas']['PluginSettingsUpdateRequest'];
type OpenApiPluginSettingsUpdateResponse = components['schemas']['PluginSettingsUpdateResponse'];

const _infoAnchor: keyof OpenApiPluginInfo = 'settings_count';
const _listAnchor: keyof OpenApiPluginListResponse = 'total';
const _lifecycleRequestAnchor: keyof OpenApiPluginLifecycleRequest = 'action';
const _lifecycleResponseAnchor: keyof OpenApiPluginLifecycleResponse = 'restart_required';
const _settingsAnchor: keyof OpenApiPluginSettingsResponse = 'masked_keys';
const _settingsRequestAnchor: keyof OpenApiPluginSettingsUpdateRequest = 'mask_token';
const _settingsUpdateAnchor: keyof OpenApiPluginSettingsUpdateResponse = 'changed_keys';
void _infoAnchor;
void _listAnchor;
void _lifecycleRequestAnchor;
void _lifecycleResponseAnchor;
void _settingsAnchor;
void _settingsRequestAnchor;
void _settingsUpdateAnchor;

export type PluginLifecycleAction = OpenApiPluginLifecycleRequest['action'];
export type PluginLifecycleState = OpenApiPluginInfo['state'];
export type PluginSource = OpenApiPluginInfo['source'];
export type PluginSettingValue = string | number | boolean | null;

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
  lastErrorCode?: string | null;
  description: string;
  author: string;
  settingsCount: number;
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

export type PluginSettingField = {
  key: string;
  title: string;
  description: string;
  dataType: 'string' | 'integer' | 'number' | 'boolean';
  uiControl: 'text' | 'password' | 'number' | 'select' | 'textarea' | 'switch';
  isSensitive: boolean;
  isRequired: boolean;
  defaultValue: PluginSettingValue;
  options: Array<{ label: string; value: PluginSettingValue }>;
  validation: Record<string, unknown>;
  displayOrder: number;
};

export type PluginSettingsResponse = {
  pluginId: string;
  schema: PluginSettingField[];
  values: Record<string, PluginSettingValue>;
  maskedKeys: string[];
  maskToken: string;
};

export type PluginSettingsUpdateResponse = PluginSettingsResponse & {
  changedKeys: string[];
  restartRequired: boolean;
};

const finiteNumberSchema = z.number().finite();
const settingValueSchema = z.union([
  z.string(),
  z.number().int().finite(),
  finiteNumberSchema,
  z.boolean(),
  z.null(),
]);

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
  lastErrorCode: z.string().nullable().optional(),
  description: z.string().optional(),
  author: z.string().optional(),
  settingsCount: z.number().int().nonnegative().optional(),
}).passthrough();

const pluginListResponseSchema = z.object({
  items: z.array(pluginInfoSchema).optional(),
  total: z.number().int().nonnegative(),
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

const pluginSettingFieldSchema = z.object({
  key: z.string(),
  title: z.string(),
  description: z.string().optional(),
  dataType: z.enum(['string', 'integer', 'number', 'boolean']),
  uiControl: z.enum(['text', 'password', 'number', 'select', 'textarea', 'switch']),
  isSensitive: z.boolean().optional(),
  isRequired: z.boolean().optional(),
  defaultValue: settingValueSchema.optional(),
  options: z.array(z.object({
    label: z.string(),
    value: settingValueSchema,
  })).optional(),
  validation: z.record(z.string(), z.unknown()).optional(),
  displayOrder: z.number().int().nonnegative().optional(),
}).passthrough();

const pluginSettingsResponseSchema = z.object({
  pluginId: z.string(),
  schema: z.array(pluginSettingFieldSchema).optional(),
  values: z.record(z.string(), settingValueSchema).optional(),
  maskedKeys: z.array(z.string()).optional(),
  maskToken: z.string(),
}).passthrough();

const pluginSettingsUpdateResponseSchema = pluginSettingsResponseSchema.extend({
  changedKeys: z.array(z.string()).optional(),
  restartRequired: z.boolean().optional(),
});

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
    lastErrorCode: raw.lastErrorCode ?? null,
    description: raw.description ?? '',
    author: raw.author ?? '',
    settingsCount: raw.settingsCount ?? 0,
  };
}

function normalizeSettings(
  raw: z.infer<typeof pluginSettingsResponseSchema>,
): PluginSettingsResponse {
  return {
    pluginId: raw.pluginId,
    schema: (raw.schema ?? []).map((field) => ({
      key: field.key,
      title: field.title,
      description: field.description ?? '',
      dataType: field.dataType,
      uiControl: field.uiControl,
      isSensitive: field.isSensitive ?? false,
      isRequired: field.isRequired ?? false,
      defaultValue: field.defaultValue ?? null,
      options: field.options ?? [],
      validation: field.validation ?? {},
      displayOrder: field.displayOrder ?? 100,
    })),
    values: raw.values ?? {},
    maskedKeys: raw.maskedKeys ?? [],
    maskToken: raw.maskToken,
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
    return { items: (parsed.items ?? []).map(normalizePlugin), total: parsed.total };
  },

  async updateLifecycle(
    pluginId: string,
    action: PluginLifecycleAction,
  ): Promise<PluginLifecycleResponse> {
    const response = await apiClient.post<Record<string, unknown>>(
      `/api/v1/plugins/${encodeURIComponent(pluginId)}/lifecycle`,
      { action } satisfies OpenApiPluginLifecycleRequest,
      locallyRecoverableResourceConfig(),
    );
    const parsed = parseCamelCasePayload<z.infer<typeof pluginLifecycleResponseSchema>>(
      response.data,
      pluginLifecycleResponseSchema,
      'PluginLifecycleResponse',
      'plugins',
    );
    return {
      pluginId: parsed.pluginId,
      action: parsed.action,
      success: parsed.success,
      state: parsed.state,
      reloaded: parsed.reloaded ?? false,
      restartRequired: parsed.restartRequired ?? false,
      errorCode: parsed.errorCode ?? null,
      message: parsed.message ?? null,
      plugin: parsed.plugin ? normalizePlugin(parsed.plugin) : null,
    };
  },

  async getSettings(pluginId: string): Promise<PluginSettingsResponse> {
    const response = await apiClient.get<Record<string, unknown>>(
      `/api/v1/plugins/${encodeURIComponent(pluginId)}/settings`,
      locallyRecoverableResourceConfig(),
    );
    const parsed = parseCamelCasePayload<z.infer<typeof pluginSettingsResponseSchema>>(
      response.data,
      pluginSettingsResponseSchema,
      'PluginSettingsResponse',
      'plugins',
    );
    return normalizeSettings(parsed);
  },

  async updateSettings(
    pluginId: string,
    values: Record<string, PluginSettingValue>,
    maskToken: string,
  ): Promise<PluginSettingsUpdateResponse> {
    const payload = { values, mask_token: maskToken } satisfies OpenApiPluginSettingsUpdateRequest;
    const response = await apiClient.put<Record<string, unknown>>(
      `/api/v1/plugins/${encodeURIComponent(pluginId)}/settings`,
      payload,
      locallyRecoverableResourceConfig(),
    );
    const parsed = parseCamelCasePayload<z.infer<typeof pluginSettingsUpdateResponseSchema>>(
      response.data,
      pluginSettingsUpdateResponseSchema,
      'PluginSettingsUpdateResponse',
      'plugins',
    );
    return {
      ...normalizeSettings(parsed),
      changedKeys: parsed.changedKeys ?? [],
      restartRequired: parsed.restartRequired ?? false,
    };
  },
};
