// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type { SettingsHelpContent } from './settingsHelpTypes';

export type SettingsHelpDefinition = Omit<SettingsHelpContent, 'title'> & {
  title?: string;
};

export type SettingsHelpSourceMap = Record<string, SettingsHelpDefinition>;
