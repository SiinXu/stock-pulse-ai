// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { agentFeedbackApi, type AgentRunFeedbackItem } from '../../api/agentFeedback';
import { createApiError, createParsedApiError } from '../../api/error';
import { createDeferred } from '../../test-utils';
import {
  buildAgentRunFeedbackQueryKey,
  useAgentRunFeedback,
} from '../useAgentRunFeedback';

vi.mock('../../api/agentFeedback', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../api/agentFeedback')>();
  return {
    ...actual,
    agentFeedbackApi: {
      getRunFeedback: vi.fn(),
      putRunFeedback: vi.fn(),
    },
  };
});

function emptyItem(runId: string, overrides: Partial<AgentRunFeedbackItem> = {}): AgentRunFeedbackItem {
  return {
    runId,
    feedbackValue: null,
    note: null,
    source: null,
    provenanceSource: null,
    actorId: null,
    createdAt: null,
    updatedAt: null,
    ...overrides,
  };
}

function notFoundError() {
  return createApiError(createParsedApiError({
    title: 'Not found',
    message: 'Analysis run not found.',
    status: 404,
    code: 'not_found',
    category: 'http_error',
  }));
}

function validationError() {
  return createApiError(createParsedApiError({
    title: 'Invalid',
    message: 'Feedback note was rejected.',
    status: 400,
    code: 'invalid_request',
    category: 'http_error',
  }));
}

function createWrapper() {
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false, refetchOnWindowFocus: false },
      mutations: { retry: false },
    },
  });
  return {
    client,
    Wrapper({ children }: { children: ReactNode }) {
      return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
    },
  };
}

