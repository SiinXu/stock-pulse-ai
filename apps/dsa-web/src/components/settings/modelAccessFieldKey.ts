export const CHANNEL_FIELD_SUFFIXES = [
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
