import { useCallback, useEffect, useLayoutEffect, useMemo, useRef } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import type { ParsedApiError } from '../api/error';
import type { RunFlowSnapshotSource } from '../types/runFlow';
import {
  clearHomeRecord,
  clearHomeRunFlow,
  parseHomeUrlState,
  setHomeHistoryRunFlow,
  setHomeRecord,
  setHomeTaskRunFlow,
} from '../utils/homeUrlState';

type UseHomeUrlStateOptions = {
  defaultRecordId: number | null;
  isHistoryLoading: boolean;
  selectedRecordId: number | null;
  isReportLoading: boolean;
  reportError: ParsedApiError | null;
  selectHistoryItem: (recordId: number, isUserInitiated?: boolean) => Promise<void>;
  clearSelectedRecord: (preserveError?: boolean) => void;
};

type UseHomeUrlStateResult = {
  runFlowSource: RunFlowSnapshotSource | null;
  urlIssue: 'invalid_record' | 'invalid_run_flow' | null;
  dismissUrlIssue: () => void;
  navigateToRecord: (recordId: number) => void;
  openTaskRunFlow: (taskId: string) => void;
  openHistoryRunFlow: (recordId: number) => void;
  closeRunFlow: () => void;
  removeUnavailableRunFlow: () => void;
};

type HomeUrlIssue = 'invalid_record' | 'invalid_run_flow';
const HOME_URL_ISSUE_STATE_KEY = '__stockPulseHomeUrlIssue';

const isPermanentRecordError = (error: ParsedApiError | null): boolean => Boolean(
  error
  && (
    error.status === 401
    || error.status === 403
    || error.status === 404
    || error.code === 'unauthorized'
    || error.code === 'forbidden'
    || error.code === 'not_found'
  ),
);

