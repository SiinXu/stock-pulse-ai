// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { analysisApi } from '../analysis';
import { historyApi } from '../history';

const { get, post } = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
}));

vi.mock('../index', () => ({
  default: { get, post },
  locallyRecoverableResourceConfig: () => ({}),
}));

const snakeCaseReport = {
  meta: {
    query_id: 'report-contract',
    stock_code: 'AAPL',
    stock_name: 'Apple',
    report_type: 'detailed',
    report_language: 'en',
    created_at: '2026-07-29T12:00:00Z',
  },
  summary: {
    analysis_summary: 'summary',
    operation_advice: 'Hold',
    trend_prediction: 'Neutral',
    sentiment_score: 50,
  },
  details: {
    structured_insights: {
      schema_version: 'report-structured-insights-v1',
      phase_decision: {
        phase_context: {
          phase: 'intraday',
          trigger_source: 'api',
        },
        immediate_action: 'Wait for confirmation',
      },
      signal_attribution: {
        technical_indicators: 40,
        news_sentiment: 20,
        fundamentals: 30,
        market_conditions: 10,
      },
      strategy_synthesis: {
        final_signal: 'hold',
        consensus_level: 'low',
        opposing_skills: [
          {
            skill_id: 'event_driven',
            signal: 'sell',
          },
        ],
      },
    },
  },
};

describe('structured report insight API contract', () => {
  beforeEach(() => {
    get.mockReset();
    post.mockReset();
  });

  it('camelizes the same typed contract for sync, task, and history reports', async () => {
    post.mockResolvedValueOnce({
      status: 200,
      data: {
        query_id: 'report-contract',
        stock_code: 'AAPL',
        stock_name: 'Apple',
        created_at: '2026-07-29T12:00:00Z',
        report: snakeCaseReport,
      },
    });
    get
      .mockResolvedValueOnce({
        status: 200,
        data: {
          task_id: 'task-report-contract',
          status: 'completed',
          message_code: 'task.status',
          progress: 100,
          result: {
            query_id: 'report-contract',
            stock_code: 'AAPL',
            stock_name: 'Apple',
            created_at: '2026-07-29T12:00:00Z',
            report: snakeCaseReport,
          },
        },
      })
      .mockResolvedValueOnce({
        status: 200,
        data: snakeCaseReport,
      });

    const syncResult = await analysisApi.analyze({ stockCode: 'AAPL' });
    const taskResult = await analysisApi.getStatus('task-report-contract');
    const historyResult = await historyApi.getDetail(42);

    if (!('report' in syncResult)) {
      throw new Error('Expected a synchronous analysis report');
    }
    const syncInsights = syncResult.report.details?.structuredInsights;
    const taskInsights = taskResult.result?.report.details?.structuredInsights;
    const historyInsights = historyResult.details?.structuredInsights;

    expect(syncInsights).toEqual(taskInsights);
    expect(taskInsights).toEqual(historyInsights);
    expect(historyInsights).toMatchObject({
      schemaVersion: 'report-structured-insights-v1',
      phaseDecision: {
        phaseContext: {
          phase: 'intraday',
          triggerSource: 'api',
        },
        immediateAction: 'Wait for confirmation',
      },
      signalAttribution: {
        technicalIndicators: 40,
        newsSentiment: 20,
        fundamentals: 30,
        marketConditions: 10,
      },
      strategySynthesis: {
        finalSignal: 'hold',
        consensusLevel: 'low',
        opposingSkills: [
          {
            skillId: 'event_driven',
            signal: 'sell',
          },
        ],
      },
    });
  });
});
