import { createUiLanguageRecord } from '../i18n/createUiLanguageRecord';
import type { UiLanguage } from '../i18n/uiText';

const zh = {
  statusError: '有错误', statusAction: '需要操作', statusDirty: '有未保存修改',
  errorSummary: '有 {count} 项配置需要修正', errorSummaryOne: '有 {count} 项配置需要修正', jumpToField: '前往修正',
  helpLabel: '查看 {title} 配置说明',
  confidenceHigh: '高', confidenceMedium: '中', confidenceLow: '低',
  loadFailedSuffix: '加载失败', runtimeError: '该设置区域发生前端运行时异常，页面其他设置仍可继续使用。', diagnosticHint: '请补充 release 版本、运行环境和触发入口，便于定位问题。', errorSummaryPrefix: '错误摘要：',
  overviewTitle: '任务路由总览', overviewDescription: '每个任务当前的执行方式与生效模型，无需查看环境变量即可判断实际路径。', colTask: '任务', colBackend: '执行方式', colPrimary: '主要模型', colFallback: '备用模型', colStatus: '状态', inherited: '继承报告模型', none: '未配置', failover: '失败切换', editRouting: '前往任务路由',
} as const;

const en: Record<keyof typeof zh, string> = {
  statusError: 'has errors', statusAction: 'needs action', statusDirty: 'unsaved changes',
  errorSummary: '{count} settings need attention', errorSummaryOne: '{count} setting needs attention', jumpToField: 'Go to field',
  helpLabel: 'View {title} configuration help',
  confidenceHigh: 'High', confidenceMedium: 'Medium', confidenceLow: 'Low',
  loadFailedSuffix: ' failed to load', runtimeError: 'This settings area hit a frontend runtime error. Other settings remain usable.', diagnosticHint: 'Provide the release version, runtime environment, and trigger path to help diagnose the issue.', errorSummaryPrefix: 'Error summary: ',
  overviewTitle: 'Task routing overview', overviewDescription: 'The execution backend and effective model for each task, without exposing environment variables.', colTask: 'Task', colBackend: 'Execution backend', colPrimary: 'Primary model', colFallback: 'Fallback models', colStatus: 'Status', inherited: 'inherits report model', none: 'not configured', failover: 'failover', editRouting: 'Edit task routing',
};

export const SETTINGS_MISC_TEXT: Record<UiLanguage, Record<keyof typeof zh, string>> = createUiLanguageRecord("locales.settingsMisc.SETTINGS_MISC_TEXT", { zh, en });

export const SETTINGS_OVERVIEW_STATUS: Record<UiLanguage, Record<'active' | 'unavailable' | 'unconfigured', string>> = createUiLanguageRecord("locales.settingsMisc.SETTINGS_OVERVIEW_STATUS", {
  zh: { active: '生效', unavailable: '当前配置不可用', unconfigured: '待配置' },
  en: { active: 'Active', unavailable: 'Unavailable', unconfigured: 'Needs config' },
});
