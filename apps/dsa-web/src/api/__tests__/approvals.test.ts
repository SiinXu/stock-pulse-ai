import { beforeEach, describe, expect, it, vi } from 'vitest';
import { approvalsApi } from '../approvals';
import { getParsedApiError, isApiRequestError } from '../error';

const { get, put, post } = vi.hoisted(() => ({
  get: vi.fn(),
  put: vi.fn(),
  post: vi.fn(),
}));

vi.mock('../index', () => ({
  default: { get, put, post },
}));

describe('approvalsApi', () => {
  beforeEach(() => {
    get.mockReset();
    put.mockReset();
    post.mockReset();
  });

  it('camel-cases bounded proposal context and sends decision CAS fields', async () => {
    get.mockResolvedValueOnce({
      data: {
        items: [{
          id: 'a'.repeat(32),
          owner: 'local_admin',
          action: 'risk_control_bypass',
          status: 'pending',
          version: 1,
          expires_at: '2026-07-25T18:00:00Z',
          consumed_at: null,
          context: {
            stock_code: 'AAPL',
            original_signal: 'buy',
            conservative_signal: 'hold',
            risk_source: 'risk_veto',
            risk_summary: 'Risk veto',
          },
          created_at: '2026-07-25T17:55:00Z',
          updated_at: '2026-07-25T17:55:00Z',
        }],
        page: 1,
        page_size: 50,
        total: 1,
      },
    });
    post.mockResolvedValueOnce({
      data: {
        id: 'a'.repeat(32),
        owner: 'local_admin',
        action: 'risk_control_bypass',
        status: 'approved',
        version: 2,
        expires_at: '2026-07-25T18:00:00Z',
        consumed_at: null,
        context: {
          stock_code: 'AAPL',
          original_signal: 'buy',
          conservative_signal: 'hold',
          risk_source: 'risk_veto',
          risk_summary: 'Risk veto',
        },
        created_at: '2026-07-25T17:55:00Z',
        updated_at: '2026-07-25T17:56:00Z',
      },
    });

    const page = await approvalsApi.list({ status: 'pending', pageSize: 50 });
    expect(page.items[0].context.originalSignal).toBe('buy');
    expect(get).toHaveBeenCalledWith('/api/v1/approvals', {
      params: {
        page: undefined,
        page_size: 50,
        status: 'pending',
      },
    });
    const decided = await approvalsApi.decide('a'.repeat(32), 'approved', 1);
    expect(decided.status).toBe('approved');
    expect(post).toHaveBeenCalledWith(
      `/api/v1/approvals/${'a'.repeat(32)}/decision`,
      { decision: 'approved', expected_version: 1 },
    );
  });

  it('sends rule version and bounded settings in snake case', async () => {
    put.mockResolvedValueOnce({
      data: {
        owner: 'local_admin',
        action: 'risk_control_bypass',
        enabled: true,
        risk_sources: ['risk_veto'],
        expires_in_seconds: 300,
        version: 2,
        updated_at: '2026-07-25T18:00:00Z',
      },
    });

    const rule = await approvalsApi.updateRule({
      enabled: true,
      riskSources: ['risk_veto'],
      expiresInSeconds: 300,
      expectedVersion: 1,
    });
    expect(rule.riskSources).toEqual(['risk_veto']);
    expect(put).toHaveBeenCalledWith(
      '/api/v1/approvals/rules/risk-control-bypass',
      {
        enabled: true,
        risk_sources: ['risk_veto'],
        expires_in_seconds: 300,
        expected_version: 1,
      },
    );
  });

  it('preserves extra keys on valid rule payloads (byte-identical toCamelCase pass-through)', async () => {
    get.mockResolvedValueOnce({
      data: {
        owner: 'local_admin', enabled: false, risk_sources: [],
        expires_in_seconds: 60, version: 1, unexpected_server_field: 'keep-me',
      },
    });
    const rule = await approvalsApi.getRule();
    expect(rule).toEqual({
      owner: 'local_admin', enabled: false, riskSources: [],
      expiresInSeconds: 60, version: 1, unexpectedServerField: 'keep-me',
    });
  });

  it('surfaces shape mismatches through ParsedApiError', async () => {
    get.mockResolvedValueOnce({
      data: { owner: 'local_admin', risk_sources: [], expires_in_seconds: 60, version: 1 },
    });
    await expect(approvalsApi.getRule()).rejects.toSatisfy((error: unknown) => {
      expect(isApiRequestError(error)).toBe(true);
      const parsed = getParsedApiError(error);
      expect(parsed.code).toBe('api_response_validation_failed');
      expect(parsed.message).toContain('ApprovalRule');
      return true;
    });
  });

});
