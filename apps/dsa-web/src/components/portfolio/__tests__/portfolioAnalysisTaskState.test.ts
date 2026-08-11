// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { beforeEach, describe, expect, it } from 'vitest';
import {
  PORTFOLIO_ANALYSIS_TASK_QUERY_KEY,
  PORTFOLIO_ANALYSIS_TASK_SESSION_KEY,
  applyPortfolioAnalysisTaskToSearch,
  clearPersistedPortfolioAnalysisTasks,
  persistPortfolioAnalysisTasks,
  readPersistedPortfolioAnalysisTasks,
  readPortfolioAnalysisTaskIdFromSearch,
  removePersistedPortfolioAnalysisTask,
  upsertPersistedPortfolioAnalysisTask,
} from '../portfolioAnalysisTaskState';

describe('portfolioAnalysisTaskState', () => {
  beforeEach(() => {
    window.sessionStorage.clear();
  });

  it('persists and restores tracked analysis tasks', () => {
    persistPortfolioAnalysisTasks([
      { taskId: 'task-a', stockCode: 'AAPL', analysisPhase: 'auto' },
      { taskId: 'task-b', stockCode: 'MSFT' },
    ]);
    expect(window.sessionStorage.getItem(PORTFOLIO_ANALYSIS_TASK_SESSION_KEY)).toContain('task-a');
    expect(readPersistedPortfolioAnalysisTasks()).toEqual([
      { taskId: 'task-a', stockCode: 'AAPL', analysisPhase: 'auto' },
      { taskId: 'task-b', stockCode: 'MSFT' },
    ]);
  });

  it('upserts and removes tasks without duplicating ids', () => {
    const first = upsertPersistedPortfolioAnalysisTask([], {
      taskId: 'task-1',
      stockCode: 'AAPL',
    });
    const second = upsertPersistedPortfolioAnalysisTask(first, {
      taskId: 'task-1',
      stockCode: 'AAPL',
      analysisPhase: 'postmarket',
    });
    expect(second).toEqual([
      { taskId: 'task-1', stockCode: 'AAPL', analysisPhase: 'postmarket' },
    ]);
    expect(removePersistedPortfolioAnalysisTask(second, 'task-1')).toEqual([]);
  });

  it('reads and writes the portfolio task query param without clobbering account', () => {
    const current = new URLSearchParams('account=3&keep=yes');
    expect(readPortfolioAnalysisTaskIdFromSearch(current)).toBeNull();

    const withTask = applyPortfolioAnalysisTaskToSearch(current, 'task-restore-1');
    expect(withTask).not.toBeNull();
    expect(withTask!.get(PORTFOLIO_ANALYSIS_TASK_QUERY_KEY)).toBe('task-restore-1');
    expect(withTask!.get('account')).toBe('3');
    expect(withTask!.get('keep')).toBe('yes');

    const unchanged = applyPortfolioAnalysisTaskToSearch(withTask!, 'task-restore-1');
    expect(unchanged).toBeNull();

    const cleared = applyPortfolioAnalysisTaskToSearch(withTask!, null);
    expect(cleared).not.toBeNull();
    expect(cleared!.get(PORTFOLIO_ANALYSIS_TASK_QUERY_KEY)).toBeNull();
    expect(cleared!.get('account')).toBe('3');
  });

  it('rejects unstable task ids for URL restore', () => {
    expect(readPortfolioAnalysisTaskIdFromSearch('?task=')).toBeNull();
    expect(readPortfolioAnalysisTaskIdFromSearch('?task=bad id')).toBeNull();
    expect(readPortfolioAnalysisTaskIdFromSearch('?task=task_ok-1')).toBe('task_ok-1');
  });

  it('clears empty persistence', () => {
    persistPortfolioAnalysisTasks([{ taskId: 'task-z', stockCode: 'ZZZ' }]);
    clearPersistedPortfolioAnalysisTasks();
    expect(readPersistedPortfolioAnalysisTasks()).toEqual([]);
    expect(window.sessionStorage.getItem(PORTFOLIO_ANALYSIS_TASK_SESSION_KEY)).toBeNull();
  });
});
