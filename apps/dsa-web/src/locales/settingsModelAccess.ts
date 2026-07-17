import { createUiLanguageRecord } from '../i18n/createUiLanguageRecord';
import type { UiLanguage } from '../i18n/uiText';

const zh = {
  runtimeSecret: '运行时注入的密钥不会显示；如需在设置页测试，请重新输入 API 密钥。', localPurpose: '连接本地模型服务', customPurpose: '接入兼容的自定义模型服务', aggregatorPurpose: '接入聚合模型平台', cloudPurpose: '接入云端模型服务', connectedCount: '已接入 {count} 条', connectionSucceeded: '连接成功', testFailed: '测试失败', noDiscoveredModels: '服务已连通，但没有返回可用模型', noDiscoveredModelsHint: '请确认服务地址指向兼容的模型列表接口，或在下方手动添加模型。', discoveredModels: '已获取 {count} 个模型', discoveryFailed: '获取模型失败', customProvider: '自定义服务', unsaved: '未保存', incompleteDraft: '草稿 · 未完成', enabled: '已启用', disabled: '已停用', testPassed: '测试通过', testing: '测试中', untested: '未测试', manageModels: '管理模型 {name}', noModels: '尚未添加可用模型，点击此处获取或手动添加模型', usedBy: '被以下任务使用：{tasks}', test: '测试', edit: '编辑', moreActions: '更多操作 {name}', disableConnection: '停用连接', enableConnection: '启用连接', deleteConnection: '删除连接', loadingModels: '正在获取模型列表…', duplicateName: '连接名称已存在，请更换', editService: '编辑模型服务', addService: '添加模型服务', chooseProviderDescription: '选择要接入的模型服务商，下一步填写凭据并选择可用模型。', catalogFailed: '模型服务列表加载失败', retry: '重试', chooseProvider: '选择模型服务商', provider: '模型服务商', providerPlaceholder: '搜索或选择服务商', providerSearch: '输入服务商名称搜索', cancel: '取消', next: '下一步', connectionName: '连接名称', protocol: '协议', chooseProtocol: '选择协议', providerProtocolRequired: '该服务商要求使用 {protocol} 协议。', baseUrl: '服务地址', officialUrl: '使用服务商官方地址', officialUrlHint: '使用官方接口地址，无需填写。', customUrl: '使用自定义服务地址', restoreOfficialUrl: '恢复官方默认地址', apiKey: 'API 密钥', extraHeaders: '附加请求头（JSON）', extraHeadersPlaceholder: '输入 JSON 对象，清空可移除无效配置', localKeyOptional: '本地服务可留空', multipleKeys: '支持多个密钥，用逗号分隔', getKey: '获取密钥：', availableModels: '可用模型', removeModel: '移除模型 {model}', cannotDeleteModel: '无法直接删除模型', modelReferenced: '该模型正被以下任务引用：', replacementModel: '替代模型', chooseReplacement: '选择替代模型', searchReplacement: '搜索替代模型', replaceAndDelete: '替换引用并删除', goTaskRouting: '前往任务路由', gettingModels: '获取中…', getModels: '获取模型', discoveryDescription: '自动拉取该服务的可用模型，确认后再加入连接。', noDiscovery: '该服务暂不支持自动获取模型，请在下方手动添加模型 ID。', addModelAria: '手动添加模型', addModelPlaceholder: '输入模型 ID 后回车添加', add: '添加', manualModel: '没有找到需要的模型？手动添加模型', testConnection: '测试连接', enableThis: '启用此连接', disabledDraftHint: '停用的连接会保留为草稿，不参与任务路由。', enableAria: '启用此连接', missingBeforeEnable: '启用前需补齐以下内容', fixName: '连接名称需要修正', incompleteSavedDraft: '未补齐的内容会以草稿保存：{issues}', back: '上一步', saveChanges: '保存修改', addToConfig: '添加到配置', readonly: '当前模型配置由外部配置管理，网页暂时只读。', viewDetails: '查看详情', emptyTitle: '还没有接入模型服务', emptyDescription: '接入后即可在任务路由中为报告、Agent 和视觉任务选择模型。', invalidTitle: '有模型服务未完成，无法保存', invalidDescription: '以下模型服务需补全后才能保存（点击顶部“保存并应用”统一提交）：', connectionNumber: '连接 #{number}', assignModels: '前往任务路由分配模型 →', cannotDeleteConnection: '无法直接删除连接', deleteConnectionTitle: '删除连接？', referencedConnection: '模型服务「{name}」正被以下任务引用：{tasks}。请先在任务路由为这些任务改选其它模型，再回来删除该连接。', removeDraftConnection: '将从当前草稿中移除模型服务「{name}」，保存后才生效。', replaceInRouting: '前往任务路由替换',
  apiKeyOptional: 'API 密钥（可选）',
} as const;

