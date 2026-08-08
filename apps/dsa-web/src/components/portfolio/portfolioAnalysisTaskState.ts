// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
// Portfolio-owned analysis task continuity (session + URL restore).

import {
  isStableAnalysisWorkbenchTaskId,
} from '../../routing/routes';
import {
  readSessionItem,
  removeSessionItem,
  writeSessionItem,
} from '../../utils/sessionPersistence';
import type { AnalysisPhase } from '../../types/analysis';

/** Session key for portfolio-started analysis tasks that should reattach after leave/refresh. */
export const PORTFOLIO_ANALYSIS_TASK_SESSION_KEY = 'dsa.portfolio.activeAnalysisTasks.v1';

/** Portfolio URL query key for reattaching a tracked analysis task after refresh. */
export const PORTFOLIO_ANALYSIS_TASK_QUERY_KEY = 'task';

export type PersistedPortfolioAnalysisTask = {
  taskId: string;
  stockCode: string;
  analysisPhase?: AnalysisPhase;
};

const MAX_TRACKED_TASKS = 12;

function isAnalysisPhase(value: unknown): value is AnalysisPhase {
  return value === 'auto'
    || value === 'premarket'
    || value === 'intraday'
    || value === 'postmarket';
}

function normalizePersistedTask(
  value: Partial<PersistedPortfolioAnalysisTask> | null | undefined,
): PersistedPortfolioAnalysisTask | null {
  if (!value || typeof value.taskId !== 'string' || typeof value.stockCode !== 'string') {
    return null;
  }
  const taskId = value.taskId.trim();
  const stockCode = value.stockCode.trim();
  if (!taskId || !stockCode || !isStableAnalysisWorkbenchTaskId(taskId)) {
    return null;
  }
  const task: PersistedPortfolioAnalysisTask = { taskId, stockCode };
  if (isAnalysisPhase(value.analysisPhase)) {
    task.analysisPhase = value.analysisPhase;
  }
  return task;
}

export function readPersistedPortfolioAnalysisTasks(): PersistedPortfolioAnalysisTask[] {
  const raw = readSessionItem(PORTFOLIO_ANALYSIS_TASK_SESSION_KEY);
  if (!raw) return [];
  try {
    const parsed = JSON.parse(raw) as unknown;
    if (!Array.isArray(parsed)) return [];
    const tasks: PersistedPortfolioAnalysisTask[] = [];
    const seen = new Set<string>();
    for (const item of parsed) {
      const task = normalizePersistedTask(item as Partial<PersistedPortfolioAnalysisTask>);
      if (!task || seen.has(task.taskId)) continue;
      seen.add(task.taskId);
      tasks.push(task);
      if (tasks.length >= MAX_TRACKED_TASKS) break;
    }
    return tasks;
  } catch {
    return [];
  }
}

export function persistPortfolioAnalysisTasks(tasks: readonly PersistedPortfolioAnalysisTask[]): void {
  const normalized: PersistedPortfolioAnalysisTask[] = [];
  const seen = new Set<string>();
  for (const item of tasks) {
    const task = normalizePersistedTask(item);
    if (!task || seen.has(task.taskId)) continue;
    seen.add(task.taskId);
    normalized.push(task);
    if (normalized.length >= MAX_TRACKED_TASKS) break;
  }
  if (normalized.length === 0) {
    removeSessionItem(PORTFOLIO_ANALYSIS_TASK_SESSION_KEY);
    return;
  }
  writeSessionItem(PORTFOLIO_ANALYSIS_TASK_SESSION_KEY, JSON.stringify(normalized));
}

export function clearPersistedPortfolioAnalysisTasks(): void {
  removeSessionItem(PORTFOLIO_ANALYSIS_TASK_SESSION_KEY);
}

export function readPortfolioAnalysisTaskIdFromSearch(
  search: string | URLSearchParams,
): string | null {
  const params = typeof search === 'string' ? new URLSearchParams(search) : search;
  const raw = params.get(PORTFOLIO_ANALYSIS_TASK_QUERY_KEY)?.trim() ?? '';
  return isStableAnalysisWorkbenchTaskId(raw) ? raw : null;
}

/**
 * Write or clear the portfolio analysis `task` query param without clobbering other params.
 * Returns null when the search string is unchanged.
 */
export function applyPortfolioAnalysisTaskToSearch(
  search: string | URLSearchParams,
  taskId: string | null,
): URLSearchParams | null {
  const source = typeof search === 'string' ? new URLSearchParams(search) : new URLSearchParams(search);
  const current = source.get(PORTFOLIO_ANALYSIS_TASK_QUERY_KEY);
  const nextValue = taskId && isStableAnalysisWorkbenchTaskId(taskId) ? taskId.trim() : null;
  if (nextValue === null) {
    if (current === null) return null;
    source.delete(PORTFOLIO_ANALYSIS_TASK_QUERY_KEY);
    return source;
  }
  if (current === nextValue) return null;
  source.set(PORTFOLIO_ANALYSIS_TASK_QUERY_KEY, nextValue);
  return source;
}

export function upsertPersistedPortfolioAnalysisTask(
  tasks: readonly PersistedPortfolioAnalysisTask[],
  next: PersistedPortfolioAnalysisTask,
): PersistedPortfolioAnalysisTask[] {
  const normalized = normalizePersistedTask(next);
  if (!normalized) return [...tasks];
  const others = tasks.filter((task) => task.taskId !== normalized.taskId);
  return [normalized, ...others].slice(0, MAX_TRACKED_TASKS);
}

export function removePersistedPortfolioAnalysisTask(
  tasks: readonly PersistedPortfolioAnalysisTask[],
  taskId: string,
): PersistedPortfolioAnalysisTask[] {
  return tasks.filter((task) => task.taskId !== taskId);
}
