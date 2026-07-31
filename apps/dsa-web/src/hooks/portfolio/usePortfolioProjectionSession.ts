// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
// Feature-private projection policy for the Portfolio route.

import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type SetStateAction,
} from 'react';
import { portfolioApi } from '../../api/portfolio';
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
import {
  buildFxRefreshFeedback,
  type FxRefreshFeedback,
} from '../../utils/portfolioFormat';

const DEFAULT_PAGE_SIZE = 20;

export type PortfolioEventType = 'trade' | 'cash' | 'corporate';

type PortfolioEventFilters = {
  dateFrom: string;
  dateTo: string;
  symbol: string;
  side: '' | PortfolioSide;
  direction: '' | PortfolioCashDirection;
  actionType: '' | PortfolioCorporateActionType;
};

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

const EMPTY_EVENT_FILTERS: PortfolioEventFilters = {
  dateFrom: '',
  dateTo: '',
  symbol: '',
  side: '',
  direction: '',
  actionType: '',
};

function buildEventScopeKey(
  accountScopeKey: string,
  eventType: PortfolioEventType,
  filters: PortfolioEventFilters,
  page: number,
): string {
  return JSON.stringify({
    accountScopeKey,
    eventType,
    filters,
    page,
  });
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
  const [snapshot, setSnapshot] = useState<PortfolioSnapshotResponse | null>(null);
  const [risk, setRisk] = useState<PortfolioRiskResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [riskWarning, setRiskWarning] = useState<string | null>(null);
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
  const [eventRefreshKey, setEventRefreshKey] = useState(0);
  const [eventTotal, setEventTotal] = useState(0);
  const [eventLoading, setEventLoading] = useState(false);
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
    scopeKey: buildEventScopeKey(
      accountScopeKey,
      eventType,
      EMPTY_EVENT_FILTERS,
      eventPage,
    ),
  });
  const fxRequestRef = useRef<ProjectionRequest>({
    requestId: 0,
    scopeKey: snapshotScopeKey,
  });

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

  const invalidateEventRequest = useCallback(() => {
    eventRequestRef.current = {
      ...eventRequestRef.current,
      accountScopeKey: activeAccountScopeRef.current,
      requestId: eventRequestRef.current.requestId + 1,
    };
  }, []);

  const activeEventTypeRef = useRef(eventType);
  const eventPageRef = useRef(eventPage);
  activeEventTypeRef.current = eventType;
  eventPageRef.current = eventPage;

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

  const loadSnapshotAndRiskForActiveScope = useCallback(async (
    showLoading: boolean,
  ): Promise<SnapshotRiskLoadOutcome> => {
    const request = {
      scopeKey: snapshotScopeKey,
      requestId: snapshotRequestRef.current.requestId + 1,
    };
    snapshotRequestRef.current = request;
    if (showLoading) {
      snapshotLoadingOwnerRef.current = request;
      setIsLoading(true);
    } else if (snapshotLoadingOwnerRef.current !== null) {
      snapshotLoadingOwnerRef.current = null;
      setIsLoading(false);
    }
    setRiskWarning(null);

    try {
      const snapshotData = await portfolioApi.getSnapshot({
        accountId,
        costMethod,
        includeRealtime: false,
      });
      if (!isActiveSnapshotRequest(request)) {
        return { snapshotAccepted: false, riskAccepted: false };
      }
      setSnapshot(snapshotData);
      setError(null);

      try {
        const riskData = await portfolioApi.getRisk({
          accountId,
          costMethod,
          includeRealtime: false,
        });
        if (!isActiveSnapshotRequest(request)) {
          return { snapshotAccepted: false, riskAccepted: false };
        }
        setRisk(riskData);
        return { snapshotAccepted: true, riskAccepted: true };
      } catch (riskError) {
        if (!isActiveSnapshotRequest(request)) {
          return { snapshotAccepted: false, riskAccepted: false };
        }
        setRisk(null);
        setRiskWarning(
          getParsedApiError(riskError, language).message || riskFallbackMessage,
        );
        return { snapshotAccepted: true, riskAccepted: false };
      }
    } catch (snapshotError) {
      if (!isActiveSnapshotRequest(request)) {
        return { snapshotAccepted: false, riskAccepted: false };
      }
      setSnapshot(null);
      setRisk(null);
      setError(getParsedApiError(snapshotError));
      return { snapshotAccepted: false, riskAccepted: false };
    } finally {
      if (showLoading && snapshotLoadingOwnerRef.current === request) {
        snapshotLoadingOwnerRef.current = null;
        setIsLoading(false);
      }
    }
  }, [
    accountId,
    costMethod,
    isActiveSnapshotRequest,
    language,
    riskFallbackMessage,
    setError,
    snapshotScopeKey,
  ]);

  const loadSnapshotAndRisk = useCallback(async (): Promise<boolean> => {
    const outcome = await loadSnapshotAndRiskForActiveScope(true);
    return outcome.snapshotAccepted && outcome.riskAccepted;
  }, [loadSnapshotAndRiskForActiveScope]);

  const loadEventsPage = useCallback(async (
    page: number,
    requestedEventType: PortfolioEventType = eventType,
  ): Promise<boolean> => {
    const request = {
      accountScopeKey,
      scopeKey: buildEventScopeKey(
        accountScopeKey,
        requestedEventType,
        appliedEventFilters,
        page,
      ),
      requestId: eventRequestRef.current.requestId + 1,
    };
    eventRequestRef.current = request;
    setEventLoading(true);
    setEventError(null);

    try {
      if (requestedEventType === 'trade') {
        const response = await portfolioApi.listTrades({
          accountId,
          dateFrom: appliedEventFilters.dateFrom || undefined,
          dateTo: appliedEventFilters.dateTo || undefined,
          symbol: appliedEventFilters.symbol || undefined,
          side: appliedEventFilters.side || undefined,
          page,
          pageSize: DEFAULT_PAGE_SIZE,
        });
        if (!isActiveEventRequest(request)) return false;
        setTradeEvents(response.items || []);
        setEventTotal(response.total || 0);
      } else if (requestedEventType === 'cash') {
        const response = await portfolioApi.listCashLedger({
          accountId,
          dateFrom: appliedEventFilters.dateFrom || undefined,
          dateTo: appliedEventFilters.dateTo || undefined,
          direction: appliedEventFilters.direction || undefined,
          page,
          pageSize: DEFAULT_PAGE_SIZE,
        });
        if (!isActiveEventRequest(request)) return false;
        setCashEvents(response.items || []);
        setEventTotal(response.total || 0);
      } else {
        const response = await portfolioApi.listCorporateActions({
          accountId,
          dateFrom: appliedEventFilters.dateFrom || undefined,
          dateTo: appliedEventFilters.dateTo || undefined,
          symbol: appliedEventFilters.symbol || undefined,
          actionType: appliedEventFilters.actionType || undefined,
          page,
          pageSize: DEFAULT_PAGE_SIZE,
        });
        if (!isActiveEventRequest(request)) return false;
        setCorporateEvents(response.items || []);
        setEventTotal(response.total || 0);
      }
      return true;
    } catch (eventLoadError) {
      if (isActiveEventRequest(request)) {
        setEventError(getParsedApiError(eventLoadError));
      }
      return false;
    } finally {
      if (isActiveEventRequest(request)) {
        setEventLoading(false);
      }
    }
  }, [
    accountId,
    accountScopeKey,
    appliedEventFilters,
    eventType,
    isActiveEventRequest,
  ]);

  const activeProjectionRef = useRef({
    eventPage,
    loadAccounts,
    loadEventsPage,
    loadSnapshotAndRisk,
  });
  activeProjectionRef.current = {
    eventPage,
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
    void loadSnapshotAndRisk();
  }, [loadSnapshotAndRisk]);

  useEffect(() => {
    void loadEventsPage(eventPage);
  }, [eventPage, eventRefreshKey, loadEventsPage]);

  useEffect(() => {
    fxRequestRef.current = {
      scopeKey: snapshotScopeKey,
      requestId: fxRequestRef.current.requestId + 1,
    };
    setFxRefreshing(false);
    setFxRefreshFeedback(null);
  }, [snapshotScopeKey]);

  useEffect(() => {
    transitionEventQuery(activeEventTypeRef.current, 1);
  }, [accountId, transitionEventQuery]);

  const totalEventPages = Math.max(1, Math.ceil(eventTotal / DEFAULT_PAGE_SIZE));
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
    eventPage,
    setEventPage,
    totalEventPages,
    currentEventCount,
    eventLoading,
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
