// Presentation-only provider content for the LLM channel editor.
//
// The authoritative provider *business* metadata (label, default endpoint,
// protocol, capabilities, credential/base-URL requirements, and quick links)
// lives in the backend provider catalog (`GET /system/config/llm/providers`,
// consumed via useProviderCatalog). This module intentionally holds only the
// curated *presentation* content the backend does not model: capability display
// labels. Provider-specific links and setup metadata belong to the Catalog.

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
