import axios from 'axios';
import type { UiLanguage } from '../i18n/uiText';

export type ApiErrorCategory =
  | 'agent_disabled'
  | 'missing_params'
  | 'llm_not_configured'
  | 'model_tool_incompatible'
  | 'invalid_tool_call'
  | 'portfolio_oversell'
  | 'portfolio_busy'
  | 'upstream_llm_400'
  | 'upstream_timeout'
  | 'upstream_network'
  | 'local_connection_failed'
  | 'http_error'
  | 'unknown';

export interface ParsedApiError {
  title: string;
  message: string;
  rawMessage: string;
  status?: number;
  category: ApiErrorCategory;
  code?: string;
  params?: Record<string, unknown>;
  details?: unknown;
  traceId?: string;
}

type LocalizedErrorText = {
  category: ApiErrorCategory;
  zh: { title: string; message: string };
  en: { title: string; message: string };
};

const STABLE_ERROR_TEXT: Record<string, LocalizedErrorText> = {
  agent_disabled: {
    category: 'agent_disabled',
    zh: { title: 'Agent 模式未开启', message: '请先在设置中开启 Agent 模式，然后重试。' },
    en: { title: 'Agent mode is disabled', message: 'Enable Agent mode in Settings, then try again.' },
  },
  agent_request_failed: {
    category: 'unknown',
    zh: { title: 'Agent 请求失败', message: '请求未能完成，请稍后重试。' },
    en: { title: 'Agent request failed', message: 'The request could not be completed. Try again later.' },
  },
  agent_stream_failed: {
    category: 'upstream_network',
    zh: { title: 'Agent 响应中断', message: '流式响应未能完成，请重试。' },
    en: { title: 'Agent response interrupted', message: 'The streaming response could not be completed. Try again.' },
  },
  upstream_timeout: {
    category: 'upstream_timeout',
    zh: { title: '上游服务响应超时', message: '请稍后重试，或检查网络和代理设置。' },
    en: { title: 'The upstream service timed out', message: 'Try again later, or check the network and proxy settings.' },
  },
  notification_channels_missing: {
    category: 'http_error',
    zh: { title: '尚未配置通知渠道', message: '请先在设置中配置至少一个通知渠道。' },
    en: { title: 'No notification channel is configured', message: 'Configure at least one notification channel in Settings.' },
  },
  auth_disabled: {
    category: 'http_error',
    zh: { title: '密码登录尚未启用', message: '请先完成管理员认证设置。' },
    en: { title: 'Password login is disabled', message: 'Complete the administrator authentication setup first.' },
  },
  password_required: {
    category: 'missing_params',
    zh: { title: '请输入密码', message: '密码不能为空。' },
    en: { title: 'Password required', message: 'Enter a password to continue.' },
  },
  current_required: {
    category: 'missing_params',
    zh: { title: '请输入当前密码', message: '验证当前密码后才能继续。' },
    en: { title: 'Current password required', message: 'Verify the current password to continue.' },
  },
  password_mismatch: {
    category: 'http_error',
    zh: { title: '两次密码不一致', message: '请重新输入并确认相同的密码。' },
    en: { title: 'Passwords do not match', message: 'Re-enter the same password in both fields.' },
  },
  invalid_password: {
    category: 'http_error',
    zh: { title: '密码验证失败', message: '请检查密码后重试。' },
    en: { title: 'Password verification failed', message: 'Check the password and try again.' },
  },
  password_already_set: {
    category: 'http_error',
    zh: { title: '管理员密码已存在', message: '请使用当前密码启用认证，或登录后修改密码。' },
    en: { title: 'Administrator password already exists', message: 'Use the current password to enable authentication, or change it after signing in.' },
  },
  not_changeable: {
    category: 'http_error',
    zh: { title: '无法在网页中修改密码', message: '请使用部署环境支持的密码管理方式。' },
    en: { title: 'Password cannot be changed here', message: 'Use the password management method supported by this deployment.' },
  },
  rate_limited: {
    category: 'http_error',
    zh: { title: '尝试次数过多', message: '请稍后再试。' },
    en: { title: 'Too many attempts', message: 'Wait a moment, then try again.' },
  },
  validation_error: {
    category: 'missing_params',
    zh: { title: '输入未通过验证', message: '请检查标记的字段后重试。' },
    en: { title: 'Input validation failed', message: 'Review the highlighted fields and try again.' },
  },
  portfolio_oversell: {
    category: 'portfolio_oversell',
    zh: { title: '卖出数量超过可用持仓', message: '请修正对应卖出记录后重试。' },
    en: { title: 'Sell quantity exceeds available holdings', message: 'Correct the related sell entry, then try again.' },
  },
  portfolio_busy: {
    category: 'portfolio_busy',
    zh: { title: '持仓账本正忙', message: '另一笔持仓变更正在处理，请稍后重试。' },
    en: { title: 'The portfolio ledger is busy', message: 'Another portfolio change is being processed. Try again shortly.' },
  },
  idempotency_key_reused: {
    category: 'http_error',
    zh: { title: '操作标识已被使用', message: '请刷新当前数据后重新提交。' },
    en: { title: 'Operation identifier already used', message: 'Refresh the current data before submitting again.' },
  },
  alphasift_unavailable: {
    category: 'http_error',
    zh: { title: 'AlphaSift 未就绪', message: '请检查 AlphaSift 配置和运行环境后重试。' },
    en: { title: 'AlphaSift is unavailable', message: 'Check the AlphaSift configuration and runtime, then try again.' },
  },
  alphasift_adapter_unavailable: {
    category: 'http_error',
    zh: { title: 'AlphaSift 适配层不可用', message: '请重新安装或升级 AlphaSift 后重试。' },
    en: { title: 'AlphaSift adapter is unavailable', message: 'Reinstall or upgrade AlphaSift, then try again.' },
  },
  alphasift_screen_task_not_found: {
    category: 'http_error',
    zh: { title: '选股任务不可恢复', message: '任务记录可能已清理，请重新运行选股。' },
    en: { title: 'Screening task cannot be recovered', message: 'The task record may have expired. Run the screening again.' },
  },
  alphasift_screen_failed: {
    category: 'upstream_network',
    zh: { title: 'AlphaSift 选股失败', message: '请稍后重试，或检查行情、模型服务和网络设置。' },
    en: { title: 'AlphaSift screening failed', message: 'Try again later, or check market data, model services, and network settings.' },
  },
  internal_error: {
    category: 'unknown',
    zh: { title: '服务暂时不可用', message: '请求未能完成，请稍后重试。' },
    en: { title: 'Service temporarily unavailable', message: 'The request could not be completed. Try again later.' },
  },
};

