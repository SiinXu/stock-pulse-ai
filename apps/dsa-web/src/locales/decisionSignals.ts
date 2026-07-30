// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

import { createUiLanguageRecord } from '../i18n/createUiLanguageRecord';

const zh = {
  memoryDefault: '未标记',
  memoryDescription: '分别控制历史决策复盘中的优先记忆与检索排除。',
  memoryIgnored: '忽略',
  memoryIgnoredDescription: '从历史决策记忆检索中排除该信号。',
  memoryIgnoredPrecedence: '“忽略”优先：即使同时标记为重点记忆，该信号仍不会进入历史决策记忆检索。',
  memoryLoadErrorTitle: '决策记忆标记加载失败',
  memoryMemorable: '重点记忆',
  memoryMemorableDescription: '在历史决策复盘中提高该信号的展示优先级。',
  memorySaveErrorTitle: '决策记忆标记保存失败',
  memoryTitle: '决策记忆',
  outcomeExplorerAllHorizons: '全部周期',
  outcomeExplorerAllOutcomes: '全部结果',
  outcomeExplorerAllStatuses: '全部评估状态',
  outcomeExplorerApplyFilters: '应用筛选',
  outcomeExplorerDescription: '按真实后验接口筛选并分页浏览所有信号的结果，可追溯到对应信号详情。',
  outcomeExplorerEmptyDescription: '当前筛选条件下没有可展示的后验结果。',
  outcomeExplorerEngineVersion: '引擎版本',
  outcomeExplorerErrorTitle: '全局后验结果加载失败',
  outcomeExplorerInvalidSignalId: '信号 ID 必须是大于 0 的整数。',
  outcomeExplorerOpenSignal: '查看信号 #{id}',
  outcomeExplorerSignalId: '信号 ID',
  outcomeExplorerTitle: '全局后验结果',
  outcomeExplorerUpdatedAt: '更新时间',
} as const;

const en = {
  memoryDefault: 'Unmarked',
  memoryDescription: 'Control priority recall and retrieval exclusion independently for historical decision review.',
  memoryIgnored: 'Ignored',
  memoryIgnoredDescription: 'Exclude this signal from historical decision-memory retrieval.',
  memoryIgnoredPrecedence: 'Ignored takes precedence: even when Memorable is also enabled, this signal stays out of decision-memory retrieval.',
  memoryLoadErrorTitle: 'Failed to load decision-memory flags',
  memoryMemorable: 'Memorable',
  memoryMemorableDescription: 'Raise this signal’s display priority in historical decision review.',
  memorySaveErrorTitle: 'Failed to save decision-memory flags',
  memoryTitle: 'Decision memory',
  outcomeExplorerAllHorizons: 'All horizons',
  outcomeExplorerAllOutcomes: 'All outcomes',
  outcomeExplorerAllStatuses: 'All evaluation statuses',
  outcomeExplorerApplyFilters: 'Apply filters',
  outcomeExplorerDescription: 'Filter and page through outcomes across every signal using the server’s outcome contract, then trace a result to its signal.',
  outcomeExplorerEmptyDescription: 'No outcome results match the current filters.',
  outcomeExplorerEngineVersion: 'Engine version',
  outcomeExplorerErrorTitle: 'Failed to load global outcomes',
  outcomeExplorerInvalidSignalId: 'Signal ID must be a whole number greater than 0.',
  outcomeExplorerOpenSignal: 'View signal #{id}',
  outcomeExplorerSignalId: 'Signal ID',
  outcomeExplorerTitle: 'Global outcomes',
  outcomeExplorerUpdatedAt: 'Updated',
} as const;

export const DECISION_SIGNAL_WORKSTREAM_TEXT = createUiLanguageRecord(
  // Preserve the established generated keys while moving source ownership
  // from the global dictionary into this decision-signals domain module.
  'i18n.uiText.UI_TEXT.decisionSignals',
  { zh, en },
);
