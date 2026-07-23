import type { SystemConfigDocLink } from '../types/systemConfig';

export interface SettingsHelpContent {
  title: string;
  summary?: string;
  usage?: string;
  valueNotes?: string[];
  impact?: string[];
  notes?: string[];
  examples?: string[];
  showFieldKey?: boolean;
  docs?: SystemConfigDocLink[];
}

export type SettingsHelpMap = Record<string, SettingsHelpContent>;
