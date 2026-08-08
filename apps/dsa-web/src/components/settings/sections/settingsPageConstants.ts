// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { parseStockListValue } from '../../../utils/stockList';

// Routing fields whose options must be limited to channels the user has
// actually configured (values follow ROUTABLE_NOTIFICATION_CHANNELS).
export const CHANNEL_ROUTING_FIELD_KEYS = new Set([
  'NOTIFICATION_REPORT_CHANNELS',
  'NOTIFICATION_ALERT_CHANNELS',
  'NOTIFICATION_SYSTEM_ERROR_CHANNELS',
]);
export const LOCAL_MODEL_CONFIG_KEYS = [
  'GENERATION_BACKEND',
  'LLM_CONFIG_MODE',
  'LLM_CHANNELS',
  'LLM_OLLAMA_PROVIDER',
  'LLM_OLLAMA_PROTOCOL',
  'LLM_OLLAMA_BASE_URL',
  'LLM_OLLAMA_MODELS',
  'LLM_OLLAMA_ENABLED',
  'LITELLM_MODEL',
  'AGENT_LITELLM_MODEL',
];
export function parseSetupStockList(value: unknown) {
  return parseStockListValue(String(value ?? ''));
}
