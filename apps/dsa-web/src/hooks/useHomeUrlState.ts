// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef } from 'react';
import { useLocation, useNavigate, useNavigationType } from 'react-router-dom';
import type { ParsedApiError } from '../api/error';
import type { HomeWorkspaceValue } from '../routing/routes';
import type { RunFlowSnapshotSource } from '../types/runFlow';
import {
  clearHomeRecord,
  clearHomeRunFlow,
  parseHomeUrlState,
  setHomeHistoryRunFlow,
  setHomeRecord,
  setHomeTaskRunFlow,
  setHomeWorkspace,
} from '../utils/homeUrlState';

type UseHomeUrlStateOptions = {
  defaultRecordId: number | null;
  isHistoryLoading: boolean;
  selectedRecordId: number | null;
  selectedReportId: number | null;
  isReportLoading: boolean;
  reportError: ParsedApiError | null;
  reportSelectionEpoch?: number;
  selectHistoryItem: (recordId: number, isUserInitiated?: boolean) => Promise<void>;
  clearSelectedRecord: (preserveError?: boolean) => void;
};

type UseHomeUrlStateResult = {
  recordId: number | null;
  runFlowSource: RunFlowSnapshotSource | null;
  stockCode: string | null;
  workspace: HomeWorkspaceValue;
  urlIssue: HomeUrlIssue | null;
  dismissUrlIssue: () => void;
  navigateToRecord: (recordId: number) => void;
  replaceRecord: (recordId: number | null, preserveError?: boolean) => void;
  openTaskRunFlow: (taskId: string) => void;
  openHistoryRunFlow: (recordId: number) => void;
  closeRunFlow: () => void;
  removeUnavailableRunFlow: () => void;
  setWorkspace: (workspace: HomeWorkspaceValue) => void;
};

type HomeUrlIssue =
  | 'invalid_record'
  | 'invalid_run_flow'
  | 'invalid_stock'
  | 'invalid_workspace'
  | 'sensitive_parameter';
