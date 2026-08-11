// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { createUiLanguageRecord } from '../../i18n/createUiLanguageRecord';
import type { UiLanguage } from '../../i18n/uiText';
import { APP_ROUTE_PATHS, buildSettingsHref } from '../../routing/routes';
import type {
  ApiErrorCategory,
  ErrorRemediation,
  ParsedApiError,
  StableErrorText,
} from './types';

export const STABLE_ERROR_TEXT: Record<string, StableErrorText> = {
  unauthorized: createUiLanguageRecord("api.error.STABLE_ERROR_TEXT.unauthorized", {
    zh: { title: '需要登录', message: '登录状态已失效，请重新登录。' },
    en: { title: 'Sign-in required', message: 'Your session has expired. Sign in again.' },
  }),
  approval_auth_required: createUiLanguageRecord("api.error.STABLE_ERROR_TEXT.approval_auth_required", {
    zh: {
      title: '需要启用管理员认证',
      message: '人工审批要求 ADMIN_AUTH_ENABLED=true 且持有有效管理员会话；认证关闭时返回 403。',
    },
    en: {
      title: 'Administrator authentication required',
      message: 'Human approvals require ADMIN_AUTH_ENABLED=true and a valid administrator session; disabled authentication returns 403.',
    },
  }),
  auth_disabled: createUiLanguageRecord("api.error.STABLE_ERROR_TEXT.auth_disabled", {
    zh: { title: '密码登录未启用', message: '当前服务尚未启用密码登录。' },
    en: { title: 'Password login is disabled', message: 'Password login is not enabled for this service.' },
  }),
  security_audit_auth_required: createUiLanguageRecord("api.error.STABLE_ERROR_TEXT.security_audit_auth_required", {
    zh: { title: '安全审计需要管理员认证', message: '管理员认证未启用时无法查询审计事件（HTTP 403）。请先启用认证并登录。' },
    en: { title: 'Security audit requires administrator authentication', message: 'Audit events cannot be queried while administrator authentication is disabled (HTTP 403). Enable authentication and sign in first.' },
  }),
  security_audit_unavailable: createUiLanguageRecord("api.error.STABLE_ERROR_TEXT.security_audit_unavailable", {
    zh: { title: '安全审计存储不可用', message: '无法读写安全审计记录。请稍后重试，或检查数据库与迁移状态。' },
    en: { title: 'Security audit storage is unavailable', message: 'Security audit records cannot be read or written. Retry later, or check the database and migration state.' },
  }),
  password_required: createUiLanguageRecord("api.error.STABLE_ERROR_TEXT.password_required", {
    zh: { title: '请输入密码', message: '填写所需密码后再试。' },
    en: { title: 'Password required', message: 'Enter the required password and try again.' },
  }),
  current_required: createUiLanguageRecord("api.error.STABLE_ERROR_TEXT.current_required", {
    zh: { title: '需要当前密码', message: '填写当前管理员密码后再试。' },
    en: { title: 'Current password required', message: 'Enter the current administrator password and try again.' },
  }),
  password_mismatch: createUiLanguageRecord("api.error.STABLE_ERROR_TEXT.password_mismatch", {
    zh: { title: '两次密码不一致', message: '确认两次输入完全一致后再试。' },
    en: { title: 'Passwords do not match', message: 'Make sure both password entries match.' },
  }),
  password_already_set: createUiLanguageRecord("api.error.STABLE_ERROR_TEXT.password_already_set", {
    zh: { title: '管理员密码已存在', message: '请使用修改密码功能更新现有密码。' },
    en: { title: 'Administrator password already exists', message: 'Use Change password to update the existing password.' },
  }),
  invalid_password: createUiLanguageRecord("api.error.STABLE_ERROR_TEXT.invalid_password", {
    zh: { title: '密码验证失败', message: '检查密码后再试。' },
    en: { title: 'Password verification failed', message: 'Check the password and try again.' },
  }),
  not_changeable: createUiLanguageRecord("api.error.STABLE_ERROR_TEXT.not_changeable", {
    zh: { title: '无法在网页修改密码', message: '当前密码来源不支持在网页中修改。' },
    en: { title: 'Password cannot be changed here', message: 'This password source does not support changes from the Web app.' },
  }),
  rate_limited: createUiLanguageRecord("api.error.STABLE_ERROR_TEXT.rate_limited", {
    zh: { title: '尝试过于频繁', message: '请稍后再试。' },
    en: { title: 'Too many attempts', message: 'Wait a moment and try again.' },
  }),
  agent_disabled: createUiLanguageRecord("api.error.STABLE_ERROR_TEXT.agent_disabled", {
    category: 'agent_disabled',
    zh: { title: 'Agent 模式未开启', message: '当前功能依赖 Agent 模式，请先开启后再试。' },
    en: { title: 'Agent mode is disabled', message: 'Enable Agent mode, then try again.' },
  }),
  agent_chat_failed: createUiLanguageRecord("api.error.STABLE_ERROR_TEXT.agent_chat_failed", {
    zh: { title: 'Agent 请求失败', message: 'Agent 未能完成本次请求，请重试。' },
    en: { title: 'Agent request failed', message: 'The Agent could not complete this request. Try again.' },
  }),
  agent_research_failed: createUiLanguageRecord("api.error.STABLE_ERROR_TEXT.agent_research_failed", {
    zh: { title: '深度研究失败', message: '深度研究未能完成，请稍后重试。' },
    en: { title: 'Research failed', message: 'Deep research could not finish. Try again later.' },
  }),
  agent_stream_failed: createUiLanguageRecord("api.error.STABLE_ERROR_TEXT.agent_stream_failed", {
    category: 'upstream_network',
    zh: { title: 'Agent 响应中断', message: '流式响应未能完成，请重试。' },
    en: { title: 'Agent response interrupted', message: 'The streaming response did not finish. Try again.' },
  }),
  agent_stream_timeout: createUiLanguageRecord("api.error.STABLE_ERROR_TEXT.agent_stream_timeout", {
    category: 'upstream_timeout',
    zh: { title: 'Agent 响应超时', message: '本次请求等待时间过长，请稍后重试。' },
    en: { title: 'Agent response timed out', message: 'This request took too long. Try again later.' },
  }),
  validation_error: createUiLanguageRecord("api.error.STABLE_ERROR_TEXT.validation_error", {
    zh: { title: '输入未通过校验', message: '检查输入内容后再试。' },
    en: { title: 'Input validation failed', message: 'Check the input and try again.' },
  }),
  invalid_params: createUiLanguageRecord("api.error.STABLE_ERROR_TEXT.invalid_params", {
    zh: { title: '请求参数无效', message: '检查筛选条件或参数后再试。' },
    en: { title: 'Invalid request parameters', message: 'Check the filters or parameters and try again.' },
  }),
  not_found: createUiLanguageRecord("api.error.STABLE_ERROR_TEXT.not_found", {
    zh: { title: '未找到请求的内容', message: '该内容可能已删除、过期或尚未生成。' },
    en: { title: 'Requested content not found', message: 'It may have been removed, expired, or not generated yet.' },
  }),
  duplicate_task: createUiLanguageRecord("api.error.STABLE_ERROR_TEXT.duplicate_task", {
    zh: { title: '任务已在运行', message: '{stock_code} 已有分析任务，请等待当前任务完成。' },
    en: { title: 'Task already running', message: 'An analysis task for {stock_code} is already running.' },
  }),
  duplicate_market_review: createUiLanguageRecord("api.error.STABLE_ERROR_TEXT.duplicate_market_review", {
    zh: { title: '大盘复盘已在运行', message: '请等待当前复盘任务完成。' },
    en: { title: 'Market review already running', message: 'Wait for the current market review to finish.' },
  }),
  config_conflict: createUiLanguageRecord("api.error.STABLE_ERROR_TEXT.config_conflict", {
    zh: { title: '配置版本冲突', message: '服务器配置已更新，请刷新后重新应用本次修改。' },
    en: { title: 'Configuration conflict', message: 'The server configuration changed. Refresh and apply your changes again.' },
  }),
  config_version_conflict: createUiLanguageRecord("api.error.STABLE_ERROR_TEXT.config_version_conflict", {
    zh: { title: '配置版本冲突', message: '服务器配置已更新，请刷新后重新应用本次修改。' },
    en: { title: 'Configuration conflict', message: 'The server configuration changed. Refresh and apply your changes again.' },
  }),
  rollback_unavailable: createUiLanguageRecord("api.error.STABLE_ERROR_TEXT.rollback_unavailable", {
    zh: { title: '没有可回滚的配置', message: '当前没有可用的上一份稳定配置，未执行任何更改。' },
    en: { title: 'No configuration is available to roll back', message: 'There is no previous stable configuration available, so nothing was changed.' },
  }),
  validation_failed: createUiLanguageRecord("api.error.STABLE_ERROR_TEXT.validation_failed", {
    zh: { title: '配置校验失败', message: '检查标记的配置项后再试。' },
    en: { title: 'Configuration validation failed', message: 'Check the marked settings and try again.' },
  }),
  scheduler_busy: createUiLanguageRecord("api.error.STABLE_ERROR_TEXT.scheduler_busy", {
    zh: { title: '调度任务正忙', message: '已有调度任务正在执行，请稍后重试。' },
    en: { title: 'Scheduler is busy', message: 'A scheduled task is already running. Try again later.' },
  }),
  env_backup_access_denied: createUiLanguageRecord("api.error.STABLE_ERROR_TEXT.env_backup_access_denied", {
    zh: { title: '无权访问配置备份', message: '当前环境不允许执行此备份操作。' },
    en: { title: 'Configuration backup access denied', message: 'This environment does not allow that backup operation.' },
  }),
  invalid_import_file: createUiLanguageRecord("api.error.STABLE_ERROR_TEXT.invalid_import_file", {
    zh: { title: '导入文件无效', message: '检查文件类型与内容后再试。' },
    en: { title: 'Invalid import file', message: 'Check the file type and content, then try again.' },
  }),
  no_channels: createUiLanguageRecord("api.error.STABLE_ERROR_TEXT.no_channels", {
    zh: { title: '未配置通知渠道', message: '请先在设置中配置通知渠道。' },
    en: { title: 'No notification channel configured', message: 'Configure a notification channel in Settings first.' },
  }),
  conflict: createUiLanguageRecord("api.error.STABLE_ERROR_TEXT.conflict", {
    zh: { title: '操作发生冲突', message: '数据已发生变化，请刷新后重试。' },
    en: { title: 'Operation conflict', message: 'The data changed. Refresh and try again.' },
  }),
  unsupported_alert_type: createUiLanguageRecord("api.error.STABLE_ERROR_TEXT.unsupported_alert_type", {
    zh: { title: '不支持的告警类型', message: '请选择受支持的告警条件。' },
    en: { title: 'Unsupported alert type', message: 'Choose a supported alert condition.' },
  }),
  portfolio_oversell: createUiLanguageRecord("api.error.STABLE_ERROR_TEXT.portfolio_oversell", {
    category: 'portfolio_oversell',
    zh: { title: '卖出数量超过可用持仓', message: '修正对应卖出流水后再试。' },
    en: { title: 'Sell quantity exceeds available holdings', message: 'Correct the related sell entry and try again.' },
  }),
  portfolio_busy: createUiLanguageRecord("api.error.STABLE_ERROR_TEXT.portfolio_busy", {
    category: 'portfolio_busy',
    zh: { title: '持仓账本正忙', message: '另一笔变更正在处理，请稍后重试。' },
    en: { title: 'Portfolio ledger is busy', message: 'Another change is being processed. Try again shortly.' },
  }),
  idempotency_conflict: createUiLanguageRecord("api.error.STABLE_ERROR_TEXT.idempotency_conflict", {
    zh: { title: '提交标识冲突', message: '同一操作标识已用于不同内容，请刷新后重新提交。' },
    en: { title: 'Submission identifier conflict', message: 'This operation identifier was already used for different content. Refresh and submit again.' },
  }),
  operation_id_mismatch: createUiLanguageRecord("api.error.STABLE_ERROR_TEXT.operation_id_mismatch", {
    zh: { title: '提交标识不一致', message: '请求头与表单中的操作标识必须保持一致。' },
    en: { title: 'Submission identifiers do not match', message: 'The operation identifiers in the request header and form must match.' },
  }),
  alphasift_disabled: createUiLanguageRecord("api.error.STABLE_ERROR_TEXT.alphasift_disabled", {
    zh: { title: '选股功能未启用', message: '请先启用 AlphaSift 后再运行选股。' },
    en: { title: 'Screening is disabled', message: 'Enable AlphaSift before running a screen.' },
  }),
  alphasift_unavailable: createUiLanguageRecord("api.error.STABLE_ERROR_TEXT.alphasift_unavailable", {
    zh: { title: 'AlphaSift 未就绪', message: '检查安装状态和后端依赖后再试。' },
    en: { title: 'AlphaSift is unavailable', message: 'Check its installation and backend dependencies, then try again.' },
  }),
  alphasift_screen_task_not_found: createUiLanguageRecord("api.error.STABLE_ERROR_TEXT.alphasift_screen_task_not_found", {
    zh: { title: '选股任务不可恢复', message: '任务可能已过期或后端已重启，请重新运行选股。' },
    en: { title: 'Screening task cannot be restored', message: 'It may have expired or the backend restarted. Run the screen again.' },
  }),
  alphasift_screen_failed: createUiLanguageRecord("api.error.STABLE_ERROR_TEXT.alphasift_screen_failed", {
    category: 'upstream_network',
    zh: { title: 'AlphaSift 选股失败', message: '外部行情或模型服务不可用，请稍后重试。' },
    en: { title: 'AlphaSift screening failed', message: 'An external market-data or model service is unavailable. Try again later.' },
  }),
  internal_error: createUiLanguageRecord("api.error.STABLE_ERROR_TEXT.internal_error", {
    zh: { title: '服务器处理失败', message: '请稍后重试，并在问题持续时提供诊断编号。' },
    en: { title: 'Server request failed', message: 'Try again later and provide the diagnostic ID if the issue continues.' },
  }),
  analysis_failed: createUiLanguageRecord("api.error.STABLE_ERROR_TEXT.analysis_failed", {
    zh: { title: '分析失败', message: '分析未能完成，请检查配置后重试。' },
    en: { title: 'Analysis failed', message: 'The analysis could not finish. Check the configuration and try again.' },
  }),
  api_response_validation_failed: createUiLanguageRecord("api.error.STABLE_ERROR_TEXT.api_response_validation_failed", {
    category: 'unknown',
    zh: { title: '响应校验失败', message: '接口响应未通过校验（{label}）。{issues}' },
    en: { title: 'Response validation failed', message: 'API response failed validation ({label}). {issues}' },
  }),
  llm_not_configured: createUiLanguageRecord("api.error.STABLE_ERROR_TEXT.llm_not_configured", {
    category: 'llm_not_configured',
    zh: { title: '尚未配置 LLM 模型', message: '请在设置中配置主要模型、模型连接或 API Key。' },
    en: { title: 'No LLM model is configured', message: 'Configure a primary model, connection, or API key in Settings, then try again.' },
  }),
  share_image_content_too_large: createUiLanguageRecord("api.error.STABLE_ERROR_TEXT.share_image_content_too_large", {
    zh: {
      title: '报告内容过长，无法生成分享图片',
      message: '当前报告有 {actual} 个字符，超过分享图片上限 {limit}。可在设置中提高 SHARE_IMAGE_MAX_CHARS，或缩短报告后再试。',
    },
    en: {
      title: 'Report is too long to generate a share image',
      message: 'This report has {actual} characters, which exceeds the share-image limit of {limit}. Raise SHARE_IMAGE_MAX_CHARS in Settings, or shorten the report and try again.',
    },
  }),
  share_image_unavailable: createUiLanguageRecord("api.error.STABLE_ERROR_TEXT.share_image_unavailable", {
    zh: {
      title: '分享图片引擎不可用',
      message: '请检查转图工具是否已安装并可用。Playwright 引擎需要：cd apps/dsa-web && npm ci && npx playwright install chromium。',
    },
    en: {
      title: 'Share image renderer unavailable',
      message: 'Install and enable the image renderer. For Playwright: cd apps/dsa-web && npm ci && npx playwright install chromium.',
    },
  }),
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

const ZH_ERROR_TEXT: Record<ApiErrorCategory, { title: string; message: string }> = {
  agent_disabled: { title: 'Agent 模式未开启', message: '开启 Agent 模式后重试。' },
  missing_params: { title: '缺少必要输入', message: '提供所需股票代码或输入后重试。' },
  llm_not_configured: { title: '尚未配置 LLM 模型', message: '请在设置中配置主要模型、模型连接或 API Key。' },
  model_tool_incompatible: { title: '模型不支持工具调用', message: '请选择支持 Agent 工具调用的模型。' },
  invalid_tool_call: { title: '模型返回了无效工具调用', message: '请选择其他模型，或关闭不兼容的推理模式。' },
  portfolio_oversell: { title: '卖出数量超过可用持仓', message: '修正或删除对应卖出流水后重试。' },
  portfolio_busy: { title: '持仓账本正忙', message: '另一笔持仓变更正在处理，请稍后重试。' },
  upstream_llm_400: { title: '模型服务拒绝了请求', message: '请检查模型名称、请求参数和工具调用兼容性。' },
  upstream_timeout: { title: '上游服务响应超时', message: '请稍后重试，或检查网络和代理设置。' },
  upstream_network: { title: '服务器无法连接外部依赖', message: '请检查代理、DNS 和出站网络设置。' },
  local_connection_failed: { title: '无法连接本地服务', message: '请确认 Web 服务正在运行，并检查地址和端口。' },
  http_error: { title: '请求失败', message: '请求未能完成，请查看详情后重试。' },
  unknown: { title: '请求失败', message: '请求未能完成，请稍后重试。' },
};

export const GENERIC_ERROR_TEXT = createUiLanguageRecord('api.error.GENERIC_ERROR_TEXT', {
  zh: ZH_ERROR_TEXT,
  en: EN_ERROR_TEXT,
});

type RemediationDefinition = {
  href?: string;
  copy: Record<UiLanguage, { actionLabel: string; hint?: string }>;
};

const SETTINGS_AI_CONNECTIONS = buildSettingsHref({ section: 'ai_models', view: 'connections' });
const SETTINGS_AGENT_EXECUTION = buildSettingsHref({ section: 'agent_behavior', view: 'execution' });
const SETTINGS_AUTH_SECURITY = buildSettingsHref({ section: 'system_security', view: 'security' });
const SETTINGS_NOTIFICATIONS = buildSettingsHref({ section: 'notifications', view: 'channels' });
const SETTINGS_DATA_SOURCES = buildSettingsHref({ section: 'data_sources', view: 'sources' });
const SETTINGS_REPORTS = buildSettingsHref({ section: 'reports', view: 'output' });
const SETTINGS_OVERVIEW = buildSettingsHref({ section: 'overview', view: 'readiness' });

const ERROR_REMEDIATION_BY_CODE: Record<string, RemediationDefinition> = {
  llm_not_configured: {
    href: SETTINGS_AI_CONNECTIONS,
    copy: createUiLanguageRecord('api.error.ERROR_REMEDIATION.llm_not_configured', {
      zh: { actionLabel: '打开模型设置', hint: '在「AI 与模型 → 模型接入」中配置主要模型或 API Key。' },
      en: { actionLabel: 'Open model settings', hint: 'Configure a primary model or API key under AI & Models → Model Access.' },
    }),
  },
  unauthorized: {
    href: APP_ROUTE_PATHS.login,
    copy: createUiLanguageRecord('api.error.ERROR_REMEDIATION.unauthorized', {
      zh: { actionLabel: '前往登录', hint: '登录状态已失效，重新登录后即可继续。' },
      en: { actionLabel: 'Go to sign-in', hint: 'Your session expired. Sign in again to continue.' },
    }),
  },
  agent_disabled: {
    href: SETTINGS_AGENT_EXECUTION,
    copy: createUiLanguageRecord('api.error.ERROR_REMEDIATION.agent_disabled', {
      zh: { actionLabel: '打开 Agent 设置', hint: '在「Agent 行为 → 执行」中启用 Agent 模式。' },
      en: { actionLabel: 'Open Agent settings', hint: 'Enable Agent mode under Agent Behavior → Execution.' },
    }),
  },
  auth_disabled: {
    href: SETTINGS_AUTH_SECURITY,
    copy: createUiLanguageRecord('api.error.ERROR_REMEDIATION.auth_disabled', {
      zh: { actionLabel: '打开认证设置', hint: '在「系统与安全 → 认证与安全」中启用密码登录。' },
      en: { actionLabel: 'Open auth settings', hint: 'Enable password login under System & Security → Auth & Security.' },
    }),
  },
  approval_auth_required: {
    href: SETTINGS_AUTH_SECURITY,
    copy: createUiLanguageRecord('api.error.ERROR_REMEDIATION.approval_auth_required', {
      zh: { actionLabel: '打开认证设置', hint: '启用管理员认证并登录后，才能使用人工审批。' },
      en: { actionLabel: 'Open auth settings', hint: 'Enable administrator authentication and sign in to use human approvals.' },
    }),
  },
  security_audit_auth_required: {
    href: SETTINGS_AUTH_SECURITY,
    copy: createUiLanguageRecord('api.error.ERROR_REMEDIATION.security_audit_auth_required', {
      zh: { actionLabel: '打开认证设置', hint: '启用管理员认证并登录后，才能查看安全审计。' },
      en: { actionLabel: 'Open auth settings', hint: 'Enable administrator authentication and sign in to view the security audit.' },
    }),
  },
  no_channels: {
    href: SETTINGS_NOTIFICATIONS,
    copy: createUiLanguageRecord('api.error.ERROR_REMEDIATION.no_channels', {
      zh: { actionLabel: '配置通知渠道', hint: '在「通知 → 渠道」中至少配置一个可用渠道。' },
      en: { actionLabel: 'Configure channels', hint: 'Add at least one channel under Notifications → Channels.' },
    }),
  },
  config_conflict: {
    href: SETTINGS_OVERVIEW,
    copy: createUiLanguageRecord('api.error.ERROR_REMEDIATION.config_conflict', {
      zh: { actionLabel: '刷新设置页', hint: '服务器配置已更新。刷新后重新应用你的修改。' },
      en: { actionLabel: 'Refresh settings', hint: 'Server configuration changed. Refresh and re-apply your edits.' },
    }),
  },
  config_version_conflict: {
    href: SETTINGS_OVERVIEW,
    copy: createUiLanguageRecord('api.error.ERROR_REMEDIATION.config_version_conflict', {
      zh: { actionLabel: '刷新设置页', hint: '服务器配置已更新。刷新后重新应用你的修改。' },
      en: { actionLabel: 'Refresh settings', hint: 'Server configuration changed. Refresh and re-apply your edits.' },
    }),
  },
  rate_limited: {
    copy: createUiLanguageRecord('api.error.ERROR_REMEDIATION.rate_limited', {
      zh: { actionLabel: '稍后再试', hint: '请求过于频繁，请等待片刻后重试。' },
      en: { actionLabel: 'Try again later', hint: 'Too many attempts. Wait a moment, then retry.' },
    }),
  },
  alphasift_disabled: {
    href: SETTINGS_DATA_SOURCES,
    copy: createUiLanguageRecord('api.error.ERROR_REMEDIATION.alphasift_disabled', {
      zh: { actionLabel: '打开数据源设置', hint: '在设置中启用 AlphaSift 后再运行选股。' },
      en: { actionLabel: 'Open data source settings', hint: 'Enable AlphaSift in Settings before running a screen.' },
    }),
  },
  alphasift_unavailable: {
    href: SETTINGS_DATA_SOURCES,
    copy: createUiLanguageRecord('api.error.ERROR_REMEDIATION.alphasift_unavailable', {
      zh: { actionLabel: '检查选股依赖', hint: '确认 AlphaSift 已安装，并检查后端依赖状态。' },
      en: { actionLabel: 'Check screening setup', hint: 'Confirm AlphaSift is installed and backend dependencies are healthy.' },
    }),
  },
  model_tool_incompatible: {
    href: SETTINGS_AI_CONNECTIONS,
    copy: createUiLanguageRecord('api.error.ERROR_REMEDIATION.model_tool_incompatible', {
      zh: { actionLabel: '更换模型', hint: '在「AI 与模型 → 模型接入」中选择支持工具调用的模型。' },
      en: { actionLabel: 'Change model', hint: 'Pick a tool-capable model under AI & Models → Model Access.' },
    }),
  },
  invalid_tool_call: {
    href: SETTINGS_AI_CONNECTIONS,
    copy: createUiLanguageRecord('api.error.ERROR_REMEDIATION.invalid_tool_call', {
      zh: { actionLabel: '调整模型配置', hint: '更换模型，或关闭不兼容的推理模式后重试。' },
      en: { actionLabel: 'Adjust model settings', hint: 'Switch models, or disable an incompatible reasoning mode, then retry.' },
    }),
  },
  share_image_content_too_large: {
    href: SETTINGS_REPORTS,
    copy: createUiLanguageRecord('api.error.ERROR_REMEDIATION.share_image_content_too_large', {
      zh: { actionLabel: '打开报告设置', hint: '可在「报告 → 输出」提高 SHARE_IMAGE_MAX_CHARS，或缩短报告内容。' },
      en: { actionLabel: 'Open report settings', hint: 'Raise SHARE_IMAGE_MAX_CHARS under Reports → Output, or shorten the report.' },
    }),
  },
  invalid_password: {
    href: APP_ROUTE_PATHS.login,
    copy: createUiLanguageRecord('api.error.ERROR_REMEDIATION.invalid_password', {
      zh: { actionLabel: '重新登录', hint: '核对密码后重试；如忘记密码，请在认证设置中处理。' },
      en: { actionLabel: 'Sign in again', hint: 'Check the password and try again. Use auth settings if you need a reset path.' },
    }),
  },
  analysis_failed: {
    href: SETTINGS_OVERVIEW,
    copy: createUiLanguageRecord('api.error.ERROR_REMEDIATION.analysis_failed', {
      zh: { actionLabel: '检查就绪状态', hint: '在「概览 → 就绪状态」确认模型与数据源配置完整。' },
      en: { actionLabel: 'Check readiness', hint: 'Confirm model and data-source setup under Overview → Readiness.' },
    }),
  },
  local_connection_failed: {
    copy: createUiLanguageRecord('api.error.ERROR_REMEDIATION.local_connection_failed', {
      zh: { actionLabel: '检查本地服务', hint: '确认 Web 服务已启动，并检查地址与端口是否可访问。' },
      en: { actionLabel: 'Check local service', hint: 'Confirm the Web service is running and its host/port are reachable.' },
    }),
  },
  upstream_timeout: {
    copy: createUiLanguageRecord('api.error.ERROR_REMEDIATION.upstream_timeout', {
      zh: { actionLabel: '稍后重试', hint: '上游服务响应超时。可稍后重试，或检查网络与代理设置。' },
      en: { actionLabel: 'Retry later', hint: 'The upstream service timed out. Retry later, or check network and proxy settings.' },
    }),
  },
  upstream_network: {
    copy: createUiLanguageRecord('api.error.ERROR_REMEDIATION.upstream_network', {
      zh: { actionLabel: '检查出站网络', hint: '本地服务正常，但无法访问外部依赖。请检查代理、DNS 与出站策略。' },
      en: { actionLabel: 'Check outbound network', hint: 'The local service is up, but an external dependency is unreachable. Check proxy, DNS, and outbound policy.' },
    }),
  },
};

const ERROR_REMEDIATION_BY_CATEGORY: Partial<Record<ApiErrorCategory, RemediationDefinition>> = {
  llm_not_configured: ERROR_REMEDIATION_BY_CODE.llm_not_configured,
  agent_disabled: ERROR_REMEDIATION_BY_CODE.agent_disabled,
  model_tool_incompatible: ERROR_REMEDIATION_BY_CODE.model_tool_incompatible,
  invalid_tool_call: ERROR_REMEDIATION_BY_CODE.invalid_tool_call,
  local_connection_failed: ERROR_REMEDIATION_BY_CODE.local_connection_failed,
  upstream_timeout: ERROR_REMEDIATION_BY_CODE.upstream_timeout,
  upstream_network: ERROR_REMEDIATION_BY_CODE.upstream_network,
};

export function resolveErrorRemediation(
  error: ParsedApiError,
  language: UiLanguage,
): ErrorRemediation | null {
  const definition = (
    (error.code ? ERROR_REMEDIATION_BY_CODE[error.code] : undefined)
    ?? ERROR_REMEDIATION_BY_CATEGORY[error.category]
  );
  if (!definition) return null;
  const localized = definition.copy[language] ?? definition.copy.en;
  return {
    actionLabel: localized.actionLabel,
    hint: localized.hint,
    href: definition.href,
  };
}
