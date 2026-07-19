// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
export const CHANNEL_FIELD_SUFFIXES = [
  'DISPLAY_NAME',
  'PROVIDER',
  'PROTOCOL',
  'BASE_URL',
  'API_KEY',
  'API_KEYS',
  'MODELS',
  'EXTRA_HEADERS',
  'ENABLED',
] as const;

export type ChannelFieldSuffix = (typeof CHANNEL_FIELD_SUFFIXES)[number];

export const CONNECTION_SCHEMA_KEY_BY_SUFFIX: Record<ChannelFieldSuffix, string> = {
  DISPLAY_NAME: 'display_name',
  PROVIDER: 'provider_id',
  PROTOCOL: 'protocol',
  BASE_URL: 'base_url',
  API_KEY: 'api_key',
  API_KEYS: 'api_keys',
  MODELS: 'models',
  EXTRA_HEADERS: 'extra_headers',
  ENABLED: 'enabled',
};

/** Fields the current Connection editor can inspect, validate, and serialize. */
export const SUPPORTED_CONNECTION_SCHEMA_KEYS: ReadonlySet<string> = new Set([
  'connection_name',
  ...Object.values(CONNECTION_SCHEMA_KEY_BY_SUFFIX),
]);

export const CHANNEL_FIELD_KEY_PATTERN = new RegExp(
  `^LLM_([A-Z0-9_]+)_(${CHANNEL_FIELD_SUFFIXES.join('|')})$`,
);

export interface ModelAccessFieldFocusRequest {
  requestId: number;
  key: string;
}

export interface ParsedChannelFieldKey {
  connectionName: string;
  suffix: ChannelFieldSuffix;
}

export function parseModelAccessFieldKey(key: string): ParsedChannelFieldKey | null {
  const match = CHANNEL_FIELD_KEY_PATTERN.exec(key.trim().toUpperCase());
  if (!match) {
    return null;
  }
  return {
    connectionName: match[1].toLowerCase(),
    suffix: match[2] as ChannelFieldSuffix,
  };
}