type PendingSearchNavigation = {
  originKey: string;
  targetSearch: string;
};
type RejectedRecordLocation = {
  recordId: number;
  locationKey: string;
  search: string;
};
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
  selectedReportId,
  isReportLoading,
  reportError,
  reportSelectionEpoch = 0,
  selectHistoryItem,
  clearSelectedRecord,
}: UseHomeUrlStateOptions): UseHomeUrlStateResult {
  const location = useLocation();
  const navigate = useNavigate();
  const navigationType = useNavigationType();
  const urlState = useMemo(() => parseHomeUrlState(location.search), [location.search]);
  const suppressDefaultForSearchRef = useRef<string | null>(null);
  const rejectedRecordLocationRef = useRef<RejectedRecordLocation | null>(null);
  // Deduplicate the URL intent itself so StrictMode effect replay cannot issue
  // the same detail request while React still exposes the prior store snapshot.
  const intendedRecordIdRef = useRef<number | null>(selectedRecordId);
  const defaultRecordIntentRef = useRef<number | null>(null);
  const pendingSearchRef = useRef<PendingSearchNavigation | null>(null);
  const preserveErrorOnClearRef = useRef(false);
  const observedReportSelectionEpochRef = useRef(reportSelectionEpoch);
  const navigationState = useMemo<Record<string, unknown>>(() => (
    location.state && typeof location.state === 'object'
      ? { ...(location.state as Record<string, unknown>) }
      : {}
  ), [location.state]);
  const persistedUrlIssue = navigationState[HOME_URL_ISSUE_STATE_KEY];
  const detectedUrlIssue: HomeUrlIssue | null = urlState.sensitiveParameterRemoved
    ? 'sensitive_parameter'
    : urlState.invalidRecordId
      ? 'invalid_record'
      : urlState.invalidRunFlow
        ? 'invalid_run_flow'
        : urlState.invalidStockCode
          ? 'invalid_stock'
          : urlState.invalidWorkspace
            ? 'invalid_workspace'
            : null;
  const isPersistedUrlIssue = (
    persistedUrlIssue === 'invalid_record'
    || persistedUrlIssue === 'invalid_run_flow'
    || persistedUrlIssue === 'invalid_stock'
    || persistedUrlIssue === 'invalid_workspace'
    || persistedUrlIssue === 'sensitive_parameter'
  );
  const urlIssue: HomeUrlIssue | null = detectedUrlIssue
    ?? (isPersistedUrlIssue ? persistedUrlIssue : null);

  useEffect(() => {
    if (observedReportSelectionEpochRef.current === reportSelectionEpoch) {
      return;
    }
    observedReportSelectionEpochRef.current = reportSelectionEpoch;
    intendedRecordIdRef.current = null;
    defaultRecordIntentRef.current = null;
    rejectedRecordLocationRef.current = null;
    suppressDefaultForSearchRef.current = null;
    preserveErrorOnClearRef.current = false;
  }, [reportSelectionEpoch]);

  const navigateSearch = useCallback((
    search: string,
    replace: boolean,
    issueAction: { set?: HomeUrlIssue; clear?: boolean } = {},
  ) => {
    pendingSearchRef.current = search === location.search
      ? null
      : { originKey: location.key, targetSearch: search };
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
  }, [location.hash, location.key, location.pathname, location.search, navigate, navigationState]);

  // Confirm the programmatic target before the new report can be painted and navigated away from.
  useLayoutEffect(() => {
    const pendingNavigation = pendingSearchRef.current;
    if (
      pendingNavigation
      && (
        pendingNavigation.targetSearch === location.search
        || pendingNavigation.originKey !== location.key
        || navigationType === 'POP'
      )
    ) {
      pendingSearchRef.current = null;
    }
  }, [location.key, location.search, navigationType]);

  useEffect(() => {
    if (urlState.needsNormalization) {
      navigateSearch(
        urlState.normalizedSearch,
        true,
        detectedUrlIssue ? { set: detectedUrlIssue } : {},
      );
    }
  }, [
    detectedUrlIssue,
    navigateSearch,
    urlState.needsNormalization,
    urlState.normalizedSearch,
  ]);

  useEffect(() => {
    if (urlState.needsNormalization) {
      return;
    }
    if (
      pendingSearchRef.current !== null
      && pendingSearchRef.current.targetSearch !== location.search
    ) {
      return;
    }

    if (urlState.recordId !== null) {
      const rejectedRecordLocation = rejectedRecordLocationRef.current;
      if (
        rejectedRecordLocation?.recordId === urlState.recordId
        && rejectedRecordLocation.locationKey === location.key
        && rejectedRecordLocation.search === location.search
      ) {
        return;
      }
      rejectedRecordLocationRef.current = null;
      suppressDefaultForSearchRef.current = null;
      const isDefaultSelection = defaultRecordIntentRef.current === urlState.recordId;
      defaultRecordIntentRef.current = null;
      if (intendedRecordIdRef.current !== urlState.recordId) {
        intendedRecordIdRef.current = urlState.recordId;
        void selectHistoryItem(urlState.recordId, !isDefaultSelection);
      }
      return;
    }

    if (suppressDefaultForSearchRef.current === location.search) {
      const preserveError = preserveErrorOnClearRef.current;
      preserveErrorOnClearRef.current = false;
      if (selectedRecordId !== null) {
        intendedRecordIdRef.current = null;
        clearSelectedRecord(preserveError);
      }
      return;
    }

    if (!isHistoryLoading && defaultRecordId !== null) {
      if (intendedRecordIdRef.current !== defaultRecordId) {
        defaultRecordIntentRef.current = defaultRecordId;
        intendedRecordIdRef.current = defaultRecordId;
        navigateSearch(setHomeRecord(location.search, defaultRecordId), true);
        void selectHistoryItem(defaultRecordId, false);
      }
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
    location.key,
    location.search,
    navigateSearch,
    reportSelectionEpoch,
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
    rejectedRecordLocationRef.current = {
      recordId: urlState.recordId,
      locationKey: location.key,
      search: location.search,
    };
    suppressDefaultForSearchRef.current = nextSearch;
    intendedRecordIdRef.current = null;
    preserveErrorOnClearRef.current = true;
    navigateSearch(nextSearch, true);
  }, [
    clearSelectedRecord,
    isReportLoading,
    location.key,
    location.search,
    navigateSearch,
    reportError,
    selectedRecordId,
    urlState.needsNormalization,
    urlState.recordId,
  ]);

  const navigateToRecord = useCallback((recordId: number) => {
    if (recordId === urlState.recordId) {
      if (selectedReportId !== recordId && !isReportLoading) {
        defaultRecordIntentRef.current = null;
        rejectedRecordLocationRef.current = null;
        suppressDefaultForSearchRef.current = null;
        preserveErrorOnClearRef.current = false;
        intendedRecordIdRef.current = recordId;
        void selectHistoryItem(recordId, true);
      }
      return;
    }
    defaultRecordIntentRef.current = null;
    rejectedRecordLocationRef.current = null;
    suppressDefaultForSearchRef.current = null;
    preserveErrorOnClearRef.current = false;
    navigateSearch(setHomeRecord(location.search, recordId), false, { clear: true });
  }, [
    isReportLoading,
    location.search,
    navigateSearch,
    selectHistoryItem,
    selectedReportId,
    urlState.recordId,
  ]);

  const replaceRecord = useCallback((recordId: number | null, preserveError = false) => {
    defaultRecordIntentRef.current = null;
    rejectedRecordLocationRef.current = null;
    if (recordId === null) {
      const nextSearch = clearHomeRecord(location.search);
      suppressDefaultForSearchRef.current = nextSearch;
      intendedRecordIdRef.current = null;
      preserveErrorOnClearRef.current = preserveError;
      navigateSearch(nextSearch, true, { clear: true });
      if (nextSearch === location.search && selectedRecordId !== null) {
        preserveErrorOnClearRef.current = false;
        clearSelectedRecord(preserveError);
      }
      return;
    }

    suppressDefaultForSearchRef.current = null;
    preserveErrorOnClearRef.current = false;
    navigateSearch(setHomeRecord(location.search, recordId), true, { clear: true });
  }, [clearSelectedRecord, location.search, navigateSearch, selectedRecordId]);

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

  const setWorkspace = useCallback((workspace: HomeWorkspaceValue) => {
    const nextSearch = setHomeWorkspace(location.search, workspace);
    if (nextSearch !== location.search) {
      navigateSearch(nextSearch, false, { clear: true });
    }
  }, [location.search, navigateSearch]);

  return {
    recordId: urlState.recordId,
    runFlowSource: urlState.runFlow,
    stockCode: urlState.stockCode,
    workspace: urlState.workspace,
    urlIssue,
    dismissUrlIssue,
    navigateToRecord,
    replaceRecord,
    openTaskRunFlow,
    openHistoryRunFlow,
    closeRunFlow,
    removeUnavailableRunFlow,
    setWorkspace,
  };
}

export default useHomeUrlState;
