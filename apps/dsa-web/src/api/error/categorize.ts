// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { createParsedApiError } from './parseCore';
import type { ParsedApiError } from './types';

export function buildMatchText(parts: Array<string | undefined | null>): string {
  return parts
    .filter((part): part is string => typeof part === 'string' && part.trim().length > 0)
    .join(' | ')
    .toLowerCase();
}

export function includesAny(haystack: string, needles: string[]): boolean {
  return needles.some((needle) => haystack.includes(needle.toLowerCase()));
}


export type HeuristicCategorizeInput = {
  status?: number;
  rawMessage: string;
  errorCode: string | null;
  transportCode?: string;
  matchText: string;
  hasResponse: boolean;
};

export function categorizeHeuristicError(input: HeuristicCategorizeInput): ParsedApiError | null {
  const { status, rawMessage, errorCode, transportCode: code, matchText, hasResponse } = input;

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
      message: 'StockPulse 已尝试修复安装 AlphaSift，但 pip 安装未成功。请检查 ALPHASIFT_INSTALL_SPEC、网络代理或后端 Python 环境。',
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
      message: '请检查安装状态和后端依赖后再试。',
      rawMessage,
      status,
      category: 'http_error',
    });
  }

  if (errorCode === 'alphasift_adapter_unavailable') {
    return createParsedApiError({
      title: 'AlphaSift 适配层不可用',
      message: '当前 AlphaSift 版本缺少 StockPulse 稳定适配层。请重新安装或升级 AlphaSift 后再试。',
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

  const localConnectionFailed = !hasResponse && (
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

  return null;
}

export function categorizeGenericHttpError(input: {
  status?: number;
  rawMessage: string;
  hasPayload: boolean;
}): ParsedApiError {
  if (input.hasPayload || input.status) {
    return createParsedApiError({
      title: '请求失败',
      message: '请求未能完成，请检查输入后重试。',
      rawMessage: input.rawMessage,
      status: input.status,
      category: 'http_error',
    });
  }
  return createParsedApiError({
    title: '请求失败',
    message: '请求未能完成，请稍后重试。',
    rawMessage: input.rawMessage,
    status: input.status,
    category: 'unknown',
  });
}
