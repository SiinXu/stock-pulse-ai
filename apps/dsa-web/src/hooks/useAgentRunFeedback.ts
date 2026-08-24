// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useCallback, useEffect, useRef, useState } from 'react';
import {
  agentFeedbackApi,
  canonicalizeAgentRunId,
  type AgentRunFeedbackItem,
  type AgentRunFeedbackValue,
} from '../api/agentFeedback';
import { getParsedApiError, type ParsedApiError } from '../api/error';
import { useUiLanguage } from '../contexts/UiLanguageContext';

export const AGENT_RUN_FEEDBACK_QUERY_KEY_ROOT = ['agent-run-feedback'] as const;

export function buildAgentRunFeedbackQueryKey(
  runId: string | null,
): readonly unknown[] {
  return [...AGENT_RUN_FEEDBACK_QUERY_KEY_ROOT, runId] as const;
}

function isNotFoundError(error: ParsedApiError | null): boolean {
  return Boolean(error && (error.status === 404 || error.code === 'not_found'));
}

export type AgentRunFeedbackView = {
  hidden: boolean;
  runId: string | null;
  feedbackValue: AgentRunFeedbackValue | null;
  draftNote: string;
  isLoading: boolean;
  isSaving: boolean;
  errorMessage: string | null;
  setDraftNote: (note: string) => void;
  submitValue: (feedbackValue: AgentRunFeedbackValue) => Promise<void>;
};

export function useAgentRunFeedback(
  queryId: string | null | undefined,
): AgentRunFeedbackView {
  const runId = canonicalizeAgentRunId(queryId);
  const { language } = useUiLanguage();
  const queryClient = useQueryClient();
  const runIdRef = useRef(runId);
  runIdRef.current = runId;

  const query = useQuery({
    queryKey: buildAgentRunFeedbackQueryKey(runId),
    queryFn: async () => {
      if (runId == null) {
        return null as AgentRunFeedbackItem | null;
      }
      return agentFeedbackApi.getRunFeedback(runId);
    },
    enabled: runId != null,
    retry: false,
    refetchOnWindowFocus: false,
  });

  const [draftNote, setDraftNote] = useState('');
  const [writeError, setWriteError] = useState<ParsedApiError | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  const savingRef = useRef(false);
  const seededRunIdRef = useRef<string | null>(null);

  useEffect(() => {
    seededRunIdRef.current = null;
    savingRef.current = false;
    setDraftNote('');
    setWriteError(null);
    setIsSaving(false);
  }, [runId]);

  useEffect(() => {
    if (runId == null || query.isLoading || query.isError || !query.data) {
      return;
    }
    if (seededRunIdRef.current === runId) {
      return;
    }
    seededRunIdRef.current = runId;
    setDraftNote(query.data.note ?? '');
  }, [runId, query.data, query.isError, query.isLoading]);

  const submitValue = useCallback(async (feedbackValue: AgentRunFeedbackValue) => {
    const submittedRunId = runIdRef.current;
    if (submittedRunId == null || savingRef.current || query.isLoading) {
      return;
    }
    const submittedNote = draftNote;
    savingRef.current = true;
    setIsSaving(true);
    try {
      const updated = await agentFeedbackApi.putRunFeedback(submittedRunId, {
        feedbackValue,
        note: submittedNote,
        source: 'web',
      });
      if (runIdRef.current !== submittedRunId) {
        return;
      }
      queryClient.setQueryData(buildAgentRunFeedbackQueryKey(submittedRunId), updated);
      seededRunIdRef.current = submittedRunId;
      setDraftNote(updated.note ?? '');
      setWriteError(null);
    } catch (error) {
      if (runIdRef.current !== submittedRunId) {
        return;
      }
      setWriteError(getParsedApiError(error, language));
    } finally {
      if (runIdRef.current === submittedRunId) {
        savingRef.current = false;
        setIsSaving(false);
      }
    }
  }, [draftNote, language, query.isLoading, queryClient]);

  const readError = query.isError ? getParsedApiError(query.error, language) : null;
  const parsedError = writeError ?? readError;
  const hidden = runId == null || isNotFoundError(parsedError);
  const serverItem = query.isError ? null : (query.data ?? null);

  return {
    hidden,
    runId,
    feedbackValue: serverItem?.feedbackValue ?? null,
    draftNote,
    isLoading: runId != null && query.isLoading,
    isSaving,
    errorMessage: hidden ? null : (parsedError?.message ?? null),
    setDraftNote,
    submitValue,
  };
}

export default useAgentRunFeedback;
