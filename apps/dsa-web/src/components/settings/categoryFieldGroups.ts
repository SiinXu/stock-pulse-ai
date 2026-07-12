import type { UiTextKey } from '../../i18n/uiText';

interface CategoryFieldGroup {
  id: string;
  titleKey: UiTextKey;
  keys: string[];
}

const DATA_SOURCE_GROUPS: CategoryFieldGroup[] = [
  {
    id: 'quote',
    titleKey: 'settings.dataGroupQuote',
    keys: [
      'REALTIME_SOURCE_PRIORITY',
      'ENABLE_REALTIME_QUOTE',
      'ENABLE_REALTIME_TECHNICAL_INDICATORS',
      'ENABLE_CHIP_DISTRIBUTION',
      'TUSHARE_TOKEN',
      'TICKFLOW_API_KEY',
      'TICKFLOW_PRIORITY',
      'TICKFLOW_KLINE_ADJUST',
      'TICKFLOW_BATCH_DAILY_ENABLED',
      'TICKFLOW_BATCH_SIZE',
      'ALPHASIFT_ENABLED',
      'ALPHASIFT_INSTALL_SPEC',
      'PYTDX_HOST',
      'PYTDX_PORT',
      'PYTDX_SERVERS',
      'STOCK_INDEX_REMOTE_UPDATE_ENABLED',
    ],
  },
  {
    id: 'search',
    titleKey: 'settings.dataGroupSearch',
    keys: [
      'TAVILY_API_KEYS',
      'SERPAPI_API_KEYS',
      'BRAVE_API_KEYS',
      'BOCHA_API_KEYS',
      'SEARXNG_BASE_URLS',
      'SEARXNG_PUBLIC_INSTANCES_ENABLED',
      'ANSPIRE_API_KEYS',
      'MINIMAX_API_KEYS',
    ],
  },
  {
    id: 'news',
    titleKey: 'settings.dataGroupNews',
    keys: [
      'NEWS_MAX_AGE_DAYS',
      'NEWS_STRATEGY_PROFILE',
      'BIAS_THRESHOLD',
    ],
  },
];

const AI_MODEL_GROUPS: CategoryFieldGroup[] = [
  {
    id: 'backend',
    titleKey: 'settings.aiGroupBackend',
    keys: [
      'GENERATION_BACKEND',
      'GENERATION_FALLBACK_BACKEND',
      'GENERATION_BACKEND_MAX_CONCURRENCY',
      'GENERATION_BACKEND_MAX_OUTPUT_BYTES',
      'GENERATION_BACKEND_TIMEOUT_SECONDS',
      'LOCAL_CLI_BACKEND_MAX_CONCURRENCY',
      'OPENCODE_CLI_MODEL',
    ],
  },
  {
    id: 'primary',
    titleKey: 'settings.aiGroupPrimary',
    keys: [
      'LITELLM_MODEL',
      'AGENT_LITELLM_MODEL',
      'LITELLM_FALLBACK_MODELS',
      'LITELLM_CONFIG',
      'LLM_CHANNELS',
      'LLM_TEMPERATURE',
    ],
  },
  {
    id: 'openai',
    titleKey: 'settings.aiGroupOpenai',
    keys: [
      'OPENAI_API_KEY',
      'OPENAI_API_KEYS',
      'OPENAI_BASE_URL',
      'OPENAI_MODEL',
      'OPENAI_VISION_MODEL',
      'OPENAI_TEMPERATURE',
    ],
  },
  {
    id: 'anthropic',
    titleKey: 'settings.aiGroupAnthropic',
    keys: [
      'ANTHROPIC_API_KEY',
      'ANTHROPIC_API_KEYS',
      'ANTHROPIC_MODEL',
      'ANTHROPIC_TEMPERATURE',
      'ANTHROPIC_MAX_TOKENS',
    ],
  },
  {
    id: 'gemini',
    titleKey: 'settings.aiGroupGemini',
    keys: [
      'GEMINI_API_KEY',
      'GEMINI_API_KEYS',
      'GEMINI_MODEL',
      'GEMINI_MODEL_FALLBACK',
      'GEMINI_TEMPERATURE',
    ],
  },
  {
    id: 'deepseek',
    titleKey: 'settings.aiGroupDeepseek',
    keys: [
      'DEEPSEEK_API_KEY',
      'DEEPSEEK_API_KEYS',
    ],
  },
  {
    id: 'anspire',
    titleKey: 'settings.aiGroupAnspire',
    keys: [
      'ANSPIRE_LLM_ENABLED',
      'ANSPIRE_LLM_BASE_URL',
      'ANSPIRE_LLM_MODEL',
    ],
  },
  {
    id: 'aihubmix',
    titleKey: 'settings.aiGroupAihubmix',
    keys: [
      'AIHUBMIX_KEY',
    ],
  },
  {
    id: 'cache',
    titleKey: 'settings.aiGroupCache',
    keys: [
      'LLM_PROMPT_CACHE_TELEMETRY_ENABLED',
      'LLM_PROMPT_CACHE_HINTS_ENABLED',
      'LLM_PROMPT_CACHE_DIAGNOSTICS_LEVEL',
      'LLM_USAGE_HMAC_SECRET',
      'LLM_USAGE_HMAC_KEY_VERSION',
    ],
  },
];