const en: Record<keyof typeof zh, string> = {
  runtimeSecret: 'Runtime-injected secrets are hidden. Re-enter the API key to test from Settings.', localPurpose: 'Connect a local model service', customPurpose: 'Connect a compatible custom model service', aggregatorPurpose: 'Connect a model aggregator', cloudPurpose: 'Connect a cloud model service', connectedCount: '{count} connected', connectionSucceeded: 'Connection succeeded', testFailed: 'Test failed', noDiscoveredModels: 'Connected, but no models were returned', noDiscoveredModelsHint: 'Confirm that the base URL exposes a compatible model-list endpoint, or add models manually below.', discoveredModels: 'Found {count} models', discoveryFailed: 'Model discovery failed', customProvider: 'Custom service', unsaved: 'Unsaved', incompleteDraft: 'Draft · Incomplete', enabled: 'Enabled', disabled: 'Disabled', testPassed: 'Test passed', testing: 'Testing', untested: 'Not tested', manageModels: 'Manage models for {name}', noModels: 'No models added. Select here to discover or add models manually.', usedBy: 'Used by: {tasks}', test: 'Test', edit: 'Edit', moreActions: 'More actions for {name}', disableConnection: 'Disable connection', enableConnection: 'Enable connection', deleteConnection: 'Delete connection', loadingModels: 'Loading model list…', duplicateName: 'Connection name already exists', editService: 'Edit model service', addService: 'Add model service', chooseProviderDescription: 'Choose a model provider, then enter credentials and select available models.', catalogFailed: 'Could not load model providers', retry: 'Retry', chooseProvider: 'Choose model provider', provider: 'Model provider', providerPlaceholder: 'Search or choose a provider', providerSearch: 'Search providers', cancel: 'Cancel', next: 'Next', connectionName: 'Connection name', protocol: 'Protocol', chooseProtocol: 'Choose protocol', providerProtocolRequired: 'This provider requires the {protocol} protocol.', baseUrl: 'Base URL', officialUrl: 'Use the provider endpoint', officialUrlHint: 'Uses the official endpoint; no value is required.', customUrl: 'Use a custom base URL', restoreOfficialUrl: 'Restore provider default', apiKey: 'API key', extraHeaders: 'Extra request headers (JSON)', extraHeadersPlaceholder: 'Enter a JSON object, or clear an invalid value', localKeyOptional: 'Local services may leave this blank', multipleKeys: 'Separate multiple keys with commas', getKey: 'Get a key:', availableModels: 'Available models', removeModel: 'Remove model {model}', cannotDeleteModel: 'Model cannot be deleted', modelReferenced: 'This model is used by:', replacementModel: 'Replacement model', chooseReplacement: 'Choose a replacement', searchReplacement: 'Search replacements', replaceAndDelete: 'Replace references and delete', goTaskRouting: 'Go to task routing', gettingModels: 'Loading…', getModels: 'Get models', discoveryDescription: 'Fetch available models from this service and review them before adding them.', noDiscovery: 'This service does not support model discovery. Add model IDs manually below.', addModelAria: 'Add a model manually', addModelPlaceholder: 'Enter a model ID and press Enter', add: 'Add', manualModel: 'Model not listed? Add it manually', testConnection: 'Test connection', enableThis: 'Enable this connection', disabledDraftHint: 'Disabled connections stay in the draft and are excluded from task routing.', enableAria: 'Enable this connection', missingBeforeEnable: 'Complete these fields before enabling', fixName: 'Fix the connection name', incompleteSavedDraft: 'Incomplete fields remain in the draft: {issues}', back: 'Back', saveChanges: 'Save changes', addToConfig: 'Add to configuration', readonly: 'Model configuration is managed externally. This page is read-only.', viewDetails: 'View details', emptyTitle: 'No model services connected', emptyDescription: 'Connect a service to choose models for reports, Agent, and vision tasks.', invalidTitle: 'Incomplete model services cannot be saved', invalidDescription: 'Complete these model services before using Save & Apply:', connectionNumber: 'Connection #{number}', assignModels: 'Assign models in Task routing →', cannotDeleteConnection: 'Connection cannot be deleted', deleteConnectionTitle: 'Delete connection?', referencedConnection: 'Model service "{name}" is used by: {tasks}. Choose replacement models in Task routing before deleting this connection.', removeDraftConnection: 'Remove model service "{name}" from the draft? This takes effect after saving.', replaceInRouting: 'Replace in Task routing',
  apiKeyOptional: 'API key (optional)',
};