describe('useAgentRunFeedback', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('does not fetch empty or whitespace run ids and hides the panel', () => {
    const { Wrapper } = createWrapper();
    const { result } = renderHook(() => useAgentRunFeedback('   '), { wrapper: Wrapper });
    expect(agentFeedbackApi.getRunFeedback).not.toHaveBeenCalled();
    expect(result.current.hidden).toBe(true);
    expect(result.current.isLoading).toBe(false);
  });

  it('writes PUT 200 into the current runId cache and seeds the echoed note', async () => {
    vi.mocked(agentFeedbackApi.getRunFeedback).mockResolvedValueOnce(
      emptyItem('run-a', { note: 'keep-me' }),
    );
    vi.mocked(agentFeedbackApi.putRunFeedback).mockResolvedValueOnce(
      emptyItem('run-a', { feedbackValue: 'partial', note: 'keep-me' }),
    );
    const { client, Wrapper } = createWrapper();
    const { result } = renderHook(() => useAgentRunFeedback('run-a'), { wrapper: Wrapper });
    await waitFor(() => expect(result.current.draftNote).toBe('keep-me'));
    await act(async () => {
      await result.current.submitValue('partial');
    });
    expect(agentFeedbackApi.putRunFeedback).toHaveBeenCalledWith('run-a', {
      feedbackValue: 'partial',
      note: 'keep-me',
      source: 'web',
    });
    expect(result.current.feedbackValue).toBe('partial');
    expect(client.getQueryData(buildAgentRunFeedbackQueryKey('run-a'))).toMatchObject({
      feedbackValue: 'partial',
      note: 'keep-me',
    });
  });

  it('seeds an empty draft from a GET 200 null sidecar', async () => {
    vi.mocked(agentFeedbackApi.getRunFeedback).mockResolvedValueOnce(emptyItem('run-a'));
    const { Wrapper } = createWrapper();
    const { result } = renderHook(() => useAgentRunFeedback('run-a'), { wrapper: Wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.hidden).toBe(false);
    expect(result.current.feedbackValue).toBeNull();
    expect(result.current.draftNote).toBe('');
  });

  it('keeps the panel visible on GET 403 and does not treat forbidden as not_found', async () => {
    vi.mocked(agentFeedbackApi.getRunFeedback).mockRejectedValueOnce(
      createApiError(createParsedApiError({
        title: 'Forbidden',
        message: 'Not allowed.',
        status: 403,
        code: 'forbidden',
        category: 'http_error',
      })),
    );
    const { Wrapper } = createWrapper();
    const { result } = renderHook(() => useAgentRunFeedback('run-a'), { wrapper: Wrapper });
    await waitFor(() => expect(result.current.errorMessage).toBeTruthy());
    expect(result.current.hidden).toBe(false);
    expect(result.current.errorMessage).not.toBe('Analysis run not found.');
  });

  it('hides on GET 404 and shows an inline error on GET 500', async () => {
    vi.mocked(agentFeedbackApi.getRunFeedback)
      .mockRejectedValueOnce(notFoundError())
      .mockRejectedValueOnce(createApiError(createParsedApiError({
        title: 'Server error',
        message: 'Temporary failure.',
        status: 500,
        code: 'internal_error',
        category: 'http_error',
      })));
    const first = createWrapper();
    const { result: hidden } = renderHook(() => useAgentRunFeedback('missing'), { wrapper: first.Wrapper });
    await waitFor(() => expect(hidden.current.hidden).toBe(true));
    expect(hidden.current.errorMessage).toBeNull();

    const second = createWrapper();
    const { result: errored } = renderHook(() => useAgentRunFeedback('run-b'), { wrapper: second.Wrapper });
    await waitFor(() => expect(errored.current.errorMessage).toBeTruthy());
    expect(errored.current.hidden).toBe(false);
    expect(errored.current.errorMessage).not.toBe('Analysis run not found.');
  });

  it('updates only the submitted run cache on PUT 200 and ignores stale responses', async () => {
    const firstPut = createDeferred<AgentRunFeedbackItem>();
    vi.mocked(agentFeedbackApi.getRunFeedback)
      .mockResolvedValueOnce(emptyItem('run-a', { note: 'note-a' }))
      .mockResolvedValueOnce(emptyItem('run-b', { note: 'note-b' }));
    vi.mocked(agentFeedbackApi.putRunFeedback).mockReturnValueOnce(firstPut.promise);
    const { client, Wrapper } = createWrapper();
    const { result, rerender } = renderHook(
      ({ queryId }: { queryId: string }) => useAgentRunFeedback(queryId),
      { wrapper: Wrapper, initialProps: { queryId: 'run-a' } },
    );
    await waitFor(() => expect(result.current.draftNote).toBe('note-a'));

    act(() => {
      void result.current.submitValue('useful');
    });
    rerender({ queryId: 'run-b' });
    await waitFor(() => expect(result.current.draftNote).toBe('note-b'));

    await act(async () => {
      firstPut.resolve(emptyItem('run-a', {
        feedbackValue: 'useful',
        note: 'stale-note',
      }));
    });

    await waitFor(() => expect(result.current.draftNote).toBe('note-b'));
    expect(client.getQueryData(buildAgentRunFeedbackQueryKey('run-b'))).toMatchObject({ note: 'note-b' });
    expect(client.getQueryData(buildAgentRunFeedbackQueryKey('run-a'))).not.toMatchObject({ note: 'stale-note' });
    expect(result.current.feedbackValue).toBeNull();
  });

  it('does not setQueryData on a failed PUT and does not copy notes across run ids', async () => {
    vi.mocked(agentFeedbackApi.getRunFeedback)
      .mockResolvedValueOnce(emptyItem('run-a', { feedbackValue: 'useful', note: 'keep-me' }))
      .mockResolvedValueOnce(emptyItem('run-b', { note: 'other-run' }));
    vi.mocked(agentFeedbackApi.putRunFeedback).mockRejectedValueOnce(validationError());
    const { client, Wrapper } = createWrapper();
    const { result, rerender } = renderHook(
      ({ queryId }: { queryId: string }) => useAgentRunFeedback(queryId),
      { wrapper: Wrapper, initialProps: { queryId: 'run-a' } },
    );
    await waitFor(() => expect(result.current.draftNote).toBe('keep-me'));
    act(() => {
      result.current.setDraftNote('stockpulse-agent-soul');
    });
    await act(async () => {
      await result.current.submitValue('useful');
    });
    expect(result.current.feedbackValue).toBe('useful');
    expect(result.current.draftNote).toBe('stockpulse-agent-soul');
    expect(result.current.errorMessage).toBe('Feedback note was rejected.');
    expect(client.getQueryData(buildAgentRunFeedbackQueryKey('run-a'))).toMatchObject({ note: 'keep-me' });

    rerender({ queryId: 'run-b' });
    await waitFor(() => expect(result.current.draftNote).toBe('other-run'));
    expect(result.current.feedbackValue).toBeNull();
  });
});
