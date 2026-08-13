// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { analysisApi } from '../../api/analysis';
import {
  ANALYSIS_WORKBENCH_SEGMENT_VALUES,
  APP_ROUTE_PATHS,
  RUN_FLOW_ROUTE_QUERY_VALUES,
} from '../../routing/routes';
import { buildAnalysisTasksHref, runSetupSmokeAnalysis } from '../setupSmokeTask';

vi.mock('../../api/analysis', async () => {
  const actual = await vi.importActual<typeof import('../../api/analysis')>('../../api/analysis');
  return {
    ...actual,
    analysisApi: {
      ...actual.analysisApi,
      analyzeAsync: vi.fn(),
    },
  };
});

const t = (key: string, params?: Record<string, string | number>) => {
  if (params?.stock) return `${key}:${params.stock}`;
  return key;
};

describe('setupSmokeTask', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('builds workbench tasks href with optional run-flow task id', () => {
    expect(buildAnalysisTasksHref()).toContain(APP_ROUTE_PATHS.researchAnalysis);
    expect(buildAnalysisTasksHref()).toContain(
      `${ANALYSIS_WORKBENCH_SEGMENT_VALUES.tasks}`,
    );
    const withTask = buildAnalysisTasksHref('task-1');
    expect(withTask).toContain(RUN_FLOW_ROUTE_QUERY_VALUES.task);
    expect(withTask).toContain('task-1');
  });

  it('returns blocked outcomes without calling analyze', async () => {
    const notReady = await runSetupSmokeAnalysis({
      readyForSmoke: false,
      stockCode: 'AAPL',
      t: t as never,
    });
    expect(notReady.status).toBe('blocked');
    expect(analysisApi.analyzeAsync).not.toHaveBeenCalled();

    const noStock = await runSetupSmokeAnalysis({
      readyForSmoke: true,
      stockCode: '',
      t: t as never,
    });
    expect(noStock.status).toBe('blocked');
  });

  it('accepts smoke without bare task-id-only success copy', async () => {
    vi.mocked(analysisApi.analyzeAsync).mockResolvedValue({
      taskId: 'smoke-task',
      status: 'accepted',
    } as never);
    const outcome = await runSetupSmokeAnalysis({
      readyForSmoke: true,
      stockCode: '600519',
      t: t as never,
    });
    expect(outcome).toMatchObject({
      status: 'accepted',
      successMessage: 'settings.setupGuideSmokeAccepted:600519',
    });
    if (outcome.status === 'accepted') {
      expect(outcome.tasksHref).toContain('smoke-task');
      expect(outcome.successMessage).not.toContain('smoke-task');
    }
  });

  it('links busy duplicate failures to the tasks surface', async () => {
    vi.mocked(analysisApi.analyzeAsync).mockRejectedValue({
      response: {
        status: 409,
        data: {
          error: 'duplicate_task',
          message: 'busy',
          params: { existing_task_id: 'existing-1' },
        },
      },
    });
    const outcome = await runSetupSmokeAnalysis({
      readyForSmoke: true,
      stockCode: 'AAPL',
      t: t as never,
    });
    expect(outcome.status).toBe('failed');
    if (outcome.status === 'failed') {
      expect(outcome.error).toMatchObject({ code: 'duplicate_task' });
      expect(outcome.tasksHref).toContain('existing-1');
    }
  });
});