export const MODEL_ACCESS_TEXT: Record<UiLanguage, Record<keyof typeof zh, string>> = createUiLanguageRecord("locales.settingsModelAccess.MODEL_ACCESS_TEXT", { zh, en });

const editorZh = {
  testing: '测试中…',
  schemaUnavailableTitle: '连接 Schema 不完整或不可用',
  schemaUnavailableMessage: '模型服务连接已进入只读保护；请更新后端或恢复完整的连接 Schema 后重试。',
  readonly: '当前模型配置由外部配置管理，网页暂时只读。',
  viewDetails: '查看详情',
  catalogFailed: '模型服务列表加载失败',
  retry: '重试',
  emptyTitle: '还没有接入模型服务',
  emptyDescription: '接入后即可在任务路由中为报告、Agent 和视觉任务选择模型。',
  invalidTitle: '有模型服务未完成，无法保存',
  invalidDescription: '以下模型服务需补全；补全后会自动保存：',
  connectionNumber: '连接 #{number}',
  invalidConnection: '{name}：{issues}',
  assignModels: '前往任务路由分配模型 →',
  cannotDeleteConnection: '无法直接删除连接',
  deleteConnectionTitle: '删除连接？',
  referencedConnection: '模型服务「{name}」正被以下任务引用：{tasks}。请先在任务路由为这些任务改选其它模型，再回来删除该连接。',
  removeDraftConnection: '将移除模型服务「{name}」，确认后自动保存。',
  replaceInRouting: '前往任务路由替换',
  connectionTest: '连接测试',
  rawSummary: '原始摘要：{summary}',
  testedModel: '本次测试模型：{model}。',
  firstModelOnly: '基础连接测试默认只测试模型列表中的第一个模型。',
  adjustModelList: '若该模型不可用，请调整模型顺序或移除不可用模型后重试。',
  discoveryFormatHint: '该连接返回的 /models 响应格式不兼容，请改为手动填写模型列表。',
  completionFormatHint: '返回结构与预期不一致，请确认该连接兼容 Chat Completions 接口。',
  discoveryEmptyHint: '该连接的 /models 接口未返回可用模型 ID；请检查服务地址是否指向兼容的模型列表接口，或改为手动填写模型列表。',
} as const;

const editorEn: Record<keyof typeof editorZh, string> = {
  testing: 'Testing…',
  schemaUnavailableTitle: 'Connection Schema is incomplete or unavailable',
  schemaUnavailableMessage: 'Model-service connections are read-only until the backend provides a complete Connection Schema.',
  readonly: 'Model configuration is managed externally. This page is read-only.',
  viewDetails: 'View details',
  catalogFailed: 'Could not load model providers',
  retry: 'Retry',
  emptyTitle: 'No model services connected',
  emptyDescription: 'Connect a service to choose models for reports, Agent, and vision tasks.',
  invalidTitle: 'Incomplete model services cannot be saved',
  invalidDescription: 'Complete these model services; they will autosave when valid:',
  connectionNumber: 'Connection #{number}',
  invalidConnection: '{name}: {issues}',
  assignModels: 'Assign models in Task routing →',
  cannotDeleteConnection: 'Connection cannot be deleted',
  deleteConnectionTitle: 'Delete connection?',
  referencedConnection: 'Model service "{name}" is used by: {tasks}. Choose replacement models in Task routing before deleting this connection.',
  removeDraftConnection: 'Remove model service "{name}"? The change will autosave after confirmation.',
  replaceInRouting: 'Replace in Task routing',
  connectionTest: 'Connection test',
  rawSummary: 'Raw summary: {summary}',
  testedModel: 'Tested model: {model}.',
  firstModelOnly: 'The basic connection test checks only the first model in the list.',
  adjustModelList: 'If this model is unavailable, reorder or remove it and try again.',
  discoveryFormatHint: 'The /models response is incompatible. Add the model list manually.',
  completionFormatHint: 'The response shape is incompatible with Chat Completions.',
  discoveryEmptyHint: 'The /models endpoint returned no usable model IDs. Check the base URL or add the model list manually.',
};