const EN_ERROR_TEXT: Record<ApiErrorCategory, { title: string; message: string }> = {
  agent_disabled: { title: 'Agent mode is disabled', message: 'Enable Agent mode, then try again.' },
  missing_params: { title: 'Required input is missing', message: 'Provide the required stock code or input, then try again.' },
  llm_not_configured: { title: 'No LLM model is configured', message: 'Configure a primary model, connection, or API key in Settings, then try again.' },
  model_tool_incompatible: { title: 'The model does not support tool calls', message: 'Choose a model that supports Agent tool calls, then try again.' },
  invalid_tool_call: { title: 'The model returned an invalid tool call', message: 'Choose another model or disable the incompatible reasoning mode, then try again.' },
  portfolio_oversell: { title: 'Sell quantity exceeds available holdings', message: 'Correct or remove the related sell entry, then try again.' },
  portfolio_busy: { title: 'The portfolio ledger is busy', message: 'Another portfolio change is being processed. Try again shortly.' },
  upstream_llm_400: { title: 'The model provider rejected the request', message: 'Check the model name, request parameters, and tool-call compatibility.' },
  upstream_timeout: { title: 'The upstream service timed out', message: 'Try again later, or check the network and proxy settings.' },
  upstream_network: { title: 'The server cannot reach an external dependency', message: 'Check proxy, DNS, and outbound network settings, then try again.' },
  local_connection_failed: { title: 'Cannot connect to the local service', message: 'Check that the Web service is running and that its address and port are reachable.' },
  http_error: { title: 'Request failed', message: 'The request could not be completed. Review the details and try again.' },
  unknown: { title: 'Request failed', message: 'The request could not be completed. Try again later.' },
};

