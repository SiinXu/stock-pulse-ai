import { beforeEach, describe, expect, it, vi } from 'vitest';
import apiClient from '../index';
import { agentApi } from '../agent';
import { getParsedApiError, isApiRequestError } from '../error';

vi.mock('../index', () => ({
  default: { post: vi.fn(), get: vi.fn(), delete: vi.fn() },
}));

const mockPost = vi.mocked(apiClient.post);
const mockGet = vi.mocked(apiClient.get);

describe('agentApi.research', () => {
  beforeEach(() => {
    mockPost.mockReset();
    mockGet.mockReset();
  });

  it('POSTs the question with session identity and a long timeout', async () => {
    mockPost.mockResolvedValue({
      data: { success: true, content: '# Findings', sources: ['q1', 'q2'], token_usage: 100 },
    });
    const result = await agentApi.research(
      {
        question: 'Why?',
        stockCode: '600519',
        sessionId: 'session-1',
        turnId: 'turn-1',
      },
    );
    expect(mockPost).toHaveBeenCalledWith(
      '/api/v1/agent/research',
      {
        question: 'Why?',
        stock_code: '600519',
        session_id: 'session-1',
        turn_id: 'turn-1',
      },
      expect.objectContaining({ timeout: 200000 }),
    );
    expect(result.success).toBe(true);
    expect(result.sources).toEqual(['q1', 'q2']);
  });

  it('sends undefined stock_code when omitted and surfaces the error field', async () => {
    mockPost.mockResolvedValue({
      data: { success: false, content: '', sources: [], token_usage: 0, error: 'timed out' },
    });
    const result = await agentApi.research({ question: 'Q' });
    expect(mockPost).toHaveBeenCalledWith(
      '/api/v1/agent/research',
      {
        question: 'Q',
        stock_code: undefined,
        session_id: undefined,
        turn_id: undefined,
      },
      expect.any(Object),
    );
    expect(result.error).toBe('timed out');
  });

  it('preserves extra keys on valid research payloads (byte-identical pass-through)', async () => {
    mockPost.mockResolvedValue({
      data: {
        success: true,
        content: 'ok',
        sources: [],
        token_usage: 1,
        unexpected_server_field: 'keep-me',
      },
    });
    const result = await agentApi.research({ question: 'Q' });
    expect(result).toEqual({
      success: true,
      content: 'ok',
      sources: [],
      token_usage: 1,
      unexpected_server_field: 'keep-me',
    });
  });

  it('defaults optional sources to [] when omitted', async () => {
    mockPost.mockResolvedValue({
      data: { success: true, content: 'ok', token_usage: 0 },
    });
    const result = await agentApi.research({ question: 'Q' });
    expect(result.sources).toEqual([]);
  });

  it('surfaces research shape mismatches through ParsedApiError', async () => {
    mockPost.mockResolvedValue({
      data: {
        success: true,
        content: 'ok',
        // token_usage missing — required by ResearchResponse
      },
    });
    await expect(agentApi.research({ question: 'Q' })).rejects.toSatisfy((error: unknown) => {
      expect(isApiRequestError(error)).toBe(true);
      const parsed = getParsedApiError(error);
      expect(parsed.code).toBe('api_response_validation_failed');
      expect(parsed.message).toContain('ResearchResponse');
      return true;
    });
  });

  it.each([Number.NaN, Number.POSITIVE_INFINITY, Number.NEGATIVE_INFINITY])(
    'rejects non-finite token usage (%s)',
    async (tokenUsage) => {
      mockPost.mockResolvedValue({
        data: { success: true, content: 'ok', sources: [], token_usage: tokenUsage },
      });
      await expect(agentApi.research({ question: 'Q' })).rejects.toSatisfy(
        (error: unknown) => {
          expect(getParsedApiError(error).code).toBe('api_response_validation_failed');
          return true;
        },
      );
    },
  );
});

describe('agentApi.chat', () => {
  beforeEach(() => {
    mockPost.mockReset();
    mockGet.mockReset();
  });

  it('preserves additive Agent Soul run metadata from the Chat response', async () => {
    mockPost.mockResolvedValue({
      data: {
        success: true,
        content: 'Evidence is limited.',
        session_id: 'chat-1',
        agent_runtime: {
          soul_version: '1.0.0',
          soul_hash: 'sha256:test',
        },
      },
    });

    const result = await agentApi.chat({ message: 'Analyze AAPL' });

    expect(mockPost).toHaveBeenCalledWith(
      '/api/v1/agent/chat',
      { message: 'Analyze AAPL' },
      { timeout: 120000 },
    );
    expect(result.agent_runtime).toEqual({
      soul_version: '1.0.0',
      soul_hash: 'sha256:test',
    });
  });

  it('keeps agent_runtime absent when the Chat response omits it', async () => {
    mockPost.mockResolvedValue({
      data: {
        success: true,
        content: 'No verified runtime identity.',
        session_id: 'chat-2',
      },
    });

    const result = await agentApi.chat({ message: 'Analyze MSFT' });

    expect(result).not.toHaveProperty('agent_runtime');
  });

  it('surfaces chat shape mismatches through ParsedApiError', async () => {
    mockPost.mockResolvedValue({
      data: {
        success: true,
        content: 'x',
        // session_id missing
      },
    });
    await expect(agentApi.chat({ message: 'hi' })).rejects.toSatisfy((error: unknown) => {
      const parsed = getParsedApiError(error);
      expect(parsed.code).toBe('api_response_validation_failed');
      expect(parsed.params).toMatchObject({ label: 'ChatResponse' });
      return true;
    });
  });
});

