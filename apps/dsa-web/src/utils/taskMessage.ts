// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { createUiLanguageRecord } from '../i18n/createUiLanguageRecord';
import type { UiLanguage } from '../i18n/uiText';

type TaskMessageLike = {
  status?: string | null;
  message?: string | null;
  messageCode?: string | null;
  messageParams?: Record<string, unknown> | null;
};

type LocalizedTaskMessage = Record<UiLanguage, string>;

const TASK_MESSAGE_TEXT: Record<string, LocalizedTaskMessage> = {
  'task.queued': createUiLanguageRecord("utils.taskMessage.TASK_MESSAGE_TEXT.task.queued", { zh: '任务已加入队列', en: 'Task queued' }),
  'task.processing': createUiLanguageRecord("utils.taskMessage.TASK_MESSAGE_TEXT.task.processing", { zh: '任务执行中', en: 'Task in progress' }),
  'task.completed': createUiLanguageRecord("utils.taskMessage.TASK_MESSAGE_TEXT.task.completed", { zh: '任务执行完成', en: 'Task completed' }),
  'task.failed': createUiLanguageRecord("utils.taskMessage.TASK_MESSAGE_TEXT.task.failed", { zh: '任务执行失败', en: 'Task failed' }),
  'task.analysis.preparing': createUiLanguageRecord("utils.taskMessage.TASK_MESSAGE_TEXT.task.analysis.preparing", { zh: '{subject}正在准备分析任务', en: 'Preparing analysis for {subject}' }),
  'task.analysis.market_data': createUiLanguageRecord("utils.taskMessage.TASK_MESSAGE_TEXT.task.analysis.market_data", { zh: '{subject}正在获取行情与筹码数据', en: 'Loading market and position data for {subject}' }),
  'task.analysis.market_data_ready': createUiLanguageRecord("utils.taskMessage.TASK_MESSAGE_TEXT.task.analysis.market_data_ready", { zh: '{subject}行情数据准备完成', en: 'Market data is ready for {subject}' }),
  'task.analysis.fundamentals': createUiLanguageRecord("utils.taskMessage.TASK_MESSAGE_TEXT.task.analysis.fundamentals", { zh: '{subject}正在聚合基本面与趋势数据', en: 'Loading fundamentals and trend data for {subject}' }),
  'task.analysis.agent': createUiLanguageRecord("utils.taskMessage.TASK_MESSAGE_TEXT.task.analysis.agent", { zh: '{subject}正在切换 Agent 分析链路', en: 'Starting the Agent analysis path for {subject}' }),
  'task.analysis.news': createUiLanguageRecord("utils.taskMessage.TASK_MESSAGE_TEXT.task.analysis.news", { zh: '{subject}正在检索新闻与舆情', en: 'Searching news and sentiment for {subject}' }),
  'task.analysis.context': createUiLanguageRecord("utils.taskMessage.TASK_MESSAGE_TEXT.task.analysis.context", { zh: '{subject}正在整理分析上下文', en: 'Preparing analysis context for {subject}' }),
  'task.analysis.llm': createUiLanguageRecord("utils.taskMessage.TASK_MESSAGE_TEXT.task.analysis.llm", { zh: '{subject}正在请求模型生成报告', en: 'Generating the report for {subject}' }),
  'task.analysis.validating': createUiLanguageRecord("utils.taskMessage.TASK_MESSAGE_TEXT.task.analysis.validating", { zh: '{subject}正在校验并整理分析结果', en: 'Validating analysis results for {subject}' }),
  'task.analysis.saving': createUiLanguageRecord("utils.taskMessage.TASK_MESSAGE_TEXT.task.analysis.saving", { zh: '{subject}正在保存分析报告', en: 'Saving the analysis report for {subject}' }),
  'task.analysis.processing': createUiLanguageRecord("utils.taskMessage.TASK_MESSAGE_TEXT.task.analysis.processing", { zh: '正在分析中', en: 'Analysis in progress' }),
  'task.analysis.completed': createUiLanguageRecord("utils.taskMessage.TASK_MESSAGE_TEXT.task.analysis.completed", { zh: '分析完成', en: 'Analysis completed' }),
  'task.analysis.failed': createUiLanguageRecord("utils.taskMessage.TASK_MESSAGE_TEXT.task.analysis.failed", { zh: '分析失败', en: 'Analysis failed' }),
  'task.market_review.queued': createUiLanguageRecord("utils.taskMessage.TASK_MESSAGE_TEXT.task.market_review.queued", { zh: '大盘复盘任务已提交', en: 'Market review queued' }),
  'task.screening.queued': createUiLanguageRecord("utils.taskMessage.TASK_MESSAGE_TEXT.task.screening.queued", { zh: '选股任务已提交', en: 'Screening task queued' }),
  'task.screening.processing': createUiLanguageRecord("utils.taskMessage.TASK_MESSAGE_TEXT.task.screening.processing", { zh: '正在执行选股任务', en: 'Screening in progress' }),
  'task.screening.organizing': createUiLanguageRecord("utils.taskMessage.TASK_MESSAGE_TEXT.task.screening.organizing", { zh: '正在整理 {candidate_count} 条候选', en: 'Preparing {candidate_count} candidates' }),
};

const STATUS_FALLBACK: Record<string, LocalizedTaskMessage> = {
  pending: createUiLanguageRecord("utils.taskMessage.STATUS_FALLBACK.pending", { zh: '任务等待中', en: 'Task pending' }),
  processing: createUiLanguageRecord("utils.taskMessage.STATUS_FALLBACK.processing", { zh: '任务执行中', en: 'Task in progress' }),
  cancel_requested: createUiLanguageRecord("utils.taskMessage.STATUS_FALLBACK.cancel_requested", { zh: '正在请求取消任务', en: 'Cancelling task' }),
  cancelled: createUiLanguageRecord("utils.taskMessage.STATUS_FALLBACK.cancelled", { zh: '任务已取消', en: 'Task cancelled' }),
  completed: createUiLanguageRecord("utils.taskMessage.STATUS_FALLBACK.completed", { zh: '任务已完成', en: 'Task completed' }),
  failed: createUiLanguageRecord("utils.taskMessage.STATUS_FALLBACK.failed", { zh: '任务执行失败', en: 'Task failed' }),
};

const TASK_STATUS_UPDATED = createUiLanguageRecord('utils.taskMessage.TASK_STATUS_UPDATED', {
  zh: '任务状态已更新',
  en: 'Task status updated',
});

const formatTemplate = (template: string, params: Record<string, unknown>): string =>
  template.replace(/\{([a-zA-Z0-9_]+)\}/g, (_, key: string) => {
    const value = params[key];
    if (key === 'subject') {
      const subject = typeof value === 'string' ? value.trim() : '';
      return subject ? `${subject}${template.includes('正在') ? '：' : ''}` : '';
    }
    return value === undefined || value === null ? '' : String(value);
  });

/** Render task state from stable identity so changing UI language is immediate. */
export function formatTaskMessage(task: TaskMessageLike, language: UiLanguage): string {
  const code = typeof task.messageCode === 'string' ? task.messageCode.trim() : '';
  const localized = TASK_MESSAGE_TEXT[code] ?? STATUS_FALLBACK[String(task.status ?? '')];
  if (localized) {
    return formatTemplate(localized[language], task.messageParams ?? {});
  }

  // Rolling-upgrade adapter for servers that only provide raw task copy. Raw
  // copy is intentionally not shown as the primary UI message.
  return TASK_STATUS_UPDATED[language];
}
