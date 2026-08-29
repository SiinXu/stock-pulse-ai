// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
// Feature-private projection policy for the Portfolio route.

import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type SetStateAction,
} from 'react';
import { CancelledError, keepPreviousData, useQuery, useQueryClient } from '@tanstack/react-query';
import type { ParsedApiError } from '../../api/error';
import { getParsedApiError } from '../../api/error';
import type { UiLanguage } from '../../i18n/uiText';
import type {
  PortfolioCashDirection,
  PortfolioCashLedgerListItem,
  PortfolioCorporateActionListItem,
  PortfolioCorporateActionType,
  PortfolioCostMethod,
  PortfolioRiskResponse,
  PortfolioSide,
  PortfolioSnapshotResponse,
  PortfolioTradeListItem,
} from '../../types/portfolio';
import { portfolioApi } from '../../api/portfolio';
import {
  buildFxRefreshFeedback,
  type FxRefreshFeedback,
} from '../../utils/portfolioFormat';
import {
  PORTFOLIO_PROJECTION_CANCEL,
  PORTFOLIO_PROJECTION_DEFAULT_PAGE_SIZE,
  PORTFOLIO_PROJECTION_QUERY_SCHEDULE,
  buildPortfolioProjectionEventsQueryKey,
  buildPortfolioProjectionSnapshotQueryKey,
  fetchPortfolioEvents,
  fetchPortfolioSnapshotAndRisk,
  type PortfolioEventFilters,
  type PortfolioEventType,
} from './usePortfolioProjectionQueries';

export type { PortfolioEventType } from './usePortfolioProjectionQueries';

type ProjectionRequest = {
  requestId: number;
  scopeKey: string;
};

type EventProjectionRequest = ProjectionRequest & {
  accountScopeKey: string;
};

type SnapshotRiskLoadOutcome = {
  snapshotAccepted: boolean;
  riskAccepted: boolean;
};

type UsePortfolioProjectionSessionOptions = {
  accountId: number | undefined;
  costMethod: PortfolioCostMethod;
  hasAccounts: boolean;
  language: UiLanguage;
  riskFallbackMessage: string;
  loadAccounts: () => Promise<boolean>;
  setError: (error: ParsedApiError | null) => void;
};

/** Query-scope fencing input. Page is eventPageForScope, not lagging React state. */
type PortfolioProjectionActiveParams = {
  accountId: number | undefined;
  costMethod: PortfolioCostMethod;
  language: UiLanguage;
  riskFallbackMessage: string;
  eventType: PortfolioEventType;
  appliedEventFilters: PortfolioEventFilters;
  eventPageForScope: number;
  eventRefreshKey: number;
};

const EMPTY_EVENT_FILTERS: PortfolioEventFilters = {
  dateFrom: '',
  dateTo: '',
  symbol: '',
  side: '',
  direction: '',
  actionType: '',
};

function isCancelledError(error: unknown): boolean {
  return error instanceof CancelledError;
}

function queryKeysEqual(left: readonly unknown[], right: readonly unknown[]): boolean {
  return JSON.stringify(left) === JSON.stringify(right);
}

