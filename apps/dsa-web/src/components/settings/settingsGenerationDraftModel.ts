// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type { SystemConfigItem, SystemConfigUpdateItem } from '../../types/systemConfig';

const LLM_CHANNEL_EDITOR_RUNTIME_KEYS = new Set([
  'LITELLM_MODEL',
  'LITELLM_FALLBACK_MODELS',
  'AGENT_LITELLM_MODEL',
  'VISION_MODEL',
  'LLM_TEMPERATURE',
]);

export const KNOWN_AI_UI_PLACEMENTS = new Set([
  'model_access',
  'task_routing',
  'developer_diagnostics',
  'hidden_legacy',
]);

export function getUnsafeAiPlacement(
  item: SystemConfigItem,
  categoryHint?: string,
): 'missing' | 'unknown' | null {
  if ((item.schema?.category ?? categoryHint) !== 'ai_model') {
    return null;
  }
  const placement = item.schema?.uiPlacement;
  if (!placement) {
    return 'missing';
  }
  return KNOWN_AI_UI_PLACEMENTS.has(String(placement)) ? null : 'unknown';
}

const GENERATION_BACKEND_STATUS_KEYS = new Set([
  'GENERATION_BACKEND',
  'GENERATION_FALLBACK_BACKEND',
  'GENERATION_BACKEND_TIMEOUT_SECONDS',
  'GENERATION_BACKEND_MAX_OUTPUT_BYTES',
  'GENERATION_BACKEND_MAX_CONCURRENCY',
  'LOCAL_CLI_BACKEND_MAX_CONCURRENCY',
  'OPENCODE_CLI_MODEL',
  'LITELLM_CONFIG',
  'LITELLM_MODEL',
  'LITELLM_FALLBACK_MODELS',
]);
const LLM_CHANNEL_STATUS_KEY_PATTERN = /^LLM_[A-Z0-9_]+_(PROVIDER|PROTOCOL|BASE_URL|API_KEY|API_KEYS|MODELS|EXTRA_HEADERS|ENABLED)$/;

function isLlmChannelEditorDraftKey(key: string): boolean {
  const normalized = key.trim().toUpperCase();
  return normalized.startsWith('LLM_') || LLM_CHANNEL_EDITOR_RUNTIME_KEYS.has(normalized);
}

function isGenerationBackendStatusDraftKey(key: string): boolean {
  const normalized = key.trim().toUpperCase();
  return (
    GENERATION_BACKEND_STATUS_KEYS.has(normalized)
    || normalized === 'LLM_CHANNELS'
    || LLM_CHANNEL_STATUS_KEY_PATTERN.test(normalized)
  );
}

export function mergeGenerationBackendDraftItems(
  outerItems: SystemConfigUpdateItem[],
  llmChannelItems: SystemConfigUpdateItem[],
): SystemConfigUpdateItem[] {
  const merged = new Map<string, SystemConfigUpdateItem>();
  for (const item of outerItems) {
    const normalizedKey = item.key.trim().toUpperCase();
    if (isGenerationBackendStatusDraftKey(normalizedKey)) {
      merged.set(normalizedKey, item);
    }
  }
  for (const item of llmChannelItems) {
    const normalizedKey = item.key.trim().toUpperCase();
    if (isLlmChannelEditorDraftKey(normalizedKey) && isGenerationBackendStatusDraftKey(normalizedKey)) {
      merged.set(normalizedKey, item);
    }
  }
  return Array.from(merged.values());
}

const PROMPT_CACHE_ADVANCED_SETTING_KEYS = new Set([
  'LLM_PROMPT_CACHE_TELEMETRY_ENABLED',
  'LLM_PROMPT_CACHE_HINTS_ENABLED',
  'LLM_PROMPT_CACHE_DIAGNOSTICS_LEVEL',
]);

export function isPromptCacheAdvancedSetting(item: { key: string }) {
  return PROMPT_CACHE_ADVANCED_SETTING_KEYS.has(item.key);
}
