import type { SystemConfigItem, SystemConfigUpdateItem } from '../../types/systemConfig';

export type SettingsSaveStatus = 'idle' | 'scheduled' | 'saving' | 'saved' | 'failed' | 'conflicted';

export type SettingsSaveGroupState = {
  status: SettingsSaveStatus;
  error?: string;
  updatedAt?: number;
};

const MODEL_GRAPH_KEYS = new Set([
  'LITELLM_MODEL',
  'LITELLM_FALLBACK_MODELS',
  'AGENT_LITELLM_MODEL',
  'VISION_MODEL',
  'LLM_TEMPERATURE',
]);

export function getSettingsSaveGroup<T extends { key: string; schema?: SystemConfigItem['schema'] }>(item: T): string {
  if ('schema' in item) {
    const authoredGroup = item.schema?.saveGroup?.trim();
    if (authoredGroup) return authoredGroup;
  }

  const key = item.key.trim().toUpperCase();
  const category = item.schema?.category;
  if (category === 'ai_model' || key === 'LLM_CHANNELS' || key.startsWith('LLM_') || MODEL_GRAPH_KEYS.has(key)) {
    return 'ai.model_graph';
  }
  if (key.startsWith('SCHEDULE_')) return 'system.scheduler';
  if (key.startsWith('ADMIN_')) return 'system.authentication';
  if (category === 'notification') return 'notifications.channels';
  if (key.startsWith('REPORT_') || key.startsWith('MARKET_REVIEW_') || key.startsWith('DAILY_MARKET_')) {
    return 'reports.generation';
  }
  if (category === 'agent') return 'agent.behavior';
  if (category === 'backtest') return 'backtest.defaults';
  if (key === 'STOCK_LIST') return 'overview.watchlist';
  return `${category ?? 'uncategorized'}.general`;
}

export function mergeSaveGroupItems(
  currentItems: SystemConfigUpdateItem[],
  explicitItems: SystemConfigUpdateItem[],
): SystemConfigUpdateItem[] {
  const merged = new Map<string, SystemConfigUpdateItem>();
  for (const item of [...currentItems, ...explicitItems]) {
    merged.set(item.key.trim().toUpperCase(), item);
  }
  return [...merged.values()];
}

export function isBlockingSaveStatus(status: SettingsSaveStatus): boolean {
  return status === 'scheduled'
    || status === 'saving'
    || status === 'failed'
    || status === 'conflicted';
}