export function useHomeUrlState({
  defaultRecordId,
  isHistoryLoading,
  selectedRecordId,
  isReportLoading,
  reportError,
  selectHistoryItem,
  clearSelectedRecord,
}: UseHomeUrlStateOptions): UseHomeUrlStateResult {
  const location = useLocation();
  const navigate = useNavigate();
  const urlState = useMemo(() => parseHomeUrlState(location.search), [location.search]);
  const suppressDefaultForSearchRef = useRef<string | null>(null);
  const rejectedRecordIdRef = useRef<number | null>(null);
  const intendedRecordIdRef = useRef<number | null>(selectedRecordId);
  const observedSelectedRecordIdRef = useRef<number | null>(selectedRecordId);
  const pendingSearchRef = useRef<string | null>(null);
  const navigationState = useMemo<Record<string, unknown>>(() => (
    location.state && typeof location.state === 'object'
      ? { ...(location.state as Record<string, unknown>) }
      : {}
  ), [location.state]);
  const persistedUrlIssue = navigationState[HOME_URL_ISSUE_STATE_KEY];
  const urlIssue: HomeUrlIssue | null = urlState.invalidRecordId
    ? 'invalid_record'
    : urlState.invalidRunFlow
      ? 'invalid_run_flow'
      : persistedUrlIssue === 'invalid_record' || persistedUrlIssue === 'invalid_run_flow'
        ? persistedUrlIssue
        : null;

  useEffect(() => {
    if (observedSelectedRecordIdRef.current !== selectedRecordId) {
      observedSelectedRecordIdRef.current = selectedRecordId;
      intendedRecordIdRef.current = selectedRecordId;
    }
  }, [selectedRecordId]);

  const navigateSearch = useCallback((
    search: string,
    replace: boolean,
    issueAction: { set?: HomeUrlIssue; clear?: boolean } = {},
  ) => {
    pendingSearchRef.current = search === location.search ? null : search;
    const nextState = { ...navigationState };
    if (issueAction.set) {
      nextState[HOME_URL_ISSUE_STATE_KEY] = issueAction.set;
    } else if (issueAction.clear) {
      delete nextState[HOME_URL_ISSUE_STATE_KEY];
    }
    navigate(
      {
        pathname: location.pathname,
        search,
        hash: location.hash,
      },
      { replace, state: Object.keys(nextState).length > 0 ? nextState : null },
    );
  }, [location.hash, location.pathname, location.search, navigate, navigationState]);

  // Confirm the programmatic target before the new report can be painted and navigated away from.
  useLayoutEffect(() => {
    if (pendingSearchRef.current === location.search) {
      pendingSearchRef.current = null;
    }
  }, [location.search]);

  useEffect(() => {
    if (urlState.needsNormalization) {
      const issue = urlState.invalidRecordId
        ? 'invalid_record'
        : urlState.invalidRunFlow
          ? 'invalid_run_flow'
          : undefined;
      navigateSearch(urlState.normalizedSearch, true, { set: issue });
    }
  }, [
    navigateSearch,
    urlState.invalidRecordId,
    urlState.invalidRunFlow,
    urlState.needsNormalization,
    urlState.normalizedSearch,
  ]);

  useEffect(() => {
    if (urlState.needsNormalization) {
      return;
    }
    if (pendingSearchRef.current !== null && pendingSearchRef.current !== location.search) {
      return;
    }

    if (urlState.recordId !== null) {
      if (rejectedRecordIdRef.current === urlState.recordId) {
        return;
      }
      rejectedRecordIdRef.current = null;
      suppressDefaultForSearchRef.current = null;
      if (intendedRecordIdRef.current !== urlState.recordId) {
        intendedRecordIdRef.current = urlState.recordId;
        void selectHistoryItem(urlState.recordId, true);
      }
      return;
    }

    if (suppressDefaultForSearchRef.current === location.search) {
      return;
    }

    if (!isHistoryLoading && defaultRecordId !== null) {
      if (intendedRecordIdRef.current !== defaultRecordId) {
        intendedRecordIdRef.current = defaultRecordId;
        void selectHistoryItem(defaultRecordId, false);
      }
      navigateSearch(setHomeRecord(location.search, defaultRecordId), true);
      return;
    }

    if (!isHistoryLoading && defaultRecordId === null && selectedRecordId !== null) {
      intendedRecordIdRef.current = null;
      clearSelectedRecord();
    }
  }, [
    clearSelectedRecord,
    defaultRecordId,
    isHistoryLoading,
    location.search,
    navigateSearch,
    selectHistoryItem,
    selectedRecordId,
    urlState.needsNormalization,
    urlState.recordId,
  ]);

  useEffect(() => {
    if (
      urlState.needsNormalization
      || urlState.recordId === null
      || urlState.recordId !== selectedRecordId
      || isReportLoading
      || !isPermanentRecordError(reportError)
    ) {
      return;
    }

    const nextSearch = clearHomeRecord(location.search);
    rejectedRecordIdRef.current = urlState.recordId;
    suppressDefaultForSearchRef.current = nextSearch;
    intendedRecordIdRef.current = null;
    clearSelectedRecord(true);
    navigateSearch(nextSearch, true);
  }, [
    clearSelectedRecord,
    isReportLoading,
    location.search,
    navigateSearch,
    reportError,
    selectedRecordId,
    urlState.needsNormalization,
    urlState.recordId,
  ]);

  const navigateToRecord = useCallback((recordId: number) => {
    rejectedRecordIdRef.current = null;
    suppressDefaultForSearchRef.current = null;
    navigateSearch(setHomeRecord(location.search, recordId), false, { clear: true });
    if (intendedRecordIdRef.current !== recordId) {
      intendedRecordIdRef.current = recordId;
      void selectHistoryItem(recordId, true);
    }
  }, [location.search, navigateSearch, selectHistoryItem]);

  const openTaskRunFlow = useCallback((taskId: string) => {
    navigateSearch(setHomeTaskRunFlow(location.search, taskId), false, { clear: true });
  }, [location.search, navigateSearch]);

  const openHistoryRunFlow = useCallback((recordId: number) => {
    navigateSearch(setHomeHistoryRunFlow(location.search, recordId), false, { clear: true });
  }, [location.search, navigateSearch]);

  const closeRunFlow = useCallback(() => {
    navigateSearch(clearHomeRunFlow(location.search), false);
  }, [location.search, navigateSearch]);

  const removeUnavailableRunFlow = useCallback(() => {
    navigateSearch(clearHomeRunFlow(location.search), true);
  }, [location.search, navigateSearch]);

  const dismissUrlIssue = useCallback(() => {
    navigateSearch(location.search, true, { clear: true });
  }, [location.search, navigateSearch]);

  return {
    runFlowSource: urlState.runFlow,
    urlIssue,
    dismissUrlIssue,
    navigateToRecord,
    openTaskRunFlow,
    openHistoryRunFlow,
    closeRunFlow,
    removeUnavailableRunFlow,
  };
}

export default useHomeUrlState;
