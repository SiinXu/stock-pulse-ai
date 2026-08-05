// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { useCallback, useReducer } from 'react';
import type { ParsedApiError } from '../../api/error';
import type {
  DecisionProfile,
  DecisionSignalReassessBlockedError,
  DecisionSignalReassessResponse,
} from '../../types/decisionSignals';

export type DecisionSignalReassessState = {
  profile: DecisionProfile;
  response: DecisionSignalReassessResponse | null;
  loading: boolean;
  persisting: boolean;
  persistConfirm: boolean;
  persistBlocked: DecisionSignalReassessBlockedError | null;
  error: ParsedApiError | null;
};

type DecisionSignalReassessAction =
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

const INITIAL_REASSESS_STATE: DecisionSignalReassessState = {
  profile: 'balanced',
  response: null,
  loading: false,
  persisting: false,
  persistConfirm: false,
  persistBlocked: null,
  error: null,
};

function reassessReducer(
  state: DecisionSignalReassessState,
  action: DecisionSignalReassessAction,
): DecisionSignalReassessState {
  switch (action.type) {
    case 'setProfile':
      return { ...state, profile: action.profile };
    case 'resetForContext':
      return {
        ...state,
        response: null,
        error: null,
        loading: false,
        persisting: false,
        persistConfirm: false,
        persistBlocked: null,
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

  return {
    ...state,
    dispatch,
    setProfile,
    resetForContext,
    requestPersistConfirm,
    cancelPersistConfirm,
  };
}