describe('agentApi.getSkills / sessions', () => {
  beforeEach(() => {
    mockGet.mockReset();
  });

  it('validates skills and session list responses', async () => {
    mockGet.mockResolvedValueOnce({
      data: {
        default_skill_id: 'default',
        skills: [{ id: 's1', name: 'Skill', description: 'd' }],
        unexpected: true,
      },
    });
    const skills = await agentApi.getSkills();
    expect(skills.default_skill_id).toBe('default');
    expect(skills.skills[0].id).toBe('s1');
    expect((skills as { unexpected?: boolean }).unexpected).toBe(true);

    mockGet.mockResolvedValueOnce({
      data: {
        sessions: [{
          session_id: 's1',
          title: 'T',
          message_count: 2,
          created_at: null,
          last_active: null,
        }],
      },
    });
    const sessions = await agentApi.getChatSessions(10);
    expect(mockGet).toHaveBeenCalledWith('/api/v1/agent/chat/sessions', { params: { limit: 10 } });
    expect(sessions[0].session_id).toBe('s1');

    mockGet.mockResolvedValueOnce({
      data: {
        // default_skill_id missing
        skills: [],
      },
    });
    await expect(agentApi.getSkills()).rejects.toSatisfy((error: unknown) => {
      const parsed = getParsedApiError(error);
      expect(parsed.code).toBe('api_response_validation_failed');
      expect(parsed.params).toMatchObject({ label: 'SkillsResponse' });
      return true;
    });
  });

  it('validates session messages and rejects missing message ids', async () => {
    mockGet.mockResolvedValueOnce({
      data: {
        session_id: 's1',
        messages: [{
          id: 'm1',
          role: 'user',
          content: 'hello',
          created_at: null,
          turn_id: 'turn-1',
        }],
        session_state: { selected_skill_ids: ['technical'] },
        turn_identity_supported: true,
      },
    });
    const detail = await agentApi.getChatSessionMessages('s1');
    expect(detail.messages[0]).toMatchObject({ content: 'hello', turn_id: 'turn-1' });
    expect(detail.session_state.selected_skill_ids).toEqual(['technical']);
    expect(detail.turn_identity_supported).toBe(true);

    mockGet.mockResolvedValueOnce({
      data: {
        session_id: 's1',
        messages: [{ role: 'user', content: 'no id' }],
        session_state: { selected_skill_ids: null },
      },
    });
    await expect(agentApi.getChatSessionMessages('s1')).rejects.toSatisfy((error: unknown) => {
      const parsed = getParsedApiError(error);
      expect(parsed.code).toBe('api_response_validation_failed');
      expect(parsed.params).toMatchObject({ label: 'SessionMessagesResponse' });
      return true;
    });
  });

  it('rejects a session envelope that drops persisted session state', async () => {
    mockGet.mockResolvedValueOnce({
      data: {
        session_id: 's1',
        messages: [],
      },
    });

    await expect(agentApi.getChatSessionMessages('s1')).rejects.toSatisfy((error: unknown) => {
      const parsed = getParsedApiError(error);
      expect(parsed.code).toBe('api_response_validation_failed');
      expect(parsed.params).toMatchObject({ label: 'SessionMessagesResponse' });
      expect(parsed.message).toContain('session_state');
      return true;
    });
  });
});

describe('agentApi.getChatSessionMessages', () => {
  beforeEach(() => {
    mockPost.mockReset();
    mockGet.mockReset();
  });

  it('returns session messages together with persisted Skill state', async () => {
    mockGet.mockResolvedValueOnce({
      data: {
        session_id: 'session-1',
        messages: [
          { id: '1', role: 'user', content: '分析 AAPL', created_at: null },
        ],
        session_state: {
          selected_skill_ids: ['technical', 'risk'],
        },
      },
    });

    const result = await agentApi.getChatSessionMessages('session-1');

    expect(mockGet).toHaveBeenCalledWith('/api/v1/agent/chat/sessions/session-1');
    expect(result.session_state.selected_skill_ids).toEqual(['technical', 'risk']);
  });

  it('preserves null when a legacy session has no persisted Skill state', async () => {
    mockGet.mockResolvedValueOnce({
      data: {
        session_id: 'legacy-session',
        messages: [
          { id: '1', role: 'user', content: '继续分析', created_at: null },
        ],
        session_state: {
          selected_skill_ids: null,
        },
      },
    });

    const result = await agentApi.getChatSessionMessages('legacy-session');

    expect(result.session_state.selected_skill_ids).toBeNull();
  });
});
