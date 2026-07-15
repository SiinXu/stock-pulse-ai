// Presentation-only provider content for the LLM channel editor.
//
// The authoritative provider *business* metadata (label, default endpoint,
// protocol, placeholder models, capabilities, credential/base-URL requirements)
// lives in the backend provider catalog (`GET /system/config/llm/providers`,
// consumed via useProviderCatalog). This module intentionally holds only the
// curated *presentation* content the backend does not model: capability display
// labels, per-protocol placeholder fallbacks, and per-provider documentation
// links / config hints. It must not re-declare a second business source.

export type ChannelProtocol = 'openai' | 'deepseek' | 'gemini' | 'anthropic' | 'vertex_ai' | 'ollama';
export type LLMProviderCapability =
  | 'openai-compatible'
  | 'aggregator'
  | 'official-api'
  | 'model-discovery'
  | 'vision'
  | 'local-runtime';

export const LLM_PROVIDER_CAPABILITY_LABELS: Record<LLMProviderCapability, { label: string; hint: string }> = {
  'openai-compatible': {
    label: 'OpenAI 兼容',
    hint: '按 OpenAI-compatible endpoint 配置服务地址，不额外拼接 /chat/completions。',
  },
  aggregator: {
    label: '聚合平台',
    hint: '模型可见性、路由和价格可能随账号权限与平台策略变化。',
  },
  'official-api': {
    label: '官方 API',
    hint: '使用服务商官方协议或官方兼容入口。',
  },
  'model-discovery': {
    label: '可获取模型',
    hint: '支持尝试通过 /models 获取模型列表；实际结果仍取决于账号权限和 API 密钥。',
  },
  vision: {
    label: 'Vision 提示',
    hint: '模板提示该 provider 常用于 Vision 场景；具体模型能力仍以账号和模型列表为准。',
  },
  'local-runtime': {
    label: '本地运行',
    hint: '需要当前运行环境能访问对应本地服务。',
  },
};

export function getCapabilityLabel(capability: string): { label: string; hint: string } | undefined {
  if (!Object.prototype.hasOwnProperty.call(LLM_PROVIDER_CAPABILITY_LABELS, capability)) {
    return undefined;
  }
  return LLM_PROVIDER_CAPABILITY_LABELS[capability as LLMProviderCapability];
}

export interface ProviderPresentation {
  configHint?: string;
}

// Focused presentation hints keyed by provider id. Provider URLs, identity,
// protocol, endpoints, credentials, and discovery rules belong exclusively to
// the backend Catalog and must not be added here.
export const PROVIDER_PRESENTATION_BY_ID: Record<string, ProviderPresentation> = {
  anspire: {
    configHint:
      '同一 ANSPIRE_API_KEYS 可复用到搜索与 LLM 模型连接。实际可用性请以账号权限和控制台为准；建议先点“测试连接”确认。',
  },
  volcengine: {
    configHint: '确认在线推理 endpoint / region 与 Coding Plan 专用入口不要混用。',
  },
  siliconflow: {
    configHint: '模型列表和模型可见性依赖账号权限与 API 密钥。',
  },
  openrouter: {
    configHint: '模型列表和模型可见性依赖账号权限与 API 密钥。',
  },
  ollama: {
    configHint: '需要本机、Docker 或 self-hosted runner 能访问 Ollama 服务。',
  },
};

export function getProviderPresentation(id: string): ProviderPresentation {
  if (!Object.prototype.hasOwnProperty.call(PROVIDER_PRESENTATION_BY_ID, id)) {
    return {};
  }
  return PROVIDER_PRESENTATION_BY_ID[id];
}
