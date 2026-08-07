// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
/**
 * Client for recommended config presets and stockpulse-profile YAML.
 * Intentionally separate from systemConfig.ts (owned by open PR fence).
 */
import type {
  ConfigPresetApplyResponse,
  ConfigPresetListResponse,
  ConfigPresetPreviewResponse,
  ConfigProfileExportResponse,
  ConfigProfileImportApplyResponse,
  ConfigProfileImportPreviewResponse,
} from '../types/configProfiles';
import apiClient from './index';
import { toCamelCase } from './utils';

export const configProfilesApi = {
  async listPresets(): Promise<ConfigPresetListResponse> {
    const response = await apiClient.get<Record<string, unknown>>('/api/v1/config-profiles/presets');
    return toCamelCase<ConfigPresetListResponse>(response.data);
  },

  async previewPreset(
    presetId: string,
    payload: { configVersion: string },
  ): Promise<ConfigPresetPreviewResponse> {
    const response = await apiClient.post<Record<string, unknown>>(
      `/api/v1/config-profiles/presets/${encodeURIComponent(presetId)}/preview`,
      { config_version: payload.configVersion },
    );
    return toCamelCase<ConfigPresetPreviewResponse>(response.data);
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
    return toCamelCase<ConfigPresetApplyResponse>(response.data);
  },

  async exportProfile(): Promise<ConfigProfileExportResponse> {
    const response = await apiClient.get<Record<string, unknown>>('/api/v1/config-profiles/export');
    return toCamelCase<ConfigProfileExportResponse>(response.data);
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
    return toCamelCase<ConfigProfileImportPreviewResponse>(response.data);
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
    return toCamelCase<ConfigProfileImportApplyResponse>(response.data);
  },
};
