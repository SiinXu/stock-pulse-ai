// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
/**
 * Client for recommended config presets and stockpulse-profile YAML.
 * Response boundaries use OpenAPI-generated anchors + Zod fail-closed validation.
 */
import { z } from 'zod';
import type {
  ConfigPresetApplyResponse,
  ConfigPresetListResponse,
  ConfigPresetPreviewResponse,
  ConfigProfileExportResponse,
  ConfigProfileImportApplyResponse,
  ConfigProfileImportPreviewResponse,
} from '../types/configProfiles';
import type { components } from '../types/api.generated';
import apiClient from './index';
import { parseCamelCasePayload } from './parseCamelCasePayload';

type OpenApiPresetList = components['schemas']['ConfigPresetListResponse'];
type OpenApiPresetItem = components['schemas']['ConfigPresetItem'];
type OpenApiPresetPreview = components['schemas']['ConfigPresetPreviewResponse'];
type OpenApiPresetApply = components['schemas']['ConfigPresetApplyResponse'];
type OpenApiExport = components['schemas']['ConfigProfileExportResponse'];
type OpenApiImportPreview = components['schemas']['ConfigProfileImportPreviewResponse'];
type OpenApiImportApply = components['schemas']['ConfigProfileImportApplyResponse'];
type _AssertList = keyof OpenApiPresetList;
type _AssertItem = keyof OpenApiPresetItem;
type _AssertPreview = keyof OpenApiPresetPreview;
type _AssertApply = keyof OpenApiPresetApply;
type _AssertExport = keyof OpenApiExport;
type _AssertImportPreview = keyof OpenApiImportPreview;
type _AssertImportApply = keyof OpenApiImportApply;
const _listAnchor: _AssertList = 'recommended_preset_id';
const _itemAnchor: _AssertItem = 'display_name';
const _previewAnchor: _AssertPreview = 'config_version';
const _applyAnchor: _AssertApply = 'new_config_version';
const _exportAnchor: _AssertExport = 'keys_redacted';
const _importPreviewAnchor: _AssertImportPreview = 'change_count';
const _importApplyAnchor: _AssertImportApply = 'updated_keys';
void _listAnchor;
void _itemAnchor;
void _previewAnchor;
void _applyAnchor;
void _exportAnchor;
void _importPreviewAnchor;
void _importApplyAnchor;

const finiteNumber = z.number().refine((value) => Number.isFinite(value), {
  message: 'non-finite number rejected',
});

const configProfileChangeSchema = z
  .object({
    key: z.string(),
    fromValue: z.string(),
    to: z.string(),
  })
  .passthrough();

const configProfileDetectionSchema = z
  .object({
    ollamaHealthy: z.boolean().optional(),
    modelPackPresent: z.boolean().optional(),
    cliDetected: z.array(z.string()).optional(),
    cloudReady: z.boolean().optional(),
  })
  .passthrough();

const configPresetItemSchema = z
  .object({
    id: z.string(),
    displayName: z.string(),
    description: z.string(),
    tags: z.array(z.string()).optional(),
    preferenceOrder: z.array(z.string()).optional(),
    configValues: z.record(z.string(), z.string()).optional(),
    strategies: z.record(z.string(), z.unknown()).optional(),
    features: z.record(z.string(), z.unknown()).optional(),
    requirements: z.record(z.string(), z.unknown()).optional(),
    recommended: z.boolean().optional(),
    score: finiteNumber.optional(),
    meetsRequirements: z.boolean().optional(),
  })
  .passthrough();

const configPresetListResponseSchema = z
  .object({
    recommendedPresetId: z.string().nullable().optional(),
    detection: configProfileDetectionSchema.optional(),
    presets: z.array(configPresetItemSchema).optional(),
  })
  .passthrough();

const configPresetPreviewResponseSchema = z
  .object({
    presetId: z.string(),
    displayName: z.string(),
    configVersion: z.string(),
    features: z.record(z.string(), z.unknown()).optional(),
    changes: z.array(configProfileChangeSchema).optional(),
    changeCount: finiteNumber.optional(),
  })
  .passthrough();

const configPresetApplyResponseSchema = z
  .object({
    presetId: z.string(),
    displayName: z.string(),
    applied: z.boolean(),
    configVersion: z.string(),
    newConfigVersion: z.string(),
    updatedKeys: z.array(z.string()).optional(),
    changes: z.array(configProfileChangeSchema).optional(),
    features: z.record(z.string(), z.unknown()).optional(),
    message: z.string().optional(),
  })
  .passthrough();