export function usePortfolioProjectionSession({
  accountId,
  costMethod,
  hasAccounts,
  language,
  riskFallbackMessage,
  loadAccounts,
  setError,
}: UsePortfolioProjectionSessionOptions) {
  const queryClient = useQueryClient();

  const [isLoading, setIsLoading] = useState(true);
  const [fxRefreshing, setFxRefreshing] = useState(false);
  const [fxRefreshFeedback, setFxRefreshFeedback] = useState<FxRefreshFeedback | null>(null);

  const [eventType, setEventTypeState] = useState<PortfolioEventType>('trade');
  const [eventDateFrom, setEventDateFrom] = useState('');
  const [eventDateTo, setEventDateTo] = useState('');
  const [eventSymbol, setEventSymbol] = useState('');
  const [eventSide, setEventSide] = useState<'' | PortfolioSide>('');
  const [eventDirection, setEventDirection] = useState<'' | PortfolioCashDirection>('');
  const [eventActionType, setEventActionType] = useState<'' | PortfolioCorporateActionType>('');
  const [appliedEventFilters, setAppliedEventFilters] = useState<PortfolioEventFilters>(EMPTY_EVENT_FILTERS);
  const [eventPage, setEventPageState] = useState(1);
  const eventPageAccountRef = useRef(accountId);
  let eventPageForScope = eventPage;
  if (eventPageAccountRef.current !== accountId) {
    eventPageAccountRef.current = accountId;
    eventPageForScope = 1;
    if (eventPage !== 1) {
      setEventPageState(1);
    }
  }
  const [eventRefreshKey, setEventRefreshKey] = useState(0);
  const [eventTotal, setEventTotal] = useState(0);
  const [eventError, setEventError] = useState<ParsedApiError | null>(null);
  const [tradeEvents, setTradeEvents] = useState<PortfolioTradeListItem[]>([]);
  const [cashEvents, setCashEvents] = useState<PortfolioCashLedgerListItem[]>([]);
  const [corporateEvents, setCorporateEvents] = useState<PortfolioCorporateActionListItem[]>([]);
  const [paperTradeProjectionRevision, setPaperTradeProjectionRevision] = useState(0);

  const accountScopeKey = accountId === undefined ? 'all' : `account:${accountId}`;
  const snapshotScopeKey = `${accountScopeKey}:cost:${costMethod}`;
  const activeAccountScopeRef = useRef(accountScopeKey);
  const activeSnapshotScopeRef = useRef(snapshotScopeKey);
  activeAccountScopeRef.current = accountScopeKey;
  activeSnapshotScopeRef.current = snapshotScopeKey;

  const snapshotRequestRef = useRef<ProjectionRequest>({
    requestId: 0,
    scopeKey: snapshotScopeKey,
  });
  const snapshotLoadingOwnerRef = useRef<ProjectionRequest | null>(null);
  const eventRequestRef = useRef<EventProjectionRequest>({
    requestId: 0,
    accountScopeKey,
    scopeKey: JSON.stringify({
      accountScopeKey,
      eventType,
      filters: EMPTY_EVENT_FILTERS,
      page: eventPageForScope,
      refreshKey: 0,
    }),
  });
  const fxRequestRef = useRef<ProjectionRequest>({
    requestId: 0,
    scopeKey: snapshotScopeKey,
  });
  const snapshotFenceRef = useRef(0);
  const eventFenceRef = useRef(0);

  const snapshotQueryKey = useMemo(
    () => buildPortfolioProjectionSnapshotQueryKey(accountId, costMethod, language),
    [accountId, costMethod, language],
  );
  const eventsQueryKey = useMemo(
    () => buildPortfolioProjectionEventsQueryKey(
      accountId,
      eventType,
      appliedEventFilters,
      eventPageForScope,
      eventRefreshKey,
    ),
    [accountId, appliedEventFilters, eventPageForScope, eventRefreshKey, eventType],
  );
  const eventsQueryKeyRef = useRef(eventsQueryKey);
  eventsQueryKeyRef.current = eventsQueryKey;
  const snapshotQueryKeyRef = useRef(snapshotQueryKey);
  snapshotQueryKeyRef.current = snapshotQueryKey;
  const inFlightEventQueryKeysRef = useRef<Array<readonly unknown[]>>([]);
  const activeParamsRef = useRef<PortfolioProjectionActiveParams>({
    accountId,
    costMethod,
    language,
    riskFallbackMessage,
    eventType,
    appliedEventFilters,
    eventPageForScope,
    eventRefreshKey,
  });
  activeParamsRef.current = {
    accountId,
    costMethod,
    language,
    riskFallbackMessage,
    eventType,
    appliedEventFilters,
    eventPageForScope,
    eventRefreshKey,
  };

  const isActiveSnapshotRequest = useCallback((request: ProjectionRequest) => (
    activeSnapshotScopeRef.current === request.scopeKey
    && snapshotRequestRef.current.requestId === request.requestId
    && snapshotRequestRef.current.scopeKey === request.scopeKey
  ), []);

  const isActiveEventRequest = useCallback((request: EventProjectionRequest) => (
    activeAccountScopeRef.current === request.accountScopeKey
    && eventRequestRef.current.requestId === request.requestId
    && eventRequestRef.current.scopeKey === request.scopeKey
  ), []);

  const isActiveFxRequest = useCallback((request: ProjectionRequest) => (
    activeSnapshotScopeRef.current === request.scopeKey
    && fxRequestRef.current.requestId === request.requestId
    && fxRequestRef.current.scopeKey === request.scopeKey
  ), []);

  const terminateExactEventQuery = useCallback((key: readonly unknown[]) => {
    void queryClient.cancelQueries(
      { queryKey: key, exact: true },
      PORTFOLIO_PROJECTION_CANCEL,
    );
    queryClient.removeQueries({ queryKey: key, exact: true });
  }, [queryClient]);

  const invalidateEventRequest = useCallback(() => {
    eventFenceRef.current += 1;
    eventRequestRef.current = {
      ...eventRequestRef.current,
      accountScopeKey: activeAccountScopeRef.current,
      requestId: eventRequestRef.current.requestId + 1,
    };
    // Never silent-cancel the live observer key here: Query 5 returns the
    // pending retryer and skips error dispatch, so fetchStatus sticks unless a
    // same-key successor or exact-key removeQueries follows. Key-changing
    // transitions rely on the observer layout cleanup. Off-key fetchQuery
    // (paper-trade page-1 while cash is current) must be exact-removed now.
    const observerKey = eventsQueryKeyRef.current;
    const remaining: Array<readonly unknown[]> = [];
    inFlightEventQueryKeysRef.current.forEach((key) => {
      if (queryKeysEqual(key, observerKey)) {
        remaining.push(key);
        return;
      }
      terminateExactEventQuery(key);
    });
    inFlightEventQueryKeysRef.current = remaining;
  }, [terminateExactEventQuery]);

  const activeEventTypeRef = useRef(eventType);
  const eventPageRef = useRef(eventPageForScope);
  activeEventTypeRef.current = eventType;
  eventPageRef.current = eventPageForScope;

  const transitionEventQuery = useCallback((
    nextEventType: PortfolioEventType,
    nextPage: number,
    forceInvalidate = false,
  ): boolean => {
    const typeChanged = nextEventType !== activeEventTypeRef.current;
    const pageChanged = nextPage !== eventPageRef.current;
    if (!typeChanged && !pageChanged && !forceInvalidate) return false;

    invalidateEventRequest();
    activeEventTypeRef.current = nextEventType;
    eventPageRef.current = nextPage;
    if (typeChanged) setEventTypeState(nextEventType);
    if (pageChanged) setEventPageState(nextPage);
    return true;
  }, [invalidateEventRequest]);

  const setEventType = useCallback((nextEventType: PortfolioEventType) => {
    if (nextEventType === activeEventTypeRef.current) return;
    transitionEventQuery(nextEventType, 1);
  }, [transitionEventQuery]);

  const setEventPage = useCallback((nextPage: SetStateAction<number>) => {
    const resolvedPage = typeof nextPage === 'function'
      ? nextPage(eventPageRef.current)
      : nextPage;
    transitionEventQuery(activeEventTypeRef.current, resolvedPage);
  }, [transitionEventQuery]);

  const snapshotQuery = useQuery({
    queryKey: snapshotQueryKey,
    queryFn: async ({ signal }) => {
      const startedAt = snapshotFenceRef.current;
      const requestScope = snapshotScopeKey;
      return fetchPortfolioSnapshotAndRisk({
        accountId,
        costMethod,
        language,
        riskFallbackMessage,
        signal,
        stillActive: () => (
          snapshotFenceRef.current === startedAt
          && activeSnapshotScopeRef.current === requestScope
        ),
      });
    },
    ...PORTFOLIO_PROJECTION_QUERY_SCHEDULE,
    placeholderData: keepPreviousData,
  });

  const eventsQuery = useQuery({
    queryKey: eventsQueryKey,
    queryFn: async ({ signal }) => {
      const startedAt = eventFenceRef.current;
      const startedAccountId = accountId;
      const startedEventType = eventType;
      const startedPage = eventPageForScope;
      const startedRefreshKey = eventRefreshKey;
      const startedFilters = appliedEventFilters;
      return fetchPortfolioEvents({
        accountId: startedAccountId,
        eventType: startedEventType,
        filters: startedFilters,
        page: startedPage,
        signal,
        stillActive: () => {
          const active = activeParamsRef.current;
          return eventFenceRef.current === startedAt
            && active.accountId === startedAccountId
            && active.eventType === startedEventType
            && active.eventPageForScope === startedPage
            && active.eventRefreshKey === startedRefreshKey
            && active.appliedEventFilters === startedFilters;
        },
      });
    },
    ...PORTFOLIO_PROJECTION_QUERY_SCHEDULE,
  });

  useLayoutEffect(() => {
    return () => {
      void queryClient.cancelQueries(
        { queryKey: snapshotQueryKey, exact: true },
        PORTFOLIO_PROJECTION_CANCEL,
      );
      queryClient.removeQueries({ queryKey: snapshotQueryKey, exact: true });
    };
  }, [queryClient, snapshotQueryKey]);

  useLayoutEffect(() => {
    return () => {
      void queryClient.cancelQueries(
        { queryKey: eventsQueryKey, exact: true },
        PORTFOLIO_PROJECTION_CANCEL,
      );
      queryClient.removeQueries({ queryKey: eventsQueryKey, exact: true });
    };
  }, [eventsQueryKey, queryClient]);

  useLayoutEffect(() => {
    const client = queryClient;
    return () => {
      snapshotFenceRef.current += 1;
      eventFenceRef.current += 1;
      inFlightEventQueryKeysRef.current.forEach((key) => {
        void client.cancelQueries(
          { queryKey: key, exact: true },
          PORTFOLIO_PROJECTION_CANCEL,
        );
        client.removeQueries({ queryKey: key, exact: true });
      });
      inFlightEventQueryKeysRef.current = [];
    };
  }, [queryClient]);

  const loadSnapshotAndRiskForActiveScope = useCallback(async (
    showLoading: boolean,
  ): Promise<SnapshotRiskLoadOutcome> => {
    const request = {
      scopeKey: activeSnapshotScopeRef.current,
      requestId: snapshotRequestRef.current.requestId + 1,
    };
    snapshotRequestRef.current = request;
    snapshotFenceRef.current += 1;
    const startedAt = snapshotFenceRef.current;
    const scope = activeParamsRef.current;
    const key = buildPortfolioProjectionSnapshotQueryKey(
      scope.accountId,
      scope.costMethod,
      scope.language,
    );

    if (showLoading) {
      snapshotLoadingOwnerRef.current = request;
      setIsLoading(true);
    } else if (snapshotLoadingOwnerRef.current !== null) {
      snapshotLoadingOwnerRef.current = null;
      setIsLoading(false);
    }

    try {
      await queryClient.cancelQueries(
        { queryKey: key, exact: true },
        PORTFOLIO_PROJECTION_CANCEL,
      );
      const data = await queryClient.fetchQuery({
        queryKey: key,
        queryFn: ({ signal }) => fetchPortfolioSnapshotAndRisk({
          accountId: scope.accountId,
          costMethod: scope.costMethod,
          language: scope.language,
          riskFallbackMessage: scope.riskFallbackMessage,
          signal,
          stillActive: () => (
            snapshotFenceRef.current === startedAt
            && isActiveSnapshotRequest(request)
          ),
        }),
        ...PORTFOLIO_PROJECTION_QUERY_SCHEDULE,
      });
      if (!isActiveSnapshotRequest(request)) {
        return { snapshotAccepted: false, riskAccepted: false };
      }
      return { snapshotAccepted: true, riskAccepted: data.riskWarning === null };
    } catch (snapshotError) {
      if (!isActiveSnapshotRequest(request) || isCancelledError(snapshotError)) {
        return { snapshotAccepted: false, riskAccepted: false };
      }
      return { snapshotAccepted: false, riskAccepted: false };
    } finally {
      if (!queryKeysEqual(key, snapshotQueryKeyRef.current)) {
        void queryClient.cancelQueries(
          { queryKey: key, exact: true },
          PORTFOLIO_PROJECTION_CANCEL,
        );
        queryClient.removeQueries({ queryKey: key, exact: true });
      }
      if (showLoading && snapshotLoadingOwnerRef.current === request) {
        snapshotLoadingOwnerRef.current = null;
        setIsLoading(false);
      }
    }
  }, [isActiveSnapshotRequest, queryClient]);

  const loadSnapshotAndRisk = useCallback(async (): Promise<boolean> => {
    const outcome = await loadSnapshotAndRiskForActiveScope(true);
    return outcome.snapshotAccepted && outcome.riskAccepted;
  }, [loadSnapshotAndRiskForActiveScope]);

  const loadEventsPage = useCallback(async (
    page: number,
    requestedEventType?: PortfolioEventType,
  ): Promise<boolean> => {
    const scope = activeParamsRef.current;
    const resolvedEventType = requestedEventType ?? scope.eventType;
    const request = {
      accountScopeKey: accountScopeKey,
      scopeKey: JSON.stringify({
        accountScopeKey,
        eventType: resolvedEventType,
        filters: scope.appliedEventFilters,
        page,
        refreshKey: scope.eventRefreshKey,
      }),
      requestId: eventRequestRef.current.requestId + 1,
    };
    eventRequestRef.current = request;
    eventFenceRef.current += 1;
    const startedAt = eventFenceRef.current;
    const key = buildPortfolioProjectionEventsQueryKey(
      scope.accountId,
      resolvedEventType,
      scope.appliedEventFilters,
      page,
      scope.eventRefreshKey,
    );
    setEventError(null);
    inFlightEventQueryKeysRef.current = [...inFlightEventQueryKeysRef.current, key];

    try {
      await queryClient.cancelQueries(
        { queryKey: key, exact: true },
        PORTFOLIO_PROJECTION_CANCEL,
      );
      const data = await queryClient.fetchQuery({
        queryKey: key,
        queryFn: ({ signal }) => fetchPortfolioEvents({
          accountId: scope.accountId,
          eventType: resolvedEventType,
          filters: scope.appliedEventFilters,
          page,
          signal,
          stillActive: () => (
            eventFenceRef.current === startedAt
            && isActiveEventRequest(request)
          ),
        }),
        ...PORTFOLIO_PROJECTION_QUERY_SCHEDULE,
      });
      if (!isActiveEventRequest(request)) return false;
      setEventTotal(data.total);
      if (data.eventType === 'trade') setTradeEvents(data.items);
      else if (data.eventType === 'cash') setCashEvents(data.items);
      else setCorporateEvents(data.items);
      return true;
    } catch (eventLoadError) {
      if (isActiveEventRequest(request) && !isCancelledError(eventLoadError)) {
        setEventError(getParsedApiError(eventLoadError));
      }
      return false;
    } finally {
      inFlightEventQueryKeysRef.current = inFlightEventQueryKeysRef.current.filter(
        (item) => !queryKeysEqual(item, key),
      );
      if (!queryKeysEqual(key, eventsQueryKeyRef.current)) {
        terminateExactEventQuery(key);
      }
    }
  }, [accountScopeKey, isActiveEventRequest, queryClient, terminateExactEventQuery]);

  const activeProjectionRef = useRef({
    eventPage: eventPageForScope,
    loadAccounts,
    loadEventsPage,
    loadSnapshotAndRisk,
  });
  activeProjectionRef.current = {
    eventPage: eventPageForScope,
    loadAccounts,
    loadEventsPage,
    loadSnapshotAndRisk,
  };

  const refreshPortfolioData = useCallback(async (page?: number) => {
    const active = activeProjectionRef.current;
    await Promise.all([
      active.loadSnapshotAndRisk(),
      active.loadEventsPage(page ?? active.eventPage),
    ]);
  }, []);

  const refreshPaperTradeSurfaces = useCallback(async (): Promise<boolean> => {
    const active = activeProjectionRef.current;
    const results = await Promise.allSettled([
      active.loadAccounts(),
      active.loadSnapshotAndRisk(),
      active.loadEventsPage(1, 'trade'),
    ]);
    const fullyRefreshed = results.every((result) => (
      result.status === 'fulfilled' && result.value
    ));
    if (!fullyRefreshed) return false;

    transitionEventQuery('trade', 1);
    setPaperTradeProjectionRevision((current) => current + 1);
    return true;
  }, [transitionEventQuery]);

  const applyEventFilters = useCallback(() => {
    transitionEventQuery(activeEventTypeRef.current, 1, true);
    setAppliedEventFilters({
      dateFrom: eventDateFrom,
      dateTo: eventDateTo,
      symbol: eventSymbol.trim(),
      side: eventSide,
      direction: eventDirection,
      actionType: eventActionType,
    });
    setEventRefreshKey((current) => current + 1);
  }, [
    eventActionType,
    eventDateFrom,
    eventDateTo,
    eventDirection,
    eventSide,
    eventSymbol,
    transitionEventQuery,
  ]);

  const handleRefreshFx = useCallback(async () => {
    if (!hasAccounts || isLoading || fxRefreshing) return;

    const request = {
      scopeKey: snapshotScopeKey,
      requestId: fxRequestRef.current.requestId + 1,
    };
    fxRequestRef.current = request;

    try {
      setFxRefreshing(true);
      setFxRefreshFeedback(null);
      const result = await portfolioApi.refreshFx({ accountId });
      if (!isActiveFxRequest(request)) return;

      const reloadOutcome = await loadSnapshotAndRiskForActiveScope(false);
      if (!reloadOutcome.snapshotAccepted || !isActiveFxRequest(request)) return;
      setFxRefreshFeedback(buildFxRefreshFeedback(result, language));
    } catch (refreshError) {
      if (isActiveFxRequest(request)) {
        setError(getParsedApiError(refreshError));
      }
    } finally {
      if (isActiveFxRequest(request)) {
        setFxRefreshing(false);
      }
    }
  }, [
    accountId,
    fxRefreshing,
    hasAccounts,
    isActiveFxRequest,
    isLoading,
    language,
    loadSnapshotAndRiskForActiveScope,
    snapshotScopeKey,
    setError,
  ]);

  useEffect(() => {
    if (snapshotQuery.isFetching) return;
    if (snapshotLoadingOwnerRef.current !== null) {
      snapshotLoadingOwnerRef.current = null;
      setIsLoading(false);
    }
  }, [snapshotQuery.dataUpdatedAt, snapshotQuery.errorUpdatedAt, snapshotQuery.isFetching]);

  useEffect(() => {
    if (snapshotQuery.isFetching) return;
    if (snapshotQuery.isError) {
      if (isCancelledError(snapshotQuery.error)) return;
      setError(getParsedApiError(snapshotQuery.error));
      return;
    }
    if (snapshotQuery.isSuccess) {
      setError(null);
    }
  }, [
    setError,
    snapshotQuery.error,
    snapshotQuery.errorUpdatedAt,
    snapshotQuery.isError,
    snapshotQuery.isFetching,
    snapshotQuery.isSuccess,
  ]);

  useEffect(() => {
    if (eventsQuery.isFetching) return;
    if (eventsQuery.isError) {
      if (isCancelledError(eventsQuery.error)) return;
      setEventError(getParsedApiError(eventsQuery.error));
      return;
    }
    const data = eventsQuery.data;
    if (!eventsQuery.isSuccess || data === undefined) return;
    setEventError(null);
    setEventTotal(data.total);
    if (data.eventType === 'trade') setTradeEvents(data.items);
    else if (data.eventType === 'cash') setCashEvents(data.items);
    else setCorporateEvents(data.items);
  }, [
    eventsQuery.data,
    eventsQuery.error,
    eventsQuery.isError,
    eventsQuery.isFetching,
    eventsQuery.isSuccess,
  ]);

  useEffect(() => {
    snapshotLoadingOwnerRef.current = {
      requestId: snapshotRequestRef.current.requestId,
      scopeKey: snapshotScopeKey,
    };
    setIsLoading(true);
  }, [snapshotScopeKey]);

  useEffect(() => {
    fxRequestRef.current = {
      scopeKey: snapshotScopeKey,
      requestId: fxRequestRef.current.requestId + 1,
    };
    setFxRefreshing(false);
    setFxRefreshFeedback(null);
  }, [snapshotScopeKey]);

  useLayoutEffect(() => {
    // Reset ledger page before page-owned URL clamp effects run. A useEffect
    // reset left eventPage=2 with eventLoading=false (Query fetch not started
    // yet), so PortfolioWorkspace writeParams reordered `keep=yes`.
    transitionEventQuery(activeEventTypeRef.current, 1);
  }, [accountId, transitionEventQuery]);

  const snapshotQueryFailed = snapshotQuery.isError && !isCancelledError(snapshotQuery.error);
  const snapshot: PortfolioSnapshotResponse | null = snapshotQueryFailed
    ? null
    : (snapshotQuery.data?.snapshot ?? null);
  const risk: PortfolioRiskResponse | null = snapshotQueryFailed
    ? null
    : (snapshotQuery.data?.risk ?? null);
  const riskWarning = snapshotQuery.isFetching || snapshotQueryFailed
    ? null
    : (snapshotQuery.data?.riskWarning ?? null);

  const projectedEventTotal = eventsQuery.isSuccess && eventsQuery.data !== undefined
    ? eventsQuery.data.total
    : eventTotal;
  const totalEventPages = Math.max(1, Math.ceil(projectedEventTotal / PORTFOLIO_PROJECTION_DEFAULT_PAGE_SIZE));
  const currentEventCount = eventType === 'trade'
    ? tradeEvents.length
    : eventType === 'cash'
      ? cashEvents.length
      : corporateEvents.length;

  return {
    snapshot,
    risk,
    isLoading,
    riskWarning,
    fxRefreshing,
    fxRefreshFeedback,
    handleRefreshFx,
    loadSnapshotAndRisk,
    eventType,
    setEventType,
    eventDateFrom,
    setEventDateFrom,
    eventDateTo,
    setEventDateTo,
    eventSymbol,
    setEventSymbol,
    eventSide,
    setEventSide,
    eventDirection,
    setEventDirection,
    eventActionType,
    setEventActionType,
    eventPage: eventPageForScope,
    setEventPage,
    totalEventPages,
    currentEventCount,
    eventLoading: eventsQuery.isPending || eventsQuery.isFetching,
    eventError,
    setEventError,
    tradeEvents,
    cashEvents,
    corporateEvents,
    applyEventFilters,
    loadEventsPage,
    refreshPortfolioData,
    refreshPaperTradeSurfaces,
    paperTradeProjectionRevision,
  };
}
