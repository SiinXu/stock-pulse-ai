import type { SystemConfigDocLink } from '../types/systemConfig';

export interface SettingsHelpDefinition {
  title?: string;
  summary?: string;
  usage?: string;
  valueNotes?: string[];
  impact?: string[];
  notes?: string[];
  examples?: string[];
  showFieldKey?: boolean;
  docs?: SystemConfigDocLink[];
}

export interface SettingsHelpContent extends SettingsHelpDefinition {
  title: string;
}

export type SettingsHelpMap = Record<string, SettingsHelpContent>;
export type SettingsHelpSourceMap = Record<string, SettingsHelpDefinition>;
