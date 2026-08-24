// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  agentFeedbackApi,
  canonicalizeAgentRunId,
} from '../agentFeedback';
import { getParsedApiError, isApiRequestError } from '../error';

const { get, put } = vi.hoisted(() => ({
  get: vi.fn(),
  put: vi.fn(),
}));

vi.mock('../index', () => ({
  default: {
    get,
    put,
  },
}));

const emptyItem = {
  run_id: 'run-a',
  feedback_value: null,
  note: null,
  source: null,
  provenance_source: null,
  actor_id: null,
  created_at: null,
  updated_at: null,
};

describe('canonicalizeAgentRunId', () => {
  it('accepts a stripped token and rejects empty, whitespace, and oversize ids', () => {
    expect(canonicalizeAgentRunId('  run-a  ')).toBe('run-a');
    expect(canonicalizeAgentRunId('')).toBeNull();
    expect(canonicalizeAgentRunId('   ')).toBeNull();
    expect(canonicalizeAgentRunId('run a')).toBeNull();
    expect(canonicalizeAgentRunId('x'.repeat(129))).toBeNull();
    expect(canonicalizeAgentRunId(null)).toBeNull();
  });
});

describe('agentFeedbackApi', () => {
  beforeEach(() => {
    get.mockReset();
    put.mockReset();
  });

  it('encodes the run id path segment and maps snake_case GET payloads', async () => {
    get.mockResolvedValueOnce({ data: emptyItem });
    const feedback = await agentFeedbackApi.getRunFeedback('pred-5:run-a:600519');
    expect(get).toHaveBeenCalledWith('/api/v1/agent/runs/pred-5%3Arun-a%3A600519/feedback');
    expect(get.mock.calls[0][1]).toBeUndefined();
    expect(feedback).toMatchObject({
      runId: 'run-a',
      feedbackValue: null,
      note: null,
    });
  });

  it('always sends note and source=web on PUT, including an empty-string clear', async () => {
    put.mockResolvedValueOnce({
      data: {
        ...emptyItem,
        feedback_value: 'partial',
        note: null,
        source: 'web',
      },
    });
    const updated = await agentFeedbackApi.putRunFeedback('run-a', {
      feedbackValue: 'partial',
      note: '',
      source: 'web',
    });
    expect(put).toHaveBeenCalledWith('/api/v1/agent/runs/run-a/feedback', {
      feedback_value: 'partial',
      note: '',
      source: 'web',
    });
    const body = put.mock.calls[0][1] as Record<string, unknown>;
    expect(body).toHaveProperty('note', '');
    expect(body).not.toHaveProperty('run_id');
    expect(body).not.toHaveProperty('prediction_id');
    expect(updated.feedbackValue).toBe('partial');
  });

  it('echoes a non-empty note on PUT and does not omit the key', async () => {
    put.mockResolvedValueOnce({
      data: {
        ...emptyItem,
        feedback_value: 'useful',
        note: 'Looks consistent with the tape.',
        source: 'web',
      },
    });
    const updated = await agentFeedbackApi.putRunFeedback('run-a', {
      feedbackValue: 'useful',
      note: 'Looks consistent with the tape.',
      source: 'web',
    });
    expect(put).toHaveBeenCalledWith('/api/v1/agent/runs/run-a/feedback', {
      feedback_value: 'useful',
      note: 'Looks consistent with the tape.',
      source: 'web',
    });
    expect(updated.note).toBe('Looks consistent with the tape.');
  });

  it('maps 404/400/401 through ParsedApiError without local unauthorized handling', async () => {
    get.mockRejectedValueOnce({
      response: { status: 404, data: { error: 'not_found', message: 'Analysis run not found.' } },
    });
    await expect(agentFeedbackApi.getRunFeedback('missing')).rejects.toSatisfy((error: unknown) => {
      const parsed = getParsedApiError(error);
      expect(parsed.status).toBe(404);
      expect(parsed.code).toBe('not_found');
      return true;
    });

    put.mockRejectedValueOnce({
      response: { status: 400, data: { error: 'invalid_request', message: 'Feedback note was rejected.' } },
    });
    await expect(agentFeedbackApi.putRunFeedback('run-a', {
      feedbackValue: 'useful',
      note: 'stockpulse-agent-soul',
      source: 'web',
    })).rejects.toSatisfy((error: unknown) => {
      const parsed = getParsedApiError(error);
      expect(parsed.status).toBe(400);
      return parsed.status === 400;
    });

    put.mockRejectedValueOnce({
      response: { status: 401, data: { error: 'unauthorized', message: 'Login required.' } },
    });
    await expect(agentFeedbackApi.putRunFeedback('run-a', {
      feedbackValue: 'useful',
      note: '',
      source: 'web',
    })).rejects.toSatisfy((error: unknown) => {
      expect(isApiRequestError(error) || Boolean((error as { response?: { status?: number } }).response)).toBe(true);
      expect(put.mock.calls.at(-1)?.[2]).toBeUndefined();
      return true;
    });
  });
});
