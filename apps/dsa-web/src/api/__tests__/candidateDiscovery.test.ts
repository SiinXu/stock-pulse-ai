import { beforeEach, describe, expect, it, vi } from 'vitest';
import { candidateDiscoveryApi } from '../candidateDiscovery';
import { getParsedApiError } from '../error';

const { get, post } = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
}));

vi.mock('../index', () => ({
  default: { get, post },
}));

describe('candidateDiscoveryApi', () => {
  beforeEach(() => {
    get.mockReset();
    post.mockReset();
  });

  it('submits a bounded task and validates the accepted wire contract', async () => {
    post.mockResolvedValueOnce({
      data: {
        task_id: 'discovery-1',
        trace_id: 'trace-1',
        status: 'pending',
        message: 'Queued',
        universe: 'watchlist',
        page: 1,
        page_size: 50,
        max_results: 10,
        max_provider_calls: 20,
      },
    });

    const request = { query: 'banks', universe: 'watchlist' as const, maxProviderCalls: 20 };
    const accepted = await candidateDiscoveryApi.startTask(request);

    expect(post).toHaveBeenCalledWith('/api/v1/discover/screen/tasks', request);
    expect(accepted).toMatchObject({
      taskId: 'discovery-1',
      traceId: 'trace-1',
      pageSize: 50,
      maxProviderCalls: 20,
    });
  });

  it('maps a completed task and its candidates from the snake-case response', async () => {
    get.mockResolvedValueOnce({
      data: {
        task_id: 'discovery-1',
        trace_id: 'trace-1',
        status: 'completed',
        progress: 100,
        result: {
          pack_version: 'candidate_discovery/1.0',
          run_id: 'run-1',
          status: 'completed',
          universe: 'watchlist',
          candidate_count: 1,
          candidates: [{
            rank: 1,
            code: '600519',
            name: 'Kweichow Moutai',
            reason: 'Matched bounded criteria',
            change_pct: 1.25,
          }],
        },
      },
    });

    const task = await candidateDiscoveryApi.getTask('discovery/1');

    expect(get).toHaveBeenCalledWith('/api/v1/discover/screen/tasks/discovery%2F1');
    expect(task.result?.candidates[0]).toMatchObject({
      code: '600519',
      changePct: 1.25,
      reason: 'Matched bounded criteria',
    });
  });

  it('surfaces accepted-response drift through the shared parsed API error', async () => {
    post.mockResolvedValueOnce({ data: { status: 'pending' } });

    await expect(candidateDiscoveryApi.startTask({ universe: 'watchlist' })).rejects.toSatisfy(
      (error: unknown) => {
        const parsed = getParsedApiError(error);
        expect(parsed.code).toBe('api_response_validation_failed');
        expect(parsed.params).toMatchObject({ label: 'candidate discovery task accepted' });
        return true;
      },
    );
  });
});
