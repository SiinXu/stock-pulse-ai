// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

import { beforeEach, describe, expect, it, vi } from 'vitest';
import { investmentFrameworkApi } from '../investmentFramework';
import { getParsedApiError } from '../error';

const put = vi.hoisted(() => vi.fn());

vi.mock('../index', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
    put,
    delete: vi.fn(),
  },
}));

describe('investmentFrameworkApi', () => {
  beforeEach(() => {
    put.mockReset();
    put.mockResolvedValue({
      data: {
        framework_id: 1,
        scope: 'local',
        version: 2,
        active_version: 2,
        revision: 2,
        is_active: true,
        content: {
          title: 'Framework',
          free_form_rules: 'Rule',
        },
        created_at: '2026-07-26T00:00:00Z',
        updated_at: '2026-07-26T00:00:00Z',
        version_created_at: '2026-07-26T00:00:00Z',
      },
    });
  });

  it('preserves unknown future fields while encoding known structured fields', async () => {
    await investmentFrameworkApi.update({
      expectedRevision: 1,
      changeSummary: 'Structured update',
      content: {
        schemaVersion: 'investment-framework-content-v1',
        title: 'Framework',
        rootNodeId: 'root',
        futurePolicy: { reviewWindowDays: 30 },
        decisionTree: [{
          nodeId: 'root',
          question: 'Proceed?',
          futureNodeHint: 'keep-me',
          branches: [{
            condition: 'Yes',
            targetNodeId: null,
            outcome: 'Proceed',
            futureBranchScore: 5,
          }],
        }],
        evaluationDimensions: [{
          name: 'Moat',
          weight: 50,
          criteria: ['Pricing power'],
          futureDimensionFlag: true,
        }],
        riskRules: [],
        trackingCriteria: [],
        freeFormRules: null,
      },
    });

    expect(put).toHaveBeenCalledWith(
      '/api/v1/investment-framework',
      expect.objectContaining({
        expected_revision: 1,
        content: expect.objectContaining({
          future_policy: { review_window_days: 30 },
          decision_tree: [
            expect.objectContaining({
              future_node_hint: 'keep-me',
              branches: [
                expect.objectContaining({ future_branch_score: 5 }),
              ],
            }),
          ],
          evaluation_dimensions: [
            expect.objectContaining({ future_dimension_flag: true }),
          ],
        }),
      }),
    );
  });

  it('preserves sanitized 422 issue locations for structured-editor field mapping', async () => {
    const details = {
      issues: [
        {
          type: 'string_too_long',
          loc: ['body', 'content', 'decision_tree', 1, 'question'],
          msg: 'String should have at most 1000 characters',
        },
      ],
    };
    put.mockRejectedValueOnce({
      response: {
        status: 422,
        data: {
          error: 'validation_error',
          message: 'Request validation failed',
          details,
          trace_id: 'trace-framework-422',
        },
      },
    });

    await expect(investmentFrameworkApi.update({
      expectedRevision: 1,
      content: {
        title: 'Framework',
        freeFormRules: 'Rule',
      },
    })).rejects.toMatchObject({
      status: 422,
      code: 'validation_error',
      details,
      traceId: 'trace-framework-422',
    });
  });

  it('preserves extra keys on valid framework payloads (toCamelCase pass-through)', async () => {
    put.mockResolvedValueOnce({
      data: {
        framework_id: 1,
        scope: 'local',
        version: 2,
        active_version: 2,
        revision: 2,
        is_active: true,
        content: { title: 'Framework', free_form_rules: 'Rule' },
        created_at: '2026-07-26T00:00:00Z',
        updated_at: '2026-07-26T00:00:00Z',
        version_created_at: '2026-07-26T00:00:00Z',
        unexpected_server_field: 'keep-me',
      },
    });
    const updated = await investmentFrameworkApi.update({
      expectedRevision: 1,
      content: { title: 'Framework', freeFormRules: 'Rule' },
    });
    expect(updated).toEqual(expect.objectContaining({
      frameworkId: 1,
      unexpectedServerField: 'keep-me',
      content: expect.objectContaining({ title: 'Framework', freeFormRules: 'Rule' }),
    }));
  });

  it('surfaces framework shape mismatches through ParsedApiError', async () => {
    put.mockResolvedValueOnce({
      data: {
        framework_id: 1,
        version: 2,
        revision: 2,
        is_active: true,
        content: { title: 'Framework' },
        created_at: '2026-07-26T00:00:00Z',
        updated_at: '2026-07-26T00:00:00Z',
        version_created_at: '2026-07-26T00:00:00Z',
      },
    });
    await expect(investmentFrameworkApi.update({
      expectedRevision: 1,
      content: { title: 'Framework' },
    })).rejects.toSatisfy((error: unknown) => {
      const parsed = getParsedApiError(error);
      expect(parsed.code).toBe('api_response_validation_failed');
      expect(String(parsed.message || '') + String(parsed.params || '')).toContain('InvestmentFrameworkResponse');
      return true;
    });
  });
});
