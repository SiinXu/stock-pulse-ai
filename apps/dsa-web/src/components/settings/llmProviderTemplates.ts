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
    hint: '按 OpenAI-compatible endpoint 配置 Base URL，不额外拼接 /chat/completions。',
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
    hint: '支持尝试通过 /models 获取模型列表；实际结果仍取决于账号权限和 API Key。',
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
  officialSources: Array<{ label: string; url: string }>;
  configHint?: string;
}

// Curated documentation links / config hints keyed by provider id. These are
// help content (like the settings help locale), not routing business metadata.
export const PROVIDER_PRESENTATION_BY_ID: Record<string, ProviderPresentation> = {
  aihubmix: { officialSources: [{ label: 'AIHubmix', url: 'https://aihubmix.com/' }] },
  anspire: {
    officialSources: [
      { label: 'Anspire Open', url: 'https://open.anspire.cn/?share_code=QFBC0FYC' },
      { label: 'LiteLLM OpenAI-compatible', url: 'https://docs.litellm.ai/docs/providers/openai_compatible' },
    ],
    configHint:
      '同一 ANSPIRE_API_KEYS 可复用到搜索与 LLM 渠道。以下模型与网关为配置示例，实际可用性请以账号权限和控制台为准；建议先点“测试连接”确认。',
  },
  deepseek: { officialSources: [{ label: 'DeepSeek API Docs', url: 'https://api-docs.deepseek.com/' }] },
  dashscope: {
    officialSources: [
      { label: 'DashScope Text Generation', url: 'https://help.aliyun.com/zh/model-studio/text-generation-model/' },
    ],
  },
  zhipu: {
    officialSources: [{ label: 'Zhipu Model Overview', url: 'https://docs.bigmodel.cn/cn/guide/start/model-overview' }],
  },
  moonshot: { officialSources: [{ label: 'Kimi Platform Docs', url: 'https://platform.kimi.com/docs/models' }] },
  minimax: {
    officialSources: [
      { label: 'MiniMax OpenAI API', url: 'https://platform.minimax.io/docs/api-reference/text-chat' },
      { label: 'MiniMax Models', url: 'https://platform.minimax.io/docs/api-reference/models/openai/list-models' },
    ],
  },
  volcengine: {
    officialSources: [
      { label: 'Volcengine Ark Inference', url: 'https://www.volcengine.com/docs/82379/2121998' },
      { label: 'Volcengine Ark Models', url: 'https://www.volcengine.com/docs/82379/1949118' },
    ],
    configHint: '确认在线推理 endpoint / region 与 Coding Plan 专用入口不要混用。',
  },
  siliconflow: {
    officialSources: [{ label: 'SiliconFlow Models', url: 'https://docs.siliconflow.cn/quickstart/models' }],
    configHint: '模型列表和模型可见性依赖账号权限与 API Key。',
  },
  openrouter: {
    officialSources: [
      { label: 'OpenRouter Models API', url: 'https://openrouter.ai/docs/api/api-reference/models/get-models' },
    ],
    configHint: '模型列表和模型可见性依赖账号权限与 API Key。',
  },
  gemini: { officialSources: [{ label: 'Gemini Models', url: 'https://ai.google.dev/gemini-api/docs/models' }] },
  anthropic: {
    officialSources: [
      { label: 'Anthropic Models', url: 'https://docs.anthropic.com/en/docs/about-claude/models/all-models' },
    ],
  },
  openai: { officialSources: [{ label: 'OpenAI Models', url: 'https://platform.openai.com/docs/models' }] },
  ollama: {
    officialSources: [{ label: 'Ollama API', url: 'https://github.com/ollama/ollama/blob/main/docs/api.md' }],
    configHint: '需要本机、Docker 或 self-hosted runner 能访问 Ollama 服务。',
  },
};

export function getProviderPresentation(id: string): ProviderPresentation {
  if (!Object.prototype.hasOwnProperty.call(PROVIDER_PRESENTATION_BY_ID, id)) {
    return { officialSources: [] };
  }
  return PROVIDER_PRESENTATION_BY_ID[id];
}

export const MODEL_PLACEHOLDERS_BY_PROTOCOL: Record<ChannelProtocol, string> = {
  openai: 'gpt-5.5,qwen3.6-plus',
  deepseek: 'deepseek-v4-flash,deepseek-v4-pro',
  gemini: 'gemini-3.1-pro-preview,gemini-3-flash-preview',
  anthropic: 'claude-sonnet-4-6,claude-opus-4-7',
  vertex_ai: 'gemini-3.1-pro-preview',
  ollama: 'llama3.2,qwen2.5',
};
