import { beforeEach, describe, expect, it, vi } from 'vitest';
import apiClient from '../index';
import { agentApi } from '../agent';

vi.mock('../index', () => ({ default: { post: vi.fn() } }));

const mockPost = vi.mocked(apiClient.post);

describe('agentApi.research', () => {
  beforeEach(() => mockPost.mockReset());

  it('POSTs the question with snake_case stock_code, a long timeout, and the abort signal', async () => {
    mockPost.mockResolvedValue({ data: { success: true, content: '# Findings', sources: ['q1', 'q2'], token_usage: 100 } });
    const controller = new AbortController();
    const result = await agentApi.research({ question: 'Why?', stockCode: '600519' }, { signal: controller.signal });
    expect(mockPost).toHaveBeenCalledWith(
      '/api/v1/agent/research',
      { question: 'Why?', stock_code: '600519' },
      expect.objectContaining({ timeout: 200000, signal: controller.signal }),
    );
    expect(result.success).toBe(true);
    expect(result.sources).toEqual(['q1', 'q2']);
  });

  it('sends undefined stock_code when omitted and surfaces the error field', async () => {
    mockPost.mockResolvedValue({ data: { success: false, content: '', sources: [], token_usage: 0, error: 'timed out' } });
    const result = await agentApi.research({ question: 'Q' });
    expect(mockPost).toHaveBeenCalledWith(
      '/api/v1/agent/research',
      { question: 'Q', stock_code: undefined },
      expect.any(Object),
    );
    expect(result.error).toBe('timed out');
  });
});

describe('agentApi.chat', () => {
  beforeEach(() => mockPost.mockReset());

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
});