export const MODEL_ACCESS_EDITOR_TEXT: Record<UiLanguage, Record<keyof typeof editorZh, string>> = createUiLanguageRecord("locales.settingsModelAccess.MODEL_ACCESS_EDITOR_TEXT", {
  zh: editorZh,
  en: editorEn,
});

export const MODEL_ACCESS_STAGE_LABELS: Record<UiLanguage, Record<string, string>> = createUiLanguageRecord("locales.settingsModelAccess.MODEL_ACCESS_STAGE_LABELS", {
  zh: { model_discovery: '模型发现', chat_completion: '聊天调用', response_parse: '响应解析', capability_json: 'JSON 能力', capability_tools: 'Tools 能力', capability_stream: 'Stream 能力', capability_vision: 'Vision 能力' },
  en: { model_discovery: 'Model discovery', chat_completion: 'Chat completion', response_parse: 'Response parsing', capability_json: 'JSON capability', capability_tools: 'Tools capability', capability_stream: 'Streaming capability', capability_vision: 'Vision capability' },
});

export const MODEL_ACCESS_ERROR_LABELS: Record<UiLanguage, Record<string, string>> = createUiLanguageRecord("locales.settingsModelAccess.MODEL_ACCESS_ERROR_LABELS", {
  zh: { auth: '鉴权失败', timeout: '请求超时', quota: '额度或限流', model_not_found: '模型不可用', request_blocked: '请求被拦截', empty_response: '空响应', format_error: '格式异常', network_error: '网络异常', invalid_config: '配置无效', unsupported_protocol: '协议暂不支持', capability_unsupported: '能力不支持', skipped: '已跳过' },
  en: { auth: 'Authentication failed', timeout: 'Request timed out', quota: 'Quota or rate limit', model_not_found: 'Model unavailable', request_blocked: 'Request blocked', empty_response: 'Empty response', format_error: 'Invalid response format', network_error: 'Network error', invalid_config: 'Invalid configuration', unsupported_protocol: 'Unsupported protocol', capability_unsupported: 'Capability unsupported', skipped: 'Skipped' },
});

export const MODEL_ACCESS_TROUBLESHOOTING: Record<UiLanguage, Record<string, string>> = createUiLanguageRecord("locales.settingsModelAccess.MODEL_ACCESS_TROUBLESHOOTING", {
  zh: { auth: '请检查 API 密钥是否正确、是否有多余空格，以及当前连接是否需要额外组织/项目权限。', timeout: '可重试；若持续超时，请检查服务地址、网络代理、服务商可用区或本地防火墙。', quota: '请检查余额、套餐额度、RPM/TPM 限流或并发设置，必要时稍后重试。', model_not_found: '请确认模型名与连接协议匹配，并先用“获取模型”核对该连接实际可用模型列表。', empty_response: '连接已连通但未返回正文；可尝试切换兼容模型、关闭额外响应模式后再测试。', network_error: '请检查服务地址、代理、TLS/证书、中转网关或本地网络策略，并可稍后重试。', invalid_config: '先补齐协议、服务地址、API 密钥和模型配置，再执行一键测试。', unsupported_protocol: '当前连接不支持自动模型发现，请改为手动维护模型列表。' },
  en: { auth: 'Check the API key, surrounding whitespace, and any required organization or project access.', timeout: 'Try again. If timeouts continue, check the base URL, proxy, provider region, and local firewall.', quota: 'Check account balance, plan limits, RPM/TPM limits, and concurrency before retrying.', model_not_found: 'Confirm that the model ID matches this connection, then compare it with the discovered model list.', empty_response: 'The connection succeeded but returned no content. Try a compatible model or disable extra response modes.', network_error: 'Check the base URL, proxy, TLS certificate, gateway, and local network policy, then retry.', invalid_config: 'Complete the protocol, base URL, API key, and model configuration before testing.', unsupported_protocol: 'This connection does not support automatic model discovery. Maintain the model list manually.' },
});

