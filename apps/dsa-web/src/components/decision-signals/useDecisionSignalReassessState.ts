// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { useCallback, useReducer } from 'react';
import type { ParsedApiError } from '../../api/error';
import type {
  DecisionProfile,
  DecisionSignalReassessBlockedError,
  DecisionSignalReassessResponse,
} from '../../types/decisionSignals';

export type ReassessSessionStatus = 'idle' | 'active';

export type ReassessLockedContext = {
  signalId: number | null;
  stockCode: string | null;
  sourceReportId: number | null;
};

export type ReassessIdentityCandidate = {
  signalId?: number | null;
  stockCode?: string | null;
};

export type DecisionSignalReassessState = {
  sessionStatus: ReassessSessionStatus;
  lockedContext: ReassessLockedContext | null;
  profile: DecisionProfile;
  response: DecisionSignalReassessResponse | null;
  loading: boolean;
  persisting: boolean;
  persistConfirm: boolean;
  persistBlocked: DecisionSignalReassessBlockedError | null;
  error: ParsedApiError | null;
};

type DecisionSignalReassessAction =
  | { type: 'enterSession'; context: ReassessLockedContext }
  | { type: 'exitSession' }
  | { type: 'setProfile'; profile: DecisionProfile }
  | { type: 'resetForContext' }
  | { type: 'previewStart' }
  | { type: 'previewSuccess'; response: DecisionSignalReassessResponse }
  | { type: 'previewFailure'; error: ParsedApiError }
  | { type: 'previewEnd' }
  | { type: 'requestPersistConfirm' }
  | { type: 'cancelPersistConfirm' }
  | { type: 'persistStart' }
  | { type: 'persistSuccess'; response: DecisionSignalReassessResponse }
  | { type: 'persistBlocked'; blocked: DecisionSignalReassessBlockedError }
  | { type: 'persistFailure'; error: ParsedApiError }
  | { type: 'persistEnd' };

const IDLE_ASYNC_STATE = {
  response: null,
  loading: false,
  persisting: false,
  persistConfirm: false,
  persistBlocked: null,
  error: null,
} as const;

const INITIAL_REASSESS_STATE: DecisionSignalReassessState = {
  sessionStatus: 'idle',
  lockedContext: null,
  profile: 'balanced',
  ...IDLE_ASYNC_STATE,
};

export function shouldAcceptReassessIdentityChange(
  sessionStatus: ReassessSessionStatus,
  lockedContext: ReassessLockedContext | null,
  next: ReassessIdentityCandidate,
): boolean {
  if (sessionStatus !== 'active' || lockedContext === null) return true;
  if (next.signalId !== undefined && next.signalId !== lockedContext.signalId) return false;
  if (next.stockCode !== undefined && next.stockCode !== lockedContext.stockCode) return false;
  return true;
}

function reassessReducer(
  state: DecisionSignalReassessState,
  action: DecisionSignalReassessAction,
): DecisionSignalReassessState {
  switch (action.type) {
    case 'enterSession':
      if (state.sessionStatus === 'active') return state;
      return {
        ...state,
        sessionStatus: 'active',
        lockedContext: action.context,
        ...IDLE_ASYNC_STATE,
      };
    case 'exitSession':
      return {
        ...state,
        sessionStatus: 'idle',
        lockedContext: null,
        ...IDLE_ASYNC_STATE,
      };
    case 'setProfile':
      return { ...state, profile: action.profile };
    case 'resetForContext':
      return {
        ...state,
        ...IDLE_ASYNC_STATE,
      };
    case 'previewStart':
      return {
        ...state,
        loading: true,
        error: null,
        persistBlocked: null,
      };
    case 'previewSuccess':
      return {
        ...state,
        response: action.response,
        error: null,
      };
    case 'previewFailure':
      return {
        ...state,
        response: null,
        error: action.error,
      };
    case 'previewEnd':
      return { ...state, loading: false };
    case 'requestPersistConfirm':
      return { ...state, persistConfirm: true };
    case 'cancelPersistConfirm':
      return { ...state, persistConfirm: false };
    case 'persistStart':
      return {
        ...state,
        persistConfirm: false,
        persisting: true,
        error: null,
        persistBlocked: null,
      };
    case 'persistSuccess':
      return {
        ...state,
        response: action.response,
        error: null,
        persistBlocked: null,
      };
    case 'persistBlocked':
      return {
        ...state,
        persistBlocked: action.blocked,
        error: null,
      };
    case 'persistFailure':
      return {
        ...state,
        error: action.error,
      };
    case 'persistEnd':
      return { ...state, persisting: false };
    default:
      return state;
  }
}

export function useDecisionSignalReassessState() {
  const [state, dispatch] = useReducer(reassessReducer, INITIAL_REASSESS_STATE);

  const enterSession = useCallback((context: ReassessLockedContext) => {
    dispatch({ type: 'enterSession', context });
  }, []);

  const exitSession = useCallback(() => {
    dispatch({ type: 'exitSession' });
  }, []);

  const setProfile = useCallback((profile: DecisionProfile) => {
    dispatch({ type: 'setProfile', profile });
  }, []);

  const resetForContext = useCallback(() => {
    dispatch({ type: 'resetForContext' });
  }, []);

  const requestPersistConfirm = useCallback(() => {
    dispatch({ type: 'requestPersistConfirm' });
  }, []);

  const cancelPersistConfirm = useCallback(() => {
    dispatch({ type: 'cancelPersistConfirm' });
  }, []);

  const shouldAcceptIdentityChange = useCallback((next: ReassessIdentityCandidate) => (
    shouldAcceptReassessIdentityChange(state.sessionStatus, state.lockedContext, next)
  ), [state.lockedContext, state.sessionStatus]);

  return {
    ...state,
    dispatch,
    enterSession,
    exitSession,
    setProfile,
    resetForContext,
    requestPersistConfirm,
    cancelPersistConfirm,
    shouldAcceptIdentityChange,
  };
}