export function localizeParsedApiError(error: ParsedApiError, language: UiLanguage): ParsedApiError {
  if (error.code) {
    const stable = STABLE_ERROR_TEXT[error.code];
    const localized = stable?.[language] ?? (language === 'en' ? EN_ERROR_TEXT.unknown : {
      title: '请求失败',
      message: '请求未能完成，请稍后重试。',
    });
    return {
      ...error,
      title: localized.title,
      message: localized.message,
      category: stable?.category ?? 'unknown',
    };
  }
  if (language !== 'en') return error;
  const localized = EN_ERROR_TEXT[error.category] ?? EN_ERROR_TEXT.unknown;
  return {
    ...error,
    title: localized.title,
    message: localized.message,
  };
}

type ResponseLike = {
  status?: number;
  data?: unknown;
  statusText?: string;
};

type ErrorCarrier = {
  response?: ResponseLike;
  code?: string;
  message?: string;
  parsedError?: ParsedApiError;
  cause?: unknown;
};

type CreateParsedApiErrorOptions = {
  title: string;
  message: string;
  rawMessage?: string;
  status?: number;
  category?: ApiErrorCategory;
  code?: string;
  params?: Record<string, unknown>;
  details?: unknown;
  traceId?: string;
};

type StableErrorEnvelope = {
  code: string;
  message: string | null;
  params: Record<string, unknown>;
  details: unknown;
  traceId?: string;
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null;
}

function pickString(...values: unknown[]): string | null {
  for (const value of values) {
    if (typeof value === 'string' && value.trim()) {
      return value.trim();
    }
  }
  return null;
}

