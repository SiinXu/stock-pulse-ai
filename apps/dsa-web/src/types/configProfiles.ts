// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

export type ConfigProfileChange = {
  key: string;
  fromValue: string;
  to: string;
};

export type ConfigProfileDetection = {
  ollamaHealthy: boolean;
  modelPackPresent: boolean;
  cliDetected: string[];
  cloudReady: boolean;
};

export type ConfigPresetItem = {
  id: string;
  displayName: string;
  description: string;
  tags: string[];
  preferenceOrder: string[];
  configValues: Record<string, string>;
  strategies: Record<string, unknown>;
  features: Record<string, unknown>;
  requirements: Record<string, unknown>;
  recommended: boolean;
  score: number;
  meetsRequirements: boolean;
};

export type ConfigPresetListResponse = {
  recommendedPresetId: string | null;
  detection: ConfigProfileDetection;
  presets: ConfigPresetItem[];
};

export type ConfigPresetPreviewResponse = {
  presetId: string;
  displayName: string;
  configVersion: string;
  features: Record<string, unknown>;
  changes: ConfigProfileChange[];
  changeCount: number;
};

export type ConfigPresetApplyResponse = {
  presetId: string;
  displayName: string;
  applied: boolean;
  configVersion: string;
  newConfigVersion: string;
  updatedKeys: string[];
  changes: ConfigProfileChange[];
  features: Record<string, unknown>;
  message: string;
};

export type ConfigProfileExportResponse = {
  content: string;
  configVersion: string;
  filename: string;
  keysExported: string[];
  keysRedacted: number;
};

export type ConfigProfileImportPreviewResponse = {
  valid: boolean;
  configVersion: string;
  name: string;
  displayName: string;
  description: string;
  features: Record<string, unknown>;
  changes: ConfigProfileChange[];
  changeCount: number;
  issues: Array<Record<string, unknown>>;
};

export type ConfigProfileImportApplyResponse = {
  applied: boolean;
  configVersion: string;
  newConfigVersion: string;
  updatedKeys: string[];
  changes: ConfigProfileChange[];
  name: string;
  features: Record<string, unknown>;
  message: string;
};