export const MODEL_ACCESS_REASON_HINTS: Record<UiLanguage, Record<string, string>> = createUiLanguageRecord("locales.settingsModelAccess.MODEL_ACCESS_REASON_HINTS", {
  zh: { missing_api_key: 'API 密钥为空，或逗号分隔后没有任何可用密钥；请填入至少一个有效密钥后再测试。', api_key_rejected: '服务商拒绝了当前 API 密钥；请检查密钥、组织/项目权限、区域和账号状态。', rate_limit: '服务商触发 RPM/TPM 或并发限流；请降低请求频率或稍后重试。', insufficient_balance: '服务商返回余额、账单或额度不足；请检查账户余额和套餐状态。', quota_exceeded: '服务商返回配额已耗尽；请确认账号套餐、余量和项目额度。', provider_blocked: '请求被服务商或中转网关拦截；请检查账号风控、地域限制、模型权限、网关策略、内容安全策略或请求来源限制。', dns_error: '域名解析失败；请检查服务地址域名、网络代理和 DNS 配置。', tls_error: 'TLS/证书握手失败；请检查 HTTPS 证书、中转网关或公司代理策略。', connection_refused: '目标服务拒绝连接；请确认服务地址端口、服务进程和防火墙配置。', model_access_denied: '当前账号无法使用该模型；请确认模型是否已开通、账号是否可见，或模型是否已被禁用。', provider_prefix_mismatch: '模型 provider 前缀与当前连接不匹配；请确认模型名是否应使用该连接的兼容路由。', capability_unsupported: '当前模型或兼容层不支持该能力；这不影响基础文本连接，可换模型或关闭该能力依赖。' },
  en: { missing_api_key: 'Enter at least one valid API key before testing.', api_key_rejected: 'The provider rejected this API key. Check the key, project access, region, and account status.', rate_limit: 'The provider rate-limited the request. Reduce request frequency or retry later.', insufficient_balance: 'The provider reported insufficient balance or billing credit. Check the account and plan.', quota_exceeded: 'The provider quota is exhausted. Check the plan and project limits.', provider_blocked: 'The provider or gateway blocked the request. Check account, region, model access, gateway, and content policies.', dns_error: 'DNS resolution failed. Check the base URL, proxy, and DNS configuration.', tls_error: 'TLS negotiation failed. Check the HTTPS certificate, gateway, and corporate proxy.', connection_refused: 'The service refused the connection. Check the port, service process, and firewall.', model_access_denied: 'This account cannot access the model. Confirm model access and account visibility.', provider_prefix_mismatch: 'The model provider prefix does not match this connection. Check the compatible route.', capability_unsupported: 'The model or compatibility layer does not support this capability. Basic text access may still work.' },
});

export const MODEL_ACCESS_ISSUES: Record<UiLanguage, Record<string, string>> = createUiLanguageRecord("locales.settingsModelAccess.MODEL_ACCESS_ISSUES", {
  zh: { name_required: '连接名称必填', name_invalid: '连接名称仅限小写字母、数字或下划线', missing_provider: '缺少模型服务商', missing_protocol: '缺少连接协议', missing_api_key: '缺少 API 密钥', missing_base_url: '缺少服务地址', missing_models: '至少配置一个模型', missing_extra_headers: '附加请求头必填', contract_unknown: '连接字段契约包含不支持的条件', schema_unavailable: '连接 Schema 不完整或不可用' },
  en: { name_required: 'Connection name is required', name_invalid: 'Use lowercase letters, numbers, or underscores', missing_provider: 'Model provider is required', missing_protocol: 'Connection protocol is required', missing_api_key: 'API key is required', missing_base_url: 'Base URL is required', missing_models: 'Add at least one model', missing_extra_headers: 'Extra headers are required', contract_unknown: 'The Connection field contract contains an unsupported condition', schema_unavailable: 'Connection Schema is incomplete or unavailable' },
});

export function localizeModelAccessIssue(issue: string, language: UiLanguage): string {
  const codeByZh: Record<string, keyof typeof MODEL_ACCESS_ISSUES.zh> = {
    '连接名称必填': 'name_required', '连接名称仅限小写字母、数字或下划线': 'name_invalid', '缺少模型服务商': 'missing_provider', '缺少连接协议': 'missing_protocol', '缺少 API 密钥': 'missing_api_key', '缺少服务地址': 'missing_base_url', '至少配置一个模型': 'missing_models', '附加请求头必填': 'missing_extra_headers', '连接字段契约包含不支持的条件': 'contract_unknown', '连接 Schema 不完整或不可用': 'schema_unavailable',
  };
  const code = codeByZh[issue];
  return code ? MODEL_ACCESS_ISSUES[language][code] : issue;
}