function stringifyValue(value: unknown): string | null {
  if (value === null || value === undefined) {
    return null;
  }

  if (typeof value === 'string') {
    return value.trim() || null;
  }

  if (typeof value === 'number' || typeof value === 'boolean') {
    return String(value);
  }

  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

function extractStableErrorEnvelope(data: unknown): StableErrorEnvelope | null {
  if (!isRecord(data)) {
    return null;
  }

  const nested = isRecord(data.detail) ? data.detail : null;
  const candidate = nested && pickString(nested.error, nested.code) ? nested : data;
  const code = pickString(candidate.error, candidate.code);
  if (!code) {
    return null;
  }

  const params = isRecord(candidate.params) ? candidate.params : {};
  const details = candidate.details ?? candidate.detail ?? {};
  const traceId = pickString(candidate.trace_id, candidate.traceId, data.trace_id, data.traceId) ?? undefined;
  return {
    code,
    message: pickString(candidate.message),
    params,
    details,
    traceId,
  };
}

function hasDiagnosticValue(value: unknown): boolean {
  if (value === null || value === undefined || value === '') {
    return false;
  }
  if (Array.isArray(value)) {
    return value.length > 0;
  }
  if (isRecord(value)) {
    return Object.keys(value).length > 0;
  }
  return true;
}

function formatEnvelopeDiagnostics(envelope: StableErrorEnvelope, status?: number): string {
  if (status !== undefined && status >= 500) {
    return envelope.traceId ? `Trace ID: ${envelope.traceId}` : 'Internal server error';
  }

  const parts: string[] = [];
  if (envelope.message) {
    parts.push(envelope.message);
  }
  if (hasDiagnosticValue(envelope.details)) {
    const serialized = stringifyValue(envelope.details);
    if (serialized) {
      parts.push(serialized);
    }
  }
  if (envelope.traceId) {
    parts.push(`Trace ID: ${envelope.traceId}`);
  }
  return parts.join('\n') || 'Request failed';
}

function getResponse(error: unknown): ResponseLike | undefined {
  if (!isRecord(error)) {
    return undefined;
  }

  const response = (error as ErrorCarrier).response;
  return response && typeof response === 'object' ? response : undefined;
}

function getErrorCode(error: unknown): string | undefined {
  return isRecord(error) && typeof (error as ErrorCarrier).code === 'string'
    ? (error as ErrorCarrier).code
    : undefined;
}

function getErrorMessage(error: unknown): string | null {
  if (typeof error === 'string') {
    return error.trim() || null;
  }

  if (error instanceof Error && error.message.trim()) {
    return error.message.trim();
  }

  if (isRecord(error) && typeof (error as ErrorCarrier).message === 'string') {
    const message = (error as ErrorCarrier).message?.trim();
    return message || null;
  }

  return null;
}

function getCauseMessage(error: unknown): string | null {
  if (!isRecord(error)) {
    return null;
  }

  return getErrorMessage((error as ErrorCarrier).cause);
}

function buildMatchText(parts: Array<string | undefined | null>): string {
  return parts
    .filter((part): part is string => typeof part === 'string' && part.trim().length > 0)
    .join(' | ')
    .toLowerCase();
}

function includesAny(haystack: string, needles: string[]): boolean {
  return needles.some((needle) => haystack.includes(needle.toLowerCase()));
}

function extractValidationDetail(detail: unknown): string | null {
  if (!Array.isArray(detail)) {
    return null;
  }

  const parts = detail
    .map((item) => {
      if (!isRecord(item)) {
        return stringifyValue(item);
      }

      const location = Array.isArray(item.loc)
        ? item.loc.map((segment) => String(segment)).join('.')
        : null;
      const message = pickString(item.msg, item.message, item.error);
      if (!location && !message) {
        return stringifyValue(item);
      }
      return [location, message].filter(Boolean).join(': ');
    })
    .filter((entry): entry is string => Boolean(entry));

  return parts.length > 0 ? parts.join('; ') : null;
}

export function extractErrorPayloadText(data: unknown): string | null {
  if (typeof data === 'string') {
    return data.trim() || null;
  }

  if (Array.isArray(data)) {
    return extractValidationDetail(data) ?? stringifyValue(data);
  }

  if (!isRecord(data)) {
    return stringifyValue(data);
  }

  const detail = data.detail;
  if (isRecord(detail)) {
    return (
      pickString(detail.message, detail.error)
      ?? extractValidationDetail(detail.detail)
      ?? stringifyValue(detail)
    );
  }

  return (
    pickString(
      detail,
      data.message,
      data.error,
      data.title,
      data.reason,
      data.description,
      data.msg,
    )
    ?? extractValidationDetail(detail)
    ?? stringifyValue(data)
  );
}

export function createParsedApiError(options: CreateParsedApiErrorOptions): ParsedApiError {
  return {
    title: options.title,
    message: options.message,
    rawMessage: options.rawMessage?.trim() || options.message,
    status: options.status,
    category: options.category ?? 'unknown',
    code: options.code,
    params: options.params,
    details: options.details,
    traceId: options.traceId,
  };
}

export function isParsedApiError(value: unknown): value is ParsedApiError {
  return isRecord(value)
    && typeof value.title === 'string'
    && typeof value.message === 'string'
    && typeof value.rawMessage === 'string'
    && typeof value.category === 'string';
}

export function isApiRequestError(
  value: unknown,
): value is Error & ErrorCarrier & { parsedError: ParsedApiError } {
  return value instanceof Error
    && isRecord(value)
    && isParsedApiError((value as ErrorCarrier).parsedError);
}

export function formatParsedApiError(parsed: ParsedApiError): string {
  if (!parsed.title.trim()) {
    return parsed.message;
  }
  if (parsed.title === parsed.message) {
    return parsed.title;
  }
  return `${parsed.title}：${parsed.message}`;
}

export function getParsedApiError(error: unknown, language: UiLanguage = 'zh'): ParsedApiError {
  if (isParsedApiError(error)) {
    return localizeParsedApiError(error, language);
  }
  if (isRecord(error) && isParsedApiError((error as ErrorCarrier).parsedError)) {
    return localizeParsedApiError((error as ErrorCarrier).parsedError as ParsedApiError, language);
  }
  return localizeParsedApiError(parseApiError(error), language);
}

export function createApiError(
  parsed: ParsedApiError,
  extra: { response?: ResponseLike; code?: string; cause?: unknown } = {},
): Error & ErrorCarrier & { status?: number; category: ApiErrorCategory; rawMessage: string } {
  const apiError = new Error(formatParsedApiError(parsed)) as Error & ErrorCarrier & {
    status?: number;
    category: ApiErrorCategory;
    rawMessage: string;
  };
  apiError.name = 'ApiRequestError';
  apiError.parsedError = parsed;
  apiError.response = extra.response;
  apiError.code = extra.code;
  apiError.status = parsed.status;
  apiError.category = parsed.category;
  apiError.rawMessage = parsed.rawMessage;
  if (extra.cause !== undefined) {
    apiError.cause = extra.cause;
  }
  return apiError;
}

export function attachParsedApiError(error: unknown): ParsedApiError {
  const parsed = parseApiError(error);
  if (isRecord(error)) {
    const carrier = error as ErrorCarrier;
    carrier.parsedError = parsed;
  }
  if (error instanceof Error) {
    error.name = 'ApiRequestError';
    error.message = formatParsedApiError(parsed);
  }
  return parsed;
}

export function isLocalConnectionFailure(error: unknown): boolean {
  return parseApiError(error).category === 'local_connection_failed';
}

export function parseApiError(error: unknown): ParsedApiError {
  const response = getResponse(error);
  const status = response?.status;
  const envelope = extractStableErrorEnvelope(response?.data);
  if (envelope) {
    const scrubInternal = status !== undefined && status >= 500;
    return localizeParsedApiError(createParsedApiError({
      title: '请求失败',
      message: '请求未能完成，请稍后重试。',
      rawMessage: formatEnvelopeDiagnostics(envelope, status),
      status,
      category: STABLE_ERROR_TEXT[envelope.code]?.category ?? 'unknown',
      code: envelope.code,
      params: scrubInternal ? {} : envelope.params,
      details: scrubInternal ? {} : envelope.details,
      traceId: envelope.traceId,
    }), 'zh');
  }

  if (response) {
    const legacyDiagnostic = status !== undefined && status >= 500
      ? pickString(response.statusText) ?? 'Internal server error'
      : extractErrorPayloadText(response.data)
        ?? pickString(response.statusText)
        ?? 'Request failed';
    return createParsedApiError({
      title: '请求失败',
      message: '请求未能完成，请稍后重试。',
      rawMessage: legacyDiagnostic,
      status,
      category: 'http_error',
    });
  }

  const payloadText: string | null = null;
  const errorCode: string | null = null;
  const errorMessage = getErrorMessage(error);
  const causeMessage = getCauseMessage(error);
  const code = getErrorCode(error);
  const rawMessage = pickString(payloadText, errorMessage, causeMessage, code)
    ?? '请求未成功完成，请稍后重试。';
  const matchText = buildMatchText([rawMessage, errorMessage, causeMessage, code, errorCode]);

  if (includesAny(matchText, ['agent mode is not enabled', 'agent_mode'])) {
    return createParsedApiError({
      title: 'Agent 模式未开启',
      message: '当前功能依赖 Agent 模式，请先开启后再重试。',
      rawMessage,
      status,
      category: 'agent_disabled',
    });
  }

  const hasStockCodeField = includesAny(matchText, ['stock_code', 'stock_codes']);
  const hasMissingParamText = includesAny(matchText, ['必须提供 stock_code 或 stock_codes', 'missing', 'required']);
  if (hasStockCodeField && hasMissingParamText) {
    return createParsedApiError({
      title: '请求缺少必要参数',
      message: '请先补充股票代码或必要输入后再试。',
      rawMessage,
      status,
      category: 'missing_params',
    });
  }

  if (errorCode === 'portfolio_oversell' || includesAny(matchText, ['oversell detected'])) {
    return createParsedApiError({
      title: '卖出数量超过可用持仓',
      message: '卖出数量超过当前可用持仓，请删除或修正对应卖出流水后重试。',
      rawMessage,
      status,
      category: 'portfolio_oversell',
    });
  }

  if (errorCode === 'portfolio_busy' || includesAny(matchText, ['portfolio ledger is busy'])) {
    return createParsedApiError({
      title: '持仓账本正忙',
      message: '持仓账本正在处理另一笔变更，请稍后重试。',
      rawMessage,
      status,
      category: 'portfolio_busy',
    });
  }

  if (errorCode === 'alphasift_install_failed') {
    return createParsedApiError({
      title: 'AlphaSift 修复安装失败',
      message: 'DSA 已尝试修复安装 AlphaSift，但 pip 安装未成功。请检查 ALPHASIFT_INSTALL_SPEC、网络代理或后端 Python 环境。',
      rawMessage,
      status,
      category: 'http_error',
    });
  }

  if (errorCode === 'alphasift_install_spec_missing') {
    return createParsedApiError({
      title: 'AlphaSift 安装来源未配置',
      message: '请先确认后端依赖已安装；如需使用修复安装入口，请配置受信任的 ALPHASIFT_INSTALL_SPEC。',
      rawMessage,
      status,
      category: 'http_error',
    });
  }

  if (errorCode === 'alphasift_install_spec_not_allowed') {
    return createParsedApiError({
      title: 'AlphaSift 安装来源受限',
      message: '修复安装仅允许使用受信任的 AlphaSift GitHub 来源；如需本地路径或 wheel，请先手动安装到当前 Python 环境。',
      rawMessage,
      status,
      category: 'http_error',
    });
  }

  if (errorCode === 'alphasift_unavailable' || includesAny(matchText, ['cannot import alphasift', 'alphasift.screen'])) {
    return createParsedApiError({
      title: 'AlphaSift 未就绪',
      message: rawMessage,
      rawMessage,
      status,
      category: 'http_error',
    });
  }

  if (errorCode === 'alphasift_adapter_unavailable') {
    return createParsedApiError({
      title: 'AlphaSift 适配层不可用',
      message: '当前 AlphaSift 版本缺少 DSA 稳定适配层。请重新安装或升级 AlphaSift 后再试。',
      category: 'http_error',
      rawMessage,
      status,
    });
  }

  if (errorCode === 'alphasift_screen_task_not_found') {
    return createParsedApiError({
      title: '选股任务不可恢复',
      message: '服务端没有找到这次选股任务，可能后端已重启或任务记录已清理，请重新运行选股。',
      rawMessage,
      status,
      category: 'http_error',
      code: errorCode,
    });
  }

  if (errorCode === 'alphasift_screen_failed') {
    return createParsedApiError({
      title: 'AlphaSift 选股失败',
      message: 'AlphaSift 运行时访问外部行情、快照或模型服务失败，请稍后重试，或检查网络与代理设置。',
      rawMessage,
      status,
      category: 'upstream_network',
      code: errorCode,
    });
  }

  const noConfiguredLlm = (
    includesAny(matchText, ['all llm models failed']) && includesAny(matchText, ['last error: none'])
  ) || includesAny(matchText, [
    'no llm configured',
    'no effective primary model configured',
    'litellm_model not configured',
    'ai analysis will be unavailable',
  ]);
  if (noConfiguredLlm) {
    return createParsedApiError({
      title: '系统没有配置可用的 LLM 模型',
      message: '请先在系统设置中配置主要模型、可用连接或相关 API 密钥后再重试。',
      rawMessage,
      status,
      category: 'llm_not_configured',
    });
  }

  if (includesAny(matchText, [
    'tool call',
    'function call',
    'does not support tools',
    'tools is not supported',
    'reasoning',
  ])) {
    return createParsedApiError({
      title: '当前模型不兼容工具调用',
      message: '当前模型不适合 Agent / 工具调用场景，请更换支持工具调用的模型后重试。',
      rawMessage,
      status,
      category: 'model_tool_incompatible',
    });
  }

  if (includesAny(matchText, [
    'thought_signature',
    'missing function',
    'missing tool',
    'invalid tool call',
    'invalid function call',
  ])) {
    return createParsedApiError({
      title: '上游模型返回的数据结构不完整',
      message: '上游模型返回的工具调用结构不符合要求，请更换模型或关闭相关推理模式后重试。',
      rawMessage,
      status,
      category: 'invalid_tool_call',
    });
  }

  if (includesAny(matchText, ['timeout', 'timed out', 'read timeout', 'connect timeout']) || code === 'ECONNABORTED') {
    return createParsedApiError({
      title: '连接上游服务超时',
      message: '服务端访问外部依赖时超时，请稍后重试，或检查当前网络与代理设置。',
      rawMessage,
      status,
      category: 'upstream_timeout',
    });
  }

  if (
    status === 502
    || status === 503
    || includesAny(matchText, [
      'dns',
      'enotfound',
      'name or service not known',
      'temporary failure in name resolution',
      'proxy',
      'tunnel',
      '502',
      '503',
    ])
  ) {
    return createParsedApiError({
      title: '服务端无法访问外部依赖',
      message: '页面已连接到本地服务，但本地服务访问外部模型或数据接口失败，请检查代理、DNS 或出网配置。',
      rawMessage,
      status,
      category: 'upstream_network',
    });
  }

  const hasLlmProviderHint = includesAny(matchText, [
    'chat/completions',
    'generativelanguage',
    'openai',
    'gemini',
  ]);
  if (status === 400 && hasLlmProviderHint) {
    return createParsedApiError({
      title: '上游模型接口拒绝了当前请求',
      message: '本地服务正常，但上游模型接口拒绝了请求，请检查模型名称、参数格式或工具调用兼容性。',
      rawMessage,
      status,
      category: 'upstream_llm_400',
    });
  }

  const localConnectionFailed = !response && (
    includesAny(matchText, ['fetch failed', 'failed to fetch', 'network error', 'connection refused', 'econnrefused'])
    || code === 'ERR_NETWORK'
    || code === 'ECONNREFUSED'
  );
  if (localConnectionFailed) {
    return createParsedApiError({
      title: '无法连接到本地服务',
      message: '浏览器当前无法连接到本地 Web 服务，请检查服务是否启动、监听地址是否正确、端口是否开放。',
      rawMessage,
      status,
      category: 'local_connection_failed',
    });
  }

  if (payloadText || status) {
    return createParsedApiError({
      title: '请求失败',
      message: payloadText ?? `请求未成功完成（HTTP ${status}）。`,
      rawMessage,
      status,
      category: 'http_error',
    });
  }

  return createParsedApiError({
    title: '请求失败',
    message: rawMessage,
    rawMessage,
    status,
    category: 'unknown',
  });
}

export function toApiErrorMessage(error: unknown, fallback = '请求未成功完成，请稍后重试。', language: UiLanguage = 'zh'): string {
  const parsed = getParsedApiError(error, language);
  const message = formatParsedApiError(parsed);
  return message.trim() || fallback;
}

export function isAxiosApiError(error: unknown): boolean {
  return axios.isAxiosError(error);
}