const configProfileExportResponseSchema = z
  .object({
    content: z.string(),
    configVersion: z.string(),
    filename: z.string(),
    keysExported: z.array(z.string()).optional(),
    keysRedacted: finiteNumber.optional(),
  })
  .passthrough();

const configProfileImportPreviewResponseSchema = z
  .object({
    valid: z.boolean(),
    configVersion: z.string(),
    name: z.string().optional(),
    displayName: z.string().optional(),
    description: z.string().optional(),
    features: z.record(z.string(), z.unknown()).optional(),
    changes: z.array(configProfileChangeSchema).optional(),
    changeCount: finiteNumber.optional(),
    issues: z.array(z.record(z.string(), z.unknown())).optional(),
  })
  .passthrough();

const configProfileImportApplyResponseSchema = z
  .object({
    applied: z.boolean(),
    configVersion: z.string(),
    newConfigVersion: z.string(),
    updatedKeys: z.array(z.string()).optional(),
    changes: z.array(configProfileChangeSchema).optional(),
    name: z.string().optional(),
    features: z.record(z.string(), z.unknown()).optional(),
    message: z.string().optional(),
  })
  .passthrough();

export const configProfilesApi = {
  async listPresets(): Promise<ConfigPresetListResponse> {
    const response = await apiClient.get<Record<string, unknown>>('/api/v1/config-profiles/presets');
    return parseCamelCasePayload<ConfigPresetListResponse>(
      response.data,
      configPresetListResponseSchema,
      'ConfigPresetListResponse',
      'configProfiles',
    );
  },

  async previewPreset(
    presetId: string,
    payload: { configVersion: string },
  ): Promise<ConfigPresetPreviewResponse> {
    const response = await apiClient.post<Record<string, unknown>>(
      `/api/v1/config-profiles/presets/${encodeURIComponent(presetId)}/preview`,
      { config_version: payload.configVersion },
    );
    return parseCamelCasePayload<ConfigPresetPreviewResponse>(
      response.data,
      configPresetPreviewResponseSchema,
      'ConfigPresetPreviewResponse',
      'configProfiles',
    );
  },

  async applyPreset(
    presetId: string,
    payload: { configVersion: string; reloadNow?: boolean },
  ): Promise<ConfigPresetApplyResponse> {
    const response = await apiClient.post<Record<string, unknown>>(
      `/api/v1/config-profiles/presets/${encodeURIComponent(presetId)}/apply`,
      {
        config_version: payload.configVersion,
        reload_now: payload.reloadNow ?? true,
      },
    );
    return parseCamelCasePayload<ConfigPresetApplyResponse>(
      response.data,
      configPresetApplyResponseSchema,
      'ConfigPresetApplyResponse',
      'configProfiles',
    );
  },

  async exportProfile(): Promise<ConfigProfileExportResponse> {
    const response = await apiClient.get<Record<string, unknown>>('/api/v1/config-profiles/export');
    return parseCamelCasePayload<ConfigProfileExportResponse>(
      response.data,
      configProfileExportResponseSchema,
      'ConfigProfileExportResponse',
      'configProfiles',
    );
  },

  async previewImport(payload: {
    configVersion: string;
    content: string;
  }): Promise<ConfigProfileImportPreviewResponse> {
    const response = await apiClient.post<Record<string, unknown>>(
      '/api/v1/config-profiles/import/preview',
      {
        config_version: payload.configVersion,
        content: payload.content,
      },
    );
    return parseCamelCasePayload<ConfigProfileImportPreviewResponse>(
      response.data,
      configProfileImportPreviewResponseSchema,
      'ConfigProfileImportPreviewResponse',
      'configProfiles',
    );
  },

  async applyImport(payload: {
    configVersion: string;
    content: string;
    reloadNow?: boolean;
  }): Promise<ConfigProfileImportApplyResponse> {
    const response = await apiClient.post<Record<string, unknown>>(
      '/api/v1/config-profiles/import/apply',
      {
        config_version: payload.configVersion,
        content: payload.content,
        reload_now: payload.reloadNow ?? true,
      },
    );
    return parseCamelCasePayload<ConfigProfileImportApplyResponse>(
      response.data,
      configProfileImportApplyResponseSchema,
      'ConfigProfileImportApplyResponse',
      'configProfiles',
    );
  },
};