const SYSTEM_GROUPS: CategoryFieldGroup[] = [
  {
    id: 'schedule',
    titleKey: 'settings.sysGroupSchedule',
    keys: [
      'SCHEDULE_ENABLED',
      'SCHEDULE_TIME',
      'SCHEDULE_TIMES',
      'SCHEDULE_RUN_IMMEDIATELY',
      'RUN_IMMEDIATELY',
      'TRADING_DAY_CHECK_ENABLED',
      'MAX_WORKERS',
      'ANALYSIS_DELAY',
    ],
  },
  {
    id: 'marketReview',
    titleKey: 'settings.sysGroupMarketReview',
    keys: [
      'MARKET_REVIEW_ENABLED',
      'MARKET_REVIEW_REGION',
      'MARKET_REVIEW_COLOR_SCHEME',
      'DAILY_MARKET_CONTEXT_ENABLED',
    ],
  },
  {
    id: 'web',
    titleKey: 'settings.sysGroupWeb',
    keys: [
      'WEBUI_ENABLED',
      'WEBUI_AUTO_BUILD',
      'WEBUI_HOST',
      'WEBUI_PORT',
      'ADMIN_AUTH_ENABLED',
      'TRUST_X_FORWARDED_FOR',
      'HTTP_PROXY',
    ],
  },
  {
    id: 'log',
    titleKey: 'settings.sysGroupLog',
    keys: [
      'LOG_LEVEL',
      'LOG_DIR',
      'DEBUG',
      'SAVE_CONTEXT_SNAPSHOT',
    ],
  },
];

const AGENT_GROUPS: CategoryFieldGroup[] = [
  {
    id: 'mode',
    titleKey: 'settings.agentGroupMode',
    keys: [
      'AGENT_GENERATION_BACKEND',
      'AGENT_MODE',
      'AGENT_ARCH',
      'AGENT_MAX_STEPS',
      'AGENT_NL_ROUTING',
      'AGENT_ORCHESTRATOR_MODE',
      'AGENT_ORCHESTRATOR_TIMEOUT_S',
      'AGENT_RISK_OVERRIDE',
    ],
  },
  {
    id: 'skills',
    titleKey: 'settings.agentGroupSkills',
    keys: [
      'AGENT_SKILLS',
      'AGENT_SKILL_DIR',
      'AGENT_SKILL_AUTOWEIGHT',
      'AGENT_SKILL_ROUTING',
    ],
  },
  {
    id: 'research',
    titleKey: 'settings.agentGroupResearch',
    keys: [
      'AGENT_DEEP_RESEARCH_BUDGET',
      'AGENT_DEEP_RESEARCH_TIMEOUT',
      'AGENT_EVENT_MONITOR_ENABLED',
      'AGENT_EVENT_MONITOR_INTERVAL_MINUTES',
      'AGENT_EVENT_ALERT_RULES_JSON',
    ],
  },
  {
    id: 'context',
    titleKey: 'settings.agentGroupContext',
    keys: [
      'AGENT_MEMORY_ENABLED',
      'AGENT_CONTEXT_COMPRESSION_ENABLED',
      'AGENT_CONTEXT_COMPRESSION_PROFILE',
      'AGENT_CONTEXT_COMPRESSION_TRIGGER_TOKENS',
      'AGENT_CONTEXT_PROTECTED_TURNS',
    ],
  },
];

const CATEGORY_GROUPS: Record<string, CategoryFieldGroup[]> = {
  data_source: DATA_SOURCE_GROUPS,
  ai_model: AI_MODEL_GROUPS,
  system: SYSTEM_GROUPS,
  agent: AGENT_GROUPS,
};

const OTHER_GROUP: { id: string; titleKey: UiTextKey } = {
  id: 'other',
  titleKey: 'settings.categoryGroupOther',
};

const KEY_INDEX: Record<string, { group: Map<string, string>; order: Map<string, number> }> = {};
for (const [category, groups] of Object.entries(CATEGORY_GROUPS)) {
  const groupByKey = new Map<string, string>();
  const orderByKey = new Map<string, number>();
  for (const group of groups) {
    for (const key of group.keys) {
      groupByKey.set(key, group.id);
      orderByKey.set(key, orderByKey.size);
    }
  }
  KEY_INDEX[category] = { group: groupByKey, order: orderByKey };
}

export function getCategoryFieldGroupOrder(
  category: string,
): Array<{ id: string; titleKey: UiTextKey }> | undefined {
  const groups = CATEGORY_GROUPS[category];
  if (!groups) {
    return undefined;
  }
  return [...groups.map((group) => ({ id: group.id, titleKey: group.titleKey })), OTHER_GROUP];
}

export function getCategoryFieldGroupId(category: string, key: string): string {
  return KEY_INDEX[category]?.group.get(key) ?? OTHER_GROUP.id;
}

export function getCategoryFieldOrder(category: string, key: string): number {
  return KEY_INDEX[category]?.order.get(key) ?? Number.MAX_SAFE_INTEGER;
}
